import sqlite3
import secrets
from contextlib import contextmanager
from game_state import GameState
 
 
#  Configuration 
 
DEFAULT_DB = "quest.db"
 
 
#  Low-level connection helpers 
 
def _connect(path: str) -> sqlite3.Connection:
    
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
 
 
@contextmanager
def _transaction(path: str):
   
    conn = _connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
 
 
def _query(path: str, sql: str, params: tuple = ()) -> list:
    conn = _connect(path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()
 
 
def _query_one(path: str, sql: str, params: tuple = ()):
    conn = _connect(path)
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()
 
 
# Schema 
 
def init_db(path: str = DEFAULT_DB) -> None:
   
    with _transaction(path) as conn:
        # Users — one row per registered account, never modified after creation
        conn.execute()
 
        # GameSessions — one row per game, tracks lifecycle status
        conn.execute()
 
        # SessionPlayers — join table, one row per player per session
        conn.execute()
 
        # GameState — one row per session, overwritten after EVERY resolved action
        # state_json is the full serialized GameState blob from game_state.py
        conn.execute()



# User

def create_user(username: str, password_hash: str,
                path: str = DEFAULT_DB) -> int:
    
    with _transaction(path) as conn:
        cursor = conn.execute(
            (username, password_hash),
        )
        return cursor.lastrowid
    
def get_user_by_username(username: str, path: str = DEFAULT_DB):
    return _query_one(path,(username,)
    )

def get_user_by_id(user_id: int, path: str = DEFAULT_DB):
    return _query_one(path,(user_id,)
    )

# GameSession

def create_session(path: str = DEFAULT_DB) -> tuple:
  
    invite_code = secrets.token_urlsafe(8)   # e.g. "aB3xQ7mZ"
    with _transaction(path) as conn:
        cursor = conn.execute((invite_code,),
        )
        return cursor.lastrowid, invite_code
 
 
def get_session(session_id: int, path: str = DEFAULT_DB):
    return _query_one(path,(session_id,)
    )
 
 
def get_session_by_invite(invite_code: str, path: str = DEFAULT_DB):
    
    return _query_one(path,(invite_code,)
    )
 
 
def set_session_active(session_id: int, path: str = DEFAULT_DB) -> None:
    with _transaction(path) as conn:
        conn.execute((session_id,),
        )
 
 
def end_session(session_id: int, winner, status: str,
                path: str = DEFAULT_DB) -> None:

    with _transaction(path) as conn:
        conn.execute((status, winner, session_id),
        )
 
# SessionPlayers

def add_session_player(session_id: int, user_id: int,
                       character_name: str, role: str,
                       path: str = DEFAULT_DB) -> None:
    
    with _transaction(path) as conn:
        conn.execute((session_id, user_id, character_name, role),
        )
 
 
def count_session_players(session_id: int, path: str = DEFAULT_DB) -> int:
    
    row = _query_one(path,(session_id,)
    )
    return row["n"] if row else 0
 
 
def is_player_in_session(session_id: int, user_id: int,
                         path: str = DEFAULT_DB) -> bool:
   
    row = _query_one(path,(session_id, user_id)
    )
    return row is not None
 
 
def get_session_players(session_id: int, path: str = DEFAULT_DB) -> list:
  
    return _query(path,(session_id,)
    )

# GameState

def save_game_state(session_id: int, state: GameState,path: str = DEFAULT_DB) -> None:
    
    with _transaction(path) as conn:
        conn.execute((session_id, state.to_json()),
        )
 
 
def load_game_state(session_id: int, path: str = DEFAULT_DB):
  
    row = _query_one(path,(session_id,)
    )
    if row is None:
        return None
    return GameState.from_json(row["state_json"])
 
 
def save_state_and_end_session(session_id: int, state: GameState,
                               winner, status: str,
                               path: str = DEFAULT_DB) -> None:

    with _transaction(path) as conn:
        conn.execute((session_id, state.to_json()),
        )
        conn.execute((status, winner, session_id),
        )
 
