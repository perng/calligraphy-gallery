from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import get_connection

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}

SCRIPT_LABELS = ["篆書", "隸書", "楷書", "行書", "草書", "行草", "小楷", "章草", "隸楷", "行楷"]
WORK_FORM_LABELS = ["尺牘", "長卷", "手卷", "冊頁", "碑帖", "墓誌", "神道碑", "拓本", "印譜", "寫經", "題跋", "題簽", "楹聯", "春聯"]
THEME_LABELS = ["心經", "心經書法", "蘭亭集序", "春聯", "福字", "楹聯", "集字作品", "千字文", "道德經", "赤壁賦", "前後赤壁賦", "墓誌塔銘", "敦煌寫經", "二王書法", "蘇黃米蔡", "顏柳歐趙", "傳世字畫"]
SERIES_LABELS = ["快雪堂法書", "玉煙堂法帖", "渤海藏真帖", "秋碧堂法書", "寶賢堂集古法帖", "鬱岡齋墨妙", "絳帖", "墨稼菴選帖", "二王帖", "文字會寶", "集古印譜", "飛鴻堂印譜四集"]
PERIOD_LABELS = [
    "先秦", "秦", "漢", "東漢", "西漢", "魏", "曹魏", "西晉", "東晉", "晉", "南北朝", "北魏", "東魏", "西魏", "隋", "唐", "唐代",
    "五代", "宋", "北宋", "南宋", "元", "元代", "明", "明代", "清", "清代", "民國", "現代", "20世紀",
]
INSTITUTION_LABELS = [
    "上海博物館", "北京故宮博物院", "美國大都會博物館", "哈佛大學", "大英圖書館", "國家圖書館",
    "法國國家圖書館", "丹麥皇家圖書館", "日本龍谷大學大宮圖書館藏", "早稻田大學圖書館藏", "北京故宮博物院藏",
]

NOISE_TOKENS = {"書法欣賞", "高清大圖", "高清書法", "高清拓本", "高清拓片", "投稿作品", "書法空間", "高清字帖"}


@dataclass
class ParsedTitle:
    display_title: str
    canonical_title: str
    primary_person: str | None
    associated_persons: list[str]
    scripts: list[str]
    periods: list[str]
    themes: list[str]
    series: str | None
    institutions: list[str]
    work_forms: list[str]
    source_labels: list[str]
    top_level_bucket: str | None


def slugify(value: str) -> str:
    ascii_only = re.sub(r"[^0-9a-zA-Z]+", "_", value).strip("_").lower()
    if ascii_only:
        return ascii_only[:80]
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def parse_title(raw_title: str) -> ParsedTitle:
    tokens = [token.strip() for token in raw_title.split("_") if token.strip()]
    scripts = extract_matches(raw_title, SCRIPT_LABELS)
    periods = extract_matches(raw_title, PERIOD_LABELS)
    themes = extract_matches(raw_title, THEME_LABELS)
    series = first_match(raw_title, SERIES_LABELS)
    institutions = extract_matches(raw_title, INSTITUTION_LABELS)
    work_forms = extract_matches(raw_title, WORK_FORM_LABELS)

    top_level_bucket = tokens[-1] if tokens else None
    source_labels = []
    if len(tokens) >= 2:
        source_labels = [token for token in tokens[-2:] if token not in {top_level_bucket}]
    # Extract candidate person from the first token after removing known metadata fragments.
    primary_person = None
    if tokens:
        primary_person = extract_person_candidate(tokens[0], scripts + periods + work_forms + themes)
        if not primary_person and len(tokens) > 1:
            primary_person = extract_person_candidate(tokens[1], scripts + periods + work_forms + themes)

    title_candidates = []
    for token in tokens:
        if token in NOISE_TOKENS:
            continue
        if token == top_level_bucket:
            continue
        if token in source_labels:
            continue
        if series and token == series:
            continue
        if token in institutions or token in periods or token in work_forms or token in themes:
            continue
        maybe_title = token
        if primary_person:
            maybe_title = maybe_title.replace(primary_person, "").strip("_- ")
        for label in scripts:
            maybe_title = maybe_title.replace(label, "").strip("_- ")
        if maybe_title:
            title_candidates.append(maybe_title)

    display_title = title_candidates[0] if title_candidates else raw_title
    display_title = display_title.strip("_- ") or raw_title
    return ParsedTitle(
        display_title=display_title,
        canonical_title=display_title,
        primary_person=primary_person,
        associated_persons=[primary_person] if primary_person else [],
        scripts=scripts,
        periods=periods,
        themes=themes,
        series=series,
        institutions=institutions,
        work_forms=work_forms,
        source_labels=source_labels,
        top_level_bucket=top_level_bucket,
    )


def parse_metadata_title(raw_title: str, metadata: dict[str, Any]) -> ParsedTitle:
    work = metadata.get("work") or {}
    people = metadata.get("people") or {}
    calligraphy = metadata.get("calligraphy") or {}
    classification = metadata.get("classification") or {}
    time = metadata.get("time") or {}
    segments = metadata.get("segments") or {}

    display_title = clean_text(work.get("display_title")) or raw_title
    canonical_title = clean_text(work.get("candidate_work_title")) or display_title
    primary_person = clean_text(people.get("primary_person"))
    associated_persons = normalize_labels(people.get("all_people") or [])
    if primary_person and primary_person not in associated_persons:
        associated_persons.insert(0, primary_person)

    return ParsedTitle(
        display_title=display_title,
        canonical_title=canonical_title,
        primary_person=primary_person,
        associated_persons=associated_persons,
        scripts=normalize_labels(calligraphy.get("scripts") or []),
        periods=normalize_labels(time.get("dynasty_period_labels") or []),
        themes=normalize_labels((work.get("topic_tags") or []) + (classification.get("group_tags") or [])),
        series=clean_text(work.get("series_or_collection_title")),
        institutions=normalize_labels(work.get("institution_mentions") or []),
        work_forms=normalize_labels(calligraphy.get("work_forms") or []),
        source_labels=normalize_labels(classification.get("source_labels") or segments.get("labels") or []),
        top_level_bucket=clean_text(classification.get("suggested_top_level_bucket")),
    )


def clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def normalize_labels(values: list[Any]) -> list[str]:
    labels: list[str] = []
    for value in values:
        cleaned = clean_text(value)
        if cleaned and cleaned not in labels:
            labels.append(cleaned)
    return labels


def extract_matches(text: str, labels: list[str]) -> list[str]:
    matches = [label for label in labels if label and label in text]
    # Prefer longer labels first, then preserve order uniquely.
    ordered = []
    for label in sorted(matches, key=len, reverse=True):
        if label not in ordered:
            ordered.append(label)
    return ordered


def first_match(text: str, labels: list[str]) -> str | None:
    matches = extract_matches(text, labels)
    return matches[0] if matches else None


def extract_person_candidate(token: str, known_labels: list[str]) -> str | None:
    candidate = token
    for label in known_labels:
        candidate = candidate.replace(label, "")
    candidate = re.sub(r"[0-9A-Za-z（）()《》【】\-\s]+", "", candidate)
    candidate = candidate.strip("_- ")
    if not candidate:
        return None
    # Limit obviously too-long candidates.
    return candidate[:24]


def entity_id(prefix: str, label: str) -> str:
    return f"{prefix}_{slugify(label)}"


def item_id(directory_path: Path) -> str:
    digest = hashlib.sha1(str(directory_path).encode("utf-8")).hexdigest()[:16]
    return f"item_{digest}"


def image_id(item_identifier: str, filename: str) -> str:
    digest = hashlib.sha1(f"{item_identifier}:{filename}".encode("utf-8")).hexdigest()[:16]
    return f"img_{digest}"


def upsert_label(conn, table: str, prefix: str, label: str) -> str:
    identifier = entity_id(prefix, label)
    if table == "persons":
        conn.execute(
            """
            INSERT INTO persons (id, display_name, normalized_name)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET display_name = excluded.display_name
            """,
            (identifier, label, label),
        )
    elif table in {"scripts", "periods", "themes", "series", "institutions", "work_forms"}:
        conn.execute(
            f"INSERT INTO {table} (id, label) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET label = excluded.label",
            (identifier, label),
        )
    else:
        raise ValueError(f"Unsupported table: {table}")
    return identifier


def load_metadata_index(metadata_json_path: Path | None) -> tuple[dict[str, dict[str, Any]], int]:
    if metadata_json_path is None or not metadata_json_path.exists():
        return {}, 0

    payload = json.loads(metadata_json_path.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return {}, 0

    lookup: dict[str, dict[str, Any]] = {}
    duplicates = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_title = clean_text(item.get("raw_title"))
        if not raw_title:
            continue
        if raw_title in lookup:
            duplicates += 1
            continue
        lookup[raw_title] = item
    return lookup, duplicates


def looks_like_bucket_directory(name: str) -> bool:
    return bool(re.match(r"^\d{2}_", name))


def import_archive(archive_dir: Path, db_path: Path, metadata_json_path: Path | None = None) -> dict[str, int]:
    directories = sorted([path for path in archive_dir.iterdir() if path.is_dir()])
    metadata_index, metadata_duplicates = load_metadata_index(metadata_json_path)
    stats = {"items": 0, "images": 0, "metadata_matches": 0, "metadata_fallbacks": 0, "metadata_duplicates": metadata_duplicates, "skipped_buckets": 0}
    with get_connection(db_path) as conn:
        for directory in directories:
            metadata = metadata_index.get(directory.name)
            if metadata:
                parsed = parse_metadata_title(directory.name, metadata)
                stats["metadata_matches"] += 1
            else:
                if metadata_index and looks_like_bucket_directory(directory.name):
                    stats["skipped_buckets"] += 1
                    continue
                parsed = parse_title(directory.name)
                stats["metadata_fallbacks"] += 1
            identifier = item_id(directory)
            image_files = sorted(
                [path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS],
                key=lambda path: path.name,
            )
            primary_person_id = None
            if parsed.primary_person:
                primary_person_id = upsert_label(conn, "persons", "person", parsed.primary_person)
            machine_person_ids = []
            for person_name in parsed.associated_persons:
                person_id = upsert_label(conn, "persons", "person", person_name)
                if person_id not in machine_person_ids:
                    machine_person_ids.append(person_id)
            series_id = None
            if parsed.series:
                series_id = upsert_label(conn, "series", "series", parsed.series)

            # Preserve manual edits on re-import.
            existing = conn.execute(
                "SELECT review_status, display_title, canonical_title, primary_person_id, series_id, is_deleted, view_count, last_viewed_at FROM items WHERE directory_path = ?",
                (str(directory),),
            ).fetchone()
            review_status = "auto"
            display_title = parsed.display_title
            canonical_title = parsed.canonical_title
            preserved_is_deleted = 0
            preserved_view_count = 0
            preserved_last_viewed_at = None
            if existing:
                review_status = existing["review_status"]
                preserved_is_deleted = existing["is_deleted"]
                preserved_view_count = existing["view_count"]
                preserved_last_viewed_at = existing["last_viewed_at"]
                if review_status == "edited":
                    display_title = existing["display_title"]
                    canonical_title = existing["canonical_title"]
                    primary_person_id = existing["primary_person_id"]
                    series_id = existing["series_id"]
                    machine_person_ids = [primary_person_id] if primary_person_id else []

            conn.execute(
                """
                INSERT INTO items (
                  id, raw_title, display_title, canonical_title, primary_person_id, series_id,
                  top_level_bucket, directory_path, source_labels_json, image_count, view_count,
                  last_viewed_at, review_status, is_deleted
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(directory_path) DO UPDATE SET
                  raw_title = excluded.raw_title,
                  display_title = CASE WHEN items.review_status = 'edited' THEN items.display_title ELSE excluded.display_title END,
                  canonical_title = CASE WHEN items.review_status = 'edited' THEN items.canonical_title ELSE excluded.canonical_title END,
                  primary_person_id = CASE WHEN items.review_status = 'edited' THEN items.primary_person_id ELSE excluded.primary_person_id END,
                  series_id = CASE WHEN items.review_status = 'edited' THEN items.series_id ELSE excluded.series_id END,
                  top_level_bucket = excluded.top_level_bucket,
                  source_labels_json = excluded.source_labels_json,
                  image_count = excluded.image_count,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (
                    identifier,
                    directory.name,
                    display_title,
                    canonical_title,
                    primary_person_id,
                    series_id,
                    parsed.top_level_bucket,
                    str(directory),
                    json.dumps(parsed.source_labels, ensure_ascii=False),
                    len(image_files),
                    preserved_view_count,
                    preserved_last_viewed_at,
                    review_status,
                    preserved_is_deleted,
                ),
            )
            db_item_id = conn.execute("SELECT id FROM items WHERE directory_path = ?", (str(directory),)).fetchone()["id"]

            # Refresh machine-derived relations only.
            for table in ("item_persons", "item_scripts", "item_periods", "item_themes", "item_institutions", "item_work_forms"):
                conn.execute(f"DELETE FROM {table} WHERE item_id = ?", (db_item_id,))
            conn.execute("DELETE FROM images WHERE item_id = ?", (db_item_id,))

            for person_id in machine_person_ids:
                role = "primary" if person_id == primary_person_id else "associated"
                conn.execute(
                    "INSERT OR IGNORE INTO item_persons (item_id, person_id, role) VALUES (?, ?, ?)",
                    (db_item_id, person_id, role),
                )
            for label in parsed.scripts:
                script_id = upsert_label(conn, "scripts", "script", label)
                conn.execute("INSERT OR IGNORE INTO item_scripts (item_id, script_id) VALUES (?, ?)", (db_item_id, script_id))
            for label in parsed.periods:
                period_id = upsert_label(conn, "periods", "period", label)
                conn.execute("INSERT OR IGNORE INTO item_periods (item_id, period_id) VALUES (?, ?)", (db_item_id, period_id))
            for label in parsed.themes:
                theme_id = upsert_label(conn, "themes", "theme", label)
                conn.execute("INSERT OR IGNORE INTO item_themes (item_id, theme_id) VALUES (?, ?)", (db_item_id, theme_id))
            for label in parsed.institutions:
                institution_id = upsert_label(conn, "institutions", "inst", label)
                conn.execute(
                    "INSERT OR IGNORE INTO item_institutions (item_id, institution_id) VALUES (?, ?)",
                    (db_item_id, institution_id),
                )
            for label in parsed.work_forms:
                work_form_id = upsert_label(conn, "work_forms", "form", label)
                conn.execute(
                    "INSERT OR IGNORE INTO item_work_forms (item_id, work_form_id) VALUES (?, ?)",
                    (db_item_id, work_form_id),
                )
            for index, image_path in enumerate(image_files, start=1):
                img_id = image_id(db_item_id, image_path.name)
                conn.execute(
                    """
                    INSERT INTO images (id, item_id, storage_uri, thumbnail_uri, preview_uri, file_name, page_index, sort_key)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        img_id,
                        db_item_id,
                        str(image_path),
                        None,
                        None,
                        image_path.name,
                        index,
                        f"{index:04d}",
                    ),
                )
            stats["items"] += 1
            stats["images"] += len(image_files)
    return stats
