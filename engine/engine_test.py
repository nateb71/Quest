import sys
from game_state import GameState, AdventureState, SceneState, Entity, Stats, Weapon, Action
from game_engine import initialize_combat, process_action
from ai_layer import interpret_action, narrate_combat_result, generate_scene_description
 
 
def build_test_state():
    warrior = Entity(
        id="player_1",
        type="player",
        role="warrior",
        level=1,
        hp=30, max_hp=30,
        mp=5, max_mp=5,
        stats=Stats(str=16, dex=10, int=8),
        weapon=Weapon(name="Longsword", weapon_type="sword", damage=8),
        items=["health_potion"],
    )
 
    mage = Entity(
        id="player_2",
        type="player",
        role="mage",
        level=1,
        hp=18, max_hp=18,
        mp=20, max_mp=20,
        stats=Stats(str=6, dex=12, int=18),
        weapon=Weapon(name="Apprentice Staff", weapon_type="staff", damage=4),
        items=["health_potion", "mana_potion"],
    )
 
    goblin = Entity(
        id="goblin_1",
        type="enemy",
        role="brute",
        level=1,
        hp=12, max_hp=12,
        mp=0, max_mp=0,
        stats=Stats(str=10, dex=8, int=4),
        weapon=Weapon(name="Rusty Dagger", weapon_type="dagger", damage=4),
        items=[],
    )
 
    adventure = AdventureState(
        title="The Shadow of Malgrath",
        current_chapter=1,
        boss_name="Malgrath the Undying",
        boss_defeated=False,
        story_flags={},
    )
 
    scene = SceneState(
        description_seed="dimly lit dungeon entrance, stone walls, torch flickering",
        active_entity_ids=["player_1", "player_2", "goblin_1"],
    )
 
    return GameState(
        adventure=adventure,
        scene=scene,
        entities={
            "player_1": warrior,
            "player_2": mage,
            "goblin_1": goblin,
        },
    )
 
 
def print_state(state):
    print("\n--- CURRENT STATE ---")
    for eid in state.scene.active_entity_ids:
        e = state.get_entity(eid)
        print(f"  {e.id} ({e.role}) | HP: {e.hp}/{e.max_hp} | MP: {e.mp}/{e.max_mp}")
    if state.in_combat:
        current = state.initiative_order[state.current_turn_index]
        print(f"  Round: {state.round_number} | Current turn: {current}")
    print("---------------------\n")
 
 
def main():
    print("=== Quest CLI Test (AI Powered) ===")
    print("Type actions in natural language e.g. 'I attack the goblin'\n")
 
    state = build_test_state()
 
    print("Generating scene description...")
    scene_desc = generate_scene_description(state)
    print(f"\n{scene_desc}\n")
 
    initialize_combat(state)
 
    print("Combat started! Initiative order:")
    for i, eid in enumerate(state.initiative_order):
        print(f"  {i+1}. {eid}")
 
    print_state(state)
 
    while True:
        current_actor_id = state.initiative_order[state.current_turn_index]
        raw = input(f"[{current_actor_id}] > ").strip()
 
        if not raw:
            continue
 
        if raw.lower() == "quit":
            print("Exiting.")
            sys.exit(0)
 
        if raw.lower() == "state":
            print_state(state)
            continue
 
        print("\nInterpreting action...")
        action = interpret_action(raw, current_actor_id, state)
 
        if action is None:
            print("Could not interpret that action. Try again.\n")
            continue
 
        if action.action_type == "narrative":
            print("\nThis is not a combat action. Try attacking or casting a spell.\n")
            continue
 
        print(f"Interpreted as: {action.action_type} on {action.target_id}")
 
        result = process_action(action, state)
 
        if result in ["players_win", "players_lose"]:
            narration = narrate_combat_result(action, result, state)
            print(f"\n{narration}\n")
            print("Combat over. Exiting.")
            sys.exit(0)
 
        if isinstance(result, str) and result != "ongoing":
            print(f"Action rejected: {result}\n")
            continue
 
        narration = narrate_combat_result(action, result, state)
        print(f"\n{narration}")
        print_state(state)
 
 
if __name__ == "__main__":
    main()