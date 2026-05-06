"""Combined sync loop: outbound (Notion -> Kindle) and inbound (Gmail -> Notion).

Standalone run:
    uv run python main.py

For auto-start on login, install the launchd plist (see README → "Run as a
launchd agent").

Each iteration: run one outbound poll, then one inbound poll, then sleep.
Both polls are wrapped so a transient failure (Gmail timeout, Notion 500)
just gets logged and we retry next loop instead of crashing.
"""

from __future__ import annotations

import logging
import os
import sys
import time

from dotenv import load_dotenv
from googleapiclient.discovery import build
from notion_client import Client

from gmail_auth import get_credentials
from gmail_poller import poll_once as gmail_poll_once
from notion_poller import get_data_source_id, poll_once as notion_poll_once

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 60


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("sync.log"),
        ],
    )
    load_dotenv()
    notion = Client(auth=os.environ["NOTION_TOKEN"])
    data_source_id = get_data_source_id(notion, os.environ["NOTION_DATABASE_ID"])
    gmail = build("gmail", "v1", credentials=get_credentials())

    logger.info(
        "Sync started; poll interval %ds. Ctrl+C to stop.", POLL_INTERVAL_SECONDS
    )
    try:
        while True:
            try:
                notion_poll_once(notion, data_source_id)
            except Exception:
                logger.exception("Outbound poll failed; will retry next cycle")
            try:
                gmail_poll_once(gmail, notion, data_source_id)
            except Exception:
                logger.exception("Inbound poll failed; will retry next cycle")
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
