# Delegation Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Telegram-бот для делегирования задач одному исполнителю с дедлайнами в Google Calendar и напоминаниями по голосовому расписанию.

**Architecture:** Single Python service на Railway. python-telegram-bot long-polling, OpenAI Whisper+GPT-4o-mini, Google Calendar API, SQLite + APScheduler с persistent jobstore.

**Tech Stack:** Python 3.11, python-telegram-bot 21, openai 1.50+, google-api-python-client, APScheduler 3.10, SQLAlchemy (для jobstore), pydantic 2, aiohttp (healthcheck), Railway.

---

## File Structure

```
delegation-bot/
├── app/
│   ├── __init__.py
│   ├── main.py            # entrypoint
│   ├── config.py          # env vars
│   ├── bot.py             # telegram handlers
│   ├── transcribe.py      # whisper wrapper
│   ├── parser.py          # task parser (LLM + pydantic)
│   ├── intent.py          # status intent classifier
│   ├── gcal.py            # google calendar client
│   ├── db.py              # sqlite repo
│   ├── scheduler.py       # apscheduler + reminder jobs
│   └── health.py          # aiohttp /health
├── tests/
│   ├── test_parser.py
│   ├── test_intent.py
│   ├── test_db.py
│   └── test_scheduler.py
├── scripts/
│   └── gcal_oauth.py      # one-time OAuth bootstrap
├── .env.example
├── pyproject.toml
├── railway.toml
└── README.md
```

---

### Task 1: Project setup

**Files:**
- Create: `pyproject.toml`, `.env.example`, `.gitignore`, `app/__init__.py`, `app/config.py`, `tests/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "delegation-bot"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "python-telegram-bot==21.6",
  "openai>=1.50",
  "google-api-python-client>=2.140",
  "google-auth-oauthlib>=1.2",
  "apscheduler==3.10.4",
  "sqlalchemy>=2.0",
  "pydantic>=2.8",
  "aiohttp>=3.10",
  "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "freezegun>=1.5"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: Create .env.example**

```
TELEGRAM_BOT_TOKEN=
OPENAI_API_KEY=
GOOGLE_CALENDAR_ID=
GOOGLE_CREDENTIALS_PATH=./data/credentials.json
GOOGLE_TOKEN_PATH=./data/token.json
ALLOWED_CHAT_ID=
VITALY_USER_ID=
ASSISTANT_USER_ID=
DB_PATH=./data/bot.db
TZ=Europe/Kyiv
```

- [ ] **Step 3: Create .gitignore**

```
.venv/
__pycache__/
*.pyc
.env
data/
*.db
token.json
credentials.json
```

- [ ] **Step 4: Create app/config.py**

```python
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
GOOGLE_CALENDAR_ID = os.environ["GOOGLE_CALENDAR_ID"]
GOOGLE_CREDENTIALS_PATH = os.environ["GOOGLE_CREDENTIALS_PATH"]
GOOGLE_TOKEN_PATH = os.environ["GOOGLE_TOKEN_PATH"]
ALLOWED_CHAT_ID = int(os.environ["ALLOWED_CHAT_ID"])
VITALY_USER_ID = int(os.environ["VITALY_USER_ID"])
ASSISTANT_USER_ID = int(os.environ["ASSISTANT_USER_ID"])
DB_PATH = os.environ["DB_PATH"]
TZ = os.environ.get("TZ", "Europe/Kyiv")
```

- [ ] **Step 5: Install and verify**

Run: `pip install -e ".[dev]"`
Run: `python -c "import app.config"` (after filling .env from .env.example with dummy values)
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git init
git add .
git commit -m "feat: project scaffold and config"
```

---

### Task 2: Pydantic schemas

**Files:**
- Create: `app/schemas.py`, `tests/test_schemas.py`

- [ ] **Step 1: Write failing test** — `tests/test_schemas.py`

```python
from datetime import datetime, timezone
from app.schemas import TaskSpec, Reminder

def test_taskspec_minimal():
    t = TaskSpec(
        title="Лендинг",
        description="Сделать лендинг",
        deadline=datetime(2026, 5, 3, 18, 0, tzinfo=timezone.utc),
        reminders=[],
    )
    assert t.title == "Лендинг"

def test_reminder_requires_when():
    r = Reminder(when=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc))
    assert r.text is None
```

- [ ] **Step 2: Run** — `pytest tests/test_schemas.py -v` → FAIL (no module)

- [ ] **Step 3: Implement** — `app/schemas.py`

```python
from datetime import datetime
from pydantic import BaseModel, Field

class Reminder(BaseModel):
    when: datetime
    text: str | None = None

class TaskSpec(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    description: str
    deadline: datetime | None = None
    reminders: list[Reminder] = []
```

- [ ] **Step 4: Run** — `pytest tests/test_schemas.py -v` → PASS

- [ ] **Step 5: Commit** — `git add . && git commit -m "feat: TaskSpec/Reminder schemas"`

---

### Task 3: SQLite repo

**Files:**
- Create: `app/db.py`, `tests/test_db.py`

- [ ] **Step 1: Write failing test**

```python
import tempfile, os
from datetime import datetime, timezone
from app.db import Db

def test_create_and_get_task():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        db = Db(path)
        db.init_schema()
        tid = db.create_task(
            chat_id=1, assistant_user_id=2,
            title="t", description="d",
            deadline=datetime(2026,5,3,18,0,tzinfo=timezone.utc),
            gcal_event_id="evt1",
        )
        task = db.get_task(tid)
        assert task["title"] == "t"
        assert task["status"] == "pending"

def test_update_status_logs():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = Db(path); db.init_schema()
    tid = db.create_task(chat_id=1, assistant_user_id=2, title="t",
                        description="d", deadline=None, gcal_event_id="e")
    db.update_status(tid, "in_progress", note="делаю")
    log = db.get_status_log(tid)
    assert log[-1]["status"] == "in_progress"
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement** — `app/db.py`

```python
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
```

- [ ] **Step 4: Run** — `pytest tests/test_db.py -v` → PASS

- [ ] **Step 5: Commit** — `git add . && git commit -m "feat: SQLite tasks repo"`

---

### Task 4: LLM task parser

**Files:**
- Create: `app/parser.py`, `tests/test_parser.py`

- [ ] **Step 1: Write failing test** (using mock OpenAI client)

```python
from unittest.mock import MagicMock
from datetime import datetime, timezone
from app.parser import parse_task
import json

def test_parse_task_basic():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({
            "title": "Лендинг",
            "description": "Сделать лендинг до завтра 18:00",
            "deadline": "2026-05-03T18:00:00+03:00",
            "reminders": [{"when": "2026-05-02T20:00:00+03:00", "text": None}],
        })))]
    )
    spec = parse_task(
        client=mock_client,
        transcript="Сделай лендинг до завтра 18:00, напомни сегодня в 20:00",
        now=datetime(2026,5,2,15,0,tzinfo=timezone.utc),
        tz="Europe/Kyiv",
    )
    assert spec.title == "Лендинг"
    assert len(spec.reminders) == 1
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement** — `app/parser.py`

```python
import json
from datetime import datetime
from app.schemas import TaskSpec

SYSTEM_PROMPT = """Ты парсер голосовых задач. Из транскрипта вытащи:
- title: короткое название задачи (3-7 слов, без точки)
- description: полное описание что нужно сделать
- deadline: ISO 8601 datetime с таймзоной, или null если не указан
- reminders: список {when: ISO datetime, text: null} — времена когда напомнить исполнителю

Все даты интерпретируй относительно current_time и пользовательской таймзоны.
"Сегодня в 20:00" = сегодняшняя дата + 20:00 в таймзоне пользователя.
"Завтра до 18:00" = deadline = завтра 18:00.
"К концу дня" = 23:59 указанного дня.
Если в речи нет дедлайна — deadline=null.
Если в речи нет явных напоминаний — reminders=[].

Верни ТОЛЬКО JSON без markdown."""

def parse_task(client, transcript: str, now: datetime, tz: str) -> TaskSpec:
    user_msg = f"current_time={now.isoformat()}\ntimezone={tz}\ntranscript=\"{transcript}\""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    data = json.loads(resp.choices[0].message.content)
    return TaskSpec.model_validate(data)
```

- [ ] **Step 4: Run** — PASS

- [ ] **Step 5: Commit** — `git add . && git commit -m "feat: LLM task parser"`

---

### Task 5: Whisper transcription

**Files:**
- Create: `app/transcribe.py`, `tests/test_transcribe.py`

- [ ] **Step 1: Write failing test**

```python
from unittest.mock import MagicMock
from app.transcribe import transcribe_voice

def test_transcribe(tmp_path):
    audio = tmp_path / "v.ogg"
    audio.write_bytes(b"fake")
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = MagicMock(text="Привет")
    text = transcribe_voice(mock_client, str(audio))
    assert text == "Привет"
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement** — `app/transcribe.py`

```python
def transcribe_voice(client, audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="ru",
        )
    return resp.text.strip()
```

- [ ] **Step 4: Run** — PASS

- [ ] **Step 5: Commit** — `git add . && git commit -m "feat: whisper transcription"`

---

### Task 6: Intent classifier

**Files:**
- Create: `app/intent.py`, `tests/test_intent.py`

- [ ] **Step 1: Write failing test**

```python
from unittest.mock import MagicMock
from app.intent import classify_status
import json

def test_classify_done():
    mock = MagicMock()
    mock.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps(
            {"intent":"done","note":"закрыл задачу"})))]
    )
    res = classify_status(mock, "Сделал, всё готово", task_title="Лендинг")
    assert res["intent"] == "done"
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement** — `app/intent.py`

```python
import json

INTENT_PROMPT = """Классифицируй ответ исполнителя по задаче "{title}":
- done: завершено ("сделал", "готово", "закрыл")
- in_progress: в работе ("делаю", "к вечеру", "почти")
- blocked: затык ("застрял", "не могу", "нужна инфа")
- other: не статус (мелкий вопрос, болтовня)

Верни JSON: {{"intent": "...", "note": "краткая суть ответа"}}"""

def classify_status(client, message: str, task_title: str) -> dict:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role":"system","content":INTENT_PROMPT.format(title=task_title)},
            {"role":"user","content":message},
        ],
        response_format={"type":"json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)
```

- [ ] **Step 4: Run** — PASS

- [ ] **Step 5: Commit** — `git add . && git commit -m "feat: intent classifier"`

---

### Task 7: Google Calendar OAuth bootstrap

**Files:**
- Create: `scripts/gcal_oauth.py`

- [ ] **Step 1: Implement bootstrap script**

```python
"""One-time OAuth flow. Run locally:
   python scripts/gcal_oauth.py
   Then upload data/token.json to Railway volume."""
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def main():
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", "data/credentials.json")
    token_path = os.environ.get("GOOGLE_TOKEN_PATH", "data/token.json")
    flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
    creds = flow.run_local_server(port=0)
    os.makedirs(os.path.dirname(token_path), exist_ok=True)
    with open(token_path, "w") as f:
        f.write(creds.to_json())
    print(f"Saved token to {token_path}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Document in README**

Create `README.md` with section:
```markdown
## Google Calendar setup
1. Создать OAuth client (Desktop app) в Google Cloud Console
2. Скачать credentials.json в `data/credentials.json`
3. Запустить `python scripts/gcal_oauth.py` — откроется браузер
4. Залогиниться, разрешить доступ → создастся `data/token.json`
5. Загрузить `data/token.json` и `data/credentials.json` в Railway volume `/data`
```

- [ ] **Step 3: Commit** — `git add . && git commit -m "feat: gcal oauth bootstrap"`

---

### Task 8: Google Calendar client

**Files:**
- Create: `app/gcal.py`, `tests/test_gcal.py`

- [ ] **Step 1: Write failing test**

```python
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from app.gcal import GCalClient

def test_create_event_calls_api():
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {"id": "evt123"}
    with patch("app.gcal.build", return_value=fake_service), \
         patch("app.gcal.GCalClient._creds", return_value=MagicMock()):
        c = GCalClient(calendar_id="cal", token_path="t", credentials_path="c")
        eid = c.create_event(
            title="T", description="D",
            start=datetime(2026,5,3,17,0,tzinfo=timezone.utc),
            end=datetime(2026,5,3,18,0,tzinfo=timezone.utc),
        )
    assert eid == "evt123"
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement** — `app/gcal.py`

```python
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]

class GCalClient:
    def __init__(self, calendar_id, token_path, credentials_path):
        self.calendar_id = calendar_id
        self.token_path = token_path
        self.credentials_path = credentials_path
        self.service = build("calendar", "v3", credentials=self._creds())

    def _creds(self):
        creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        if not creds.valid and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(self.token_path, "w") as f:
                f.write(creds.to_json())
        return creds

    def create_event(self, title, description, start: datetime, end: datetime = None):
        end = end or (start + timedelta(minutes=30))
        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start.isoformat()},
            "end":   {"dateTime": end.isoformat()},
        }
        evt = self.service.events().insert(calendarId=self.calendar_id, body=body).execute()
        return evt["id"]

    def append_to_description(self, event_id, line: str):
        evt = self.service.events().get(calendarId=self.calendar_id, eventId=event_id).execute()
        desc = (evt.get("description") or "") + "\n" + line
        self.service.events().patch(
            calendarId=self.calendar_id, eventId=event_id,
            body={"description": desc}).execute()

    def update_summary(self, event_id, prefix: str):
        evt = self.service.events().get(calendarId=self.calendar_id, eventId=event_id).execute()
        title = evt.get("summary", "")
        if not title.startswith(prefix):
            self.service.events().patch(
                calendarId=self.calendar_id, eventId=event_id,
                body={"summary": f"{prefix}{title}"}).execute()
```

- [ ] **Step 4: Run** — PASS

- [ ] **Step 5: Commit** — `git add . && git commit -m "feat: google calendar client"`

---

### Task 9: APScheduler setup

**Files:**
- Create: `app/scheduler.py`, `tests/test_scheduler.py`

- [ ] **Step 1: Write failing test**

```python
import asyncio
from datetime import datetime, timezone, timedelta
from app.scheduler import Scheduler

def test_schedule_and_list(tmp_path):
    db_url = f"sqlite:///{tmp_path/'jobs.db'}"
    s = Scheduler(db_url=db_url, tz="UTC")
    s.start()
    when = datetime.now(timezone.utc) + timedelta(hours=1)
    job_id = s.schedule_reminder(task_id=1, when=when, kind="reminder")
    jobs = s.list_jobs_for_task(1)
    assert len(jobs) == 1
    s.shutdown()
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement** — `app/scheduler.py`

```python
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.date import DateTrigger

# Job callback registered at runtime via set_callback
_callback = None

def _fire(task_id: int, kind: str):
    if _callback:
        _callback(task_id, kind)

class Scheduler:
    def __init__(self, db_url: str, tz: str):
        self.scheduler = AsyncIOScheduler(
            jobstores={"default": SQLAlchemyJobStore(url=db_url)},
            timezone=tz,
        )

    def start(self):
        self.scheduler.start()

    def shutdown(self):
        self.scheduler.shutdown(wait=False)

    def set_callback(self, fn):
        global _callback
        _callback = fn

    def schedule_reminder(self, task_id: int, when: datetime, kind: str) -> str:
        jid = f"task{task_id}-{kind}-{int(when.timestamp())}"
        self.scheduler.add_job(
            _fire, DateTrigger(run_date=when),
            args=[task_id, kind],
            id=jid, replace_existing=True,
        )
        return jid

    def list_jobs_for_task(self, task_id: int):
        return [j for j in self.scheduler.get_jobs()
                if j.id.startswith(f"task{task_id}-")]

    def cancel_task_jobs(self, task_id: int):
        for j in self.list_jobs_for_task(task_id):
            j.remove()
```

- [ ] **Step 4: Run** — PASS

- [ ] **Step 5: Commit** — `git add . && git commit -m "feat: persistent scheduler"`

---

### Task 10: Telegram bot — voice intake + parsing flow

**Files:**
- Create: `app/bot.py` (skeleton with handlers)

- [ ] **Step 1: Implement voice handler with confirmation**

```python
import json
import tempfile
from datetime import datetime, timezone
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from app import config
from app.transcribe import transcribe_voice
from app.parser import parse_task
from app.intent import classify_status
from app.db import Db
from app.gcal import GCalClient
from app.scheduler import Scheduler

# Module-level singletons (init in main.py)
oai: OpenAI | None = None
db: Db | None = None
gcal: GCalClient | None = None
sched: Scheduler | None = None

# Pending TaskSpecs awaiting confirmation: {chat_id: TaskSpec}
PENDING: dict[int, dict] = {}

def _allowed(update: Update) -> bool:
    return update.effective_chat and update.effective_chat.id == config.ALLOWED_CHAT_ID

async def voice_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update): return
    if update.effective_user.id != config.VITALY_USER_ID:
        # only Victor sets tasks via voice; assistant voice goes to status_handler
        await status_handler(update, ctx)
        return

    file = await update.message.voice.get_file()
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        text = transcribe_voice(oai, tmp.name)

    spec = parse_task(oai, text, datetime.now(timezone.utc), config.TZ)
    PENDING[update.effective_chat.id] = spec.model_dump(mode="json")

    msg = format_confirmation(spec)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Создать", callback_data="confirm"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
    ]])
    await update.message.reply_text(msg, reply_markup=kb, parse_mode="HTML")

def format_confirmation(spec) -> str:
    lines = [f"<b>Задача:</b> {spec.title}", f"{spec.description}"]
    if spec.deadline:
        lines.append(f"<b>Дедлайн:</b> {spec.deadline.strftime('%Y-%m-%d %H:%M')}")
    else:
        lines.append("<b>Дедлайн:</b> не указан")
    if spec.reminders:
        lines.append("<b>Напомнить:</b>")
        for r in spec.reminders:
            lines.append(f"  • {r.when.strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)
```

- [ ] **Step 2: Manual smoke test**

Run bot locally with real env, send voice → bot replies with parsed task and buttons.

- [ ] **Step 3: Commit** — `git add . && git commit -m "feat: voice intake + confirmation"`

---

### Task 11: Confirm callback — create event + schedule

**Files:**
- Modify: `app/bot.py` (add callback_handler, finalize_task helper)

- [ ] **Step 1: Implement callback + scheduling**

```python
from datetime import datetime, timezone, timedelta
from app.schemas import TaskSpec

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id
    if q.data == "cancel":
        PENDING.pop(chat_id, None)
        await q.edit_message_text("Отменено.")
        return
    if q.data == "confirm":
        data = PENDING.pop(chat_id, None)
        if not data:
            await q.edit_message_text("Срок действия истёк. Продиктуй задачу заново.")
            return
        spec = TaskSpec.model_validate(data)
        await _finalize(chat_id, spec, q)

async def _finalize(chat_id: int, spec: TaskSpec, q):
    deadline = spec.deadline or (datetime.now(timezone.utc) + timedelta(days=1))
    event_id = gcal.create_event(
        title=spec.title,
        description=spec.description,
        start=deadline - timedelta(minutes=30),
        end=deadline,
    )
    task_id = db.create_task(
        chat_id=chat_id,
        assistant_user_id=config.ASSISTANT_USER_ID,
        title=spec.title,
        description=spec.description,
        deadline=spec.deadline,
        gcal_event_id=event_id,
    )
    # schedule reminders
    for r in spec.reminders:
        sched.schedule_reminder(task_id, r.when, "reminder")
    if spec.deadline:
        sched.schedule_reminder(task_id, spec.deadline, "deadline")

    await q.edit_message_text(
        f"✅ Создано (#{task_id}). @assistant — задача:\n\n"
        f"<b>{spec.title}</b>\n{spec.description}\n\n"
        f"Дедлайн: {spec.deadline.strftime('%Y-%m-%d %H:%M') if spec.deadline else 'не задан'}",
        parse_mode="HTML",
    )
```

- [ ] **Step 2: Commit** — `git add . && git commit -m "feat: confirm callback creates event and schedules reminders"`

---

### Task 12: Reminder firing → Telegram message

**Files:**
- Modify: `app/bot.py` (add reminder_callback wiring)

- [ ] **Step 1: Implement firing**

In `app/bot.py` add:

```python
from telegram import Bot
from telegram.constants import ParseMode

# tg_bot set in main.py after Application built
tg_bot: Bot | None = None

def on_scheduler_fire(task_id: int, kind: str):
    """Called from APScheduler thread — schedule async send."""
    import asyncio
    asyncio.get_event_loop().create_task(_fire_async(task_id, kind))

async def _fire_async(task_id: int, kind: str):
    task = db.get_task(task_id)
    if not task or task["status"] in ("done", "cancelled"):
        return
    chat_id = task["chat_id"]
    if kind == "reminder":
        text = (f"⏰ @assistant напомнить по задаче #{task_id} "
                f"<b>{task['title']}</b>\nКак статус? (сделал / в работе / застрял)")
        await tg_bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
    elif kind == "deadline":
        if task["status"] != "done":
            db.update_status(task_id, "overdue")
            gcal.update_summary(task["gcal_event_id"], "⚠️ ")
            await tg_bot.send_message(
                chat_id,
                f"⚠️ Просрочка по задаче #{task_id} <b>{task['title']}</b>. "
                f"@vitaly — статус не подтверждён.",
                parse_mode=ParseMode.HTML)
```

- [ ] **Step 2: Commit** — `git add . && git commit -m "feat: scheduler firing → telegram"`

---

### Task 13: Status replies from assistant

**Files:**
- Modify: `app/bot.py` (status_handler for text + voice from assistant)

- [ ] **Step 1: Implement**

```python
async def status_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update): return
    user_id = update.effective_user.id
    if user_id != config.ASSISTANT_USER_ID:
        return  # only assistant statuses tracked here

    # Get text (transcribe if voice)
    if update.message.voice:
        file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            text = transcribe_voice(oai, tmp.name)
    else:
        text = update.message.text or ""

    if not text.strip():
        return

    task = db.find_active_for_assistant(update.effective_chat.id, user_id)
    if not task:
        return  # no active task to bind status to

    res = classify_status(oai, text, task["title"])
    intent = res["intent"]
    note = res.get("note", "")

    if intent == "other":
        return

    db.update_status(task["id"], intent, note=note)
    gcal.append_to_description(
        task["gcal_event_id"],
        f"[{datetime.now(timezone.utc).isoformat()}] {intent}: {note}")

    if intent == "done":
        sched.cancel_task_jobs(task["id"])
        await update.message.reply_text(f"✅ Задача #{task['id']} закрыта.")
    elif intent == "blocked":
        await update.message.reply_text(
            f"⚠️ Задача #{task['id']} в блоке. @vitaly — нужно вмешательство.")
    else:
        await update.message.reply_text(f"📝 Статус #{task['id']}: {intent}")
```

- [ ] **Step 2: Commit** — `git add . && git commit -m "feat: assistant status replies"`

---

### Task 14: /tasks and /cancel commands

**Files:**
- Modify: `app/bot.py`

- [ ] **Step 1: Implement**

```python
from telegram.ext import CommandHandler

async def cmd_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update): return
    rows = db.list_active(update.effective_chat.id)
    if not rows:
        await update.message.reply_text("Нет активных задач.")
        return
    lines = []
    for t in rows:
        dl = t["deadline"][:16].replace("T"," ") if t["deadline"] else "—"
        lines.append(f"#{t['id']} [{t['status']}] {t['title']} → {dl}")
    await update.message.reply_text("\n".join(lines))

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update): return
    if update.effective_user.id != config.VITALY_USER_ID: return
    args = ctx.args
    if not args:
        await update.message.reply_text("Используй: /cancel <id>")
        return
    tid = int(args[0])
    task = db.get_task(tid)
    if not task:
        await update.message.reply_text("Не найдено.")
        return
    db.update_status(tid, "cancelled")
    sched.cancel_task_jobs(tid)
    await update.message.reply_text(f"❌ Задача #{tid} отменена.")
```

- [ ] **Step 2: Commit** — `git add . && git commit -m "feat: /tasks and /cancel commands"`

---

### Task 15: Healthcheck endpoint

**Files:**
- Create: `app/health.py`

- [ ] **Step 1: Implement**

```python
from aiohttp import web

async def health(_): return web.Response(text="ok")

def make_app():
    app = web.Application()
    app.router.add_get("/health", health)
    return app
```

- [ ] **Step 2: Commit** — `git add . && git commit -m "feat: healthcheck endpoint"`

---

### Task 16: main.py — wire everything

**Files:**
- Create: `app/main.py`

- [ ] **Step 1: Implement entrypoint**

```python
import asyncio
import logging
from openai import OpenAI
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application, MessageHandler, CallbackQueryHandler,
    CommandHandler, filters,
)

from app import config, bot
from app.db import Db
from app.gcal import GCalClient
from app.scheduler import Scheduler
from app.health import make_app

logging.basicConfig(level=logging.INFO,
                   format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("main")

async def run():
    # init singletons
    bot.oai = OpenAI(api_key=config.OPENAI_API_KEY)
    bot.db = Db(config.DB_PATH)
    bot.db.init_schema()
    bot.gcal = GCalClient(
        calendar_id=config.GOOGLE_CALENDAR_ID,
        token_path=config.GOOGLE_TOKEN_PATH,
        credentials_path=config.GOOGLE_CREDENTIALS_PATH,
    )
    bot.sched = Scheduler(
        db_url=f"sqlite:///{config.DB_PATH}",
        tz=config.TZ,
    )
    bot.sched.set_callback(bot.on_scheduler_fire)
    bot.sched.start()

    # telegram app
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    bot.tg_bot = app.bot

    app.add_handler(MessageHandler(
        filters.VOICE & filters.User(user_id=config.VITALY_USER_ID),
        bot.voice_handler))
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.VOICE) & filters.User(user_id=config.ASSISTANT_USER_ID),
        bot.status_handler))
    app.add_handler(CallbackQueryHandler(bot.callback_handler))
    app.add_handler(CommandHandler("tasks", bot.cmd_tasks))
    app.add_handler(CommandHandler("cancel", bot.cmd_cancel))

    # healthcheck server
    health_app = make_app()
    runner = web.AppRunner(health_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    log.info("healthcheck on :8080/health")

    # run telegram polling
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    log.info("bot started")

    # keep alive
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        bot.sched.shutdown()

if __name__ == "__main__":
    asyncio.run(run())
```

- [ ] **Step 2: Local smoke test**

```bash
python -m app.main
```
Проверь: бот отвечает на voice, создаёт event в GCal, шлёт reminder в назначенное время (поставь напоминание через 1 минуту для теста).

- [ ] **Step 3: Commit** — `git add . && git commit -m "feat: main entrypoint wiring"`

---

### Task 17: Railway deploy

**Files:**
- Create: `railway.toml`, `Procfile`

- [ ] **Step 1: Create railway.toml**

```toml
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "python -m app.main"
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 5
```

- [ ] **Step 2: Add Procfile (fallback)**

```
web: python -m app.main
```

- [ ] **Step 3: Deploy steps in README**

```markdown
## Railway deploy
1. `railway init` (или через UI)
2. Добавить volume `/data` (1GB)
3. Залить `data/credentials.json` и `data/token.json` через `railway run` или scp
4. Установить env vars из `.env.example`
5. `railway up`
6. Проверить `https://<service>.up.railway.app/health` → `ok`
```

- [ ] **Step 4: Deploy and verify**

Run: `railway up`
Verify: `curl https://<service>.up.railway.app/health` → `ok`
Verify: voice в Telegram → бот отвечает → событие в GCal появилось.

- [ ] **Step 5: Commit** — `git add . && git commit -m "chore: railway deploy config"`

---

## Done criteria

- [ ] Воз voice от Виталийа создаёт задачу в GCal с правильным временем
- [ ] Reminders приходят в чат в указанное время
- [ ] Reply исполнителя меняет статус и пишет в description события
- [ ] Просрочка алертит Виталийа и помечает event ⚠️
- [ ] `/tasks` показывает активные
- [ ] Бот переживает рестарт (jobs persist в SQLAlchemyJobStore)
- [ ] Healthcheck отвечает 200 на Railway
