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
