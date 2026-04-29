import json
from typing import Optional
from openai import OpenAI
from game_state import GameState, Action
 
 
OPENAI_MODEL = "gpt-4"
 
# client reads OPENAI_API_KEY from environment automatically
client = OpenAI()
 
 
def _call_openai(system_prompt: str, user_message: str) -> Optional[str]:
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
 
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return None
 
 
def _build_context(state: GameState) -> dict:
    adventure_context = {
        "title": state.adventure.title,
        "current_chapter": state.adventure.current_chapter,
        "boss_name": state.adventure.boss_name,
        "boss_defeated": state.adventure.boss_defeated,
        "story_flags": state.adventure.story_flags,
    }

    scene_context = {
        "description_seed": state.scene.description_seed,
        "active_entity_ids": state.scene.active_entity_ids,
        "in_combat": state.in_combat,
    }

    entity_snapshots = {}
    players = []
    for entity in state.get_active_entities():
        entity_snapshots[entity.id] = {
            "id": entity.id,
            "type": entity.type,
            "role": entity.role,
            "character_name": entity.character_name,
            "hp": entity.hp,
            "max_hp": entity.max_hp,
            "mp": entity.mp,
            "max_mp": entity.max_mp,
            "weapon_name": entity.weapon.name,
            "weapon_type": entity.weapon.weapon_type,
        }
        if entity.type == "player":
            players.append({
                "id": entity.id,
                "role": entity.role,
                "character_name": entity.character_name,
            })

    return {
        "adventure": adventure_context,
        "scene": scene_context,
        "entities": entity_snapshots,
        "players": players,
        "player_count": len(players),
    }
 
 
def interpret_action(player_input: str, actor_id: str, state: GameState) -> Optional[Action]:
    context = _build_context(state)

    system_prompt = """You are an action interpreter for a turn-based D&D game.
Your ONLY job is to convert a player's natural language input into a structured JSON action object.

You must ALWAYS respond with ONLY a valid JSON object. No explanation, no extra text, no markdown.

The JSON must have exactly these fields:
{
    "actor_id": "the ID of the player performing the action",
    "action_type": "attack", "cast_spell", "narrative", or "rest",
    "target_id": "the ID of the target entity, or null for narrative/rest actions",
    "action_name": "short name of the action e.g. sword_strike, fireball, look_around, or short_rest",
    "mp_cost": null for attacks, narrative, and rest; or an integer cost for spells (default 5)
}

Rules:
- Use "narrative" when the player is exploring, looking around, moving, talking, or doing ANYTHING that is not a direct attack, spell, or rest
- Use "attack" ONLY when the player clearly intends to physically strike an enemy that exists in the scene
- Use "cast_spell" ONLY for combat: dealing damage to an enemy OR healing a party member in battle
- If a player uses magic for any non-combat purpose (helping villagers, affecting the environment, utility magic, rituals), ALWAYS classify as "narrative" — NEVER "cast_spell"
- Use "rest" when the player wants to rest, bandage wounds, catch their breath, meditate, or otherwise recover
- For "narrative" and "rest", set target_id to null and mp_cost to null
- For "attack", target_id must be one of the enemy IDs in active_entity_ids
- For "cast_spell" targeting an enemy, target_id must be one of the enemy IDs in active_entity_ids
- For "cast_spell" targeting a player ally to heal, target_id must be one of the player IDs in active_entity_ids
- Never invent entity IDs. Only use IDs from the active_entity_ids list
- If there are no enemies in the scene, always use "narrative" or "rest" regardless of what the player says"""

    user_message = f"""Game context:
{json.dumps(context, indent=2)}

The player with ID "{actor_id}" says: "{player_input}"

Convert this into a structured action JSON object."""

    raw_response = _call_openai(system_prompt, user_message)

    if raw_response is None:
        print("AI interpretation failed — no response from API")
        return None

    try:
        action_data = json.loads(raw_response)
    except json.JSONDecodeError:
        print(f"AI returned malformed JSON: {raw_response}")
        return None

    required_fields = ["actor_id", "action_type", "target_id", "action_name", "mp_cost"]
    for field in required_fields:
        if field not in action_data:
            print(f"AI response missing required field: {field}")
            return None

    if action_data["action_type"] not in ["attack", "cast_spell", "narrative", "rest"]:
        print(f"AI returned invalid action_type: {action_data['action_type']}")
        return None

    if action_data["action_type"] == "attack":
        if action_data["target_id"] not in state.scene.active_entity_ids:
            print(f"AI returned invalid target_id: {action_data['target_id']}")
            return None

    if action_data["action_type"] == "cast_spell":
        if action_data["target_id"] not in state.scene.active_entity_ids:
            # Reclassify as narrative (non-combat magic) instead of failing
            print(f"cast_spell target_id invalid — reclassifying as narrative: {action_data['target_id']}")
            action_data["action_type"] = "narrative"
            action_data["target_id"] = None
            action_data["mp_cost"] = None

    return Action(
        actor_id=action_data["actor_id"],
        action_type=action_data["action_type"],
        target_id=action_data["target_id"],
        action_name=action_data["action_name"],
        mp_cost=action_data["mp_cost"],
    )
 
 
def narrate_combat_result(action: Action, engine_result: str, state: GameState) -> str:
    context = _build_context(state)
    actor = state.get_entity(action.actor_id)
    target = state.get_entity(action.target_id)
 
    actor_role = actor.role if actor else "unknown"
    target_role = target.role if target else "unknown"
    target_hp = target.hp if target else 0
    action_weapon = actor.weapon.name if actor else "weapon"
 
    system_prompt = """You are a Dungeon Master narrator for a D&D game.
Your job is to narrate the result of a combat action in vivid, dramatic prose.
 
Rules:
- Keep narration to 2-4 sentences maximum
- Treat the engine result as absolute ground truth — never contradict it
- Do not invent any mechanical outcomes, damage numbers, or stat changes
- Match the tone to the action — attacks are gritty, spells are dramatic
- If the result is players_win, describe a triumphant victory
- If the result is players_lose, describe a tragic defeat
- If the result is ongoing, describe the action and its immediate effect"""
 
    user_message = f"""Game context:
{json.dumps(context, indent=2)}
 
Action performed:
- Actor: {action.actor_id} (role: {actor_role})
- Action type: {action.action_type}
- Action name: {action.action_name}
- Weapon used: {action_weapon}
- Target: {action.target_id} (role: {target_role})
- Target remaining HP: {target_hp}
- Engine result: {engine_result}
 
Narrate this combat action based on the engine result above."""
 
    narration = _call_openai(system_prompt, user_message)
 
    # fallback narration if API call fails
    if narration is None:
        if engine_result == "players_win":
            return "The last enemy falls. Victory is yours."
        elif engine_result == "players_lose":
            return "Your party has been defeated. The darkness claims you."
        else:
            return f"{action.actor_id} performs {action.action_name}."
 
    return narration


def narrate_round(action: Action, enemy_attacks: list, round_result: str, state: GameState,
                  next_player_name: str = None) -> str:
    """Narrate a full combat round: player action + enemy counterattacks."""
    context = _build_context(state)
    actor = state.get_entity(action.actor_id)
    target = state.get_entity(action.target_id)

    actor_name   = actor.character_name if actor else action.actor_id
    target_name  = target.character_name if target else str(action.target_id)
    actor_weapon = actor.weapon.name if actor else "weapon"

    if target and target.type == "player":
        player_action_line = (
            f"- {actor_name} cast {action.action_name} to heal {target_name} "
            f"(now at {target.hp}/{target.max_hp} HP)"
        )
    else:
        player_action_line = f"- {actor_name} used {action.action_name} (with {actor_weapon}) against {target_name}"

    if enemy_attacks:
        atk_lines = "\n".join(
            f"- {a['enemy_name']} attacked {a['target_name']} for {a['damage']} damage "
            f"({a['target_hp_remaining']} HP remaining)"
            for a in enemy_attacks
        )
    else:
        atk_lines = "None — all enemies are dead or could not act."

    turn_prompt_rule = (
        f"- End by naturally addressing {next_player_name} — it is now their turn to act"
        if next_player_name else
        "- Do not prompt any specific player at the end"
    )

    system_prompt = f"""You are a Dungeon Master narrator for a multiplayer D&D game.
Narrate a full combat round covering the player's action and any enemy counterattacks.

Rules:
- 3-6 sentences total
- Narrate the player's action first, then each enemy counterattack
- Treat every listed mechanical outcome as absolute truth — never contradict the numbers
- If an enemy deals damage, describe the hit vividly and convey the pain/danger
- If a player reaches 0 HP, describe their collapse dramatically
- If the player healed an ally, describe the restorative magic warmly — do NOT narrate it as an attack
- Do not invent additional damage, misses, or events not listed below
- End on the current tension level: triumphant if enemies are dead, grim if players took heavy damage
{turn_prompt_rule}"""

    user_message = f"""Game context:
{json.dumps(context, indent=2)}

Player action this turn:
{player_action_line}
- Result after player action: {round_result}

Enemy counterattacks after the player's turn:
{atk_lines}

Overall round result: {round_result}

Narrate this full combat round."""

    narration = _call_openai(system_prompt, user_message)
    if narration is None:
        parts = [f"{actor_name} strikes with {actor_weapon}."]
        for a in enemy_attacks:
            parts.append(f"{a['enemy_name']} retaliates, hitting {a['target_name']} for {a['damage']} damage!")
        return " ".join(parts)
    return narration


def generate_scene_description(state: GameState) -> str:
    context = _build_context(state)
    player_count = context["player_count"]
    player_descriptions = ", ".join(
        f"{p['character_name']} the {p['role']}" for p in context["players"]
    )

    chapter_arc = "\n".join(
        f"  Chapter {i}: {state.adventure.story_flags.get(f'chapter_{i}_seed', '(unknown)')}"
        for i in range(1, 6)
    )

    system_prompt = f"""You are a Dungeon Master for a multiplayer D&D game with {player_count} players.
Your job is to generate an immersive opening scene description for the whole party.

Rules:
- Address the entire party together — never single out just one player
- The party consists of: {player_descriptions}
- Keep the description to 5-8 sentences
- Base the description on the description_seed provided
- Maintain consistency with the adventure title, chapter, and story_flags
- Include at least one detail for each sense: sight, sound, and smell
- Reference any villain_motive, world_detail, or recurring_npc from story_flags if present
- Include a clear sense of what the party must accomplish this chapter — the threat they face or the place they must reach
- In the final 1-2 sentences, hint at the ultimate antagonist and the larger stakes of the journey
- Do not invent mechanical events or stat changes
- Do not mention specific HP or MP numbers"""

    user_message = f"""Game context:
{json.dumps(context, indent=2)}

Chapter arc (where the story is heading):
{chapter_arc}
Final boss: {state.adventure.boss_name}

Generate an immersive scene description based on the description_seed:
"{state.scene.description_seed}"

The party should come away with a sense of direction and purpose — not just atmosphere."""

    description = _call_openai(system_prompt, user_message)

    if description is None:
        return f"Your party finds yourselves in: {state.scene.description_seed}. What do you do?"

    return description


def narrate_narrative_action(action_description: str, actor_id: str, state: GameState) -> str:
    context = _build_context(state)
    actor = state.get_entity(actor_id)
    actor_role = actor.role if actor else "adventurer"
    actor_name = actor.character_name if actor else actor_id

    system_prompt = """You are a Dungeon Master narrator for a multiplayer D&D game.
A player has taken an exploratory or narrative action — not a direct attack.

Rules:
- Describe what the players perceive: sights, sounds, smells, atmosphere
- Maintain the adventure's tone and setting
- Acknowledge the whole party, not just the acting player
- Do NOT give or describe any items, weapons, keys, loot, or objects the players can pick up
- Do NOT grant any mechanical advantages, power-ups, or stat changes
- Do NOT invent enemies, ambushes, or combat — that is handled separately
- Do NOT contradict the current scene context
- Do NOT ask the players if they want to do something — they already decided, just narrate what happens
- Do NOT end with a question like "will you dare venture further?" or "what do you do next?"
- Narrate what actually occurs as a result of the action, then describe the new situation
- Keep it to 2-4 sentences"""

    chapter_seed = state.adventure.story_flags.get(
        f"chapter_{state.adventure.current_chapter}_seed", state.scene.description_seed
    )

    user_message = f"""Game context:
{json.dumps(context, indent=2)}

Current chapter objective (where the party needs to get to): "{chapter_seed}"
Final boss the party is hunting: {state.adventure.boss_name}

The {actor_role} named {actor_name} says: "{action_description}"

Narrate what happens as a direct result of this action. Subtly steer the party toward the chapter objective if it fits naturally."""

    narration = _call_openai(system_prompt, user_message)
    if narration is None:
        return f"{actor_name} {action_description.lower()}. The scene holds its breath."
    return narration


def narrate_combined_narrative(actions: dict, state: GameState) -> str:
    """actions: {actor_id: action_description} — all players submitted simultaneously."""
    context = _build_context(state)
    chapter_seed = state.adventure.story_flags.get(
        f"chapter_{state.adventure.current_chapter}_seed", state.scene.description_seed
    )

    action_lines = []
    for actor_id, action_desc in actions.items():
        actor = state.get_entity(actor_id)
        name = actor.character_name if actor else actor_id
        role = actor.role if actor else "adventurer"
        action_lines.append(f"- {name} (the {role}): \"{action_desc}\"")
    actions_text = "\n".join(action_lines)

    system_prompt = """You are a Dungeon Master narrator for a multiplayer D&D game.
All players have simultaneously submitted their exploratory actions for this moment.

Rules:
- Narrate the outcome of ALL submitted actions together in one cohesive response
- Give each player's action its own moment — don't ignore or merge anyone's contribution
- Describe what the characters perceive: sights, sounds, smells, atmosphere
- Maintain the adventure's tone and setting
- Do NOT give or describe any items, weapons, keys, loot, or objects the players can pick up
- Do NOT grant any mechanical advantages, power-ups, or stat changes
- Do NOT invent enemies, ambushes, or combat — that is handled separately
- Do NOT contradict the current scene context
- Do NOT ask the players if they want to do something — they already decided, just narrate what happens
- Do NOT end with a question like "will you dare venture further?"
- Keep it to 3-5 sentences"""

    user_message = f"""Game context:
{json.dumps(context, indent=2)}

Current chapter objective: "{chapter_seed}"
Final boss the party is hunting: {state.adventure.boss_name}

The players submitted these actions simultaneously:
{actions_text}

Narrate what happens as a result of both actions. Subtly steer the party toward the chapter objective."""

    narration = _call_openai(system_prompt, user_message)
    if narration is None:
        names = []
        for aid in actions:
            e = state.get_entity(aid)
            names.append(e.character_name if e else aid)
        return f"{' and '.join(names)} each make their move. The moment passes, the scene shifts around them."
    return narration


def narrate_rest(actor_id: str, hp_restored: int, mp_restored: int,
                 new_hp: int, max_hp: int, new_mp: int, max_mp: int,
                 state: GameState) -> str:
    context = _build_context(state)
    actor = state.get_entity(actor_id)
    actor_name = actor.character_name if actor else actor_id
    actor_role = actor.role if actor else "adventurer"

    mp_note = (
        f" They also regain some magical focus ({new_mp}/{max_mp} MP)." if mp_restored > 0 else ""
    )

    system_prompt = """You are a Dungeon Master narrator for a multiplayer D&D game.
A player has taken a short rest to recover.

Rules:
- 2-3 sentences describing the recovery
- Do NOT cite exact HP or MP numbers — convey the feeling instead (relief, steadied breathing, warmth returning)
- Convey that the character is still hurt and the danger is not over — they are not fully healed
- If magical energy was restored, briefly mention their focus or inner power returning
- Do not invent items, events, or other characters"""

    user_message = f"""Game context:
{json.dumps(context, indent=2)}

{actor_name} (a {actor_role}) took a short rest.
HP recovered: {hp_restored} (now {new_hp}/{max_hp}).{mp_note}

Narrate this recovery moment."""

    narration = _call_openai(system_prompt, user_message)
    if narration is None:
        return f"{actor_name} catches their breath and tends to their wounds, feeling slightly restored."
    return narration


def narrate_encounter_start(action_description: str, actor_id: str, enemy_names: list,
                            state: GameState, initial_attacks: list = None,
                            next_player_name: str = None) -> str:
    context = _build_context(state)
    actor = state.get_entity(actor_id)
    actor_name = actor.character_name if actor else actor_id

    if len(enemy_names) == 1:
        enemy_label = enemy_names[0]
    else:
        enemy_label = ", ".join(enemy_names[:-1]) + f" and {enemy_names[-1]}"

    if initial_attacks:
        atk_lines = "\n".join(
            f"- {a['enemy_name']} struck {a['target_name']} for {a['damage']} damage "
            f"({a['target_hp_remaining']} HP remaining) before the party could react"
            for a in initial_attacks
        )
        initiative_note = f"The enemies won initiative and attacked first:\n{atk_lines}"
    else:
        initiative_note = "The party won initiative — they act first this round."

    enemy_count_note = f"{len(enemy_names)} enemy" if len(enemy_names) == 1 else f"{len(enemy_names)} enemies"

    turn_prompt_rule = (
        f"- End by naturally addressing {next_player_name} — it is now their turn to act"
        if next_player_name and not initial_attacks else
        "- Do not prompt any specific player at the end"
    )

    system_prompt = f"""You are a Dungeon Master for a multiplayer D&D game.
Enemies have appeared and combat is beginning. Describe the encounter start vividly.

Rules:
- Briefly acknowledge what the party was doing when the enemies appeared
- Introduce all enemies dramatically — if there are multiple, make the group feel threatening
- If enemies attacked first, describe those strikes as a surprise or ambush — make it sting
- If the party won initiative, convey the tension of the standoff and that it's their move
- Address the whole party, not just one player
- 3-5 sentences total
- Do NOT invent items, loot, or damage values not listed below
{turn_prompt_rule}"""

    user_message = f"""Game context:
{json.dumps(context, indent=2)}

{actor_name} was: "{action_description}"
{enemy_count_note} appeared: {enemy_label}
{initiative_note}

Narrate this encounter start."""

    narration = _call_openai(system_prompt, user_message)
    if narration is None:
        if initial_attacks:
            hits = ", ".join(f"{a['enemy_name']} hits {a['target_name']} for {a['damage']}" for a in initial_attacks)
            return f"{enemy_label} ambushes the party! {hits}. Brace yourselves!"
        return f"{enemy_label} emerges from the shadows! Steel yourselves — combat begins!"
    return narration
 
 
def narrate_boss_encounter(action_description: str, actor_id: str, state: GameState,
                           initial_attacks: list = None, next_player_name: str = None) -> str:
    context = _build_context(state)
    actor = state.get_entity(actor_id)
    actor_name = actor.character_name if actor else actor_id
    boss_name = state.adventure.boss_name
    villain_motive = state.adventure.story_flags.get("villain_motive", "")

    if initial_attacks:
        atk_lines = "\n".join(
            f"- {a['enemy_name']} struck {a['target_name']} for {a['damage']} damage "
            f"({a['target_hp_remaining']} HP remaining)"
            for a in initial_attacks
        )
        initiative_note = f"The boss won initiative and attacked first:\n{atk_lines}"
    else:
        initiative_note = "The party won initiative — they act first."

    turn_prompt_rule = (
        f"- End by naturally addressing {next_player_name} — it is their turn to strike first"
        if next_player_name and not initial_attacks else
        "- Do not prompt any specific player at the end"
    )

    motive_note = f"The villain's motive: {villain_motive}" if villain_motive else ""

    system_prompt = f"""You are a Dungeon Master for a multiplayer D&D game.
The party has finally reached the final boss — the villain they have hunted across all five chapters.
This is the climax of the entire adventure. Make it feel earned and terrifying.

Rules:
- Open with a dramatic reveal of {boss_name} — describe their presence, power, and menace
- Reference what the party has endured to reach this moment
- If the boss attacked first, describe the strike as overwhelming and shocking
- If the party acts first, convey the weight of this moment — this is what they came for
- 4-6 sentences total — this narration should feel longer and more epic than normal encounters
- Do NOT invent items, loot, or damage values not listed below
{turn_prompt_rule}"""

    user_message = f"""Game context:
{json.dumps(context, indent=2)}

{actor_name} was: "{action_description}"
The final boss has appeared: {boss_name}
{motive_note}
{initiative_note}

Narrate this climactic confrontation."""

    narration = _call_openai(system_prompt, user_message)
    if narration is None:
        if initial_attacks:
            hits = ", ".join(f"{a['enemy_name']} hits {a['target_name']} for {a['damage']}" for a in initial_attacks)
            return f"{boss_name} has arrived — and struck before the party could react! {hits}. The final battle begins!"
        return f"The air grows cold as {boss_name} steps from the shadows. This is it — the final battle!"
    return narration


def generate_adventure_outline(title: str, theme: str, difficulty: str) -> Optional[dict]:
    system_prompt = """You are a Dungeon Master designing a D&D adventure outline.
Your job is to generate a structured adventure outline as JSON.
 
You must ALWAYS respond with ONLY a valid JSON object. No explanation, no extra text.
 
The JSON must have exactly these fields:
{
    "title": "name of the adventure",
    "boss_name": "name of the final boss enemy",
    "chapter_1_seed": "short scene description for chapter 1 (opening area)",
    "chapter_2_seed": "short scene description for chapter 2 (escalating danger)",
    "chapter_3_seed": "short scene description for chapter 3 (mid-point twist)",
    "chapter_4_seed": "short scene description for chapter 4 (penultimate challenge)",
    "chapter_5_seed": "short scene description for chapter 5 (final boss encounter)",
    "story_flags": {
        "villain_motive": "one sentence on why the boss is doing this",
        "world_detail": "one unique fact about this world (e.g. two suns, no iron)",
        "recurring_npc": "name and one-word personality of a side character"
    }
}
 
Rules:
- Keep chapter seeds to 5-10 words describing the environment
- Each chapter seed should feel like a natural escalation from the last
- The boss should fit the theme provided
- Make the adventure feel cohesive and thematic"""
 
    user_message = f"""Generate a D&D adventure outline with these parameters:
- Title: {title}
- Theme: {theme}
- Difficulty: {difficulty}
 
Return a structured JSON adventure outline."""
 
    raw_response = _call_openai(system_prompt, user_message)
 
    if raw_response is None:
        print("Adventure generation failed — no response from API")
        return None
 
    try:
        outline = json.loads(raw_response)
    except json.JSONDecodeError:
        print(f"AI returned malformed adventure JSON: {raw_response}")
        return None
 
    required_fields = ["title", "boss_name", "chapter_1_seed", "chapter_2_seed",
                       "chapter_3_seed", "chapter_4_seed", "chapter_5_seed", "story_flags"]
    for field in required_fields:
        if field not in outline:
            print(f"Adventure outline missing field: {field}")
            return None
 
    return outline
 
 
def narrate_chapter_transition(old_chapter: int, new_chapter: int, state: GameState) -> str:
    context = _build_context(state)
    new_seed = state.adventure.story_flags.get(f"chapter_{new_chapter}_seed", "a new area")

    system_prompt = """You are a Dungeon Master narrator for a multiplayer D&D game.
The party has just defeated the last enemies of a chapter and is advancing to the next chapter.

Rules:
- 4-6 sentences total
- First 1-2 sentences: celebrate the victory and acknowledge the party's effort
- Next 1-2 sentences: announce that a new chapter begins, describe the transition into the new area using the chapter seed
- Final 1-2 sentences: hint at the new chapter's threat or objective without spelling it out fully
- Keep the tone dramatic and immersive — this is a significant story moment
- Do NOT invent items, loot, or mechanical rewards"""

    user_message = f"""Game context:
{json.dumps(context, indent=2)}

The party just cleared Chapter {old_chapter}.
Chapter {new_chapter} now begins. New setting: "{new_seed}"
Final boss they are still hunting: {state.adventure.boss_name}

Narrate the chapter clear and transition into Chapter {new_chapter}."""

    narration = _call_openai(system_prompt, user_message)
    if narration is None:
        return (
            f"The last enemy falls and silence descends. Chapter {old_chapter} is complete. "
            f"The party presses on — Chapter {new_chapter} awaits: {new_seed}."
        )
    return narration


def check_for_encounter(action_description: str, actor_id: str, state: GameState) -> Optional[list]:
    """
    Ask the AI whether a combat encounter should trigger right now.
    Returns None if no encounter, or a list of 1-3 enemy proposal dicts if yes.
    """
    context = _build_context(state)
    narrative_count = state.adventure.story_flags.get("_narrative_count", 0)
    chapter_seed = state.adventure.story_flags.get(
        f"chapter_{state.adventure.current_chapter}_seed", state.scene.description_seed
    )

    system_prompt = """You are a Dungeon Master deciding whether to trigger a combat encounter.

You must ALWAYS respond with ONLY a valid JSON object. No explanation, no extra text.

If no encounter should happen now, return exactly: {"trigger": false}

If an encounter should trigger, return:
{
    "trigger": true,
    "enemies": [
        {
            "name": "enemy name",
            "role": "minion, brute, or caster",
            "weapon_name": "name of the weapon",
            "weapon_type": "dagger, sword, axe, or staff",
            "weapon_damage": 4,
            "flavor_text": "one sentence appearance description"
        }
    ]
}

Enemy roles:
- "minion" — standard weak enemy, always spawns in groups of 2-3. Use for most encounters.
- "brute" — powerful solo miniboss, always spawns alone (exactly 1). Reserve for dramatic high-stakes moments.
- "caster" — magical enemy, can appear alone or alongside minions, MUST use weapon_type "staff"

Decision rules:
- ONLY trigger if combat makes strong narrative sense at this exact moment
- Think like a DM: does the party's current action logically lead them into danger?
- Good triggers: party enters enemy territory, investigates a known threat, reaches a guarded location, walks into an ambush
- Bad triggers: party is exploring peacefully, doing routine travel, or recently finished a fight
- Do NOT trigger just because several turns have passed — wait for a dramatically appropriate moment
- DEFAULT encounter = 2-3 minions. A solo brute is a rare, dramatic event — do not default to it.
- All enemies must be thematically consistent with the scene and chapter
- weapon_damage must be an integer between 3 and 7
- Do NOT assign HP, MP, or stats — the engine handles those"""

    user_message = f"""Game context:
{json.dumps(context, indent=2)}

Chapter {state.adventure.current_chapter} objective / setting: "{chapter_seed}"
Final boss the party is hunting: {state.adventure.boss_name}
Narrative turns since last combat: {narrative_count}

The player just did: "{action_description}"

Should a combat encounter trigger right now based on the story? If yes, what enemies fit this moment?"""

    raw_response = _call_openai(system_prompt, user_message)

    if raw_response is None:
        print("check_for_encounter: no API response")
        return None

    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError:
        print(f"check_for_encounter: malformed JSON: {raw_response}")
        return None

    if not data.get("trigger"):
        return None

    enemies = data.get("enemies")
    if not isinstance(enemies, list) or len(enemies) == 0:
        print("check_for_encounter: trigger=true but no enemies list")
        return None

    valid = []
    for e in enemies[:3]:
        if not all(k in e for k in ["name", "role", "weapon_name", "weapon_type", "weapon_damage"]):
            continue
        if e["role"] not in ["minion", "brute", "caster"]:
            continue
        if e["weapon_type"] not in ["dagger", "sword", "axe", "staff"]:
            continue
        valid.append(e)

    return valid if valid else None


def propose_enemy_encounter(state: GameState) -> Optional[dict]:
    context = _build_context(state)
 
    system_prompt = """You are a Dungeon Master proposing an enemy encounter for a D&D game.
Your job is to propose a single enemy appropriate for the current scene.

You must ALWAYS respond with ONLY a valid JSON object. No explanation, no extra text.

The JSON must have exactly these fields:
{
    "name": "enemy name",
    "role": "minion, brute, or caster",
    "flavor_text": "1-2 sentence description of the enemy's appearance",
    "weapon_name": "name of the weapon",
    "weapon_type": "dagger, sword, axe, or staff",
    "weapon_damage": an integer between 3 and 7
}

Rules:
- role must be exactly "minion", "brute", or "caster"
- "minion" is a standard weak enemy; "brute" is a powerful solo miniboss; "caster" is a magical enemy
- weapon_type must be exactly one of: dagger, sword, axe, staff
- caster role must use weapon_type staff
- weapon_damage must be an integer between 3 and 7
- The enemy should fit the current scene and adventure theme
- Do NOT assign HP, MP, or stats — the engine handles those"""
 
    user_message = f"""Game context:
{json.dumps(context, indent=2)}
 
Propose a single enemy encounter appropriate for this scene and adventure.
The enemy should fit the theme: "{state.adventure.title}" in chapter {state.adventure.current_chapter}."""
 
    raw_response = _call_openai(system_prompt, user_message)
 
    if raw_response is None:
        print("Enemy proposal failed — no response from API")
        return None
 
    try:
        proposal = json.loads(raw_response)
    except json.JSONDecodeError:
        print(f"AI returned malformed enemy JSON: {raw_response}")
        return None
 
    required_fields = ["name", "role", "flavor_text", "weapon_name", "weapon_type", "weapon_damage"]
    for field in required_fields:
        if field not in proposal:
            print(f"Enemy proposal missing field: {field}")
            return None
 
    if proposal["role"] not in ["minion", "brute", "caster"]:
        print(f"Invalid enemy role: {proposal['role']}")
        return None
 
    if proposal["weapon_type"] not in ["dagger", "sword", "axe", "staff"]:
        print(f"Invalid weapon type: {proposal['weapon_type']}")
        return None
 
    return proposal