from unittest.mock import MagicMock
from datetime import datetime, timezone
from app.parser import parse_task
import json

def test_parse_task_basic():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({
            "title": "Лендинг",
            "description": "Сделать лендинг до завтра 18:00",
            "deadline": "2026-05-03T18:00:00+03:00",
            "reminders": [{"when": "2026-05-02T20:00:00+03:00", "text": None}],
        })))]
    )
    spec = parse_task(
        client=mock_client,
        transcript="Сделай лендинг до завтра 18:00, напомни сегодня в 20:00",
        now=datetime(2026,5,2,15,0,tzinfo=timezone.utc),
        tz="Europe/Kyiv",
    )
    assert spec.title == "Лендинг"
    assert len(spec.reminders) == 1
    assert spec.assignee is None  # not specified → defaults to None

def test_parse_task_assignee():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({
            "title": "Лендинг",
            "description": "Сделать лендинг",
            "assignee": "Оля",
            "deadline": None,
            "reminders": [],
        })))]
    )
    spec = parse_task(
        client=mock_client,
        transcript="поручи Оле сделать лендинг",
        now=datetime(2026, 5, 2, 15, 0, tzinfo=timezone.utc),
        tz="Europe/Kyiv",
        known_executors=["Оля", "Петя"],
    )
    assert spec.assignee == "Оля"

def test_parse_task_expected_result():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({
            "title": "Оплата оренди",
            "description": "Оплатити оренду офісу",
            "deadline": None,
            "reminders": [],
            "expected_result": "фото квитанції",
        })))]
    )
    spec = parse_task(
        client=mock_client,
        transcript="оплати оренду, результат — фото квитанції",
        now=datetime(2026, 5, 2, 15, 0, tzinfo=timezone.utc),
        tz="Europe/Kyiv",
    )
    assert spec.expected_result == "фото квитанції"

def test_parse_deadline_value_and_none():
    from app.parser import parse_deadline
    mock = MagicMock()
    mock.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps(
            {"deadline": "2026-05-03T18:00:00+03:00"})))]
    )
    dl = parse_deadline(mock, "завтра о 18:00",
                        datetime(2026, 5, 2, 15, 0, tzinfo=timezone.utc), "Europe/Kyiv")
    assert dl is not None and dl.hour == 18

    mock.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({"deadline": None})))]
    )
    assert parse_deadline(mock, "без дедлайну",
                          datetime(2026, 5, 2, 15, 0, tzinfo=timezone.utc), "Europe/Kyiv") is None
