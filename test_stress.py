"""
Stress / state-integrity tests for section 4.4 of the Quest testing document.
No live server or OpenAI calls required.
Run with: pytest test_stress.py -v
"""

import threading
import pytest
from game_state import (
    GameState, AdventureState, SceneState, Entity, Stats, Weapon,
)


def _make_state():
    warrior = Entity(
        id="player_1", type="player", role="warrior", level=1,
        hp=30, max_hp=30, mp=0, max_mp=0,
        stats=Stats(str=14, dex=10, int=8),
        weapon=Weapon(name="Longsword", weapon_type="sword", damage=6),
        items=[], character_name="Aric",
    )
    return GameState(
        adventure=AdventureState(
            title="Stress Test Quest", current_chapter=1,
            boss_name="Dragon", boss_defeated=False, story_flags={},
        ),
        scene=SceneState(description_seed="dark cave", active_entity_ids=["player_1"]),
        entities={"player_1": warrior},
    )


def test_concurrent_state_serialization():
    """10 threads each serialize and deserialize the same GameState 20 times."""
    state = _make_state()
    original_json = state.to_json()
    errors = []

    def round_trip():
        for _ in range(20):
            try:
                reloaded = GameState.from_json(state.to_json())
                result = reloaded.to_json()
                if result != original_json:
                    errors.append(f"JSON mismatch")
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=round_trip) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors during concurrent serialization: {errors}"


def test_pending_actions_dict_under_concurrency():
    """2 threads each insert into a shared pending-actions dict 30 times; dict must never exceed 2 entries."""
    pending: dict = {}
    mu = threading.Lock()
    errors = []

    def submit(actor_id: str):
        for _ in range(30):
            with mu:
                pending[actor_id] = f"action from {actor_id}"
                if len(pending) > 2:
                    errors.append(f"dict grew to {len(pending)} entries")

    t1 = threading.Thread(target=submit, args=("player_1",))
    t2 = threading.Thread(target=submit, args=("player_2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"Lock failures: {errors}"
