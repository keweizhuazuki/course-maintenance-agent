import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "tasks.sqlite3"
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
              id TEXT PRIMARY KEY, title TEXT NOT NULL, original TEXT NOT NULL,
              current TEXT NOT NULL, old_source TEXT NOT NULL, source TEXT NOT NULL,
              source_hash TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
              created REAL NOT NULL, materialized_digest TEXT, active_batch TEXT
            );
            CREATE TABLE IF NOT EXISTS assets (
              run_id TEXT NOT NULL, name TEXT NOT NULL, data BLOB NOT NULL,
              PRIMARY KEY (run_id,name)
            );
            CREATE TABLE IF NOT EXISTS proposals (
              id TEXT PRIMARY KEY, run_id TEXT NOT NULL, target_id TEXT NOT NULL,
              body TEXT NOT NULL, before_value TEXT NOT NULL, source_hash TEXT NOT NULL,
              origin TEXT NOT NULL, status TEXT NOT NULL, errors TEXT NOT NULL,
              resolution TEXT NOT NULL DEFAULT '', created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS batches (
              id TEXT PRIMARY KEY, run_id TEXT NOT NULL, before_value TEXT NOT NULL,
              after_value TEXT, proposal_ids TEXT NOT NULL, status TEXT NOT NULL,
              created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
              type TEXT NOT NULL, details TEXT NOT NULL, created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS exports (
              fingerprint TEXT PRIMARY KEY, run_id TEXT NOT NULL, data BLOB NOT NULL,
              created REAL NOT NULL
            );
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=10000")
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def event(self, db, run_id, kind, details):
        db.execute("INSERT INTO events(run_id,type,details,created) VALUES(?,?,?,?)", (run_id, kind, json.dumps(details,ensure_ascii=False),time.time()))


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
