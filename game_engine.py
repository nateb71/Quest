from game_state import GameState, Entity
import random

def validate_action(action, state):   
    #check 1
    if action.actor_id not in state.scene.active_entity_ids:
        return False, "Actor not in the current scene"
    
    #check 2
    actor = state.get_entity(action.actor_id)
    if actor is None:
        return False, "Actor does not exist"
    if not actor.is_alive():
        return False, "Actor's hp is 0 or less"
    
    #check 3
    if state.initiative_order[state.current_turn_index] != action.actor_id:
        return False, "Not the actor's turn"
    
    #check 4
    if action.target_id not in state.scene.active_entity_ids:
        return False, "Target not in the current scene"
    target = state.get_entity(action.target_id)
    if target is None:
        return False, "Target does not exist"
    
    #check 5
    if action.action_type == "cast_spell":
        if actor.weapon.weapon_type != "staff":
            return False, "Must have staff to cast spell"
        
        #check 6
        if action.mp_cost is None:
            return False, "Spell cost not provided"
        if action.mp_cost > actor.mp:
            return False, "Actor does not have enough MP to cast the spell"
    
    return True, "Action is valid"

def initialize_combat(state):
    entities = state.get_active_entities()
    initiative_order = {}

    for entity in entities:
        initiative = random.randint(1, 20) + entity.stats.dex
        initiative_order[entity.id] = initiative

    sorted_init = dict(sorted(initiative_order.items(), key=lambda item: item[1], reverse=True))

    state.initiative_order = list(sorted_init.keys())

    state.current_turn_index = 0
    state.round_number = 1
    state.in_combat = True

def resolve_attack(action, state):
    actor = state.get_entity(action.actor_id)
    target = state.get_entity(action.target_id)

    if actor is None or target is None:
        return False, "Actor or Target do not exist"
    
    if action.action_type == "attack":
        dmg = random.randint(1, max(1, actor.weapon.damage)) + actor.stats.str // 4
        target.hp -= dmg
        
        if target.hp < 1:
            state.scene.active_entity_ids.remove(target.id)
            state.initiative_order.remove(target.id)

def resolve_spell(action, state):
    actor = state.get_entity(action.actor_id)
    target = state.get_entity(action.target_id)

    if actor is None or target is None:
        return False, "Actor or Target do not exist"

    if action.action_type == "cast_spell":
        actor.mp -= action.mp_cost

        if target.type == "player":
            heal = random.randint(1, max(1, actor.weapon.damage)) + actor.stats.int // 4
            target.hp = min(target.hp + heal, target.max_hp)
        else:
            dmg = random.randint(1, max(1, actor.weapon.damage)) + actor.stats.int // 4
            target.hp -= dmg

            if target.hp < 1:
                state.scene.active_entity_ids.remove(target.id)
                state.initiative_order.remove(target.id)

def skip_enemy_turns(state):
    for _ in range(len(state.initiative_order)):
        if not state.initiative_order:
            break
        idx = state.current_turn_index % len(state.initiative_order)
        current = state.get_entity(state.initiative_order[idx])
        if current and current.type == "enemy":
            advance_turn(state)
        else:
            break


def process_enemy_turns(state):
    """
    Execute all consecutive enemy turns, applying damage to players.
    Returns (attacks, final_result) where attacks is a list of attack dicts
    and final_result is "players_lose" if all players died, otherwise None.
    """
    attacks = []

    for _ in range(len(state.initiative_order) + 1):
        if not state.initiative_order or not state.in_combat:
            break
        idx = state.current_turn_index % len(state.initiative_order)
        current_id = state.initiative_order[idx]
        current = state.get_entity(current_id)
        if current is None or current.type != "enemy":
            break

        living_players = [e for e in state.get_active_entities() if e.type == "player" and e.is_alive()]
        if not living_players:
            break

        target = random.choice(living_players)
        dmg = max(1, random.randint(1, max(1, current.weapon.damage)) + current.stats.str // 4)
        target.hp -= dmg

        attacks.append({
            "enemy_id":            current_id,
            "enemy_name":          current.character_name,
            "enemy_role":          current.role,
            "target_id":           target.id,
            "target_name":         target.character_name,
            "damage":              dmg,
            "target_hp_remaining": max(0, target.hp),
        })

        if target.hp <= 0:
            if target.id in state.scene.active_entity_ids:
                state.scene.active_entity_ids.remove(target.id)
            if target.id in state.initiative_order:
                state.initiative_order.remove(target.id)
            if not [e for e in state.get_active_entities() if e.type == "player"]:
                state.in_combat = False
                state.initiative_order = []
                state.current_turn_index = 0
                return attacks, "players_lose"

        advance_turn(state)

    return attacks, None

def advance_turn(state):
    state.current_turn_index += 1
    
    if state.current_turn_index >= len(state.initiative_order):
        state.round_number += 1
        state.current_turn_index = 0

def check_victory(state):
    enemies = [e for e in state.get_active_entities() if e.type == "enemy"]
    players = [p for p in state.get_active_entities() if p.type == "player"]

    if len(players) == 0:
        state.in_combat = False
        state.initiative_order = []
        state.current_turn_index = 0
        return "players_lose"

    if len(enemies) == 0:
        state.in_combat = False
        state.initiative_order = []
        state.current_turn_index = 0
        return "players_win"
    
    else:
        return "ongoing"
    
def process_action(action, state):
    check1 = validate_action(action, state)

    if not check1[0]:
        return check1[1]
    
    # if narrative action skip engine entirely
    if action.action_type == "narrative":
        return "narrative"

    if action.action_type == "attack":
        resolve_attack(action, state)

    if action.action_type == "cast_spell":
        resolve_spell(action, state)

    check2 = check_victory(state)

    advance_turn(state)

    return check2
   