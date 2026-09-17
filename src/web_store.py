"""Persistent storage for the hosted product (Postgres; SQLite for local tests only)."""

from contextlib import contextmanager
import os
import sqlite3
import threading


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS br_web_users (
        id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'USER',
        is_active INTEGER NOT NULL DEFAULT 1, created_at DOUBLE PRECISION NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS br_web_sessions (
        token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES br_web_users(id),
        csrf_token TEXT NOT NULL, expires_at DOUBLE PRECISION NOT NULL,
        created_at DOUBLE PRECISION NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS br_web_scans (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES br_web_users(id),
        barcode_type TEXT NOT NULL, barcode_data TEXT NOT NULL, source TEXT NOT NULL,
        image_name TEXT NOT NULL, validation_status TEXT NOT NULL,
        processing_time_ms DOUBLE PRECISION NOT NULL, created_at DOUBLE PRECISION NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS br_web_scans_owner ON br_web_scans(user_id, created_at)",
    """CREATE TABLE IF NOT EXISTS br_web_audit (
        id TEXT PRIMARY KEY, user_id TEXT, username TEXT NOT NULL, action TEXT NOT NULL,
        details TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS br_web_attempts (
        identifier TEXT PRIMARY KEY, failures INTEGER NOT NULL,
        blocked_until DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS br_web_products (
        barcode TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS br_web_settings (
        name TEXT PRIMARY KEY, value TEXT NOT NULL)""",
]


class LocalConnection:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        return self.conn.execute(sql.replace('%s', '?'), params)


class WebStore:
    def __init__(self):
        self._ready = False
        self._lock = threading.Lock()

    @property
    def configured(self):
        return bool(os.getenv('DATABASE_URL') or (not os.getenv('VERCEL') and os.getenv('WEB_DATABASE_PATH')))

    @contextmanager
    def raw_connection(self):
        url = os.getenv('DATABASE_URL')
        if url:
            import psycopg
            from psycopg.rows import dict_row
            conn = psycopg.connect(url, row_factory=dict_row, connect_timeout=10)
            try:
                with conn:
                    yield conn
            finally:
                conn.close()
        elif not os.getenv('VERCEL') and os.getenv('WEB_DATABASE_PATH'):
            conn = sqlite3.connect(os.environ['WEB_DATABASE_PATH'], timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA foreign_keys = ON')
            try:
                with conn:
                    yield LocalConnection(conn)
            finally:
                conn.close()
        else:
            raise RuntimeError('Cloud database is not configured')

    def initialize(self):
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            with self.raw_connection() as conn:
                for sql in SCHEMA:
                    conn.execute(sql)
                # Serialize admin changes and one-time administrator setup across instances.
                conn.execute("INSERT INTO br_web_settings(name, value) VALUES ('admin_lock', '0') ON CONFLICT(name) DO NOTHING")
            self._ready = True

    @contextmanager
    def connection(self):
        self.initialize()
        with self.raw_connection() as conn:
            yield conn


store = WebStore()
