from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from app.gcal import GCalClient

def test_create_event_calls_api():
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {"id": "evt123"}
    with patch("app.gcal.build", return_value=fake_service), \
         patch("app.gcal.GCalClient._creds", return_value=MagicMock()):
        c = GCalClient(calendar_id="cal", token_path="t", credentials_path="c")
        eid = c.create_event(
            title="T", description="D",
            start=datetime(2026,5,3,17,0,tzinfo=timezone.utc),
            end=datetime(2026,5,3,18,0,tzinfo=timezone.utc),
        )
    assert eid == "evt123"
