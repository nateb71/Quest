"""
Unit tests for sections 3.1 - 3.5 of the Quest testing document.
Run with: pytest test_unit.py -v
"""

import pytest
from game_state import GameState, AdventureState, SceneState, Entity, Stats, Weapon, Action
from game_engine import validate_action, resolve_attack, resolve_spell, advance_turn, check_victory


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_warrior(entity_id="player_1", str_stat=14, sword_damage=6):
    return Entity(
        id=entity_id, type="player", role="warrior", level=1,
        hp=30, max_hp=30, mp=0, max_mp=0,
        stats=Stats(str=str_stat, dex=10, int=8),
        weapon=Weapon(name="Longsword", weapon_type="sword", damage=sword_damage),
        items=[],
    )

def make_mage(entity_id="player_2", int_stat=16, mp=30):
    return Entity(
        id=entity_id, type="player", role="mage", level=1,
        hp=18, max_hp=18, mp=mp, max_mp=30,
        stats=Stats(str=8, dex=10, int=int_stat),
        weapon=Weapon(name="Staff", weapon_type="staff", damage=4),
        items=[],
    )

def make_enemy(entity_id="goblin_1", hp=22):
    return Entity(
        id=entity_id, type="enemy", role="brute", level=1,
        hp=hp, max_hp=hp, mp=0, max_mp=0,
        stats=Stats(str=12, dex=8, int=4),
        weapon=Weapon(name="Axe", weapon_type="axe", damage=6),
        items=[],
    )

def make_state(entities, active_ids, initiative_order, current_turn_index=0, round_number=1):
    return GameState(
        adventure=AdventureState(title="Test", current_chapter=1, boss_name="Boss",
                                  boss_defeated=False, story_flags={}),
        scene=SceneState(description_seed="test room", active_entity_ids=list(active_ids)),
        entities=entities,
        in_combat=True,
        initiative_order=list(initiative_order),
        current_turn_index=current_turn_index,
        round_number=round_number,
    )

def make_action(actor_id="player_1", action_type="attack", target_id="goblin_1", mp_cost=None):
    return Action(actor_id=actor_id, action_type=action_type, target_id=target_id,
                  action_name="test_action", mp_cost=mp_cost)


# ── 3.1 Action Validation ──────────────────────────────────────────────────────

def test_actor_not_in_scene():
    # player_1 is not listed in active_entity_ids
    state = make_state(
        entities={"player_1": make_warrior(), "goblin_1": make_enemy()},
        active_ids=["goblin_1"],
        initiative_order=["goblin_1"],
    )
    valid, msg = validate_action(make_action(actor_id="player_1"), state)
    assert valid == False
    assert msg == "Actor not in the current scene"

def test_actor_is_dead():
    # player_1 is in the scene but has 0 HP
    warrior = make_warrior()
    warrior.hp = 0
    state = make_state(
        entities={"player_1": warrior, "goblin_1": make_enemy()},
        active_ids=["player_1", "goblin_1"],
        initiative_order=["player_1", "goblin_1"],
    )
    valid, msg = validate_action(make_action(actor_id="player_1"), state)
    assert valid == False
    assert msg == "Actor's hp is 0 or less"

def test_wrong_turn():
    # goblin goes first (index 0), but player_1 tries to act
    state = make_state(
        entities={"player_1": make_warrior(), "goblin_1": make_enemy()},
        active_ids=["player_1", "goblin_1"],
        initiative_order=["goblin_1", "player_1"],
        current_turn_index=0,
    )
    valid, msg = validate_action(make_action(actor_id="player_1"), state)
    assert valid == False
    assert msg == "Not the actor's turn"

def test_target_not_in_scene():
    # goblin_1 exists in entities but is not in active_entity_ids
    state = make_state(
        entities={"player_1": make_warrior(), "goblin_1": make_enemy()},
        active_ids=["player_1"],
        initiative_order=["player_1"],
    )
    valid, msg = validate_action(make_action(actor_id="player_1", target_id="goblin_1"), state)
    assert valid == False
    assert msg == "Target not in the current scene"

def test_spell_without_staff():
    # warrior has a sword, not a staff
    state = make_state(
        entities={"player_1": make_warrior(), "goblin_1": make_enemy()},
        active_ids=["player_1", "goblin_1"],
        initiative_order=["player_1", "goblin_1"],
    )
    action = make_action(actor_id="player_1", action_type="cast_spell", mp_cost=5)
    valid, msg = validate_action(action, state)
    assert valid == False
    assert msg == "Must have staff to cast spell"

def test_spell_no_mp_cost():
    # mage has a staff but mp_cost was not provided
    state = make_state(
        entities={"player_2": make_mage(), "goblin_1": make_enemy()},
        active_ids=["player_2", "goblin_1"],
        initiative_order=["player_2", "goblin_1"],
    )
    action = make_action(actor_id="player_2", action_type="cast_spell", target_id="goblin_1", mp_cost=None)
    valid, msg = validate_action(action, state)
    assert valid == False
    assert msg == "Spell cost not provided"

def test_insufficient_mp():
    # mage only has 3 MP but the spell costs 10
    state = make_state(
        entities={"player_2": make_mage(mp=3), "goblin_1": make_enemy()},
        active_ids=["player_2", "goblin_1"],
        initiative_order=["player_2", "goblin_1"],
    )
    action = make_action(actor_id="player_2", action_type="cast_spell", target_id="goblin_1", mp_cost=10)
    valid, msg = validate_action(action, state)
    assert valid == False
    assert "enough MP" in msg

def test_valid_attack():
    # all checks pass for a normal attack
    state = make_state(
        entities={"player_1": make_warrior(), "goblin_1": make_enemy()},
        active_ids=["player_1", "goblin_1"],
        initiative_order=["player_1", "goblin_1"],
    )
    valid, msg = validate_action(make_action(actor_id="player_1"), state)
    assert valid == True
    assert msg == "Action is valid"

def test_valid_spell():
    # mage with staff and sufficient MP — all checks pass
    state = make_state(
        entities={"player_2": make_mage(), "goblin_1": make_enemy()},
        active_ids=["player_2", "goblin_1"],
        initiative_order=["player_2", "goblin_1"],
    )
    action = make_action(actor_id="player_2", action_type="cast_spell", target_id="goblin_1", mp_cost=5)
    valid, msg = validate_action(action, state)
    assert valid == True
    assert msg == "Action is valid"


# ── 3.2 Combat Resolution ──────────────────────────────────────────────────────

def test_physical_attack_damage():
    # STR=16, sword damage=8 → total damage = 24
    goblin = make_enemy(hp=30)
    state = make_state(
        entities={"player_1": make_warrior(str_stat=16, sword_damage=8), "goblin_1": goblin},
        active_ids=["player_1", "goblin_1"],
        initiative_order=["player_1", "goblin_1"],
    )
    resolve_attack(make_action(actor_id="player_1", action_type="attack"), state)
    assert goblin.hp == 6  # 30 - 24

def test_spell_damage():
    # INT=18, staff damage=4 → total damage = 22, mp reduced by cost
    mage = make_mage(int_stat=18)
    goblin = make_enemy(hp=30)
    state = make_state(
        entities={"player_2": mage, "goblin_1": goblin},
        active_ids=["player_2", "goblin_1"],
        initiative_order=["player_2", "goblin_1"],
    )
    action = make_action(actor_id="player_2", action_type="cast_spell", target_id="goblin_1", mp_cost=5)
    resolve_spell(action, state)
    assert goblin.hp == 8   # 30 - 22
    assert mage.mp == 25    # 30 - 5

def test_enemy_defeated_removed():
    # a killing blow should remove the enemy from active_ids and initiative_order
    goblin = make_enemy(hp=1)
    state = make_state(
        entities={"player_1": make_warrior(str_stat=16, sword_damage=8), "goblin_1": goblin},
        active_ids=["player_1", "goblin_1"],
        initiative_order=["player_1", "goblin_1"],
    )
    resolve_attack(make_action(actor_id="player_1", action_type="attack"), state)
    assert "goblin_1" not in state.scene.active_entity_ids
    assert "goblin_1" not in state.initiative_order


# ── 3.3 Turn Advancement ───────────────────────────────────────────────────────

def test_normal_advance():
    # advancing from index 0 with 3 entities should move to index 1
    state = make_state(
        entities={"player_1": make_warrior(), "player_2": make_mage(), "goblin_1": make_enemy()},
        active_ids=["player_1", "player_2", "goblin_1"],
        initiative_order=["player_1", "player_2", "goblin_1"],
        current_turn_index=0,
    )
    advance_turn(state)
    assert state.current_turn_index == 1

def test_end_of_round_wraps():
    # advancing from the last index should wrap back to 0 and increment round_number
    state = make_state(
        entities={"player_1": make_warrior(), "player_2": make_mage(), "goblin_1": make_enemy()},
        active_ids=["player_1", "player_2", "goblin_1"],
        initiative_order=["player_1", "player_2", "goblin_1"],
        current_turn_index=2,
        round_number=1,
    )
    advance_turn(state)
    assert state.current_turn_index == 0
    assert state.round_number == 2


# ── 3.4 Victory Detection ──────────────────────────────────────────────────────

def test_players_win():
    # only a player remains — should return players_win and end combat
    state = make_state(
        entities={"player_1": make_warrior()},
        active_ids=["player_1"],
        initiative_order=["player_1"],
    )
    assert check_victory(state) == "players_win"
    assert state.in_combat == False

def test_players_lose():
    # only an enemy remains — should return players_lose and end combat
    state = make_state(
        entities={"goblin_1": make_enemy()},
        active_ids=["goblin_1"],
        initiative_order=["goblin_1"],
    )
    assert check_victory(state) == "players_lose"
    assert state.in_combat == False

def test_combat_ongoing():
    # both a player and an enemy are alive — combat continues
    state = make_state(
        entities={"player_1": make_warrior(), "goblin_1": make_enemy()},
        active_ids=["player_1", "goblin_1"],
        initiative_order=["player_1", "goblin_1"],
    )
    assert check_victory(state) == "ongoing"


# ── 3.5 Serialization ─────────────────────────────────────────────────────────

def test_round_trip_serialization():
    # state serialized to JSON and back should match the original
    original = make_state(
        entities={"player_1": make_warrior(), "goblin_1": make_enemy()},
        active_ids=["player_1", "goblin_1"],
        initiative_order=["player_1", "goblin_1"],
        current_turn_index=1,
        round_number=3,
    )
    restored = GameState.from_json(original.to_json())
    assert restored.adventure.title == original.adventure.title
    assert restored.adventure.current_chapter == original.adventure.current_chapter
    assert restored.scene.active_entity_ids == original.scene.active_entity_ids
    assert restored.initiative_order == original.initiative_order
    assert restored.current_turn_index == original.current_turn_index
    assert restored.round_number == original.round_number
    assert restored.in_combat == original.in_combat

def test_entity_fields_preserved():
    # all entity fields should survive a round trip through JSON unchanged
    warrior = make_warrior(str_stat=16, sword_damage=8)
    goblin = make_enemy(hp=15)
    original = make_state(
        entities={"player_1": warrior, "goblin_1": goblin},
        active_ids=["player_1", "goblin_1"],
        initiative_order=["player_1", "goblin_1"],
    )
    restored = GameState.from_json(original.to_json())
    p1 = restored.entities["player_1"]
    assert p1.hp == 30
    assert p1.stats.str == 16
    assert p1.weapon.damage == 8
    assert p1.weapon.weapon_type == "sword"
    g1 = restored.entities["goblin_1"]
    assert g1.hp == 15
    assert g1.type == "enemy"

def test_enemies_defeated_counter_serializes():
    # enemies_defeated_this_chapter should survive a round trip when set to a non-zero value
    original = make_state(
        entities={"player_1": make_warrior(), "goblin_1": make_enemy()},
        active_ids=["player_1", "goblin_1"],
        initiative_order=["player_1", "goblin_1"],
    )
    original.adventure.enemies_defeated_this_chapter = 1
    restored = GameState.from_json(original.to_json())
    assert restored.adventure.enemies_defeated_this_chapter == 1

def test_enemies_defeated_defaults_to_zero():
    # old save data without the field should deserialize to 0, not raise an error
    state_dict = {
        "adventure": {
            "title": "Old Save",
            "current_chapter": 2,
            "boss_name": "Boss",
            "boss_defeated": False,
            "story_flags": {},
            # enemies_defeated_this_chapter intentionally missing
        },
        "scene": {"description_seed": "dungeon", "active_entity_ids": []},
        "entities": {},
        "in_combat": False,
        "initiative_order": [],
        "current_turn_index": 0,
        "round_number": 1,
    }
    import json
    restored = GameState.from_json(json.dumps(state_dict))
    assert restored.adventure.enemies_defeated_this_chapter == 0
