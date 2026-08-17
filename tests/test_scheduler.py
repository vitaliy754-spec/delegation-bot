import asyncio
from datetime import datetime, timezone, timedelta
import app.scheduler as scheduler_mod
from app.scheduler import Scheduler
from app import bot

async def test_schedule_and_list(tmp_path):
    db_url = f"sqlite:///{tmp_path/'jobs.db'}"
    s = Scheduler(db_url=db_url, tz="UTC")
    s.start()
    when = datetime.now(timezone.utc) + timedelta(hours=1)
    job_id = s.schedule_reminder(task_id=1, when=when, kind="reminder")
    jobs = s.list_jobs_for_task(1)
    assert len(jobs) == 1
    s.shutdown()

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

async def test_fired_job_reaches_the_event_loop(tmp_path, monkeypatch):
    """APScheduler runs these sync job functions on a worker thread, which has no
    event loop of its own. Regression: the callback used asyncio.get_event_loop()
    there — a RuntimeError on Python 3.12+ — so every reminder and digest was
    dropped, leaving nothing but an hourly traceback in the logs."""
    delivered = asyncio.Queue()

    async def fake_fire_async(task_id, kind):
        await delivered.put((task_id, kind))

    monkeypatch.setattr(bot, "_fire_async", fake_fire_async)
    monkeypatch.setattr(bot, "main_loop", asyncio.get_running_loop())
    monkeypatch.setattr(scheduler_mod, "_callback", bot.on_scheduler_fire)

    s = Scheduler(db_url=f"sqlite:///{tmp_path/'jobs_fire.db'}", tz="UTC")
    s.start()
    s.schedule_reminder(
        task_id=9, when=datetime.now(timezone.utc) + timedelta(seconds=1),
        kind="reminder")
    try:
        assert await asyncio.wait_for(delivered.get(), timeout=10) == (9, "reminder")
    finally:
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
