import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
GOOGLE_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "")
GOOGLE_CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "")
GOOGLE_TOKEN_PATH = os.environ.get("GOOGLE_TOKEN_PATH", "")
GCAL_ENABLED = bool(GOOGLE_CALENDAR_ID and GOOGLE_TOKEN_PATH)
VITALY_USER_ID = int(os.environ["VITALY_USER_ID"])
# Optional: a single default executor (back-compat). If set, it is seeded into the
# executors registry at startup so single-executor setups work without /add_executor.
ASSISTANT_USER_ID = int(os.environ["ASSISTANT_USER_ID"]) if os.environ.get("ASSISTANT_USER_ID") else None
DB_PATH = os.environ["DB_PATH"]
TZ = os.environ.get("TZ", "Europe/Kyiv")
# Hour (0-23) for the daily morning digest of the owner's tasks.
MORNING_DIGEST_HOUR = int(os.environ.get("MORNING_DIGEST_HOUR", "9"))
# Hour (0-23) for the daily evening digest (done today + tasks for tomorrow).
EVENING_DIGEST_HOUR = int(os.environ.get("EVENING_DIGEST_HOUR", "19"))
# Default follow-up delay (hours) for a delegated task without explicit reminders.
FOLLOWUP_DELAY_HOURS = int(os.environ.get("FOLLOWUP_DELAY_HOURS", "24"))
# Minutes after task creation before nagging if status is still 'pending'.
NOT_STARTED_REMINDER_MINUTES = int(os.environ.get("NOT_STARTED_REMINDER_MINUTES", "30"))
# Hours between repeated overdue reminders once the deadline has passed.
OVERDUE_REPEAT_HOURS = int(os.environ.get("OVERDUE_REPEAT_HOURS", "1"))
