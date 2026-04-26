import sqlite3
import secrets
from contextlib import contextmanager
from game_state import GameState

# Configuration 
DEFAULT_DB = "quest.db"

# Low-level connection helpers 
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS Users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )""")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS GameSessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invite_code TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'waiting',
                winner TEXT,
                theme TEXT NOT NULL DEFAULT 'dungeon',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )""")

        conn.execute(""" 
            CREATE TABLE IF NOT EXISTS SessionPlayers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL REFERENCES GameSessions(id),
                user_id INTEGER NOT NULL REFERENCES Users(id),
                character_name TEXT NOT NULL,
                role TEXT NOT NULL,
                joined_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(session_id, user_id)
            )""")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS GameState (
                session_id INTEGER PRIMARY KEY REFERENCES GameSessions(id),
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )""")

# --- User Functions ---

def create_user(username: str, password_hash: str, email: str = "", path: str = DEFAULT_DB) -> int:
    with _transaction(path) as conn:
        cursor = conn.execute(
            "INSERT INTO Users (username, password_hash, email) VALUES (?, ?, ?)",
            (username, password_hash, email)
        )
        return cursor.lastrowid
    
def get_user_by_username(username: str, path: str = DEFAULT_DB):
    return _query_one(path, "SELECT * FROM Users WHERE username = ?", (username,))

def get_user_by_id(user_id: int, path: str = DEFAULT_DB):
    return _query_one(path, "SELECT * FROM Users WHERE id = ?", (user_id,))

# --- GameSession Functions ---

def create_session(path: str = DEFAULT_DB) -> tuple:
    # Unambiguous uppercase alphanumeric — no O/0, I/1/L confusion
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    invite_code = "".join(secrets.choice(alphabet) for _ in range(6))
    with _transaction(path) as conn:
        cursor = conn.execute(
            "INSERT INTO GameSessions (invite_code) VALUES (?)", 
            (invite_code,)
        )
        return cursor.lastrowid, invite_code

def get_session(session_id: int, path: str = DEFAULT_DB):
    return _query_one(path, "SELECT * FROM GameSessions WHERE id = ?", (session_id,))

def get_session_by_invite(invite_code: str, path: str = DEFAULT_DB):
    return _query_one(path, "SELECT * FROM GameSessions WHERE invite_code = ?", (invite_code,))

def set_session_active(session_id: int, path: str = DEFAULT_DB) -> None:
    with _transaction(path) as conn:
        conn.execute("UPDATE GameSessions SET status = 'active' WHERE id = ?", (session_id,))

def end_session(session_id: int, winner, status: str, path: str = DEFAULT_DB) -> None:
    with _transaction(path) as conn:
        conn.execute(
            "UPDATE GameSessions SET status = ?, winner = ? WHERE id = ?", 
            (status, winner, session_id)
        )

# --- SessionPlayers Functions ---

def add_session_player(session_id: int, user_id: int, character_name: str, role: str, path: str = DEFAULT_DB) -> None:
    with _transaction(path) as conn:
        conn.execute(
            "INSERT INTO SessionPlayers (session_id, user_id, character_name, role) VALUES (?, ?, ?, ?)", 
            (session_id, user_id, character_name, role)
        )

def count_session_players(session_id: int, path: str = DEFAULT_DB) -> int:
    row = _query_one(path, "SELECT COUNT(*) as n FROM SessionPlayers WHERE session_id = ?", (session_id,))
    return row["n"] if row else 0

def is_player_in_session(session_id: int, user_id: int, path: str = DEFAULT_DB) -> bool:
    row = _query_one(path, "SELECT 1 FROM SessionPlayers WHERE session_id = ? AND user_id = ?", (session_id, user_id))
    return row is not None

def get_session_players(session_id: int, path: str = DEFAULT_DB) -> list:
    return _query(path, "SELECT * FROM SessionPlayers WHERE session_id = ?", (session_id,))

# --- GameState Functions ---

def save_game_state(session_id: int, state: GameState, path: str = DEFAULT_DB) -> None:
    with _transaction(path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO GameState (session_id, state_json, updated_at) VALUES (?, ?, datetime('now'))", 
            (session_id, state.to_json())
        )

def load_game_state(session_id: int, path: str = DEFAULT_DB):
    row = _query_one(path, "SELECT state_json FROM GameState WHERE session_id = ?", (session_id,))
    if row is None:
        return None
    return GameState.from_json(row["state_json"])

def save_state_and_end_session(session_id: int, state: GameState, winner, status: str, path: str = DEFAULT_DB) -> None:
    with _transaction(path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO GameState (session_id, state_json, updated_at) VALUES (?, ?, datetime('now'))", 
            (session_id, state.to_json())
        )
        conn.execute(
            "UPDATE GameSessions SET status = ?, winner = ? WHERE id = ?", 
            (status, winner, session_id)
        )
        
   # --- Saved Adventures (resume) Functions ---

    def get_user_sessions(user_id: int, path: str = DEFAULT_DB) -> list:
        """Return all sessions the user participated in that have a saved game state,
        ordered by most recently updated."""
        return _query(path, """
        SELECT
            gs.id            AS session_id,
            gs.status,
            gs.theme,
            gs.created_at,
            gs.invite_code,
            sp.character_name,
            sp.role,
            gst.updated_at   AS last_saved,
            gst.state_json
        FROM SessionPlayers sp
        JOIN GameSessions gs  ON gs.id = sp.session_id
        LEFT JOIN GameState gst ON gst.session_id = gs.id
        WHERE sp.user_id = ?
        ORDER BY COALESCE(gst.updated_at, gs.created_at) DESC
        LIMIT 20
    """, (user_id,))