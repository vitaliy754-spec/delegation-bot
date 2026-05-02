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

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_task(self, chat_id, assistant_user_id, title, description,
                    deadline, gcal_event_id):
        now = self._now()
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO tasks(chat_id, assistant_user_id, title,
                   description, deadline, gcal_event_id, status,
                   created_at, updated_at)
                   VALUES (?,?,?,?,?,?,'pending',?,?)""",
                (chat_id, assistant_user_id, title, description,
                 deadline.isoformat() if deadline else None,
                 gcal_event_id, now, now))
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
