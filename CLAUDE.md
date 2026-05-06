# Kindle-Notion Sync
   
   ## What this is
   A personal automation tool that syncs PDFs between a Notion database 
   and a Kindle Scribe. PDFs added to Notion are emailed to the Scribe; 
   annotated PDFs returned via Kindle's "Export Notebook" feature are 
   matched back to their Notion row and uploaded to replace the original.
   
    ## Architecture
    - Python 3.11+ with Flask (later) and standard libraries
    - Notion API for database operations (incl. File Upload API for annotated PDFs)
    - Gmail API (OAuth 2.0) for sending to Kindle and receiving exports
    - Currently running on local machine; will migrate to Pi/VPS later

    ## Authentication
    - Notion: integration token in .env
    - Gmail: OAuth 2.0 with credentials.json (downloaded from Google Cloud Console)
    and token.json (auto-generated on first auth, cached for refresh)
    - All credential files are gitignored
   
   ## Build phases
   See PLAN.md for the phased build plan. Currently working on: Phase X.
   
   ## Conventions
   - Secrets live in .env, never committed
   - All API clients wrapped in their own modules (notion_client.py, etc.)
   - Logging via Python's logging module to both stdout and sync.log
   - Filename convention for round-trip matching: {title} [{page_id_prefix}].pdf
   
   ## Testing approach
   - Each module has a __main__ block that lets it run standalone for testing
   - Real API calls during development are fine; we're our own user