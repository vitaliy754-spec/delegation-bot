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
