
from flask import Flask, request, jsonify, session as flask_session
import bcrypt
import sqlite3
 
import db
from game_state import GameState, AdventureState, SceneState, Entity, Stats, Weapon
from engine import Action, validate_action, initialize_combat
 
app = Flask(__name__)
app.secret_key = "CHANGE_THIS_BEFORE_DEPLOYING"  # signs the session cookie
 
db.init_db()   # create tables on startup if they don't exist
 
 
# Helpers 
 
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
    "mage":    dict(hp=18, max_hp=18, mp=10, max_mp=10,
                    stats={"str": 8,  "dex": 10, "int": 16},
                    weapon={"name": "Staff",     "weapon_type": "staff",   "damage": 4}),
}
 
 
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
        )
        active_ids.append(entity_id)
 
    return GameState(
        adventure=AdventureState(
            title="A New Adventure",
            current_chapter=1,
            boss_name="Unknown",
            boss_defeated=False,
            story_flags={},
        ),
        scene=SceneState(
            description_seed="tavern entrance, torchlit, evening",
            active_entity_ids=active_ids,
        ),
        entities=entities,
    )
 
 
# Auth endpoints 
 
@app.route("/auth/register", methods=["POST"])
def register():
  
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
 
    if not username or not password:
        return _err("username and password are required")
    if len(username) < 3:
        return _err("username must be at least 3 characters")
    if len(password) < 6:
        return _err("password must be at least 6 characters")
 
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
 
    try:
        user_id = db.create_user(username, pw_hash)
    except sqlite3.IntegrityError:
        return _err("Username already taken", 409)
 
    return jsonify({"user_id": user_id, "username": username}), 201
 
 
@app.route("/auth/login", methods=["POST"])
def login():
  
    data = request.get_json() or {}
    user = db.get_user_by_username(data.get("username", ""))
 
    # Same error message for unknown user and wrong password — avoids username enumeration
    if not user or not bcrypt.checkpw(
        data.get("password", "").encode(),
        user["password_hash"].encode()
    ):
        return _err("Invalid username or password", 401)
 
    flask_session["user_id"] = user["user_id"]
    return jsonify({"user_id": user["user_id"], "username": user["username"]})
 
 
@app.route("/auth/logout", methods=["POST"])
def logout():
    """Clear the session cookie."""
    flask_session.clear()
    return jsonify({"message": "Logged out"})
 
 
# Session endpoints 
 
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
 
    session_id, invite_code = db.create_session()
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
 
    if not code:
        return _err("invite_code is required")
    if not char_name:
        return _err("character_name is required")
    if role not in _ROLE_TEMPLATES:
        return _err("role must be 'warrior', 'rogue', or 'mage'")
 
    sess = db.get_session_by_invite(code)
    if not sess:
        return _err("Invite code not found", 404)
    if sess["status"] != "waiting":
        return _err(f"Session is not open for joining (status: {sess['status']})", 400)
 
    session_id = sess["session_id"]
 
    if db.count_session_players(session_id) >= 2:
        return _err("Session is already full", 400)
    if db.is_player_in_session(session_id, user_id):
        return _err("You are already in this session", 400)
 
    # Add player 2, activate session, build + save initial GameState
    db.add_session_player(session_id, user_id, char_name, role)
    db.set_session_active(session_id)
 
    players      = db.get_session_players(session_id)
    initial_state = _build_initial_state(players)
    db.save_game_state(session_id, initial_state)
 
    return jsonify({"session_id": session_id, "status": "active"})
 
 
@app.route("/session/<int:session_id>/state", methods=["GET"])
def get_state(session_id):
  
    user_id, err = _require_auth()
    if err:
        return err
    _, err = _require_membership(session_id, user_id)
    if err:
        return err
 
    state = db.load_game_state(session_id)
    if not state:
        return _err("No game state found for this session", 404)
 
    return jsonify({"session_id": session_id, "game_state": state.to_dict()})
 
 
@app.route("/session/<int:session_id>/action", methods=["POST"])
def submit_action(session_id):
 
    # Steps 1–3: auth + membership
    user_id, err = _require_auth()
    if err:
        return err
    _, err = _require_membership(session_id, user_id)
    if err:
        return err
 
    # Step 4: load state
    state = db.load_game_state(session_id)
    if not state:
        return _err("No game state found for this session", 404)
 
    # Build Action from request body — mirrors engine.py's Action dataclass
    data = request.get_json() or {}
    action = Action(
        actor_id    = data.get("actor_id", ""),
        action_type = data.get("action_type", ""),
        target_id   = data.get("target_id", ""),
        action_name = data.get("action_name", ""),
    )
    if "mp_cost" in data and data["mp_cost"] is not None:
        action.mp_cost = int(data["mp_cost"])
 
    # Start combat if it hasn't been initialised yet
    if not state.in_combat:
        initialize_combat(state)
 
    # Validate using the engine — returns (bool, message)
    # NOTE: engine.validate_action has a bug where cast_spell checks fall
    # through without an explicit return True. We guard for that here.
    result = validate_action(action, state)
    valid   = result[0] if result is not None else True
    message = result[1] if result is not None else "Action is valid"
 
    if not valid:
        # Invalid action — don't change state, don't save
        return jsonify({
            "valid":        False,
            "message":      message,
            "game_state":   state.to_dict(),
            "session_over": False,
            "winner":       None,
        })
 
    # ── Resolution (hand-off to engine when resolve_action is implemented) ──
    # Your teammate will replace this block with:
    #   state, result_message = engine.resolve_action(action, state)
    #
    # For now we stub it so the DB layer is fully testable end-to-end today.
    result_message = (
        f"{action.actor_id} used {action.action_name or action.action_type}"
        f" on {action.target_id}."
    )
 
    # Advance the turn index (wraps around)
    if state.initiative_order:
        state.current_turn_index = (
            (state.current_turn_index + 1) % len(state.initiative_order)
        )
 
    # Win / loss detection 
    players = [e for e in state.entities.values() if e.type == "player"]
    enemies = [e for e in state.entities.values() if e.type == "enemy"]
 
    all_players_dead = players and all(not p.is_alive() for p in players)
    all_enemies_dead = enemies and all(not e.is_alive() for e in enemies)
    session_over     = bool(all_players_dead or all_enemies_dead)
    winner           = None
 
    # Step 5 (+ optional step 6): save state, close session if needed
    if session_over:
        if all_enemies_dead:
            winner = "players"
            db.save_state_and_end_session(session_id, state, winner, "complete")
        else:
            db.save_state_and_end_session(session_id, state, None, "failed")
    else:
        db.save_game_state(session_id, state)
 
    return jsonify({
        "valid":        True,
        "message":      result_message,
        "game_state":   state.to_dict(),
        "session_over": session_over,
        "winner":       winner,
    })
 
 
@app.route("/session/<int:session_id>/end", methods=["POST"])
def end_session(session_id):
    """
    Manually end a session (both players quit, or error recovery).
    Saves the current state and marks status = 'failed'.
    """
    user_id, err = _require_auth()
    if err:
        return err
    _, err = _require_membership(session_id, user_id)
    if err:
        return err
 
    state = db.load_game_state(session_id)
    if state:
        db.save_state_and_end_session(session_id, state, None, "failed")
    else:
        db.end_session(session_id, None, "failed")
 
    return jsonify({"message": "Session ended"})
 
 
# Dev runner 
 
if __name__ == "__main__":
    app.run(debug=True)