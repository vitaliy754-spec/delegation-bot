import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
GOOGLE_CALENDAR_ID = os.environ["GOOGLE_CALENDAR_ID"]
GOOGLE_CREDENTIALS_PATH = os.environ["GOOGLE_CREDENTIALS_PATH"]
GOOGLE_TOKEN_PATH = os.environ["GOOGLE_TOKEN_PATH"]
ALLOWED_CHAT_ID = int(os.environ["ALLOWED_CHAT_ID"])
VITALY_USER_ID = int(os.environ["VITALY_USER_ID"])
ASSISTANT_USER_ID = int(os.environ["ASSISTANT_USER_ID"])
DB_PATH = os.environ["DB_PATH"]
TZ = os.environ.get("TZ", "Europe/Kyiv")
