from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV_PATH = ROOT / "primary_person_review.csv"
DEFAULT_JSON_PATH = ROOT / "calligraphy_title_extracted.json"


def clean_person(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def unique_clean_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    cleaned_values: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if cleaned and cleaned not in cleaned_values:
            cleaned_values.append(cleaned)
    return cleaned_values


def load_review(csv_path: Path) -> dict[str, str | None]:
    review: dict[str, str | None] = {}
    line_numbers: dict[str, int] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        required_columns = {"raw_title", "primary_person"}
        missing_columns = required_columns.difference(reader.fieldnames or [])
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"{csv_path} is missing required column(s): {missing}")

        for line_number, row in enumerate(reader, start=2):
            raw_title = (row.get("raw_title") or "").strip()
            if not raw_title:
                raise ValueError(f"{csv_path}:{line_number} has an empty raw_title")

            primary_person = clean_person(row.get("primary_person"))
            if raw_title in review and review[raw_title] != primary_person:
                previous_line = line_numbers[raw_title]
                raise ValueError(
                    f"{csv_path}:{line_number} conflicts with line {previous_line} for raw_title {raw_title!r}"
                )

            review[raw_title] = primary_person
            line_numbers[raw_title] = line_number
    return review


def update_all_people(values: Any, old_primary: str | None, new_primary: str | None) -> list[str]:
    all_people = unique_clean_strings(values)

    if old_primary and old_primary != new_primary:
        all_people = [person for person in all_people if person != old_primary]

    if new_primary:
        all_people = [person for person in all_people if person != new_primary]
        all_people.insert(0, new_primary)

    return all_people


def apply_review(payload: dict[str, Any], review: dict[str, str | None]) -> dict[str, Any]:
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("JSON payload must contain an items list")

    seen_titles: set[str] = set()
    missing_titles = set(review)
    updated_primary = 0
    updated_all_people = 0
    matched = 0

    for item in items:
        if not isinstance(item, dict):
            continue
        raw_title = item.get("raw_title")
        if not isinstance(raw_title, str) or raw_title not in review:
            continue

        matched += 1
        seen_titles.add(raw_title)
        missing_titles.discard(raw_title)

        people = item.setdefault("people", {})
        if not isinstance(people, dict):
            people = {}
            item["people"] = people

        old_primary = clean_person(people.get("primary_person"))
        new_primary = review[raw_title]
        old_all_people = unique_clean_strings(people.get("all_people"))
        new_all_people = update_all_people(old_all_people, old_primary, new_primary)

        if old_primary != new_primary:
            updated_primary += 1
        if old_all_people != new_all_people:
            updated_all_people += 1

        people["primary_person"] = new_primary
        people["all_people"] = new_all_people

    return {
        "matched": matched,
        "review_rows": len(review),
        "json_items": len(items),
        "missing_titles": sorted(missing_titles),
        "updated_primary": updated_primary,
        "updated_all_people": updated_all_people,
        "seen_titles": len(seen_titles),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply reviewed primary_person values from primary_person_review.csv to calligraphy_title_extracted.json."
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH, help="Path to primary_person_review.csv")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON_PATH, help="Path to calligraphy_title_extracted.json")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing the JSON file")
    parser.add_argument("--strict", action="store_true", help="Fail if any CSV raw_title is missing from the JSON")
    parser.add_argument("--no-backup", action="store_true", help="Do not create a .bak file before writing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csv_path = args.csv.resolve()
    json_path = args.json.resolve()

    review = load_review(csv_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    stats = apply_review(payload, review)

    print(f"Review rows: {stats['review_rows']}")
    print(f"Matched JSON items: {stats['matched']} / {stats['json_items']}")
    print(f"Updated primary_person values: {stats['updated_primary']}")
    print(f"Updated all_people lists: {stats['updated_all_people']}")

    missing_titles = stats["missing_titles"]
    if missing_titles:
        print(f"Missing raw_title values: {len(missing_titles)}", file=sys.stderr)
        for title in missing_titles[:20]:
            print(f"  - {title}", file=sys.stderr)
        if len(missing_titles) > 20:
            print(f"  ... and {len(missing_titles) - 20} more", file=sys.stderr)
        if args.strict:
            return 1

    if args.dry_run:
        print("Dry run only; JSON was not written.")
        return 0

    if not args.no_backup:
        backup_path = json_path.with_suffix(json_path.suffix + ".bak")
        shutil.copy2(json_path, backup_path)
        print(f"Backup written: {backup_path}")

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated JSON written: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
