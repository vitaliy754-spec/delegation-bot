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

def test_create_task_with_expected_result():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = Db(path); db.init_schema()
    tid = db.create_task(chat_id=1, assistant_user_id=2, title="t",
                        description="d", deadline=None, gcal_event_id="e",
                        expected_result="фото квитанції")
    task = db.get_task(tid)
    assert task["expected_result"] == "фото квитанції"

def test_create_task_without_expected_result_defaults_none():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = Db(path); db.init_schema()
    tid = db.create_task(chat_id=1, assistant_user_id=2, title="t",
                        description="d", deadline=None, gcal_event_id="e")
    assert db.get_task(tid)["expected_result"] is None

def test_update_status_logs():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = Db(path); db.init_schema()
    tid = db.create_task(chat_id=1, assistant_user_id=2, title="t",
                        description="d", deadline=None, gcal_event_id="e")
    db.update_status(tid, "in_progress", note="делаю")
    log = db.get_status_log(tid)
    assert log[-1]["status"] == "in_progress"

def test_executors_registry():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = Db(path); db.init_schema()
    db.add_executor("Оля", 111)
    db.add_executor("Петя", 222)
    assert db.get_executor_by_user_id(111)["name"] == "Оля"
    # fuzzy name lookup is case-insensitive
    matches = db.get_executors_by_name("оля")
    assert len(matches) == 1 and matches[0]["telegram_user_id"] == 111
    # re-adding same user_id updates the name (upsert), not duplicates
    db.add_executor("Ольга", 111)
    assert db.get_executor_by_user_id(111)["name"] == "Ольга"
    assert len(db.list_executors()) == 2
    # unknown name → no matches
    assert db.get_executors_by_name("Вася") == []
