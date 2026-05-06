"""Find Kindle Export Notebook emails and push the annotated PDFs back into Notion.

Standalone run (one cycle, then exit):
    uv run python gmail_poller.py

For continuous always-on polling combined with the outbound side, use main.py.

Per unread Amazon export email: parse the page-id prefix from the subject,
decode the pre-signed S3 URL embedded in the Amazon redirect, download,
upload to Notion, attach to the matching page, and mark the email read.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import sys
import tempfile
import urllib.parse
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.discovery import build
from notion_client import Client

from gmail_auth import get_credentials
from notion_poller import download_pdf, get_data_source_id, page_title

logger = logging.getLogger(__name__)

SEARCH_QUERY = (
    '(subject:"from their Kindle" OR subject:"from your Kindle") '
    'from:do-not-reply@amazon.com is:unread'
)
SUBJECT_PREFIX_PATTERN = re.compile(r"\[([0-9a-f]{8})\]")


class DownloadLinkExtractor(HTMLParser):
    """First <a> whose visible text contains 'Download PDF' wins."""

    def __init__(self) -> None:
        super().__init__()
        self.current_href: str | None = None
        self.current_text: list[str] = []
        self.found_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a" and self.found_href is None:
            self.current_href = next((v for k, v in attrs if k == "href"), None)
            self.current_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.current_href and self.found_href is None:
            text = "".join(self.current_text).strip()
            if "Download PDF" in text:
                self.found_href = self.current_href
            self.current_href = None
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href is not None:
            self.current_text.append(data)


def extract_html_body(payload: dict) -> str | None:
    if payload.get("mimeType") == "text/html" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode(
            "utf-8", errors="replace"
        )
    for part in payload.get("parts", []) or []:
        body = extract_html_body(part)
        if body:
            return body
    return None


def extract_download_url(html_body: str) -> str | None:
    parser = DownloadLinkExtractor()
    parser.feed(html_body)
    href = parser.found_href
    if not href:
        return None
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
    return qs.get("U", [None])[0]


def header(message: dict, name: str) -> str | None:
    for h in message.get("payload", {}).get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None


def upload_to_notion(notion: Client, pdf_path: Path, filename: str) -> str:
    """Upload PDF to Notion via the File Upload API. Returns the file_upload ID."""
    upload = notion.file_uploads.create(
        mode="single_part",
        filename=filename,
        content_type="application/pdf",
    )
    with pdf_path.open("rb") as f:
        notion.file_uploads.send(
            file_upload_id=upload["id"],
            file=(filename, f, "application/pdf"),
        )
    return upload["id"]


def update_notion_page(
    notion: Client, page_id: str, upload_id: str, filename: str
) -> None:
    """Attach uploaded file to the page, mark Synced, stamp Last Synced."""
    notion.pages.update(
        page_id=page_id,
        properties={
            "PDF": {
                "files": [
                    {
                        "type": "file_upload",
                        "name": filename,
                        "file_upload": {"id": upload_id},
                    }
                ]
            },
            "Status": {"select": {"name": "Synced"}},
            "Last Synced": {
                "date": {"start": datetime.now(timezone.utc).isoformat()}
            },
        },
    )


def process_export(
    service, notion: Client, pages_by_prefix: dict, message_id: str
) -> None:
    """Handle one export email end-to-end."""
    msg = (
        service.users().messages().get(userId="me", id=message_id, format="full").execute()
    )
    subject = header(msg, "Subject") or "(no subject)"
    prefix_match = SUBJECT_PREFIX_PATTERN.search(subject)
    prefix = prefix_match.group(1) if prefix_match else None
    matching_page = pages_by_prefix.get(prefix) if prefix else None
    html = extract_html_body(msg.get("payload", {}))
    url = extract_download_url(html) if html else None
    title = page_title(matching_page) if matching_page else None

    logger.info("---")
    logger.info("Message id : %s", message_id)
    logger.info("Subject    : %s", subject)
    logger.info("Page prefix: %s", prefix or "(not found)")
    if matching_page:
        logger.info("Notion page: %s — '%s'", matching_page["id"], title)
    else:
        logger.info("Notion page: (no match)")

    if not url:
        logger.info("URL        : (not found)")
        return

    logger.info("URL host   : %s", urllib.parse.urlparse(url).netloc)
    with tempfile.TemporaryDirectory(prefix="kns-inbound-") as tmpdir:
        local = Path(tmpdir) / "annotated.pdf"
        download_pdf(url, local)
        size_mb = local.stat().st_size / 1024 / 1024
        logger.info("Downloaded : %.2f MB", size_mb)
        if not matching_page:
            logger.info("Upload     : skipped (no matching page)")
            return
        upload_filename = f"{title} [{prefix}].pdf"
        upload_id = upload_to_notion(notion, local, upload_filename)
        logger.info("Uploaded   : %s (id %s)", upload_filename, upload_id)
        update_notion_page(notion, matching_page["id"], upload_id, upload_filename)
        logger.info("Page update: Status=Synced, Last Synced=now")
        service.users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
        ).execute()
        logger.info("Marked read: %s", message_id)


def poll_once(service, notion: Client, data_source_id: str) -> None:
    """One inbound polling iteration: process all unread Kindle exports."""
    listing = service.users().messages().list(userId="me", q=SEARCH_QUERY).execute()
    matches = listing.get("messages", [])
    if not matches:
        return
    pages = notion.data_sources.query(data_source_id=data_source_id).get("results", [])
    pages_by_prefix = {p["id"].replace("-", "")[:8]: p for p in pages}
    logger.info(
        "Found %d email(s); indexed %d Notion page(s).", len(matches), len(pages)
    )
    for m in matches:
        try:
            process_export(service, notion, pages_by_prefix, m["id"])
        except Exception:
            logger.exception("Failed to process email %s", m["id"])


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    load_dotenv()
    service = build("gmail", "v1", credentials=get_credentials())
    notion = Client(auth=os.environ["NOTION_TOKEN"])
    data_source_id = get_data_source_id(notion, os.environ["NOTION_DATABASE_ID"])
    poll_once(service, notion, data_source_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
