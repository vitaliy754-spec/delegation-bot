"""Pure helpers that split the owner's tasks into digest buckets.

Kept free of bot/db singletons so they can be unit-tested. Each task is a dict
with at least: 'status', 'deadline' (ISO str or None), 'updated_at' (ISO str).
Dates are compared in Kyiv local time via timefmt.to_kyiv.
"""
from datetime import date
from app.timefmt import to_kyiv

ACTIVE_EXCLUDED = ("done", "cancelled")


def _deadline_date(task) -> date | None:
    dl = task.get("deadline")
    return to_kyiv(dl).date() if dl else None


def split_morning(tasks: list[dict], today: date) -> tuple[list[dict], list[dict]]:
    """Morning digest: (tasks due today, overdue/unfinished tasks).

    'today'   — active tasks whose deadline date is today.
    'overdue' — active tasks whose deadline date is before today (not done).
    """
    todays, overdue = [], []
    for t in tasks:
        if t["status"] in ACTIVE_EXCLUDED:
            continue
        d = _deadline_date(t)
        if d == today:
            todays.append(t)
        elif d is not None and d < today:
            overdue.append(t)
    return todays, overdue


def split_evening(tasks: list[dict], today: date, tomorrow: date) -> tuple[list[dict], list[dict]]:
    """Evening digest: (tasks completed today, tasks due tomorrow).

    'done today'    — status 'done' whose last update (updated_at) is today.
    'tomorrow'      — active tasks whose deadline date is tomorrow.
    """
    done_today, tomorrow_tasks = [], []
    for t in tasks:
        if t["status"] == "done":
            ud = t.get("updated_at")
            if ud and to_kyiv(ud).date() == today:
                done_today.append(t)
        elif t["status"] != "cancelled":
            if _deadline_date(t) == tomorrow:
                tomorrow_tasks.append(t)
    return done_today, tomorrow_tasks
