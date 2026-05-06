"""Poll Notion for new rows, download their PDFs, and send to Kindle.

Standalone run:
    uv run python notion_poller.py

Drop a PDF into a new row in Notion with Status = "New", wait up to 60s,
then watch it appear on your Scribe. Status flips to "On Kindle" after send.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import tempfile
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from notion_client import Client

from send_to_kindle import send_to_kindle

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60
TITLE_MAX_LEN = 80
PAGE_ID_PREFIX_LEN = 8
UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:"*?<>|]')


def clean_title(title: str) -> str:
    cleaned = UNSAFE_FILENAME_CHARS.sub("", title).strip()
    return cleaned[:TITLE_MAX_LEN].rstrip() or "Untitled"


def page_title(page: dict) -> str:
    title_prop = page["properties"].get("Title")
    if not title_prop or title_prop["type"] != "title":
        return "untitled"
    return "".join(t["plain_text"] for t in title_prop["title"]) or "untitled"


def page_pdf_url(page: dict) -> str | None:
    pdf_prop = page["properties"].get("PDF")
    if not pdf_prop or pdf_prop["type"] != "files" or not pdf_prop["files"]:
        return None
    f = pdf_prop["files"][0]
    if f["type"] == "file":
        return f["file"]["url"]
    if f["type"] == "external":
        return f["external"]["url"]
    return None


def kindle_filename(page_id: str, title: str) -> str:
    prefix = page_id.replace("-", "")[:PAGE_ID_PREFIX_LEN]
    return f"{clean_title(title)} [{prefix}].pdf"


def download_pdf(url: str, dest: Path) -> None:
    r = requests.get(url, stream=True, timeout=30)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=64 * 1024):
            f.write(chunk)


def get_data_source_id(notion: Client, database_id: str) -> str:
    db = notion.databases.retrieve(database_id=database_id)
    sources = db.get("data_sources", [])
    if not sources:
        raise RuntimeError(f"Database {database_id} has no data sources")
    return sources[0]["id"]


def find_new_pages(notion: Client, data_source_id: str) -> list[dict]:
    response = notion.data_sources.query(
        data_source_id=data_source_id,
        filter={
            "and": [
                {"property": "Status", "select": {"equals": "New"}},
                {"property": "PDF", "files": {"is_not_empty": True}},
            ]
        },
    )
    return response.get("results", [])


def process_page(notion: Client, page: dict) -> None:
    page_id = page["id"]
    title = page_title(page)
    pdf_url = page_pdf_url(page)
    if not pdf_url:
        logger.warning("Page %s (%s) has no PDF — skipping", page_id, title)
        return

    filename = kindle_filename(page_id, title)
    with tempfile.TemporaryDirectory(prefix="kns-") as tmpdir:
        local_path = Path(tmpdir) / filename
        logger.info("Downloading '%s' (%s) to %s", title, page_id, filename)
        download_pdf(pdf_url, local_path)
        send_to_kindle(local_path)

    notion.pages.update(
        page_id=page_id,
        properties={"Status": {"select": {"name": "On Kindle"}}},
    )
    logger.info("Page %s -> Status: On Kindle", page_id)


def poll_once(notion: Client, data_source_id: str) -> None:
    pages = find_new_pages(notion, data_source_id)
    if not pages:
        return
    logger.info("Found %d new page(s)", len(pages))
    for page in pages:
        try:
            process_page(notion, page)
        except Exception:
            logger.exception("Failed to process page %s", page["id"])


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

    logger.info("Polling Notion every %ds (Ctrl+C to stop)", POLL_INTERVAL_SECONDS)
    try:
        while True:
            poll_once(notion, data_source_id)
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
