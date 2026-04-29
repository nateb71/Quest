from flask import Flask, request, jsonify, render_template, session as flask_session
import socket
import threading
from flask_socketio import SocketIO, emit, join_room, leave_room
app = Flask(__name__)
from flask_cors import CORS

def _get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None

_origins = ["http://127.0.0.1:5000", "http://localhost:5000"]
_local_ip = _get_local_ip()
if _local_ip:
    _origins.append(f"http://{_local_ip}:5000")

CORS(app, supports_credentials=True, origins=_origins, allow_headers=["Content-Type"])
import bcrypt
import sqlite3
import db
from game_state import GameState, AdventureState, SceneState, Entity, Stats, Weapon, Action
from game_engine import validate_action, initialize_combat, process_action, skip_enemy_turns, advance_turn, process_enemy_turns
from ai_layer import narrate_combat_result, narrate_narrative_action, narrate_combined_narrative, narrate_encounter_start, narrate_boss_encounter, narrate_round, narrate_rest, narrate_chapter_transition, interpret_action, generate_adventure_outline, propose_enemy_encounter, check_for_encounter, generate_scene_description

app.secret_key = "CHANGE_THIS_BEFORE_DEPLOYING"  # signs the session cookie

# Initialize SocketIO — allow_upgrades=True enables the WS upgrade from HTTP
socketio = SocketIO(app, cors_allowed_origins=_origins)

db.init_db()   # create tables on startup if they don't exist

# Bridges the host's theme choice (set at /session/create) to /session/join
_session_themes: dict = {}

# In-memory pending actions for simultaneous out-of-combat submission
# session_id -> {actor_id: action_description}
_pending_actions: dict = {}
_pending_mu = threading.Lock()

# Adventure configuration
MAX_CHAPTERS = 5          # how many chapters before the game ends
ENEMIES_PER_CHAPTER = 2   # how many enemies players must defeat per chapter
NARRATIVE_MIN_BEFORE_ENCOUNTER = 2  # minimum narrative turns before AI can trigger an encounter
REST_HEAL    = 8   # HP restored on short rest
REST_MP      = 5   # MP restored on short rest
MAX_RESTS_PER_CHAPTER = 2           # rests allowed per chapter


@app.route("/")
def home():
    return render_template("index.html")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _err(message: str, code: int = 400):
    """Standardised JSON error response."""
    return jsonify({"error": message}), code


def _require_auth():
    user_id = flask_session.get("user_id")
    if not user_id:
        return None, _err("Not logged in", 401)
    if not db.get_user_by_id(user_id):
        return None, _err("User not found", 401)
    return user_id, None


def _require_membership(session_id: int, user_id: int):
    sess = db.get_session(session_id)
    if not sess:
        return None, _err("Session not found", 404)
    if sess["status"] != "active":
        return None, _err(f"Session not active (status: {sess['status']})", 400)
    if not db.is_player_in_session(session_id, user_id):
        return None, _err("You are not a member of this session", 403)
    return sess, None


# Starter stats for each class
_ROLE_TEMPLATES = {
    "warrior": dict(hp=30, max_hp=30, mp=0,  max_mp=0,
                    stats={"str": 14, "dex": 10, "int": 8},
                    weapon={"name": "Longsword", "weapon_type": "sword",   "damage": 6}),
    "rogue":   dict(hp=22, max_hp=22, mp=0,  max_mp=0,
                    stats={"str": 10, "dex": 15, "int": 8},
                    weapon={"name": "Dagger",    "weapon_type": "dagger",  "damage": 4}),
    "mage":    dict(hp=18, max_hp=18, mp=30, max_mp=30,
                    stats={"str": 8,  "dex": 10, "int": 16},
                    weapon={"name": "Staff",     "weapon_type": "staff",   "damage": 4}),
}


def _advance_chapter(state) -> None:
    state.adventure.current_chapter += 1
    seed_key = f"chapter_{state.adventure.current_chapter}_seed"
    state.scene.description_seed = state.adventure.story_flags.get(seed_key, "deeper passage")
    state.in_combat = False
    state.adventure.enemies_defeated_this_chapter = 0
    state.adventure.story_flags["_narrative_count"] = 0
    state.adventure.story_flags["_rests_used"] = 0
    state.scene.active_entity_ids = [
        eid for eid in state.scene.active_entity_ids
        if state.entities[eid].type == "player"
    ]
    state.initiative_order = list(state.scene.active_entity_ids)
    state.current_turn_index = 0
    for eid in state.scene.active_entity_ids:
        entity = state.entities[eid]
        entity.hp = entity.max_hp
        entity.mp = entity.max_mp


def _level_up_players(state) -> None:
    for entity in state.entities.values():
        if entity.type != "player" or not entity.is_alive():
            continue
        entity.level += 1
        entity.max_hp += 5
        entity.weapon.damage += 1
        if entity.role == "warrior":
            entity.stats.str += 2
            entity.stats.dex += 1
        elif entity.role == "rogue":
            entity.stats.dex += 2
            entity.stats.str += 1
        elif entity.role == "mage":
            entity.stats.int += 2
            entity.max_mp += 5


def _build_boss_entity(state) -> Entity:
    boss_name = state.adventure.boss_name
    entity_id = boss_name.lower().replace(" ", "_") + "_boss"
    return Entity(
        id=entity_id,
        type="enemy",
        role="boss",
        level=5,
        hp=80, max_hp=80,
        mp=20, max_mp=20,
        stats=Stats(str=18, dex=12, int=12),
        weapon=Weapon(name="Ruinous Blade", weapon_type="sword", damage=9),
        items=[],
        character_name=boss_name,
    )


def _build_enemy_entity(proposal: dict) -> Entity:
    role = proposal["role"]
    if role == "minion":
        hp, mp = 10, 0
        stats  = {"str": 8, "dex": 12, "int": 4}
        dmg_lo, dmg_hi = 3, 5
    elif role == "brute":
        hp, mp = 32, 0
        stats  = {"str": 14, "dex": 10, "int": 4}
        dmg_lo, dmg_hi = 5, 7
    else:  # caster
        hp, mp = 14, 10
        stats  = {"str": 6, "dex": 14, "int": 14}
        dmg_lo, dmg_hi = 3, 5
    entity_id = proposal["name"].lower().replace(" ", "_") + f"_{proposal.get('_index', 1)}"
    return Entity(
        id=entity_id,
        type="enemy",
        role=role,
        level=1,
        hp=hp,
        max_hp=hp,
        mp=mp,
        max_mp=mp,
        stats=Stats.from_dict(stats),
        weapon=Weapon.from_dict({
            "name":        proposal["weapon_name"],
            "weapon_type": proposal["weapon_type"],
            "damage":      min(dmg_hi, max(dmg_lo, proposal["weapon_damage"])),
        }),
        items=[],
        character_name=proposal["name"],
    )


def _build_initial_state(players: list) -> GameState:
    entities = {}
    active_ids = []
    for i, p in enumerate(players, start=1):
        entity_id = f"player_{i}"
        tmpl = _ROLE_TEMPLATES.get(p["role"].lower(), _ROLE_TEMPLATES["warrior"])
        entities[entity_id] = Entity(
            id=entity_id,
            type="player",
            role=p["role"].lower(),
            level=1,
            hp=tmpl["hp"],
            max_hp=tmpl["max_hp"],
            mp=tmpl["mp"],
            max_mp=tmpl["max_mp"],
            stats=Stats.from_dict(tmpl["stats"]),
            weapon=Weapon.from_dict(tmpl["weapon"]),
            items=[],
            character_name=p["character_name"],
        )
        active_ids.append(entity_id)
    return GameState(
        adventure=AdventureState(
            title="A New Adventure",
            current_chapter=1,
            boss_name="Unknown",
            boss_defeated=False,
            story_flags={"_narrative_count": 0, "_rests_used": 0},
        ),
        scene=SceneState(
            description_seed="tavern entrance, torchlit, evening",
            active_entity_ids=active_ids,
        ),
        entities=entities,
        initiative_order=list(active_ids),  # player turn order while out of combat
        current_turn_index=0,
    )


# ── Auth endpoints (HTTP — auth stays as REST) ─────────────────────────────────

@app.route("/auth/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    email    = data.get("email", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return _err("Missing username or password")
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        user_id = db.create_user(username, pw_hash, email)
        print(f"SUCCESS: User {username} created with ID {user_id}")
        return jsonify({"user_id": user_id, "username": username}), 201
    except Exception as e:
        print(f"ERROR during registration: {e}")
        return _err("Registration failed")


@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    user = db.get_user_by_username(data.get("username", ""))
    if not user or not bcrypt.checkpw(
        data.get("password", "").encode(),
        user["password_hash"].encode()
    ):
        return _err("Invalid username or password", 401)
    flask_session["user_id"] = user["id"]
    return jsonify({"user_id": user["id"], "username": user["username"]})


@app.route("/auth/logout", methods=["POST"])
def logout():
    flask_session.clear()
    return jsonify({"message": "Logged out"})


@app.route("/auth/me", methods=["GET"])
def me():
    user_id = flask_session.get("user_id")
    if not user_id:
        return _err("Not logged in", 401)
    user = db.get_user_by_id(user_id)
    if not user:
        return _err("User not found", 401)
    return jsonify({"user_id": user["id"], "username": user["username"]})

# ── Saved adventures ──────────────────────────────────────────────────────────

@app.route("/session/my-sessions", methods=["GET"])
def my_sessions():
    user_id, err = _require_auth()
    if err:
        return err

    import json
    rows = db.get_user_sessions(user_id)
    sessions = []
    for row in rows:
        adventure_title = None
        current_chapter = None
        if row["state_json"]:
            try:
                raw = json.loads(row["state_json"])
                adv = raw.get("adventure", {})
                adventure_title = adv.get("title")
                current_chapter = adv.get("current_chapter")
            except Exception:
                pass

        sessions.append({
            "session_id":      row["session_id"],
            "status":          row["status"],
            "theme":           row["theme"],
            "character_name":  row["character_name"],
            "role":            row["role"],
            "last_saved":      row["last_saved"],
            "created_at":      row["created_at"],
            "invite_code":     row["invite_code"],
            "adventure_title": adventure_title,
            "current_chapter": current_chapter,
            "has_save":        row["state_json"] is not None,
        })
    return jsonify({"sessions": sessions})


@app.route("/session/<int:session_id>/delete", methods=["POST"])
def delete_session(session_id):
    user_id, err = _require_auth()
    if err:
        return err
    if not db.is_player_in_session(session_id, user_id):
        return _err("Not your session", 403)
    db.mark_session_deleted(session_id)
    return jsonify({"ok": True})


@app.route("/session/resume", methods=["POST"])
def resume_session():
    user_id, err = _require_auth()
    if err:
        return err

    data = request.get_json() or {}
    session_id = data.get("session_id")
    if not session_id:
        return _err("session_id is required")

    sess = db.get_session(session_id)
    if not sess:
        return _err("Session not found", 404)
    if sess["status"] != "active":
        return _err(f"This adventure cannot be resumed (status: {sess['status']})", 400)
    if not db.is_player_in_session(session_id, user_id):
        return _err("You are not a member of this session", 403)

    state = db.load_game_state(session_id)
    if not state:
        return _err("No saved game state found for this session", 404)

    # Actor IDs are player_1, player_2 based on join order
    players = db.get_session_players(session_id)
    actor_id = None
    for i, p in enumerate(players, start=1):
        if p["user_id"] == user_id:
            actor_id = f"player_{i}"
            break

    if actor_id is None or actor_id not in state.entities:
        return _err("Could not locate your character in the saved state", 500)

    return jsonify({
        "session_id": session_id,
        "actor_id":   actor_id,
    })


@app.route("/session/<int:session_id>/state", methods=["GET"])
def get_session_state(session_id):
    user_id, err = _require_auth()
    if err:
        return err

    if not db.is_player_in_session(session_id, user_id):
        return _err("You are not a member of this session", 403)

    state = db.load_game_state(session_id)
    if not state:
        return _err("No saved state found", 404)

    return jsonify({"game_state": state.to_dict()})







# ── Session creation/joining (HTTP — one-shot setup) ──────────────────────────

@app.route("/session/create", methods=["POST"])
def create_session():
    user_id, err = _require_auth()
    if err:
        return err
    data = request.get_json() or {}
    char_name = data.get("character_name", "").strip()
    role      = data.get("role", "").strip().lower()
    if not char_name:
        return _err("character_name is required")
    if role not in _ROLE_TEMPLATES:
        return _err("role must be 'warrior', 'rogue', or 'mage'")
    theme = data.get("theme", "dungeon").strip().lower()
    session_id, invite_code = db.create_session()
    _session_themes[session_id] = theme
    db.add_session_player(session_id, user_id, char_name, role)
    return jsonify({"session_id": session_id, "invite_code": invite_code}), 201


@app.route("/session/join", methods=["POST"])
def join_session():
    user_id, err = _require_auth()
    if err:
        return err
    data      = request.get_json() or {}
    code      = data.get("invite_code", "").strip()
    char_name = data.get("character_name", "").strip()
    role      = data.get("role", "").strip().lower()
    if not code or not char_name:
        return _err("Invite code and character name are required")
    if role not in _ROLE_TEMPLATES:
        return _err("Role must be 'warrior', 'rogue', or 'mage'")
    sess = db.get_session_by_invite(code)
    if not sess:
        return _err("Invite code not found", 404)
    if sess["status"] != "waiting":
        return _err(f"Session is not open for joining (status: {sess['status']})", 400)
    session_id = sess["id"]
    if db.count_session_players(session_id) >= 2:
        return _err("Session is already full", 400)
    if db.is_player_in_session(session_id, user_id):
        return _err("You cannot join your own session", 400)

    db.add_session_player(session_id, user_id, char_name, role)
    db.set_session_active(session_id)

    players = db.get_session_players(session_id)
    initial_state = _build_initial_state(players)

    theme = _session_themes.pop(session_id, "dungeon")
    difficulty = "normal"

    # Generate a unique adventure outline from the AI
    outline = generate_adventure_outline("A Quest", theme, difficulty)
    if outline:
        initial_state.adventure.title     = outline["title"]
        initial_state.adventure.boss_name = outline["boss_name"]
        # Store all 5 chapter seeds plus the narrative hooks in story_flags
        initial_state.adventure.story_flags = {
            "chapter_1_seed": outline["chapter_1_seed"],
            "chapter_2_seed": outline["chapter_2_seed"],
            "chapter_3_seed": outline["chapter_3_seed"],
            "chapter_4_seed": outline["chapter_4_seed"],
            "chapter_5_seed": outline["chapter_5_seed"],
        }
        # Merge in the narrative hooks the AI generated
        initial_state.adventure.story_flags.update(outline.get("story_flags", {}))
        # Set the opening scene seed
        initial_state.scene.description_seed = outline["chapter_1_seed"]

    # Generate an immersive opening scene description
    opening_story = generate_scene_description(initial_state)
    initial_state.messages.append({"sender": "Dungeon Master", "text": opening_story})
    db.save_game_state(session_id, initial_state)

    # Notify the host (player_1) via WebSocket that the game is starting
    room = f"session_{session_id}"
    socketio.emit("game_start", {
        "session_id":        session_id,
        "opening_narration": opening_story,
        "game_state":        initial_state.to_dict(),
    }, to=room)

    return jsonify({
        "session_id":        session_id,
        "status":            "active",
        "opening_narration": opening_story,
        "game_state":        initial_state.to_dict(),
    })


# ── WebSocket events ───────────────────────────────────────────────────────────

@socketio.on("join_session_room")
def on_join_session_room(data):
    """
    Client emits this immediately after creating or joining a session so they
    receive all future broadcasts for that session.

    Payload: { "session_id": <int> }
    """
    session_id = data.get("session_id")
    if not session_id:
        emit("error", {"message": "session_id required"})
        return
    room = f"session_{session_id}"
    join_room(room)
    emit("joined_room", {"room": room})


@socketio.on("submit_action")
def on_submit_action(data):
    user_id = flask_session.get("user_id")
    if not user_id:
        emit("error", {"message": "Not logged in"})
        return

    session_id         = data.get("session_id")
    actor_id           = data.get("actor_id", "").strip()
    action_description = data.get("action_description", "").strip()

    if not session_id or not actor_id or not action_description:
        emit("error", {"message": "session_id, actor_id, and action_description are required"})
        return

    sess = db.get_session(session_id)
    if not sess or sess["status"] != "active":
        emit("error", {"message": "Session not found or not active"})
        return
    if not db.is_player_in_session(session_id, user_id):
        emit("error", {"message": "You are not a member of this session"})
        return

    state = db.load_game_state(session_id)
    if not state:
        emit("error", {"message": "No game state found for this session"})
        return

    room = f"session_{session_id}"

    def _get_next_player_name():
        if not state.initiative_order:
            return None
        next_id = state.initiative_order[state.current_turn_index % len(state.initiative_order)]
        entity = state.get_entity(next_id)
        return entity.character_name if entity and entity.type == "player" else None

    def _broadcast(valid, message, session_over=False, winner=None):
        socketio.emit("action_result", {
            "valid":            valid,
            "actor_id":         actor_id,
            "actor_input":      action_description,
            "message":          message,
            "game_state":       state.to_dict(),
            "session_over":     session_over,
            "winner":           winner,
        }, to=room)

    def _record(dm_text):
        actor = state.get_entity(actor_id)
        sender = actor.character_name if actor else "Player"
        state.messages.append({"sender": sender, "text": action_description})
        state.messages.append({"sender": "Dungeon Master", "text": dm_text})

    def _broadcast_combined(combined, message, session_over=False, winner=None):
        inputs = []
        for pid, pdesc in combined.items():
            e = state.get_entity(pid)
            inputs.append({"actor_id": pid, "actor_name": e.character_name if e else pid, "actor_input": pdesc})
        socketio.emit("action_result", {
            "valid":           True,
            "combined_inputs": inputs,
            "message":         message,
            "game_state":      state.to_dict(),
            "session_over":    session_over,
            "winner":          winner,
        }, to=room)

    # ── Step 1: Interpret the action BEFORE spawning enemies ──────────────────
    # This lets the AI classify narrative vs. combat with the current scene state.
    action = interpret_action(action_description, actor_id, state)

    if action is None:
        _broadcast(False, "I couldn't understand that action. Try describing it differently.")
        return

    # ── Step 2: Narrative actions ─────────────────────────────────────────────
    if action.action_type == "narrative":

        # ── Out-of-combat: simultaneous submission — wait for all players ─────
        if not state.in_combat:
            # Lock only for the dict read/write — released before any AI or DB work
            with _pending_mu:
                _pending_actions.setdefault(session_id, {})[actor_id] = action_description
                living_players = [eid for eid, e in state.entities.items()
                                  if e.type == "player" and e.is_alive()]
                all_ready = len(_pending_actions[session_id]) >= len(living_players)
                combined_actions = _pending_actions.pop(session_id) if all_ready else None

            if combined_actions is None:
                # Still waiting for partner — notify the room
                actor = state.get_entity(actor_id)
                socketio.emit("action_pending", {
                    "actor_id":    actor_id,
                    "actor_name":  actor.character_name if actor else actor_id,
                    "actor_input": action_description,
                }, to=room)
                return

            # All players have submitted — process together

            count = state.adventure.story_flags.get("_narrative_count", 0) + 1
            state.adventure.story_flags["_narrative_count"] = count

            encounter_triggered = False
            if count >= NARRATIVE_MIN_BEFORE_ENCOUNTER:
                combined_desc = " | ".join(combined_actions.values())
                encounter_proposals = check_for_encounter(combined_desc, actor_id, state)
                if encounter_proposals:
                    encounter_triggered = True
                    state.adventure.story_flags["_narrative_count"] = 0
                    enemy_names = []
                    for i, proposal in enumerate(encounter_proposals, start=1):
                        proposal["_index"] = i
                        enemy = _build_enemy_entity(proposal)
                        state.entities[enemy.id] = enemy
                        state.scene.active_entity_ids.append(enemy.id)
                        enemy_names.append(proposal["name"])
                    initialize_combat(state)
                    initial_attacks, initial_result = process_enemy_turns(state)
                    combined_desc = " | ".join(combined_actions.values())
                    narration = narrate_encounter_start(combined_desc, actor_id, enemy_names, state, initial_attacks,
                                                        None if initial_result == "players_lose" else _get_next_player_name())
                    for pid, pdesc in combined_actions.items():
                        e = state.get_entity(pid)
                        state.messages.append({"sender": e.character_name if e else pid, "text": pdesc})
                    state.messages.append({"sender": "Dungeon Master", "text": narration})
                    if initial_result == "players_lose":
                        db.save_state_and_end_session(session_id, state, None, "failed")
                        _broadcast_combined(combined_actions, narration, True, None)
                    else:
                        db.save_game_state(session_id, state)
                        _broadcast_combined(combined_actions, narration)
                    return

            if not encounter_triggered:
                narration = narrate_combined_narrative(combined_actions, state)

            for pid, pdesc in combined_actions.items():
                e = state.get_entity(pid)
                state.messages.append({"sender": e.character_name if e else pid, "text": pdesc})
            state.messages.append({"sender": "Dungeon Master", "text": narration})
            db.save_game_state(session_id, state)
            _broadcast_combined(combined_actions, narration)
            return

        # ── In-combat narrative: enforce turn order ───────────────────────────
        if state.initiative_order:
            idx = state.current_turn_index % len(state.initiative_order)
            if state.initiative_order[idx] != actor_id:
                _broadcast(False, "It's not your turn yet.")
                return

        count = state.adventure.story_flags.get("_narrative_count", 0) + 1
        state.adventure.story_flags["_narrative_count"] = count

        advance_turn(state)
        skip_enemy_turns(state)
        narration = narrate_narrative_action(action_description, actor_id, state)
        _record(narration)
        db.save_game_state(session_id, state)
        _broadcast(True, narration)
        return

    # ── Step 2b: Rest action ──────────────────────────────────────────────────
    if action.action_type == "rest":
        if state.initiative_order:
            idx = state.current_turn_index % len(state.initiative_order)
            if state.initiative_order[idx] != actor_id:
                _broadcast(False, "It's not your turn yet.")
                return
        if state.in_combat:
            _broadcast(False, "You can't rest in the middle of combat!")
            return
        rests_used = state.adventure.story_flags.get("_rests_used", 0)
        if rests_used >= MAX_RESTS_PER_CHAPTER:
            _broadcast(False, "Your party has already rested too much this chapter — keep moving!")
            return
        state.adventure.story_flags["_rests_used"] = rests_used + 1
        actor = state.get_entity(actor_id)
        hp_before = actor.hp
        mp_before = actor.mp
        actor.hp = min(actor.hp + REST_HEAL, actor.max_hp)
        actor.mp = min(actor.mp + REST_MP,   actor.max_mp)
        hp_restored = actor.hp - hp_before
        mp_restored = actor.mp - mp_before
        advance_turn(state)
        narration = narrate_rest(actor_id, hp_restored, mp_restored,
                                 actor.hp, actor.max_hp, actor.mp, actor.max_mp, state)
        _record(narration)
        db.save_game_state(session_id, state)
        _broadcast(True, narration)
        return

    # ── Step 3: Combat action — spawn enemy if not yet in combat ─────────────
    if not state.in_combat:
        proposal = propose_enemy_encounter(state)
        if proposal:
            proposal["_index"] = 1
            enemy = _build_enemy_entity(proposal)
            state.entities[enemy.id] = enemy
            state.scene.active_entity_ids.append(enemy.id)
        initialize_combat(state)
        skip_enemy_turns(state)

    # ── Step 4: Validate turn order ───────────────────────────────────────────
    result  = validate_action(action, state)
    valid   = result[0] if result is not None else True
    message = result[1] if result is not None else "Action is valid"

    if not valid:
        _broadcast(False, message)
        return

    # ── Step 5: Process the combat action ─────────────────────────────────────
    engine_result = process_action(action, state)

    if engine_result == "players_win":
        result_message = narrate_combat_result(action, engine_result, state)

        if state.adventure.story_flags.get("_boss_active"):
            # Boss just died — game over
            state.adventure.boss_defeated = True
            state.adventure.story_flags["_boss_active"] = False
            session_over = True
            winner = "players"
        else:
            state.adventure.enemies_defeated_this_chapter += 1

            if state.adventure.enemies_defeated_this_chapter < ENEMIES_PER_CHAPTER:
                state.in_combat = False
                state.adventure.story_flags["_narrative_count"] = 0
                state.scene.active_entity_ids = [
                    eid for eid in state.scene.active_entity_ids
                    if state.entities[eid].type == "player"
                ]
                state.initiative_order = list(state.scene.active_entity_ids)
                state.current_turn_index = 0
                session_over = False
                winner = None
            elif state.adventure.current_chapter < MAX_CHAPTERS:
                _level_up_players(state)
                old_ch = state.adventure.current_chapter
                _advance_chapter(state)
                result_message = narrate_chapter_transition(old_ch, state.adventure.current_chapter, state)
                session_over = False
                winner = None
            else:
                # Chapter 5 enemies cleared — spawn the final boss
                boss = _build_boss_entity(state)
                state.entities[boss.id] = boss
                state.scene.active_entity_ids.append(boss.id)
                state.adventure.story_flags["_boss_active"] = True
                initialize_combat(state)
                initial_attacks, initial_result = process_enemy_turns(state)
                if initial_result == "players_lose":
                    result_message = narrate_boss_encounter(action_description, actor_id, state, initial_attacks)
                    session_over = True
                    winner = None
                else:
                    next_player = _get_next_player_name()
                    result_message = narrate_boss_encounter(action_description, actor_id, state, initial_attacks, next_player)
                    session_over = False
                    winner = None
    elif engine_result == "players_lose":
        result_message = narrate_combat_result(action, engine_result, state)
        session_over = True
        winner = None
    elif engine_result == "ongoing":
        enemy_attacks, enemy_result = process_enemy_turns(state)
        if enemy_result == "players_lose":
            result_message = narrate_round(action, enemy_attacks, "players_lose", state)
            session_over = True
            winner = None
        else:
            next_player = _get_next_player_name()
            result_message = narrate_round(action, enemy_attacks, "ongoing", state, next_player)
            session_over = False
            winner = None
    else:
        _broadcast(False, engine_result)
        return

    _record(result_message)
    if session_over:
        db.save_state_and_end_session(session_id, state, winner, "complete" if winner else "failed")
    else:
        db.save_game_state(session_id, state)

    _broadcast(True, result_message, session_over, winner)


@socketio.on("end_session")
def on_end_session(data):
    """
    Replaces POST /session/<id>/end.
    Payload: { "session_id": <int> }
    """
    user_id = flask_session.get("user_id")
    if not user_id:
        emit("error", {"message": "Not logged in"})
        return

    session_id = data.get("session_id")
    if not session_id:
        emit("error", {"message": "session_id required"})
        return

    if not db.is_player_in_session(session_id, user_id):
        emit("error", {"message": "You are not a member of this session"})
        return

    state = db.load_game_state(session_id)
    if state:
        db.save_state_and_end_session(session_id, state, None, "failed")
    else:
        db.end_session(session_id, None, "failed")

    room = f"session_{session_id}"
    socketio.emit("session_ended", {"message": "Session ended by a player."}, to=room)
    leave_room(room)


# ── Dev runner ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Use socketio.run instead of app.run so the WS server starts properly
    socketio.run(app, host='0.0.0.0', debug=True)