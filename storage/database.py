import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional, Union

logger = logging.getLogger("parqueame.storage.database")

DEFAULT_DB_PATH = Path("storage/parqueame.db")

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS camera_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    inference_time_ms REAL NOT NULL,
    total_spots INTEGER NOT NULL,
    occupied_spots INTEGER NOT NULL,
    battery_percentage REAL,
    battery_voltage REAL,
    image_path TEXT
);

CREATE TABLE IF NOT EXISTS spot_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id INTEGER NOT NULL REFERENCES camera_logs(id) ON DELETE CASCADE,
    camera_id TEXT NOT NULL,
    spot_id TEXT NOT NULL,
    is_occupied INTEGER NOT NULL CHECK (is_occupied IN (0, 1)),
    confidence REAL NOT NULL,
    timestamp REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_sessions (
    token TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    expires_at REAL NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_camera_logs_cam_time ON camera_logs(camera_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_spot_history_spot_time ON spot_history(camera_id, spot_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_spot_history_log ON spot_history(log_id);
CREATE INDEX IF NOT EXISTS idx_admin_sessions_exp ON admin_sessions(expires_at);
"""

SCHEMA_PG_SQL = """
CREATE TABLE IF NOT EXISTS camera_logs (
    id SERIAL PRIMARY KEY,
    camera_id VARCHAR(64) NOT NULL,
    timestamp DOUBLE PRECISION NOT NULL,
    inference_time_ms REAL NOT NULL,
    total_spots INT NOT NULL,
    occupied_spots INT NOT NULL,
    battery_percentage REAL,
    battery_voltage REAL,
    image_path TEXT
);

CREATE TABLE IF NOT EXISTS spot_history (
    id SERIAL PRIMARY KEY,
    log_id INT REFERENCES camera_logs(id) ON DELETE CASCADE,
    camera_id VARCHAR(64) NOT NULL,
    spot_id VARCHAR(64) NOT NULL,
    is_occupied INT NOT NULL,
    confidence REAL NOT NULL,
    timestamp DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_sessions (
    token VARCHAR(128) PRIMARY KEY,
    username VARCHAR(64) NOT NULL,
    expires_at DOUBLE PRECISION NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_camera_logs_cam_time ON camera_logs(camera_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_spot_history_spot_time ON spot_history(camera_id, spot_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_spot_history_log ON spot_history(log_id);
CREATE INDEX IF NOT EXISTS idx_admin_sessions_exp ON admin_sessions(expires_at);
"""


def is_postgres_configured() -> bool:
    db_url = os.getenv("DATABASE_URL", "").strip()
    return db_url.startswith("postgresql://") or db_url.startswith("postgres://")


class CursorWrapper:
    def __init__(self, raw_cursor: Any, is_postgres: bool):
        self._cursor = raw_cursor
        self.is_postgres = is_postgres
        self._last_id = None

    def execute(self, query: str, params: Optional[Union[tuple, list]] = None):
        if self.is_postgres:
            q = query.replace("?", "%s")
            if "INSERT OR REPLACE INTO admin_sessions" in q:
                q = (
                    "INSERT INTO admin_sessions (token, username, expires_at, created_at) "
                    "VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (token) DO UPDATE SET "
                    "username = EXCLUDED.username, expires_at = EXCLUDED.expires_at, created_at = EXCLUDED.created_at;"
                )
            if "INSERT INTO camera_logs" in q and "RETURNING" not in q:
                q = q.rstrip("; \n\t") + " RETURNING id;"
                self._cursor.execute(q, params or ())
                row = self._cursor.fetchone()
                if row:
                    self._last_id = row[0] if isinstance(row, (tuple, list)) else row.get("id")
                return self

            self._cursor.execute(q, params or ())
        else:
            self._cursor.execute(query, params or ())
        return self

    def executemany(self, query: str, seq_of_params):
        if self.is_postgres:
            q = query.replace("?", "%s")
            self._cursor.executemany(q, seq_of_params)
        else:
            self._cursor.executemany(query, seq_of_params)
        return self

    @property
    def lastrowid(self):
        if self.is_postgres:
            return self._last_id
        return self._cursor.lastrowid

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class DBConnectionWrapper:
    def __init__(self, raw_conn: Any, is_postgres: bool):
        self._conn = raw_conn
        self.is_postgres = is_postgres

    def cursor(self):
        return CursorWrapper(self._conn.cursor(), self.is_postgres)

    def execute(self, query: str, params: Optional[Union[tuple, list]] = None):
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        if hasattr(self._conn, "rollback"):
            self._conn.rollback()

    def close(self):
        self._conn.close()


def init_db(db_path: Optional[Union[str, Path]] = None) -> None:
    """Initializes the database schema for either PostgreSQL (Neon) or local SQLite."""
    if is_postgres_configured() and db_path is None:
        db_url = os.getenv("DATABASE_URL", "").strip()
        import psycopg2
        logger.info("Initializing Neon PostgreSQL database schema...")
        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_PG_SQL)
            conn.commit()
            logger.info("Neon PostgreSQL schema initialized successfully with indexes.")
        finally:
            conn.close()
        return

    # SQLite local mode
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Initializing SQLite database at: {path}")
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        logger.info("SQLite schema initialized successfully with WAL mode and indexes.")
    finally:
        conn.close()


@contextmanager
def get_db_connection(
    db_path: Optional[Union[str, Path]] = None,
) -> Generator[DBConnectionWrapper, None, None]:
    """Context manager providing managed database connections for PostgreSQL or SQLite."""
    if is_postgres_configured() and db_path is None:
        db_url = os.getenv("DATABASE_URL", "").strip()
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        wrapper = DBConnectionWrapper(conn, is_postgres=True)
        try:
            yield wrapper
            wrapper.commit()
        except Exception as e:
            wrapper.rollback()
            logger.error(f"PostgreSQL database transaction error: {e}")
            raise
        finally:
            wrapper.close()
        return

    # SQLite local fallback
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    path = Path(db_path)
    if not path.exists():
        init_db(path)

    raw_conn = sqlite3.connect(str(path), timeout=10.0)
    raw_conn.row_factory = sqlite3.Row
    raw_conn.execute("PRAGMA foreign_keys = ON;")
    wrapper = DBConnectionWrapper(raw_conn, is_postgres=False)
    try:
        yield wrapper
        wrapper.commit()
    except Exception as e:
        wrapper.rollback()
        logger.error(f"SQLite transaction error: {e}")
        raise
    finally:
        wrapper.close()
