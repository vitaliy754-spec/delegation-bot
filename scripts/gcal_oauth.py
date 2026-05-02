"""One-time OAuth flow. Run locally:
   python scripts/gcal_oauth.py
   Then upload data/token.json to Railway volume."""
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def main():
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", "data/credentials.json")
    token_path = os.environ.get("GOOGLE_TOKEN_PATH", "data/token.json")
    flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
    creds = flow.run_local_server(port=0)
    os.makedirs(os.path.dirname(token_path), exist_ok=True)
    with open(token_path, "w") as f:
        f.write(creds.to_json())
    print(f"Saved token to {token_path}")

if __name__ == "__main__":
    main()
