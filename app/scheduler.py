from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# Job callbacks registered at runtime via set_callback / set_daily_callback
_callback = None
_daily_callback = None

def _fire(task_id: int, kind: str):
    if _callback:
        _callback(task_id, kind)

def _fire_daily(which: str = "morning"):
    if _daily_callback:
        _daily_callback(which)

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

    def set_daily_callback(self, fn):
        global _daily_callback
        _daily_callback = fn

    def schedule_daily(self, which: str, hour: int, minute: int = 0) -> str:
        """Daily digest job ('morning'/'evening') at the given hour (scheduler timezone)."""
        jid = f"daily-{which}"
        self.scheduler.add_job(
            _fire_daily, CronTrigger(hour=hour, minute=minute),
            args=[which], id=jid, replace_existing=True,
        )
        return jid

    def schedule_reminder(self, task_id: int, when: datetime, kind: str) -> str:
        jid = f"task{task_id}-{kind}-{int(when.timestamp())}"
        self.scheduler.add_job(
            _fire, DateTrigger(run_date=when),
            args=[task_id, kind],
            id=jid, replace_existing=True,
        )
        return jid

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

    def list_jobs_for_task(self, task_id: int):
        return [j for j in self.scheduler.get_jobs()
                if j.id.startswith(f"task{task_id}-")]

    def cancel_task_jobs(self, task_id: int):
        for j in self.list_jobs_for_task(task_id):
            j.remove()

    def remove_job(self, job_id: str):
        """Remove a job by id if it exists (used to clean up legacy jobs)."""
        job = self.scheduler.get_job(job_id)
        if job:
            job.remove()
