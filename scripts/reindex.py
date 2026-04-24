from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.db import init_db
from app.importer import import_archive


def main() -> None:
    settings = get_settings()
    init_db(settings.db_path)
    stats = import_archive(settings.archive_dir, settings.db_path, settings.metadata_json_path)
    print(
        "Imported "
        f"{stats['items']} items and {stats['images']} images "
        f"(metadata matches: {stats['metadata_matches']}, "
        f"fallbacks: {stats['metadata_fallbacks']}, "
        f"skipped buckets: {stats['skipped_buckets']}, "
        f"skipped unmatched: {stats['skipped_unmatched']}, "
        f"stale items hidden: {stats['stale_items_hidden']}, "
        f"duplicate metadata titles: {stats['metadata_duplicates']})"
    )


if __name__ == "__main__":
    main()
