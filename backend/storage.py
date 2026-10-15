"""SQLite snapshots, deduplicated events, ownership and feedback; one process."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / 'records.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT, id TEXT, payload TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(kind,id));
                CREATE TABLE IF NOT EXISTS owners (
                    kind TEXT, id TEXT, token_hash TEXT NOT NULL, PRIMARY KEY(kind,id));
                CREATE TABLE IF NOT EXISTS events (
                    event_key TEXT PRIMARY KEY, session_id TEXT, plan_id TEXT,
                    stage TEXT NOT NULL, result TEXT, created_at TEXT NOT NULL, details TEXT);
                CREATE TABLE IF NOT EXISTS feedback (
                    id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, outcome TEXT NOT NULL,
                    stage TEXT NOT NULL, game_version TEXT, detail TEXT, created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS events_plan ON events(plan_id);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.execute('PRAGMA journal_mode=WAL')
            with db:
                yield db
        finally:
            db.close()

    def snapshot(self, kind, identifier, payload):
        with self.connect() as db:
            db.execute('INSERT INTO records VALUES(?,?,?,?) ON CONFLICT(kind,id) DO UPDATE '
                       'SET payload=excluded.payload,updated_at=excluded.updated_at',
                       (kind, identifier, json.dumps(payload, ensure_ascii=False), now()))
        if kind == 'plans':
            self.event(f'plan:{identifier}:{payload["status"]}', payload.get('ai_session'), identifier,
                       'generation' if payload['status'] != 'preview' else 'preview', payload['status'])
        else:
            for item in payload.get('history', []):
                self.event(f'ai:{identifier}:{item["request_id"]}', identifier, None,
                           item.get('kind', 'parse'), 'failed' if item.get('error') else 'succeeded', item)

    def get(self, kind, identifier):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM records WHERE kind=? AND id=?', (kind, identifier)).fetchone()
        return json.loads(row[0]) if row else None

    def event(self, key, session, plan, stage, result, details=None):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?)',
                       (key, session, plan, stage, result, now(), json.dumps(details, ensure_ascii=False)))

    @staticmethod
    def token_hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def claim(self, kind, identifier, token):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO owners VALUES(?,?,?)', (kind, identifier, self.token_hash(token)))

    def allowed(self, kind, identifier, token):
        with self.connect() as db:
            row = db.execute('SELECT token_hash FROM owners WHERE kind=? AND id=?', (kind, identifier)).fetchone()
        return bool(row and row[0] == self.token_hash(token))

    def feedback(self, plan_id, body):
        with self.connect() as db:
            previous = db.execute('SELECT plan_id,outcome,stage,game_version,detail FROM feedback WHERE id=?',
                                  (body['request_id'],)).fetchone()
            values = (plan_id, body['outcome'], body['stage'], body['game_version'], body['detail'])
            if previous and tuple(previous) != values:
                return False
            db.execute('INSERT OR IGNORE INTO feedback VALUES(?,?,?,?,?,?,?)',
                       (body['request_id'], *values, now()))
        return True
