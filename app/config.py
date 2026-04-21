from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE_DIR = Path("/Users/charles/Calligraphy_Archive")
DEFAULT_DB_PATH = Path("data/calligraphy.sqlite3")
DEFAULT_METADATA_JSON_PATH = REPO_ROOT / "calligraphy_title_extracted.json"


@dataclass(frozen=True)
class Settings:
    archive_dir: Path
    db_path: Path
    metadata_json_path: Path
    host: str
    port: int


def get_settings() -> Settings:
    archive_dir = Path(os.environ.get("CALLIGRAPHY_ARCHIVE_DIR", DEFAULT_ARCHIVE_DIR)).expanduser()
    db_path = Path(os.environ.get("CALLIGRAPHY_DB_PATH", DEFAULT_DB_PATH)).expanduser()
    metadata_json_path = Path(os.environ.get("CALLIGRAPHY_METADATA_JSON_PATH", DEFAULT_METADATA_JSON_PATH)).expanduser()
    host = os.environ.get("CALLIGRAPHY_HOST", "127.0.0.1")
    port = int(os.environ.get("CALLIGRAPHY_PORT", "8000"))
    return Settings(
        archive_dir=archive_dir,
        db_path=db_path,
        metadata_json_path=metadata_json_path,
        host=host,
        port=port,
    )
