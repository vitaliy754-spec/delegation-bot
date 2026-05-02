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
