from datetime import datetime, timezone, timedelta
from app.bot import default_reminder_times

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
