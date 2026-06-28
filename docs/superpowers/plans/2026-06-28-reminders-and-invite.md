# Reminders & Invite-Link Executor Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "взяв в роботу" button + 30-minute not-started reminder, hourly repeated overdue reminders, and invite-link-based executor self-registration to the delegation-bot Telegram bot.

**Architecture:** Builds entirely on existing patterns already in the codebase — APScheduler one-shot/interval jobs keyed by `task{id}-{kind}`, the `_fire_async(task_id, kind)` dispatcher in `app/bot.py`, and the sqlite `Db` class. No new processes, libraries, or services.

**Tech Stack:** Python, python-telegram-bot, APScheduler (`apscheduler.triggers.interval.IntervalTrigger` — new import), sqlite3, pytest + pytest-asyncio (`asyncio_mode = "auto"`, see `pyproject.toml`).

## Global Constraints

- Repo: `C:\AAA_project_group_vv_deal\delegation-bot` (GitHub: vitaliy754-spec/delegation-bot). All file paths below are relative to this repo root, not the current worktree.
- Spec: `docs/superpowers/specs/2026-06-28-reminders-and-invite-design.md` — follow it exactly; this plan implements all three of its sections.
- Follow existing code style: no docstrings beyond the one-liners already present, Ukrainian-language user-facing strings, HTML `parse_mode` for messages with `<b>` tags.
- Job IDs for any new scheduled job MUST start with `f"task{task_id}-"` so the existing `Scheduler.list_jobs_for_task` / `cancel_task_jobs` (which match on that prefix) pick them up automatically — do not add separate cancellation logic.
- `NOT_STARTED_REMINDER_MINUTES` default 30, `OVERDUE_REPEAT_HOURS` default 1 (both overridable via env, same pattern as `FOLLOWUP_DELAY_HOURS` in `app/config.py`).
- Manual `/add_executor <telegram_id> <ім'я>` must keep working (back-compat) alongside the new `/add_executor <ім'я>` invite-link mode.

---

### Task 1: `invites` table in the DB layer

**Files:**
- Modify: `app/db.py` (add to `SCHEMA` string, add 3 methods at the end of the `Db` class)
- Test: `tests/test_db.py` (append tests)

**Interfaces:**
- Produces: `Db.create_invite(token: str, name: str) -> None`, `Db.get_invite_by_token(token: str) -> dict | None` (keys: `id, token, name, created_at, used_at`), `Db.mark_invite_used(token: str) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_db.py`:

```python
def test_invite_create_and_lookup():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = Db(path); db.init_schema()
    db.create_invite("tok123", "Оля")
    invite = db.get_invite_by_token("tok123")
    assert invite["name"] == "Оля"
    assert invite["used_at"] is None

def test_invite_mark_used():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = Db(path); db.init_schema()
    db.create_invite("tok456", "Петя")
    db.mark_invite_used("tok456")
    invite = db.get_invite_by_token("tok456")
    assert invite["used_at"] is not None

def test_invite_unknown_token_returns_none():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = Db(path); db.init_schema()
    assert db.get_invite_by_token("missing") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_db.py -v -k invite`
Expected: FAIL — `AttributeError: 'Db' object has no attribute 'create_invite'`

- [ ] **Step 3: Add the `invites` table and methods**

In `app/db.py`, add to the `SCHEMA` string (after the `executors` table, before the `CREATE INDEX` line):

```python
CREATE TABLE IF NOT EXISTS invites (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  used_at TEXT
);
```

Add these methods at the end of the `Db` class (after `get_executors_by_name`):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_db.py -v -k invite`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat(db): add invites table for executor self-registration"
```

---

### Task 2: `Scheduler.schedule_interval` for repeated overdue reminders

**Files:**
- Modify: `app/scheduler.py`
- Test: `tests/test_scheduler.py` (append tests)

**Interfaces:**
- Consumes: nothing new (uses existing `_fire(task_id, kind)` module-level callback already wired via `set_callback`).
- Produces: `Scheduler.schedule_interval(task_id: int, kind: str, start: datetime, hours: float) -> str` (returns the job id, same contract as `schedule_reminder`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_scheduler.py`:

```python
async def test_schedule_interval_creates_job(tmp_path):
    db_url = f"sqlite:///{tmp_path/'jobs2.db'}"
    s = Scheduler(db_url=db_url, tz="UTC")
    s.start()
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    job_id = s.schedule_interval(task_id=3, kind="overdue_repeat", start=start, hours=1)
    assert job_id == "task3-overdue_repeat"
    jobs = s.list_jobs_for_task(3)
    assert len(jobs) == 1
    assert jobs[0].id == "task3-overdue_repeat"
    s.shutdown()

async def test_cancel_task_jobs_removes_interval_job(tmp_path):
    db_url = f"sqlite:///{tmp_path/'jobs3.db'}"
    s = Scheduler(db_url=db_url, tz="UTC")
    s.start()
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    s.schedule_interval(task_id=4, kind="overdue_repeat", start=start, hours=1)
    s.cancel_task_jobs(4)
    assert s.list_jobs_for_task(4) == []
    s.shutdown()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_scheduler.py -v -k interval`
Expected: FAIL — `AttributeError: 'Scheduler' object has no attribute 'schedule_interval'`

- [ ] **Step 3: Implement `schedule_interval`**

In `app/scheduler.py`, add the import at the top (alongside the existing trigger imports):

```python
from apscheduler.triggers.interval import IntervalTrigger
```

Add this method to the `Scheduler` class (after `schedule_reminder`):

```python
    def schedule_interval(self, task_id: int, kind: str, start: datetime, hours: float) -> str:
        """Repeating reminder (e.g. hourly overdue nags) starting at `start`.
        Job id has no timestamp suffix (one job per task+kind) so a later call
        with the same task_id/kind replaces it instead of stacking duplicates."""
        jid = f"task{task_id}-{kind}"
        self.scheduler.add_job(
            _fire, IntervalTrigger(start_date=start, hours=hours),
            args=[task_id, kind],
            id=jid, replace_existing=True,
        )
        return jid
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: all passed (original + 2 new)

- [ ] **Step 5: Commit**

```bash
git add app/scheduler.py tests/test_scheduler.py
git commit -m "feat(scheduler): add schedule_interval for repeating overdue reminders"
```

---

### Task 3: Config flags for the two new timing knobs

**Files:**
- Modify: `app/config.py`

**Interfaces:**
- Produces: `config.NOT_STARTED_REMINDER_MINUTES: int` (default 30), `config.OVERDUE_REPEAT_HOURS: int` (default 1).

- [ ] **Step 1: Add the two settings**

In `app/config.py`, append after the existing `FOLLOWUP_DELAY_HOURS` line:

```python
# Minutes after task creation before nagging if status is still 'pending'.
NOT_STARTED_REMINDER_MINUTES = int(os.environ.get("NOT_STARTED_REMINDER_MINUTES", "30"))
# Hours between repeated overdue reminders once the deadline has passed.
OVERDUE_REPEAT_HOURS = int(os.environ.get("OVERDUE_REPEAT_HOURS", "1"))
```

- [ ] **Step 2: Verify the module still imports cleanly**

Run: `python -c "from app import config; print(config.NOT_STARTED_REMINDER_MINUTES, config.OVERDUE_REPEAT_HOURS)"`
Expected: `30 1`

(No dedicated test file for `config.py` exists in the repo — this is a plain constant read by later tasks' tests.)

- [ ] **Step 3: Commit**

```bash
git add app/config.py
git commit -m "feat(config): add NOT_STARTED_REMINDER_MINUTES and OVERDUE_REPEAT_HOURS"
```

---

### Task 4: "🟢 Взяв в роботу" button on task-creation messages + `started:` callback

**Files:**
- Modify: `app/bot.py`
- Test: `tests/test_bot.py` (append tests)

**Interfaces:**
- Consumes: `db.get_task`, `db.update_status` (existing), `Scheduler` (no new methods needed here).
- Produces: `_task_kb(task_id: int, status: str) -> InlineKeyboardMarkup` (replaces `_done_kb`; callers throughout `app/bot.py` are updated in this task). Callback data format `f"started:{task_id}"` handled in `callback_handler`.

- [ ] **Step 1: Write the failing test for the keyboard helper**

Append to `tests/test_bot.py`:

```python
from app.bot import _task_kb

def test_task_kb_pending_shows_both_buttons():
    kb = _task_kb(42, "pending")
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert "🟢 Взяв в роботу" in texts
    assert "✅ Виконано" in texts
    started_btn = [b for row in kb.inline_keyboard for b in row if "Взяв" in b.text][0]
    assert started_btn.callback_data == "started:42"

def test_task_kb_in_progress_hides_started_button():
    kb = _task_kb(42, "in_progress")
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert "🟢 Взяв в роботу" not in texts
    assert "✅ Виконано" in texts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_bot.py -v -k task_kb`
Expected: FAIL — `ImportError: cannot import name '_task_kb' from 'app.bot'`

- [ ] **Step 3: Replace `_done_kb` with `_task_kb` and wire it into message sends**

In `app/bot.py`, replace the existing `_done_kb` function (currently right before `format_confirmation`):

```python
def _task_kb(task_id: int, status: str) -> InlineKeyboardMarkup:
    """Inline keyboard for a task message. Shows 'Взяв в роботу' only while
    the task is still pending; 'Виконано' is always offered until closed."""
    buttons = []
    if status == "pending":
        buttons.append(InlineKeyboardButton("🟢 Взяв в роботу", callback_data=f"started:{task_id}"))
    buttons.append(InlineKeyboardButton("✅ Виконано", callback_data=f"done:{task_id}"))
    return InlineKeyboardMarkup([buttons])
```

In `callback_handler`, add a new branch right before the existing `if q.data and q.data.startswith("done:"):` check:

```python
    if q.data and q.data.startswith("started:"):
        tid = int(q.data.split(":", 1)[1])
        task = db.get_task(tid)
        if not task or task["status"] in ("done", "cancelled"):
            await q.edit_message_text("Задачу вже закрито.")
            return
        db.update_status(tid, "in_progress")
        await q.edit_message_reply_markup(reply_markup=_task_kb(tid, "in_progress"))
        return
```

In `_finalize`, find this block:

```python
    await q.edit_message_text(
        f"✅ Задачу #{task_id} створено.\n\n<b>{spec.title}</b>\n"
        f"Дедлайн: {deadline_str}{deadline_suffix}\n\n"
        + ("Це твоя задача." if to_self else f"Надіслано виконавцю: {recipient_label}."),
        parse_mode="HTML",
        reply_markup=_done_kb(task_id) if to_self else None,
    )

    if not to_self:
        try:
            await tg_bot.send_message(
                recipient_uid,
                f"📌 <b>Нова задача #{task_id}</b>\n\n"
                f"<b>{spec.title}</b>\n{spec.description}\n\n"
                f"⏰ Дедлайн: {deadline_str}{deadline_suffix}\n\n"
                f"Коли візьмеш у роботу / завершиш / застрягнеш — напиши мені сюди (текстом або голосом).",
                parse_mode="HTML",
            )
```

Replace it with:

```python
    await q.edit_message_text(
        f"✅ Задачу #{task_id} створено.\n\n<b>{spec.title}</b>\n"
        f"Дедлайн: {deadline_str}{deadline_suffix}\n\n"
        + ("Це твоя задача." if to_self else f"Надіслано виконавцю: {recipient_label}."),
        parse_mode="HTML",
        reply_markup=_task_kb(task_id, "pending") if to_self else None,
    )

    if not to_self:
        try:
            await tg_bot.send_message(
                recipient_uid,
                f"📌 <b>Нова задача #{task_id}</b>\n\n"
                f"<b>{spec.title}</b>\n{spec.description}\n\n"
                f"⏰ Дедлайн: {deadline_str}{deadline_suffix}\n\n"
                f"Коли візьмеш у роботу / завершиш / застрягнеш — напиши мені сюди (текстом або голосом).",
                parse_mode="HTML",
                reply_markup=_task_kb(task_id, "pending"),
            )
```

(The rest of that `try/except` block — the `except Exception as e:` branch — is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_bot.py -v -k task_kb`
Expected: 2 passed

- [ ] **Step 5: Write the failing test for the `started:` callback**

Append to `tests/test_status_scenarios.py` (it already has the `setup_module_state` autouse fixture with `bot.db`/`bot.tg_bot` mocked):

```python
def make_callback_update(user_id, data):
    update = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.data = data
    update.callback_query.message.chat_id = 999
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.edit_message_reply_markup = AsyncMock()
    return update


@pytest.mark.asyncio
async def test_started_callback_marks_in_progress():
    bot.db.get_task.return_value = {"id": 8, "title": "Афіша", "status": "pending"}
    update = make_callback_update(2, "started:8")
    await bot.callback_handler(update, make_ctx())
    bot.db.update_status.assert_called_with(8, "in_progress")
    update.callback_query.edit_message_reply_markup.assert_called_once()


@pytest.mark.asyncio
async def test_started_callback_on_closed_task_is_noop():
    bot.db.get_task.return_value = {"id": 9, "title": "Афіша", "status": "done"}
    update = make_callback_update(2, "started:9")
    await bot.callback_handler(update, make_ctx())
    bot.db.update_status.assert_not_called()
    update.callback_query.edit_message_text.assert_called_once_with("Задачу вже закрито.")
```

- [ ] **Step 6: Run test to verify it fails**

Run: `python -m pytest tests/test_status_scenarios.py -v -k started_callback`
Expected: FAIL — `AssertionError` (no `update_status` call) because the `started:` branch doesn't exist yet — wait, Step 3 already added it. Skip ahead: this should now PASS once Step 3 code is in place. Run it to confirm.

Expected actual result after Step 3's code lands: 2 passed.

- [ ] **Step 7: Run the full bot test files to check nothing else broke**

Run: `python -m pytest tests/test_bot.py tests/test_status_scenarios.py -v`
Expected: all passed

- [ ] **Step 8: Commit**

```bash
git add app/bot.py tests/test_bot.py tests/test_status_scenarios.py
git commit -m "feat(bot): add 'Взяв в роботу' button and started: callback"
```

---

### Task 5: 30-minute "not started" reminder

**Files:**
- Modify: `app/bot.py` (`_finalize`, `_fire_async`)
- Test: `tests/test_status_scenarios.py` (append tests)

**Interfaces:**
- Consumes: `config.NOT_STARTED_REMINDER_MINUTES` (Task 3), `sched.schedule_reminder` (existing), `_task_kb` (Task 4).
- Produces: new `_fire_async` branch for `kind == "not_started"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_status_scenarios.py`:

```python
@pytest.mark.asyncio
async def test_not_started_reminder_self_still_pending():
    bot.db.get_task.return_value = {
        "id": 10, "title": "Звіт", "description": "опис",
        "status": "pending", "assistant_user_id": 1, "deadline": None,
    }
    bot.config.VITALY_USER_ID = 1
    await bot._fire_async(10, "not_started")
    bot.tg_bot.send_message.assert_called_once()
    args, kwargs = bot.tg_bot.send_message.call_args
    assert args[0] == 1
    assert "не взяв" in args[1].lower() or "не взяв" in kwargs.get("text", "").lower()


@pytest.mark.asyncio
async def test_not_started_reminder_delegated_still_pending():
    bot.db.get_task.return_value = {
        "id": 11, "title": "Лендинг", "description": "опис",
        "status": "pending", "assistant_user_id": 2, "deadline": None,
    }
    bot.config.VITALY_USER_ID = 1
    await bot._fire_async(11, "not_started")
    bot.tg_bot.send_message.assert_called_once()
    args, _ = bot.tg_bot.send_message.call_args
    assert args[0] == 2


@pytest.mark.asyncio
async def test_not_started_reminder_skipped_if_already_started():
    bot.db.get_task.return_value = {
        "id": 12, "title": "Лендинг", "description": "опис",
        "status": "in_progress", "assistant_user_id": 2, "deadline": None,
    }
    bot.config.VITALY_USER_ID = 1
    await bot._fire_async(12, "not_started")
    bot.tg_bot.send_message.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_status_scenarios.py -v -k not_started`
Expected: FAIL — `_fire_async` raises/returns without sending because `kind == "not_started"` is unhandled (falls through all `elif` branches, no message sent at all) → the first two tests fail on `assert_called_once()` (0 calls).

- [ ] **Step 3: Add the `not_started` branch to `_fire_async`**

In `app/bot.py`, inside `_fire_async`, add this branch — place it as the first `elif` right after the `if kind == "reminder":` block (before `elif kind == "mid":`):

```python
    elif kind == "not_started":
        if task["status"] != "pending":
            return
        if to_self:
            await tg_bot.send_message(
                recipient,
                f"⏰ Нагадування: ти ще не взяв задачу #{task_id} <b>{task['title']}</b> в роботу.",
                parse_mode=ParseMode.HTML,
                reply_markup=_task_kb(task_id, "pending"))
        else:
            await tg_bot.send_message(
                recipient,
                f"⏰ Нагадування: ти ще не взяв в роботу задачу #{task_id} <b>{task['title']}</b>.\n"
                f"Напиши мені (текстом або голосом), коли почнеш.",
                parse_mode=ParseMode.HTML)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_status_scenarios.py -v -k not_started`
Expected: 3 passed

- [ ] **Step 5: Write the failing test that `_finalize` schedules the reminder**

Append to `tests/test_bot.py`:

```python
import asyncio
from unittest.mock import MagicMock, AsyncMock
from app.schemas import TaskSpec


def _make_finalize_mocks():
    bot.db = MagicMock()
    bot.gcal = MagicMock()
    bot.gcal.create_event.return_value = "evt1"
    bot.sched = MagicMock()
    bot.tg_bot = MagicMock()
    bot.tg_bot.send_message = AsyncMock()
    bot.db.create_task.return_value = 50
    bot.config.VITALY_USER_ID = 1
    q = MagicMock()
    q.edit_message_text = AsyncMock()
    return q


def test_finalize_schedules_not_started_reminder():
    q = _make_finalize_mocks()
    spec = TaskSpec(title="t", description="d", deadline=None, reminders=[], assignee=None)
    asyncio.run(bot._finalize(999, spec, 2, "Оля", q))
    kinds = [c.args[2] for c in bot.sched.schedule_reminder.call_args_list]
    assert "not_started" in kinds
```

- [ ] **Step 6: Run test to verify it fails**

Run: `python -m pytest tests/test_bot.py -v -k finalize_schedules_not_started`
Expected: FAIL — `"not_started" not in kinds` (empty or missing)

- [ ] **Step 7: Schedule the reminder in `_finalize`**

In `app/bot.py`, inside `_finalize`, find:

```python
    to_self = recipient_uid == config.VITALY_USER_ID
    now = datetime.now(timezone.utc)

    # explicit reminders dictated in the voice/text, if any
```

Replace with:

```python
    to_self = recipient_uid == config.VITALY_USER_ID
    now = datetime.now(timezone.utc)

    # nag if still not picked up within NOT_STARTED_REMINDER_MINUTES, regardless
    # of deadline/dictated reminders — this guards the "nobody started it" case
    sched.schedule_reminder(
        task_id,
        now + timedelta(minutes=config.NOT_STARTED_REMINDER_MINUTES),
        "not_started")

    # explicit reminders dictated in the voice/text, if any
```

- [ ] **Step 8: Run test to verify it passes**

Run: `python -m pytest tests/test_bot.py -v -k finalize_schedules_not_started`
Expected: 1 passed

- [ ] **Step 9: Run the full test suite to check for regressions**

Run: `python -m pytest tests/ -v`
Expected: all passed

- [ ] **Step 10: Commit**

```bash
git add app/bot.py tests/test_bot.py tests/test_status_scenarios.py
git commit -m "feat(bot): 30-minute not-started reminder for pending tasks"
```

---

### Task 6: Hourly repeated overdue reminder

**Files:**
- Modify: `app/bot.py` (`_finalize`, `_fire_async`)
- Test: `tests/test_status_scenarios.py`, `tests/test_bot.py` (append tests)

**Interfaces:**
- Consumes: `sched.schedule_interval` (Task 2), `config.OVERDUE_REPEAT_HOURS` (Task 3).
- Produces: new `_fire_async` branch for `kind == "overdue_repeat"`.

- [ ] **Step 1: Write the failing tests for `_fire_async`**

Append to `tests/test_status_scenarios.py`:

```python
@pytest.mark.asyncio
async def test_overdue_repeat_delegated_notifies_both():
    bot.db.get_task.return_value = {
        "id": 13, "title": "Афіша", "status": "in_progress",
        "assistant_user_id": 2, "deadline": "2026-06-01T10:00:00+00:00",
    }
    bot.config.VITALY_USER_ID = 1
    await bot._fire_async(13, "overdue_repeat")
    assert bot.tg_bot.send_message.call_count == 2
    recipients = {c.args[0] for c in bot.tg_bot.send_message.call_args_list}
    assert recipients == {1, 2}


@pytest.mark.asyncio
async def test_overdue_repeat_self_notifies_once():
    bot.db.get_task.return_value = {
        "id": 14, "title": "Звіт", "status": "pending",
        "assistant_user_id": 1, "deadline": "2026-06-01T10:00:00+00:00",
    }
    bot.config.VITALY_USER_ID = 1
    await bot._fire_async(14, "overdue_repeat")
    bot.tg_bot.send_message.assert_called_once()
    args, _ = bot.tg_bot.send_message.call_args
    assert args[0] == 1


@pytest.mark.asyncio
async def test_overdue_repeat_stops_once_done():
    bot.db.get_task.return_value = {
        "id": 15, "title": "Афіша", "status": "done",
        "assistant_user_id": 2, "deadline": "2026-06-01T10:00:00+00:00",
    }
    bot.config.VITALY_USER_ID = 1
    await bot._fire_async(15, "overdue_repeat")
    bot.tg_bot.send_message.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_status_scenarios.py -v -k overdue_repeat`
Expected: FAIL — `assert_not_called` violated / call counts 0, since `kind == "overdue_repeat"` is unhandled.

Note: each test in this file resets mocks via the autouse `setup_module_state` fixture, so call counts start at zero per test.

- [ ] **Step 3: Add the `overdue_repeat` branch to `_fire_async`**

In `app/bot.py`, add this branch right after the existing `elif kind == "deadline":` block (so it becomes the final `elif`):

```python
    elif kind == "overdue_repeat":
        if task["status"] in ("done", "cancelled"):
            return
        dl = fmt_dt(task["deadline"], fallback="—")
        text = (f"⚠️ Задача #{task_id} <b>{task['title']}</b> досі не виконана "
                f"(дедлайн {dl}, {KYIV_LABEL}).")
        await tg_bot.send_message(recipient, text, parse_mode=ParseMode.HTML)
        if not to_self:
            await tg_bot.send_message(config.VITALY_USER_ID, text, parse_mode=ParseMode.HTML)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_status_scenarios.py -v -k overdue_repeat`
Expected: 3 passed

- [ ] **Step 5: Write the failing test that `_finalize` schedules the repeat job**

Append to `tests/test_bot.py`:

```python
def test_finalize_schedules_overdue_repeat_when_deadline_set():
    q = _make_finalize_mocks()
    deadline = datetime.now(timezone.utc) + timedelta(days=1)
    spec = TaskSpec(title="t", description="d", deadline=deadline, reminders=[], assignee=None)
    asyncio.run(bot._finalize(999, spec, 2, "Оля", q))
    bot.sched.schedule_interval.assert_called_once_with(50, "overdue_repeat", deadline, bot.config.OVERDUE_REPEAT_HOURS)


def test_finalize_skips_overdue_repeat_without_deadline():
    q = _make_finalize_mocks()
    spec = TaskSpec(title="t", description="d", deadline=None, reminders=[], assignee=None)
    asyncio.run(bot._finalize(999, spec, 1, "тобі", q))
    bot.sched.schedule_interval.assert_not_called()
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `python -m pytest tests/test_bot.py -v -k overdue_repeat`
Expected: FAIL on the first test — `schedule_interval` never called (`Expected mock to have been called once. Called 0 times.`); second test passes trivially already.

- [ ] **Step 7: Schedule the interval job in `_finalize`**

In `app/bot.py`, find:

```python
            if status > now:
                sched.schedule_reminder(task_id, status, "status_check")
        sched.schedule_reminder(task_id, spec.deadline, "deadline")
```

Replace with:

```python
            if status > now:
                sched.schedule_reminder(task_id, status, "status_check")
        sched.schedule_reminder(task_id, spec.deadline, "deadline")
        sched.schedule_interval(task_id, "overdue_repeat", spec.deadline, config.OVERDUE_REPEAT_HOURS)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/test_bot.py -v -k overdue_repeat`
Expected: 2 passed

- [ ] **Step 9: Run the full test suite**

Run: `python -m pytest tests/ -v`
Expected: all passed

- [ ] **Step 10: Commit**

```bash
git add app/bot.py tests/test_bot.py tests/test_status_scenarios.py
git commit -m "feat(bot): hourly repeated overdue reminder until task is done/cancelled"
```

---

### Task 7: Invite-link executor self-registration

**Files:**
- Modify: `app/bot.py` (`cmd_add_executor`, `cmd_start`, add `import secrets` at top)
- Test: `tests/test_bot.py` (append tests)

**Interfaces:**
- Consumes: `db.create_invite`, `db.get_invite_by_token`, `db.mark_invite_used` (Task 1), `db.add_executor` (existing).
- Produces: `/add_executor <ім'я>` generates and returns an invite link; `/start invite_<token>` (deep-link payload) auto-registers the executor.

- [ ] **Step 1: Write the failing tests for `cmd_add_executor` invite mode**

Append to `tests/test_bot.py`:

```python
def make_command_update(user_id, args):
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = args
    ctx.bot.username = "test_delegation_bot"
    return update, ctx


def test_add_executor_name_only_creates_invite_link():
    bot.db = MagicMock()
    bot.config.VITALY_USER_ID = 1
    update, ctx = make_command_update(1, ["Оля"])
    asyncio.run(bot.cmd_add_executor(update, ctx))
    bot.db.create_invite.assert_called_once()
    token_arg, name_arg = bot.db.create_invite.call_args.args
    assert name_arg == "Оля"
    sent_text = update.message.reply_text.call_args.args[0]
    assert f"https://t.me/test_delegation_bot?start=invite_{token_arg}" in sent_text


def test_add_executor_id_and_name_still_works_manually():
    bot.db = MagicMock()
    bot.config.VITALY_USER_ID = 1
    update, ctx = make_command_update(1, ["1680472982", "Вадім"])
    asyncio.run(bot.cmd_add_executor(update, ctx))
    bot.db.add_executor.assert_called_once_with("Вадім", 1680472982)
    bot.db.create_invite.assert_not_called()


def test_add_executor_multi_word_name_creates_invite():
    bot.db = MagicMock()
    bot.config.VITALY_USER_ID = 1
    update, ctx = make_command_update(1, ["Оля", "Петренко"])
    asyncio.run(bot.cmd_add_executor(update, ctx))
    bot.db.create_invite.assert_called_once()
    _, name_arg = bot.db.create_invite.call_args.args
    assert name_arg == "Оля Петренко"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_bot.py -v -k add_executor`
Expected: FAIL — `test_add_executor_name_only_creates_invite_link` fails because current `cmd_add_executor` rejects single-arg input (`"Use: /add_executor <id> <name>"`) instead of calling `create_invite`; `test_add_executor_multi_word_name_creates_invite` fails the same way; `test_add_executor_id_and_name_still_works_manually` should already pass (no behavior change yet).

- [ ] **Step 3: Rewrite `cmd_add_executor`**

In `app/bot.py`, add `import secrets` to the top imports (alongside `import json` / `import tempfile`):

```python
import json
import secrets
import tempfile
```

Replace the existing `cmd_add_executor` function entirely with:

```python
async def cmd_add_executor(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_vitaly(update):
        return
    args = clean_command_args(ctx.args)
    if not args:
        await update.message.reply_text(
            "Використовуй:\n"
            "/add_executor <імʼя> — надішле посилання-інвайт, виконавець зареєструється сам\n"
            "/add_executor <telegram_id> <імʼя> — додати вручну, якщо ID вже відомий")
        return
    if len(args) >= 2 and args[0].lstrip("-").isdigit():
        uid = int(args[0])
        name = " ".join(args[1:]).strip()
        db.add_executor(name, uid)
        await update.message.reply_text(f"✅ Виконавця {name} (id {uid}) додано.")
        return
    name = " ".join(args).strip()
    token = secrets.token_urlsafe(6)
    db.create_invite(token, name)
    await update.message.reply_text(
        f"🔗 Посилання-інвайт для {name}:\n"
        f"https://t.me/{ctx.bot.username}?start=invite_{token}\n\n"
        f"Надішли його виконавцю — після переходу за посиланням він автоматично "
        f"зареєструється, без введення ID.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_bot.py -v -k add_executor`
Expected: 3 passed

- [ ] **Step 5: Write the failing tests for `cmd_start` invite handling**

Append to `tests/test_bot.py`:

```python
def make_start_update(user_id, args):
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = args
    return update, ctx


def test_start_with_valid_invite_token_registers_executor():
    bot.db = MagicMock()
    bot.tg_bot = MagicMock()
    bot.tg_bot.send_message = AsyncMock()
    bot.config.VITALY_USER_ID = 1
    bot.db.get_invite_by_token.return_value = {
        "token": "abc123", "name": "Оля", "used_at": None}
    update, ctx = make_start_update(555, ["invite_abc123"])
    asyncio.run(bot.cmd_start(update, ctx))
    bot.db.add_executor.assert_called_once_with("Оля", 555)
    bot.db.mark_invite_used.assert_called_once_with("abc123")
    bot.tg_bot.send_message.assert_called_once()
    args_call, _ = bot.tg_bot.send_message.call_args
    assert args_call[0] == 1


def test_start_with_used_invite_token_falls_back_to_unregistered_flow():
    bot.db = MagicMock()
    bot.tg_bot = MagicMock()
    bot.tg_bot.send_message = AsyncMock()
    bot.config.VITALY_USER_ID = 1
    bot.db.get_invite_by_token.return_value = {
        "token": "abc123", "name": "Оля", "used_at": "2026-06-28T10:00:00+00:00"}
    bot.db.get_executor_by_user_id.return_value = None
    update, ctx = make_start_update(555, ["invite_abc123"])
    asyncio.run(bot.cmd_start(update, ctx))
    bot.db.add_executor.assert_not_called()
    update.message.reply_text.assert_called_once()
    assert "555" in update.message.reply_text.call_args.args[0]


def test_start_without_args_unchanged_for_owner():
    bot.db = MagicMock()
    bot.config.VITALY_USER_ID = 1
    update, ctx = make_start_update(1, [])
    asyncio.run(bot.cmd_start(update, ctx))
    update.message.reply_text.assert_called_once()
    assert "Привіт" in update.message.reply_text.call_args.args[0]
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `python -m pytest tests/test_bot.py -v -k start_with`
Expected: FAIL on the first two — `cmd_start` ignores `ctx.args` entirely today, so `add_executor`/`mark_invite_used` are never called and the reply text doesn't match. The third test should already pass.

- [ ] **Step 7: Add invite handling to `cmd_start`**

In `app/bot.py`, find the start of `cmd_start`:

```python
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id == config.VITALY_USER_ID:
```

Replace with:

```python
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    args = ctx.args or []
    if args and args[0].startswith("invite_"):
        token = args[0][len("invite_"):]
        invite = db.get_invite_by_token(token)
        if invite and not invite["used_at"]:
            db.add_executor(invite["name"], user_id)
            db.mark_invite_used(token)
            await update.message.reply_text(
                "Привіт! Сюди надходитимуть задачі. Відповідай мені (текстом або голосом), "
                "коли змінюється статус: «роблю», «готово», «застряг»."
            )
            await tg_bot.send_message(
                config.VITALY_USER_ID,
                f"✅ Виконавець {invite['name']} (id {user_id}) зареєстрований за посиланням.")
            return
        # invalid or already-used token → fall through to the normal flow below
    if user_id == config.VITALY_USER_ID:
```

(Everything after this line in `cmd_start` is unchanged.)

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/test_bot.py -v -k start_with`
Expected: 3 passed

- [ ] **Step 9: Run the full test suite**

Run: `python -m pytest tests/ -v`
Expected: all passed

- [ ] **Step 10: Update `/start` help text and commit**

In `app/bot.py`, in `cmd_start`'s owner-branch help text, update the `/add_executor` line to reflect the new usage. Find:

```python
            "/add_executor 1680472982 Вадім — додати виконавця (id та імʼя, без дужок)\n"
```

Replace with:

```python
            "/add_executor Вадім — надіслати інвайт-посилання (виконавець реєструється сам)\n"
            "/add_executor 1680472982 Вадім — додати вручну за відомим ID\n"
```

Run: `python -m pytest tests/ -v`
Expected: all passed (this help-text line isn't asserted on by any test, so no regression)

```bash
git add app/bot.py tests/test_bot.py
git commit -m "feat(bot): invite-link executor self-registration via /start payload"
```

---

### Task 8: README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Check current README content for the executor section**

Run: `grep -n "add_executor" README.md`

- [ ] **Step 2: Update the documented command usage**

Open `README.md`, find the line(s) documenting `/add_executor <telegram_id> <name>` and add a line above it documenting the new invite-link flow:

```markdown
- `/add_executor <імʼя>` — надсилає посилання-інвайт; виконавець переходить за ним і реєструється сам (без ручного ID).
- `/add_executor <telegram_id> <імʼя>` — додає виконавця вручну, якщо ID вже відомий.
```

Also add a short note near the task lifecycle / reminders section (wherever deadlines/reminders are currently documented) describing the two new behaviors:

```markdown
- Якщо задача (своя чи делегована) лишається в статусі `pending` довше `NOT_STARTED_REMINDER_MINUTES` (дефолт 30 хв), бот шле нагадування "не взяв в роботу".
- Після дедлайну, поки задача не `done`/`cancelled`, бот шле повторне нагадування кожні `OVERDUE_REPEAT_HOURS` (дефолт 1 год) — виконавцю і власнику для делегованих задач, тільки власнику для власних.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document invite-link executor registration and new reminder timers"
```

---

## Final verification

- [ ] Run the entire suite once more from the repo root: `python -m pytest tests/ -v`
- [ ] Expected: all tests pass, no warnings about unused mocks/imports.
- [ ] Manually re-read `docs/superpowers/specs/2026-06-28-reminders-and-invite-design.md` against the diff (`git diff master -- app/`) to confirm every section of the spec has corresponding code.
