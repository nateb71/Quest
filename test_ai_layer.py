"""
Integration tests for section 4.1 (AI Layer) of the Quest testing document.
Uses unittest.mock to avoid live OpenAI API calls.
Run with: pytest test_ai_layer.py -v
"""

import json
import pytest
from unittest.mock import patch
from game_state import GameState, AdventureState, SceneState, Entity, Stats, Weapon
from ai_layer import interpret_action, generate_adventure_outline


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_test_state():
    # minimal state with one warrior and one enemy in the scene
    warrior = Entity(
        id="player_1", type="player", role="warrior", level=1,
        hp=30, max_hp=30, mp=0, max_mp=0,
        stats=Stats(str=14, dex=10, int=8),
        weapon=Weapon(name="Longsword", weapon_type="sword", damage=6),
        items=[],
    )
    goblin = Entity(
        id="goblin_1", type="enemy", role="brute", level=1,
        hp=22, max_hp=22, mp=0, max_mp=0,
        stats=Stats(str=12, dex=8, int=4),
        weapon=Weapon(name="Axe", weapon_type="axe", damage=6),
        items=[],
    )
    return GameState(
        adventure=AdventureState(title="Test Quest", current_chapter=1, boss_name="Boss",
                                  boss_defeated=False, story_flags={}),
        scene=SceneState(description_seed="dark cave", active_entity_ids=["player_1", "goblin_1"]),
        entities={"player_1": warrior, "goblin_1": goblin},
        in_combat=True,
        initiative_order=["player_1", "goblin_1"],
        current_turn_index=0,
        round_number=1,
    )


# ── 4.1 AI Layer Integration ───────────────────────────────────────────────────

def test_valid_attack_interpretation():
    # mock returns a well-formed attack JSON — should produce an Action with action_type="attack"
    mock_response = json.dumps({
        "actor_id": "player_1",
        "action_type": "attack",
        "target_id": "goblin_1",
        "action_name": "sword_strike",
        "mp_cost": None,
    })
    with patch("ai_layer._call_openai", return_value=mock_response):
        action = interpret_action("I attack the goblin", "player_1", make_test_state())
    assert action is not None
    assert action.action_type == "attack"
    assert action.target_id == "goblin_1"

def test_spell_interpretation():
    # swap player_1 to a mage so a spell action makes sense
    state = make_test_state()
    state.entities["player_1"] = Entity(
        id="player_1", type="player", role="mage", level=1,
        hp=18, max_hp=18, mp=30, max_mp=30,
        stats=Stats(str=8, dex=10, int=16),
        weapon=Weapon(name="Staff", weapon_type="staff", damage=4),
        items=[],
    )
    mock_response = json.dumps({
        "actor_id": "player_1",
        "action_type": "cast_spell",
        "target_id": "goblin_1",
        "action_name": "fireball",
        "mp_cost": 5,
    })
    with patch("ai_layer._call_openai", return_value=mock_response):
        action = interpret_action("I cast a fire spell at the goblin", "player_1", state)
    assert action is not None
    assert action.action_type == "cast_spell"
    assert action.mp_cost == 5

def test_malformed_json_returns_none():
    # malformed JSON from the API should return None without crashing
    with patch("ai_layer._call_openai", return_value="this is not valid json {{{{"):
        action = interpret_action("I attack the goblin", "player_1", make_test_state())
    assert action is None

def test_unrecognised_action_type_returns_none():
    # the AI returning an unknown action_type is rejected — interpret_action returns None
    mock_response = json.dumps({
        "actor_id": "player_1",
        "action_type": "narrative",
        "target_id": "goblin_1",
        "action_name": "look_around",
        "mp_cost": None,
    })
    with patch("ai_layer._call_openai", return_value=mock_response):
        action = interpret_action("I look around the room", "player_1", make_test_state())
    assert action is None


def test_adventure_outline_valid_5_chapters():
    # a well-formed 5-chapter response should parse into a dict with all required fields
    mock_response = json.dumps({
        "title": "The Cursed Swamp",
        "boss_name": "Swamp Witch",
        "chapter_1_seed": "muddy trail into the swamp",
        "chapter_2_seed": "rotting bridge over dark water",
        "chapter_3_seed": "ancient stone altar covered in moss",
        "chapter_4_seed": "witch's hut surrounded by fog",
        "chapter_5_seed": "final confrontation in the ritual circle",
        "story_flags": {
            "villain_motive": "The witch seeks to flood the kingdom",
            "world_detail": "The sun has not risen in 40 years",
            "recurring_npc": "Mira the cautious",
        },
    })
    with patch("ai_layer._call_openai", return_value=mock_response):
        outline = generate_adventure_outline("A Quest", "cursed swamp", "hard")
    assert outline is not None
    assert outline["title"] == "The Cursed Swamp"
    assert outline["boss_name"] == "Swamp Witch"
    for n in [1, 2, 3, 4, 5]:
        assert f"chapter_{n}_seed" in outline
    assert "villain_motive" in outline["story_flags"]

def test_adventure_outline_missing_chapter_seed_returns_none():
    # a response missing chapter_4_seed should fail validation and return None
    mock_response = json.dumps({
        "title": "Test",
        "boss_name": "Boss",
        "chapter_1_seed": "dark cave",
        "chapter_2_seed": "deeper cave",
        "chapter_3_seed": "boss lair",
        # chapter_4_seed and chapter_5_seed intentionally missing
        "story_flags": {},
    })
    with patch("ai_layer._call_openai", return_value=mock_response):
        outline = generate_adventure_outline("A Quest", "dungeon", "normal")
    assert outline is None
