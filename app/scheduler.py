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
