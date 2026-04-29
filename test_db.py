"""
Database unit tests for section 4.2 of the Quest testing document.
Uses a temporary SQLite file per test (via pytest tmp_path) so quest.db is never touched.
Run with: pytest test_db.py -v
"""

import pytest
import sqlite3
import db
from game_state import (
    GameState, AdventureState, SceneState, Entity, Stats, Weapon,
)


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    db.init_db(path=path)
    return path


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
            title="Test Quest", current_chapter=1,
            boss_name="Dragon", boss_defeated=False, story_flags={},
        ),
        scene=SceneState(description_seed="dark cave", active_entity_ids=["player_1"]),
        entities={"player_1": warrior},
    )


def test_create_user(db_path):
    uid = db.create_user("alice", "hash_abc", path=db_path)
    assert isinstance(uid, int) and uid > 0


def test_duplicate_username(db_path):
    db.create_user("bob", "hash1", path=db_path)
    with pytest.raises(sqlite3.IntegrityError):
        db.create_user("bob", "hash2", path=db_path)


def test_login_valid(db_path):
    db.create_user("carol", "secret_hash", path=db_path)
    row = db.get_user_by_username("carol", path=db_path)
    assert row is not None
    assert row["username"] == "carol"
    assert row["password_hash"] == "secret_hash"


def test_login_invalid(db_path):
    row = db.get_user_by_username("nobody", path=db_path)
    assert row is None


def test_save_and_load_game_state(db_path):
    session_id, _ = db.create_session(path=db_path)
    state = _make_state()
    db.save_game_state(session_id, state, path=db_path)
    loaded = db.load_game_state(session_id, path=db_path)
    assert loaded is not None
    assert loaded.adventure.title == "Test Quest"
    assert loaded.scene.active_entity_ids == ["player_1"]
    assert loaded.entities["player_1"].hp == 30
    assert loaded.entities["player_1"].character_name == "Aric"


def test_session_creation(db_path):
    session_id, invite_code = db.create_session(path=db_path)
    assert isinstance(session_id, int) and session_id > 0
    assert isinstance(invite_code, str) and len(invite_code) == 6
    row = db.get_session(session_id, path=db_path)
    assert row["status"] == "waiting"


def test_session_join(db_path):
    uid = db.create_user("dave", "hash_d", path=db_path)
    session_id, _ = db.create_session(path=db_path)
    db.set_session_active(session_id, path=db_path)
    db.add_session_player(session_id, uid, "Sir Dave", "warrior", path=db_path)
    row = db.get_session(session_id, path=db_path)
    assert row["status"] == "active"
    assert db.is_player_in_session(session_id, uid, path=db_path)
