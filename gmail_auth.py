"""Shared Gmail OAuth credentials.

Imported by send_to_kindle.py (uses gmail.send) and gmail_poller.py (uses gmail.modify).
A single token.json covers both scopes.

If the existing token.json was issued for a narrower scope set, this module detects
that and re-runs the consent flow so the upgraded scope list takes effect.
"""

from __future__ import annotations

import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]
CREDENTIALS_FILE = Path("credentials.json")
TOKEN_FILE = Path("token.json")


def _granted_scopes(token_path: Path) -> set[str]:
    try:
        return set(json.loads(token_path.read_text()).get("scopes") or [])
    except (json.JSONDecodeError, OSError):
        return set()


def get_credentials() -> Credentials:
    creds: Credentials | None = None
    if TOKEN_FILE.exists() and set(SCOPES).issubset(_granted_scopes(TOKEN_FILE)):
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return creds
