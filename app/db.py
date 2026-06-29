import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id INTEGER NOT NULL,
  assistant_user_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  deadline TEXT,
  gcal_event_id TEXT,
  expected_result TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS status_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL,
  status TEXT NOT NULL,
  note TEXT,
  ts TEXT NOT NULL,
  FOREIGN KEY(task_id) REFERENCES tasks(id)
);
CREATE TABLE IF NOT EXISTS executors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  telegram_user_id INTEGER NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invites (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  used_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_chat_active
  ON tasks(chat_id, status);
"""

class Db:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path

    @contextmanager
    def _conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def init_schema(self):
        with self._conn() as c:
            c.executescript(SCHEMA)
            # migration: add expected_result to older DBs that predate the column
            cols = [r[1] for r in c.execute("PRAGMA table_info(tasks)").fetchall()]
            if "expected_result" not in cols:
                c.execute("ALTER TABLE tasks ADD COLUMN expected_result TEXT")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_task(self, chat_id, assistant_user_id, title, description,
                    deadline, gcal_event_id, expected_result=None):
        now = self._now()
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO tasks(chat_id, assistant_user_id, title,
                   description, deadline, gcal_event_id, expected_result, status,
                   created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,'pending',?,?)""",
                (chat_id, assistant_user_id, title, description,
                 deadline.isoformat() if deadline else None,
                 gcal_event_id, expected_result, now, now))
            return cur.lastrowid

    def get_task(self, task_id):
        with self._conn() as c:
            row = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            return dict(row) if row else None

    def list_active(self, chat_id):
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM tasks WHERE chat_id=? AND status NOT IN ('done','cancelled') ORDER BY deadline",
                (chat_id,)).fetchall()
            return [dict(r) for r in rows]

    def find_active_for_assistant(self, chat_id, assistant_user_id):
        with self._conn() as c:
            row = c.execute(
                """SELECT * FROM tasks WHERE chat_id=? AND assistant_user_id=?
                   AND status NOT IN ('done','cancelled')
                   ORDER BY updated_at DESC LIMIT 1""",
                (chat_id, assistant_user_id)).fetchone()
            return dict(row) if row else None

    def find_active_for_assistant_any_chat(self, assistant_user_id):
        with self._conn() as c:
            row = c.execute(
                """SELECT * FROM tasks WHERE assistant_user_id=?
                   AND status NOT IN ('done','cancelled')
                   ORDER BY updated_at DESC LIMIT 1""",
                (assistant_user_id,)).fetchone()
            return dict(row) if row else None

    def list_active_for_vitaly(self, vitaly_chat_id):
        with self._conn() as c:
            rows = c.execute(
                """SELECT * FROM tasks WHERE chat_id=?
                   AND status NOT IN ('done','cancelled')
                   ORDER BY deadline""",
                (vitaly_chat_id,)).fetchall()
            return [dict(r) for r in rows]

    def list_all_for_owner(self, chat_id):
        """Every task in the owner's chat regardless of status — used by the
        evening digest, which needs completed tasks too."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM tasks WHERE chat_id=? ORDER BY deadline",
                (chat_id,)).fetchall()
            return [dict(r) for r in rows]

    def update_status(self, task_id, status, note=None):
        now = self._now()
        with self._conn() as c:
            c.execute("UPDATE tasks SET status=?, updated_at=? WHERE id=?",
                     (status, now, task_id))
            c.execute("INSERT INTO status_log(task_id,status,note,ts) VALUES(?,?,?,?)",
                     (task_id, status, note, now))

    def get_status_log(self, task_id):
        with self._conn() as c:
            rows = c.execute("SELECT * FROM status_log WHERE task_id=? ORDER BY ts",
                            (task_id,)).fetchall()
            return [dict(r) for r in rows]

    # --- executors registry -------------------------------------------------

    def add_executor(self, name, telegram_user_id):
        """Register an executor or update the name if the user is already known."""
        now = self._now()
        with self._conn() as c:
            c.execute(
                """INSERT INTO executors(name, telegram_user_id, created_at)
                   VALUES(?,?,?)
                   ON CONFLICT(telegram_user_id) DO UPDATE SET name=excluded.name""",
                (name, telegram_user_id, now))

    def list_executors(self):
        with self._conn() as c:
            rows = c.execute("SELECT * FROM executors ORDER BY name").fetchall()
            return [dict(r) for r in rows]

    def get_executor_by_user_id(self, telegram_user_id):
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM executors WHERE telegram_user_id=?",
                (telegram_user_id,)).fetchone()
            return dict(row) if row else None

    def get_executors_by_name(self, name):
        """Fuzzy name match (case-insensitive substring), used to route a task
        from a voice phrase like 'ответственный — Оля' to a registered executor."""
        q = (name or "").strip().lower()
        if not q:
            return []
        out = []
        with self._conn() as c:
            rows = c.execute("SELECT * FROM executors").fetchall()
        for r in rows:
            nm = r["name"].lower()
            if nm == q or q in nm or nm in q:
                out.append(dict(r))
        return out

    # --- invites (executor self-registration) -------------------------------

    def create_invite(self, token, name):
        now = self._now()
        with self._conn() as c:
            c.execute(
                "INSERT INTO invites(token, name, created_at) VALUES(?,?,?)",
                (token, name, now))

    def get_invite_by_token(self, token):
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM invites WHERE token=?", (token,)).fetchone()
            return dict(row) if row else None

    def mark_invite_used(self, token):
        now = self._now()
        with self._conn() as c:
            c.execute(
                "UPDATE invites SET used_at=? WHERE token=?", (now, token))
