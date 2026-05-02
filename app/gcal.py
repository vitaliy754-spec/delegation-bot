from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]

class GCalClient:
    def __init__(self, calendar_id, token_path, credentials_path):
        self.calendar_id = calendar_id
        self.token_path = token_path
        self.credentials_path = credentials_path
        self.service = build("calendar", "v3", credentials=self._creds())

    def _creds(self):
        creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        if not creds.valid and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(self.token_path, "w") as f:
                f.write(creds.to_json())
        return creds

    def create_event(self, title, description, start: datetime, end: datetime = None):
        end = end or (start + timedelta(minutes=30))
        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start.isoformat()},
            "end":   {"dateTime": end.isoformat()},
        }
        evt = self.service.events().insert(calendarId=self.calendar_id, body=body).execute()
        return evt["id"]

    def append_to_description(self, event_id, line: str):
        evt = self.service.events().get(calendarId=self.calendar_id, eventId=event_id).execute()
        desc = (evt.get("description") or "") + "\n" + line
        self.service.events().patch(
            calendarId=self.calendar_id, eventId=event_id,
            body={"description": desc}).execute()

    def update_summary(self, event_id, prefix: str):
        evt = self.service.events().get(calendarId=self.calendar_id, eventId=event_id).execute()
        title = evt.get("summary", "")
        if not title.startswith(prefix):
            self.service.events().patch(
                calendarId=self.calendar_id, eventId=event_id,
                body={"summary": f"{prefix}{title}"}).execute()
