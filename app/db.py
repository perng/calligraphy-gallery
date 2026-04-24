from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY,
  raw_title TEXT NOT NULL,
  display_title TEXT,
  canonical_title TEXT,
  primary_person_id TEXT REFERENCES persons(id),
  series_id TEXT REFERENCES series(id),
  top_level_bucket TEXT,
  directory_path TEXT NOT NULL UNIQUE,
  source_labels_json TEXT NOT NULL DEFAULT '[]',
  image_count INTEGER NOT NULL DEFAULT 0,
  view_count INTEGER NOT NULL DEFAULT 0,
  last_viewed_at TEXT,
  review_status TEXT NOT NULL DEFAULT 'auto',
  is_deleted INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS images (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  storage_uri TEXT NOT NULL,
  thumbnail_uri TEXT,
  preview_uri TEXT,
  file_name TEXT NOT NULL,
  page_index INTEGER NOT NULL,
  sort_key TEXT,
  width INTEGER,
  height INTEGER
);

CREATE TABLE IF NOT EXISTS persons (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  normalized_name TEXT NOT NULL UNIQUE,
  frequent INTEGER NOT NULL DEFAULT 0,
  period_label TEXT,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS person_aliases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  person_id TEXT NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  UNIQUE(person_id, alias)
);

CREATE TABLE IF NOT EXISTS scripts (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS periods (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL UNIQUE,
  sort_order INTEGER
);

CREATE TABLE IF NOT EXISTS themes (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS series (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS institutions (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS work_forms (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS item_persons (
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  person_id TEXT NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  role TEXT DEFAULT 'associated',
  PRIMARY KEY (item_id, person_id)
);

CREATE TABLE IF NOT EXISTS item_scripts (
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  script_id TEXT NOT NULL REFERENCES scripts(id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, script_id)
);

CREATE TABLE IF NOT EXISTS item_periods (
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  period_id TEXT NOT NULL REFERENCES periods(id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, period_id)
);

CREATE TABLE IF NOT EXISTS item_themes (
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  theme_id TEXT NOT NULL REFERENCES themes(id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, theme_id)
);

CREATE TABLE IF NOT EXISTS item_institutions (
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  institution_id TEXT NOT NULL REFERENCES institutions(id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, institution_id)
);

CREATE TABLE IF NOT EXISTS item_work_forms (
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  work_form_id TEXT NOT NULL REFERENCES work_forms(id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, work_form_id)
);

CREATE TABLE IF NOT EXISTS item_views (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  viewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS edit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id TEXT REFERENCES items(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  payload_json TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_items_primary_person_id ON items(primary_person_id);
CREATE INDEX IF NOT EXISTS idx_items_series_id ON items(series_id);
CREATE INDEX IF NOT EXISTS idx_items_is_deleted ON items(is_deleted);
CREATE INDEX IF NOT EXISTS idx_items_last_viewed_at ON items(last_viewed_at);
CREATE INDEX IF NOT EXISTS idx_images_item_id_page_index ON images(item_id, page_index);
CREATE INDEX IF NOT EXISTS idx_item_views_item_id_viewed_at ON item_views(item_id, viewed_at DESC);
CREATE INDEX IF NOT EXISTS idx_person_aliases_alias ON person_aliases(alias);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row["name"] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def refresh_frequent_persons(conn: sqlite3.Connection, limit: int = 50) -> None:
    if not column_exists(conn, "persons", "frequent"):
        return
    conn.execute("UPDATE persons SET frequent = 0")
    conn.execute(
        """
        UPDATE persons
        SET frequent = 1
        WHERE id IN (
          SELECT primary_person_id
          FROM items
          WHERE is_deleted = 0 AND primary_person_id IS NOT NULL
          GROUP BY primary_person_id
          ORDER BY COUNT(*) DESC, primary_person_id ASC
          LIMIT ?
        )
        """,
        (limit,),
    )


def migrate_db(conn: sqlite3.Connection) -> None:
    if not column_exists(conn, "persons", "frequent"):
        conn.execute("ALTER TABLE persons ADD COLUMN frequent INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_persons_frequent_display_name ON persons(frequent, display_name)"
    )
    refresh_frequent_persons(conn)


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        migrate_db(conn)
        conn.commit()


@contextmanager
def get_connection(db_path: Path):
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
