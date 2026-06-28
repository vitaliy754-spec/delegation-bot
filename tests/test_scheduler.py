import asyncio
from datetime import datetime, timezone, timedelta
from app.scheduler import Scheduler

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

async def test_cancel_task_jobs_removes_interval_job(tmp_path):
    db_url = f"sqlite:///{tmp_path/'jobs3.db'}"
    s = Scheduler(db_url=db_url, tz="UTC")
    s.start()
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    s.schedule_interval(task_id=4, kind="overdue_repeat", start=start, hours=1)
    s.cancel_task_jobs(4)
    assert s.list_jobs_for_task(4) == []
    s.shutdown()
