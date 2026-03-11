from dataclasses import dataclass
import game_state
import random

@dataclass
class Action:
    actor_id: str
    action_type: str
    target_id: str
    action_name:str
    mp_cost = None #mp cost for cast_spell

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