"""Send a PDF to the Kindle via Gmail API.

Run standalone for testing:
    uv run python send_to_kindle.py path/to/your.pdf

First run pops a browser for OAuth consent and caches token.json for future
runs (refreshed automatically when expired). Subsequent runs are silent.
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.discovery import build

from gmail_auth import get_credentials

logger = logging.getLogger(__name__)

GMAIL_ATTACHMENT_LIMIT_BYTES = 18 * 1024 * 1024


def maybe_compress(pdf_path: Path) -> Path:
    """Return path to the file to actually send. Compresses to a tempfile if over the limit."""
    if pdf_path.stat().st_size <= GMAIL_ATTACHMENT_LIMIT_BYTES:
        return pdf_path
    if not shutil.which("gs"):
        raise RuntimeError(
            f"{pdf_path.name} is over Gmail's attachment limit and Ghostscript (gs) "
            "is not installed. Run `brew install ghostscript` and retry."
        )
    with tempfile.NamedTemporaryFile(suffix=".pdf", prefix="kns-", delete=False) as f:
        out = Path(f.name)
    subprocess.run(
        [
            "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/ebook", "-dNOPAUSE", "-dQUIET", "-dBATCH",
            f"-sOutputFile={out}", str(pdf_path),
        ],
        check=True,
    )
    original_mb = pdf_path.stat().st_size / 1024 / 1024
    compressed_mb = out.stat().st_size / 1024 / 1024
    logger.info(
        "Compressed %s: %.1f MB -> %.1f MB", pdf_path.name, original_mb, compressed_mb
    )
    if out.stat().st_size > GMAIL_ATTACHMENT_LIMIT_BYTES:
        out.unlink(missing_ok=True)
        raise RuntimeError(
            f"Even after compression, {pdf_path.name} is {compressed_mb:.1f} MB — "
            f"over the {GMAIL_ATTACHMENT_LIMIT_BYTES // 1024 // 1024} MB limit. "
            "Try splitting the PDF, or use a more aggressive Ghostscript preset."
        )
    return out


def send_to_kindle(pdf_path: Path, subject: str | None = None) -> str:
    """Send a PDF as an attachment to the Kindle. Returns the Gmail message ID."""
    load_dotenv()
    recipient = os.environ["KINDLE_EMAIL"]

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    to_send = maybe_compress(pdf_path)
    try:
        msg = EmailMessage()
        msg["To"] = recipient
        msg["Subject"] = subject or pdf_path.stem
        msg.set_content("Sent by kindle-notion-sync")
        msg.add_attachment(
            to_send.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=pdf_path.name,
        )

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service = build("gmail", "v1", credentials=get_credentials())
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        logger.info(
            "Sent %s to %s (gmail message id %s)", pdf_path.name, recipient, sent["id"]
        )
        return sent["id"]
    finally:
        if to_send != pdf_path:
            to_send.unlink(missing_ok=True)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("sync.log"),
        ],
    )

    if len(sys.argv) != 2:
        print("Usage: python send_to_kindle.py <path-to-pdf>", file=sys.stderr)
        return 2

    pdf = Path(sys.argv[1])
    try:
        send_to_kindle(pdf)
    except FileNotFoundError as e:
        logger.error("%s", e)
        return 1
    except Exception:
        logger.exception("Send failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
