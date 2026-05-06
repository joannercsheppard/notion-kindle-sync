# Kindle-Notion Sync — Build Plan

## Phase 0: Prerequisites (30 minutes)

Before writing any code, gather these. Doing this upfront saves a lot of context-switching later.

1. Install Python 3.11+ on your computer if not already there. Verify with `python3 --version` in terminal.
2. Install a code editor if you don't have one (VS Code is free and good).
3. Create a project folder:
   ```bash
   mkdir kindle-notion-sync && cd kindle-notion-sync
   ```
4. Set up a Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate   # Mac/Linux
   venv\Scripts\activate      # Windows
   ```
5. Install the libraries you'll need:
   ```bash
   pip install google-auth google-auth-oauthlib google-auth-httplib2 \
               google-api-python-client notion-client requests \
               python-dotenv flask
   ```

## Phase 1: Account setup and credentials (45 minutes)

This is the boring but necessary part. You're collecting the credentials you'll need.

1. **Find your Kindle email address.** Go to amazon.com → Account → Manage Your Content and Devices → Preferences → Personal Document Settings. You'll see your Scribe listed with an email like `yourname_xxxxx@kindle.com`. Save this.
2. **Add an approved sender email.** On the same page, scroll to "Approved Personal Document Email List" and add the Gmail address you'll send from. Amazon will reject emails from unapproved senders.
3. **Set up Gmail API access via OAuth 2.0:**
   1. Create a Google Cloud project at [console.cloud.google.com](https://console.cloud.google.com).
   2. Enable the Gmail API for the project.
   3. Configure the OAuth consent screen (External, add yourself as a test user).
   4. Create OAuth 2.0 Desktop client credentials.
   5. Download `credentials.json` to your project folder, add it to `.gitignore`.
   6. `token.json` will be created automatically on first authentication.
4. **Create a Notion integration.** Go to [notion.so/my-integrations](https://www.notion.so/my-integrations) → New Integration → name it "Kindle Sync," select your workspace, give it read/write content permissions. Save the integration token (starts with `secret_` or `ntn_`).
5. **Create the Notion database.** In Notion, create a new page with a database. Add these properties:
   - **Title** (default)
   - **PDF** (Files & media)
   - **Status** (Select type with values "New," "On Kindle," "Annotated," "Synced")
   - **Date Added** (Created time)
   - **Last Synced** (Date)
6. **Connect the integration to your database.** Open the database as a full page → click the three dots top right → Connections → add "Kindle Sync." Without this step, the integration can't see the database.
7. **Get the database ID.** Open the database as a page, copy the URL. The ID is the 32-character string between the last `/` and the `?`. Save it.

## Phase 2: Build the outbound pipe (Day 1 milestone — ~2 hours)

**Goal:** drag a PDF into Notion, watch it appear on your Scribe within a minute.

1. Create a `.env` file in your project folder with your credentials:
   ```
   NOTION_TOKEN=ntn_...
   NOTION_DATABASE_ID=...
   GMAIL_USER=youremail@gmail.com
   KINDLE_EMAIL=yourname_xxxxx@kindle.com
   APPROVED_SENDER=youremail@gmail.com
   ```
2. Add `.env` to your `.gitignore` so you never commit secrets.
3. Write a simple script `send_to_kindle.py` that takes a PDF file path and emails it to your Kindle. Test it standalone first — if you can email a PDF to your Scribe and see it appear, this piece works.
4. Write a script `notion_poller.py` that:
   - Queries your Notion database every 60 seconds.
   - Finds rows with Status = "New" that have a PDF attached.
   - Downloads the PDF, calls `send_to_kindle.py`.
   - Updates the row to Status = "On Kindle."

   Polling is simpler than webhooks for the first version — no public URL needed.
5. Run it: `python notion_poller.py`. Drag a PDF into a new row in Notion, watch your terminal logs, watch your Scribe.
6. Celebrate — you have a working outbound sync. Stop here for the day if you want.

## Phase 3: Build the inbound pipe (Day 2 milestone — ~2 hours)

**Goal:** press Export Notebook on Scribe, watch the annotated PDF appear back in Notion.

1. Send yourself one Export Notebook email manually so you can inspect it. **Note:** the email contains a 7-day download link, *not* a direct attachment. Capture:
   - The exact From address.
   - The subject line.
   - The "Download PDF" link target (right-click the link → Copy link address).
2. Write `gmail_poller.py` that connects to Gmail via the Gmail API, searches for unread messages matching the export sender (filter by From + subject), and extracts the download URL from the HTML body. Test in isolation first.
3. **Match filename to Notion page.** Each PDF sent to Kindle has a filename like `{title} [{page_id_prefix}].pdf` (set in Phase 2). The export preserves that bracketed prefix. Parse `\[([0-9a-f]{8})\]` from the filename in the email, then find the Notion page whose ID starts with that prefix.
4. **Download the annotated PDF** with `requests.get(url)` against the link from step 2. The link is signed and time-bound — fetch promptly and don't retry it days later.
5. **Upload the PDF to Notion via the File Upload API.** Notion's flow: initiate an upload to get an upload URL + ID, push the PDF bytes, then reference the resulting upload ID in the file property. Education Plus accounts allow up to 5 GB per file, so any annotated PDF will fit.
6. **Update the Notion page.** Replace the PDF property with the new file (by upload ID), set Status to "Synced," set Last Synced to now.
7. **Run end-to-end:** drag a new PDF into Notion → wait for it on Scribe → annotate a few pages → tap Export Notebook → wait up to 60 seconds → check Notion. The PDF should be replaced with your annotated version.

## Phase 4: Make it always-on (~1 hour)

**Goal:** don't have to remember to run scripts manually.

1. Combine `notion_poller.py` and `gmail_poller.py` into a single `main.py` that runs both loops. (Either as two threads, or alternating in one loop — threading is fine for this volume.)
2. Set it to start on login:
   - **Mac:** create a launchd plist file in `~/Library/LaunchAgents/`.
   - **Windows:** create a Task Scheduler entry for "At log on."
   - **Linux:** systemd user service.
3. Add basic logging to a file so you can diagnose issues without watching the terminal.
4. Add error handling so transient failures (Gmail timeout, Notion 500) don't crash the script — just log and retry next loop.

## Phase 5: Quality of life (optional, ongoing)

Things to add once the core works and you find yourself wanting them.

- **Slack/Discord webhook notifications** when sync happens, so you know without checking Notion.
- **OCR pass** on annotated PDFs using Claude's vision API or Google Vision. Extract handwritten text and dump into a Notion "Notes" property to make handwriting searchable.
- **Smart deduplication** — if you Export Notebook twice on the same article, only keep the latest version.
- **Migration to a Pi or VPS** so it runs without your computer being on.
- **Status dashboard** — a small Flask page on localhost showing recent sync history, errors, and pending items.
