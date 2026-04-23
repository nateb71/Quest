import json
import os
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
    }
 
    # only send publicly visible entity info, not raw stats or damage values
    entity_snapshots = {}
    for entity in state.get_active_entities():
        entity_snapshots[entity.id] = {
            "id": entity.id,
            "type": entity.type,
            "role": entity.role,
            "hp": entity.hp,
            "max_hp": entity.max_hp,
            "mp": entity.mp,
            "max_mp": entity.max_mp,
            "weapon_name": entity.weapon.name,
            "weapon_type": entity.weapon.weapon_type,
        }
 
    return {
        "adventure": adventure_context,
        "scene": scene_context,
        "entities": entity_snapshots,
    }
 
 
def interpret_action(player_input: str, actor_id: str, state: GameState) -> Optional[Action]:
    context = _build_context(state)
 
    system_prompt = """You are an action interpreter for a turn-based D&D game.
Your ONLY job is to convert a player's natural language input into a structured JSON action object.
 
You must ALWAYS respond with ONLY a valid JSON object. No explanation, no extra text, no markdown.
 
The JSON must have exactly these fields:
{
    "actor_id": "the ID of the player performing the action",
    "action_type": "attack" or "cast_spell",
    "target_id": "the ID of the target entity",
    "action_name": "short name of the action e.g. sword_strike or fireball",
    "mp_cost": null for attacks, or an integer cost for spells (default 5 for any spell)
}
 
Rules:
- action_type must be exactly "attack" or "cast_spell"
- target_id must be one of the active entity IDs provided in the context
- If the player tries to do something other than attack or cast a spell, default to "attack"
- mp_cost must be null for attacks and an integer for cast_spell
- Never invent entity IDs. Only use IDs from the active_entity_ids list."""
 
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
 
    if action_data["action_type"] not in ["attack", "cast_spell"]:
        print(f"AI returned invalid action_type: {action_data['action_type']}")
        return None
 
    if action_data["target_id"] not in state.scene.active_entity_ids:
        print(f"AI returned invalid target_id: {action_data['target_id']}")
        return None
 
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
 
 
def generate_scene_description(state: GameState) -> str:
    context = _build_context(state)
 
    system_prompt = """You are a Dungeon Master for a D&D game.
Your job is to generate an immersive scene description for the players.
 
Rules:
- Keep the description to 5-8 sentences
- Base the description on the description_seed provided
- Maintain consistency with the adventure title, chapter, and story_flags
- Include at least one detail for each sense: sight, sound, and smell
- Reference any villain_motive, world_detail, or recurring_npc from story_flags if present
- Do not invent mechanical events or stat changes
- Do not mention specific HP or MP numbers
- End with a clear hook that invites player action"""
 
    user_message = f"""Game context:
{json.dumps(context, indent=2)}
 
Generate an immersive scene description based on the description_seed: 
"{state.scene.description_seed}"
 
Consider the adventure context and any story_flags when writing the description."""
 
    description = _call_openai(system_prompt, user_message)
 
    # fallback if API fails
    if description is None:
        return f"You find yourself in: {state.scene.description_seed}. What do you do?"
 
    return description
 
 
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
 
 
def propose_enemy_encounter(state: GameState) -> Optional[dict]:
    context = _build_context(state)
 
    system_prompt = """You are a Dungeon Master proposing an enemy encounter for a D&D game.
Your job is to propose a single enemy appropriate for the current scene.
 
You must ALWAYS respond with ONLY a valid JSON object. No explanation, no extra text.
 
The JSON must have exactly these fields:
{
    "name": "enemy name",
    "role": "brute or caster",
    "flavor_text": "1-2 sentence description of the enemy's appearance",
    "weapon_name": "name of the weapon",
    "weapon_type": "dagger, sword, axe, or staff",
    "weapon_damage": an integer between 4 and 10
}
 
Rules:
- role must be exactly "brute" or "caster"
- weapon_type must be exactly one of: dagger, sword, axe, staff
- caster role should always have weapon_type staff
- weapon_damage must be an integer between 4 and 10
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
 
    if proposal["role"] not in ["brute", "caster"]:
        print(f"Invalid enemy role: {proposal['role']}")
        return None
 
    if proposal["weapon_type"] not in ["dagger", "sword", "axe", "staff"]:
        print(f"Invalid weapon type: {proposal['weapon_type']}")
        return None
 
    return proposal