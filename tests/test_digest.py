from datetime import date
from app.digest import split_morning, split_evening

TODAY = date(2026, 7, 1)
TOMORROW = date(2026, 7, 2)


def _task(id, status, deadline=None, updated_at=None):
    return {"id": id, "status": status, "title": f"t{id}",
            "deadline": deadline, "updated_at": updated_at}


def test_morning_splits_today_and_overdue():
    tasks = [
        _task(1, "pending", "2026-07-01T12:00:00+03:00"),       # today
        _task(2, "in_progress", "2026-06-29T10:00:00+03:00"),   # overdue
        _task(3, "pending", "2026-07-02T10:00:00+03:00"),       # tomorrow → neither
        _task(4, "done", "2026-07-01T09:00:00+03:00"),          # done → excluded
        _task(5, "cancelled", "2026-06-28T09:00:00+03:00"),     # cancelled → excluded
        _task(6, "pending", None),                              # no deadline → neither
    ]
    todays, overdue = split_morning(tasks, TODAY)
    assert [t["id"] for t in todays] == [1]
    assert [t["id"] for t in overdue] == [2]


def test_evening_splits_done_today_and_tomorrow():
    tasks = [
        _task(1, "done", deadline="2026-07-01T10:00:00+03:00",
              updated_at="2026-07-01T12:00:00+00:00"),          # done today
        _task(2, "done", deadline=None,
              updated_at="2026-06-30T12:00:00+00:00"),          # done yesterday → excluded
        _task(3, "pending", "2026-07-02T10:00:00+03:00"),       # tomorrow
        _task(4, "in_progress", "2026-07-03T10:00:00+03:00"),   # day after → excluded
        _task(5, "cancelled", "2026-07-02T10:00:00+03:00"),     # cancelled → excluded
    ]
    done_today, tomorrow_tasks = split_evening(tasks, TODAY, TOMORROW)
    assert [t["id"] for t in done_today] == [1]
    assert [t["id"] for t in tomorrow_tasks] == [3]
