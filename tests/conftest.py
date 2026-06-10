import os

# Dummy env so importing app.config / app.bot works in tests without real secrets.
# ASSISTANT_USER_ID is intentionally left unset (it is optional).
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("VITALY_USER_ID", "1")
os.environ.setdefault("DB_PATH", "./data/test.db")
os.environ.setdefault("TZ", "Europe/Kyiv")
