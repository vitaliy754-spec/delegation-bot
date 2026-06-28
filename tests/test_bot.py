from datetime import datetime, timezone, timedelta
from app.bot import default_reminder_times, delegated_tracking_times, clean_command_args
from app.bot import _task_kb
from app import bot


def test_clean_command_args_strips_angle_brackets():
    assert clean_command_args(["<1680472982>", "<Вадім>"]) == ["1680472982", "Вадім"]
    assert clean_command_args(["1680472982", "Вадім"]) == ["1680472982", "Вадім"]
    assert clean_command_args(["<123>"]) == ["123"]
    assert clean_command_args(None) == []
    assert clean_command_args(["  ", "<>"]) == []


def test_delegated_tracking_times_midpoint_and_80pct():
    # deadline in 10h → midpoint at +5h, status check at +8h (20% left)
    now = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    deadline = now + timedelta(hours=10)
    mid, status = delegated_tracking_times(deadline, now)
    assert mid == now + timedelta(hours=5)
    assert status == now + timedelta(hours=8)

def test_default_reminders_self_offsets():
    # personal task far in the future → three offset reminders (2h/1h/15m)
    deadline = datetime.now(timezone.utc) + timedelta(days=2)
    times = default_reminder_times(deadline, to_self=True)
    assert len(times) == 3
    assert all(t < deadline for t in times)

def test_default_reminders_delegated_followup():
    # delegated task → single follow-up after the configured delay
    deadline = datetime.now(timezone.utc) + timedelta(days=2)
    times = default_reminder_times(deadline, to_self=False)
    assert len(times) == 1
    assert times[0] > datetime.now(timezone.utc)

def test_default_reminders_drops_past_offsets():
    # deadline very soon → past offsets (2h/1h) dropped, only future kept
    deadline = datetime.now(timezone.utc) + timedelta(minutes=10)
    times = default_reminder_times(deadline, to_self=True)
    assert all(t > datetime.now(timezone.utc) for t in times)

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
