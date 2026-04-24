from __future__ import annotations

import argparse
import csv
import difflib
import json
import shutil
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV_PATH = ROOT / "primary_person_review.csv"
DEFAULT_LIST_PATH = ROOT / "list.txt"
DEFAULT_JSON_PATH = ROOT / "calligraphy_title_extracted.json"


def load_original_title_map(list_path: Path, original_text: str, replacement_text: str) -> dict[str, str]:
    candidates: dict[str, list[str]] = defaultdict(list)
    with list_path.open(encoding="utf-8") as list_file:
        for line in list_file:
            original_title = line.strip()
            if not original_title or original_text not in original_title:
                continue
            changed_title = original_title.replace(original_text, replacement_text)
            if changed_title != original_title:
                candidates[changed_title].append(original_title)

    return {changed_title: originals[0] for changed_title, originals in candidates.items() if len(originals) == 1}


def load_restore_map(list_path: Path, original_text: str, replacement_text: str, bidirectional: bool) -> dict[str, str]:
    candidates: dict[str, list[str]] = defaultdict(list)
    for changed_title, original_title in load_original_title_map(list_path, original_text, replacement_text).items():
        candidates[changed_title].append(original_title)

    if bidirectional:
        for changed_title, original_title in load_original_title_map(list_path, replacement_text, original_text).items():
            candidates[changed_title].append(original_title)

    return {changed_title: originals[0] for changed_title, originals in candidates.items() if len(originals) == 1}


def load_json_titles(json_path: Path) -> list[str]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError(f"{json_path} must contain an items list")

    titles: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_title = item.get("raw_title")
        if isinstance(raw_title, str) and raw_title.strip():
            titles.append(raw_title.strip())
    return titles


def best_fuzzy_title(
    raw_title: str,
    source_titles: list[str],
    min_ratio: float,
    min_margin: float,
) -> tuple[str | None, float, float]:
    scored = sorted(
        ((difflib.SequenceMatcher(None, raw_title, title).ratio(), title) for title in source_titles),
        reverse=True,
    )
    if not scored:
        return None, 0.0, 0.0

    best_ratio, best_title = scored[0]
    second_ratio = scored[1][0] if len(scored) > 1 else 0.0
    margin = best_ratio - second_ratio
    if best_ratio >= min_ratio and margin >= min_margin:
        return best_title, best_ratio, margin
    return None, best_ratio, margin


def restore_raw_titles(
    csv_path: Path,
    list_path: Path,
    json_path: Path,
    original_text: str,
    replacement_text: str,
    bidirectional: bool,
) -> tuple[list[dict[str, str]], list[tuple[int, str, str, str]], int]:
    restore_map = load_restore_map(list_path, original_text, replacement_text, bidirectional)
    source_titles = load_json_titles(json_path)
    original_titles = set(source_titles)

    with csv_path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames or "raw_title" not in reader.fieldnames:
            raise ValueError(f"{csv_path} must have a raw_title column")

        rows = list(reader)
        fieldnames = reader.fieldnames

    changes: list[tuple[int, str, str, str]] = []
    for row_index, row in enumerate(rows, start=2):
        raw_title = (row.get("raw_title") or "").strip()
        if raw_title in original_titles:
            continue

        restored_title = restore_map.get(raw_title)
        method = "replacement"
        if restored_title and restored_title not in original_titles:
            restored_title = None

        if not restored_title:
            restored_title, ratio, margin = best_fuzzy_title(raw_title, source_titles, min_ratio=0.85, min_margin=0.03)
            method = f"fuzzy ratio={ratio:.3f} margin={margin:.3f}"

        if not restored_title:
            continue

        row["raw_title"] = restored_title
        changes.append((row_index, raw_title, restored_title, method))

    return rows, changes, len(fieldnames)


def write_csv(csv_path: Path, rows: list[dict[str, str]], create_backup: bool) -> None:
    if not rows:
        return

    fieldnames = list(rows[0].keys())
    if create_backup:
        backup_path = csv_path.with_suffix(csv_path.suffix + ".bak")
        suffix = 1
        while backup_path.exists():
            backup_path = csv_path.with_suffix(csv_path.suffix + f".bak.{suffix}")
            suffix += 1
        shutil.copy2(csv_path, backup_path)
        print(f"Backup written: {backup_path}")

    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Restore primary_person_review.csv raw_title values using original titles from list.txt."
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH, help="CSV file to update")
    parser.add_argument("--list", type=Path, default=DEFAULT_LIST_PATH, help="Original title list")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON_PATH, help="JSON file whose raw_title values are the source of truth")
    parser.add_argument("--original", default="唐寅", help="Original text expected in list.txt")
    parser.add_argument("--replacement", default="唐伯虎", help="Accidental replacement text in the CSV")
    parser.add_argument("--one-way", action="store_true", help="Only restore replacement -> original, not both directions")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing the CSV")
    parser.add_argument("--no-backup", action="store_true", help="Do not create a .bak file before writing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csv_path = args.csv.resolve()
    list_path = args.list.resolve()

    rows, changes, _ = restore_raw_titles(
        csv_path,
        list_path,
        args.json.resolve(),
        args.original,
        args.replacement,
        bidirectional=not args.one_way,
    )
    print(f"Restorable raw_title values: {len(changes)}")
    for line_number, current_title, restored_title, method in changes:
        print(f"{line_number}: {current_title} -> {restored_title} ({method})")

    if args.dry_run:
        print("Dry run only; CSV was not written.")
        return 0

    if changes:
        write_csv(csv_path, rows, create_backup=not args.no_backup)
        print(f"Updated CSV written: {csv_path}")
    else:
        print("No CSV changes needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
