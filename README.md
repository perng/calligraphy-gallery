# calligraphy-gallery

Minimal local web app for browsing and curating a calligraphy archive.

## Development setup

1. Create and activate the virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Configure the archive path if needed:

   ```bash
   cp .env.example .env
   ```

   Environment variables:

   - `CALLIGRAPHY_ARCHIVE_DIR`
     - development default: `/Users/charles/Calligraphy_Archive`
     - production can point to any other archive directory
   - `CALLIGRAPHY_DB_PATH`
     - default: `data/calligraphy.sqlite3`
   - `CALLIGRAPHY_METADATA_JSON_PATH`
     - default: `calligraphy_title_extracted.json` in the repo root
     - used as the primary source for extracted titles and metadata during import

4. Build or refresh the SQLite index:

   ```bash
   .venv/bin/python scripts/reindex.py
   ```

5. Run the app with a test server:

   ```bash
   CALLIGRAPHY_ARCHIVE_DIR=/Users/charles/Calligraphy_Archive \
   .venv/bin/uvicorn app.main:app --reload
   ```

## Current features

- SQLite-backed archive index
- import from a filesystem directory of image folders
- browse by search, person, script, period, and theme
- item detail pages with direct image serving from the archive
- local recent and most-viewed history
- metadata editing, soft delete, and restore
- JSON endpoints for items, facets, images, and history

## Notes

- The app serves image files directly from the configured archive root; no separate web server is required for development.
- In the sandbox used for automated testing here, binding a local port was blocked, so route verification was done with FastAPI's in-process test client instead.
