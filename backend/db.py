"""
SQLite storage for tokens, imported playlists, and sync state.

Single-file DB, no ORM -- this is a personal-use tool, not a multi-tenant
service. Everything is keyed by a `user_id` string so the schema still
works if you ever want multiple users.
"""
import sqlite3
import json
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "app.db"


def init_db():
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tokens (
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,      -- 'ytmusic'
                token_json TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (user_id, provider)
            );

            CREATE TABLE IF NOT EXISTS playlist_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                source_name TEXT NOT NULL,       -- playlist name, from the CSV import
                ytmusic_playlist_id TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(user_id, source_name)
            );

            CREATE TABLE IF NOT EXISTS tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                album TEXT,
                duration_ms INTEGER,
                FOREIGN KEY(link_id) REFERENCES playlist_links(id)
            );

            CREATE TABLE IF NOT EXISTS sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link_id INTEGER NOT NULL,
                started_at REAL NOT NULL,
                finished_at REAL,
                status TEXT NOT NULL,        -- 'running' | 'done' | 'error'
                added INTEGER DEFAULT 0,
                skipped INTEGER DEFAULT 0,
                errors TEXT,                 -- JSON list of {track, reason}
                FOREIGN KEY(link_id) REFERENCES playlist_links(id)
            );
            """
        )
        # Migrate existing tracks table if duration_ms column is missing
        track_cols = [r["name"] for r in conn.execute("PRAGMA table_info(tracks)").fetchall()]
        if "duration_ms" not in track_cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN duration_ms INTEGER")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---- tokens (YT Music only now) ----

def save_token(user_id: str, provider: str, token: dict):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO tokens (user_id, provider, token_json, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, provider) DO UPDATE SET
                   token_json=excluded.token_json, updated_at=excluded.updated_at""",
            (user_id, provider, json.dumps(token), time.time()),
        )


def get_token(user_id: str, provider: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT token_json FROM tokens WHERE user_id=? AND provider=?",
            (user_id, provider),
        ).fetchone()
        return json.loads(row["token_json"]) if row else None


# ---- playlist links + tracks ----

def upsert_link(user_id: str, source_name: str) -> int:
    """Creates the link if new, or just bumps updated_at if it already exists
    (tracks are replaced separately via replace_tracks)."""
    with get_conn() as conn:
        now = time.time()
        conn.execute(
            """INSERT INTO playlist_links (user_id, source_name, created_at, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, source_name) DO UPDATE SET updated_at=excluded.updated_at""",
            (user_id, source_name, now, now),
        )
        row = conn.execute(
            "SELECT id FROM playlist_links WHERE user_id=? AND source_name=?",
            (user_id, source_name),
        ).fetchone()
        return row["id"]


def set_ytmusic_playlist_id(link_id: int, ytmusic_playlist_id: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE playlist_links SET ytmusic_playlist_id=? WHERE id=?",
            (ytmusic_playlist_id, link_id),
        )


def replace_tracks(link_id: int, tracks: list[dict]):
    """Wipes and reinserts tracks for a link -- used every time a CSV is (re)imported."""
    with get_conn() as conn:
        conn.execute("DELETE FROM tracks WHERE link_id=?", (link_id,))
        conn.executemany(
            "INSERT INTO tracks (link_id, position, title, artist, album, duration_ms) VALUES (?, ?, ?, ?, ?, ?)",
            [(link_id, i, t["title"], t["artist"], t.get("album", ""), t.get("duration_ms")) for i, t in enumerate(tracks)],
        )


def get_tracks(link_id: int) -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT title, artist, album, duration_ms FROM tracks WHERE link_id=? ORDER BY position", (link_id,)
        ).fetchall()]


def get_links(user_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT l.*, COUNT(t.id) as track_count
               FROM playlist_links l LEFT JOIN tracks t ON t.link_id = l.id
               WHERE l.user_id=? GROUP BY l.id ORDER BY l.updated_at DESC""",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_link(link_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM playlist_links WHERE id=?", (link_id,)).fetchone()
        return dict(row) if row else None


# ---- sync runs ----

def start_run(link_id: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO sync_runs (link_id, started_at, status) VALUES (?, ?, 'running')",
            (link_id, time.time()),
        )
        return cur.lastrowid


def finish_run(run_id: int, status: str, added: int, skipped: int, errors: list):
    with get_conn() as conn:
        conn.execute(
            """UPDATE sync_runs SET finished_at=?, status=?, added=?, skipped=?, errors=?
               WHERE id=?""",
            (time.time(), status, added, skipped, json.dumps(errors), run_id),
        )


def get_runs_for_link(link_id: int):
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM sync_runs WHERE link_id=? ORDER BY started_at DESC", (link_id,)
        ).fetchall()]
