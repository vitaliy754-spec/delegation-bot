from unittest.mock import MagicMock
from app.intent import classify_status
import json

def test_classify_done():
    mock = MagicMock()
    mock.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps(
            {"intent":"done","note":"закрыл задачу"})))]
    )
    res = classify_status(mock, "Сделал, всё готово", task_title="Лендинг")
    assert res["intent"] == "done"
