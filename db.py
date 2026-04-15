import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "data/audit.db")


VALID_SERVICES = ("scriberr", "parakeet")


def init_db():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transcriptions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp        TEXT    NOT NULL,
                user_id          INTEGER,
                username         TEXT,
                full_name        TEXT,
                chat_id          INTEGER,
                chat_title       TEXT,
                audio_duration   REAL,
                service          TEXT    NOT NULL,
                status           TEXT    NOT NULL,
                processing_time  REAL,
                error_message    TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        # Seed default service from env (only if not already set)
        default = os.environ.get("TRANSCRIPTION_SERVICE", "scriberr").lower()
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('service', ?)",
            (default,),
        )


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def log_transcription(
    *,
    user_id,
    username,
    full_name,
    chat_id,
    chat_title,
    audio_duration,
    service,
    status,
    processing_time,
    error_message=None,
):
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO transcriptions
              (timestamp, user_id, username, full_name, chat_id, chat_title,
               audio_duration, service, status, processing_time, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                user_id,
                username,
                full_name,
                chat_id,
                chat_title,
                audio_duration,
                service,
                status,
                processing_time,
                error_message,
            ),
        )


def get_logs(limit: int = 50, offset: int = 0) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM transcriptions ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]


def get_setting(key: str, default: str = "") -> str:
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


def get_total_count() -> int:
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM transcriptions").fetchone()[0]


def get_stats() -> dict:
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM transcriptions").fetchone()[0]
        success = conn.execute(
            "SELECT COUNT(*) FROM transcriptions WHERE status = 'success'"
        ).fetchone()[0]
        avg_time = conn.execute(
            "SELECT AVG(processing_time) FROM transcriptions WHERE status = 'success'"
        ).fetchone()[0]
        by_service = conn.execute(
            "SELECT service, COUNT(*) AS cnt FROM transcriptions GROUP BY service"
        ).fetchall()
        return {
            "total": total,
            "success": success,
            "errors": total - success,
            "avg_time": round(avg_time, 1) if avg_time is not None else None,
            "by_service": {r["service"]: r["cnt"] for r in by_service},
        }
