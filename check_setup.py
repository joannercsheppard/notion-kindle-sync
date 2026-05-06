"""Phase 1 sanity check: verifies .env keys, credentials.json, and Notion connection.

Cannot verify Gmail OAuth (needs interactive consent) or Kindle email delivery —
both are first exercised in Phase 2.

Usage: uv run python check_setup.py
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from notion_client import Client
from notion_client.errors import APIResponseError

REQUIRED_ENV = [
    "NOTION_TOKEN",
    "NOTION_DATABASE_ID",
    "GMAIL_USER",
    "KINDLE_EMAIL",
    "APPROVED_SENDER",
]

REQUIRED_PROPS = {
    "Title": "title",
    "PDF": "files",
    "Status": "select",
    "Date Added": "created_time",
    "Last Synced": "date",
}

REQUIRED_STATUS_OPTIONS = {"New", "On Kindle", "Annotated", "Synced"}


def report(ok: bool, msg: str) -> bool:
    print(f"[{'OK' if ok else 'FAIL'}] {msg}")
    return ok


def main() -> int:
    load_dotenv()
    results: list[bool] = []

    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
    results.append(
        report(
            not missing,
            ".env keys present" if not missing else f".env missing: {missing}",
        )
    )

    cred_path = Path("credentials.json")
    creds_ok = False
    if cred_path.exists():
        try:
            data = json.loads(cred_path.read_text())
            creds_ok = "installed" in data or "web" in data
        except json.JSONDecodeError:
            pass
    results.append(
        report(creds_ok, "credentials.json present and looks like an OAuth client")
    )

    token = os.getenv("NOTION_TOKEN")
    db_id = os.getenv("NOTION_DATABASE_ID")
    if not (token and db_id):
        print("[SKIP] Notion checks — set NOTION_TOKEN and NOTION_DATABASE_ID first")
        return 1 if not all(results) else 0

    notion = Client(auth=token)
    try:
        db = notion.databases.retrieve(database_id=db_id)
        results.append(
            report(True, "Notion token works AND integration can see the database")
        )
    except APIResponseError as e:
        results.append(
            report(
                False,
                f"Notion API error ({e.code}): check token, DB ID, and that the integration is connected to the database",
            )
        )
        return 1

    data_sources = db.get("data_sources", [])
    if not data_sources:
        results.append(report(False, "Database has no data sources"))
        return 1
    try:
        ds = notion.data_sources.retrieve(data_source_id=data_sources[0]["id"])
    except APIResponseError as e:
        results.append(report(False, f"Data source fetch failed ({e.code})"))
        return 1
    props = ds["properties"]
    problems = []
    for name, expected_type in REQUIRED_PROPS.items():
        actual = props.get(name)
        if actual is None:
            problems.append(f"missing '{name}'")
        elif actual["type"] != expected_type:
            problems.append(
                f"'{name}' is type '{actual['type']}', expected '{expected_type}'"
            )
    results.append(
        report(
            not problems,
            "Database properties correct"
            if not problems
            else "Property issues: " + "; ".join(problems),
        )
    )

    status = props.get("Status")
    if status and status["type"] == "select":
        options = {o["name"] for o in status["select"]["options"]}
        missing_opts = REQUIRED_STATUS_OPTIONS - options
        results.append(
            report(
                not missing_opts,
                "Status options present"
                if not missing_opts
                else f"Status missing options: {missing_opts}",
            )
        )

    print()
    if all(results):
        print(
            "Phase 1 looks good. Gmail OAuth and Kindle delivery will be exercised in Phase 2."
        )
        return 0
    print("Phase 1 has issues — fix the FAILs above before moving on.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
