import tempfile, os
from datetime import datetime, timezone
from app.db import Db

def test_create_and_get_task():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = Db(path)
    db.init_schema()
    tid = db.create_task(
        chat_id=1, assistant_user_id=2,
        title="t", description="d",
        deadline=datetime(2026,5,3,18,0,tzinfo=timezone.utc),
        gcal_event_id="evt1",
    )
    task = db.get_task(tid)
    assert task["title"] == "t"
    assert task["status"] == "pending"

def test_update_status_logs():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = Db(path); db.init_schema()
    tid = db.create_task(chat_id=1, assistant_user_id=2, title="t",
                        description="d", deadline=None, gcal_event_id="e")
    db.update_status(tid, "in_progress", note="делаю")
    log = db.get_status_log(tid)
    assert log[-1]["status"] == "in_progress"
