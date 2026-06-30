#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import html
import json
import re
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


def log_info(message: str) -> None:
    print(f"[INFO] {message}", file=sys.stderr)


def log_warn(message: str) -> None:
    print(f"[WARN] {message}", file=sys.stderr)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def strip_jsonp(text: str) -> tuple[dict[str, Any], str]:
    text = text.strip()

    if text.startswith("{"):
        return json.loads(text), ""

    match = re.match(
        r"^\s*([A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*)\s*\(",
        text,
    )

    if not match:
        raise ValueError("Input is neither JSON nor JSONP")

    callback = match.group(1)
    start = match.end()
    end = text.rfind(")")

    if end == -1 or end <= start:
        raise ValueError("Invalid JSONP wrapper")

    json_text = text[start:end].strip()

    if json_text.endswith(";"):
        json_text = json_text[:-1].strip()

    return json.loads(json_text), callback


def load_jsonp_file(path: Path) -> tuple[dict[str, Any], str]:
    text = read_text(path)
    return strip_jsonp(text)


def normalize_text(value: Any) -> str:
    value = html.unescape(str(value or ""))
    value = value.lower()
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[\W_]+", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_title(title: Any) -> str:
    title_text = html.unescape(str(title or ""))
    title_text = title_text.strip()
    title_text = title_text.rstrip(".")
    title_text = normalize_text(title_text)
    return title_text


def first_author_key(record: dict[str, Any]) -> str:
    authors = record.get("authors", [])

    if isinstance(authors, list) and authors:
        return normalize_text(authors[0])

    raw_authors = record.get("raw_info", {}).get("authors", {}).get("author", [])

    if isinstance(raw_authors, dict):
        return normalize_text(raw_authors.get("text", ""))

    if isinstance(raw_authors, list) and raw_authors:
        first = raw_authors[0]
        if isinstance(first, dict):
            return normalize_text(first.get("text", ""))
        return normalize_text(first)

    return ""


def make_dedup_key(record: dict[str, Any]) -> str:
    title = normalize_title(record.get("title", ""))
    first_author = first_author_key(record)

    if title and first_author:
        return f"title_author:{title}|{first_author}"

    if title:
        return f"title:{title}"

    for field in ("key", "doi", "url", "ee"):
        value = normalize_text(record.get(field, ""))
        if value:
            return f"{field}:{value}"

    return json.dumps(record, ensure_ascii=False, sort_keys=True)


def venue_text(record: dict[str, Any]) -> str:
    venue = record.get("venue", "")

    if isinstance(venue, list):
        return "; ".join(str(v).strip() for v in venue if str(v).strip())

    return str(venue or "").strip()


def is_corr_record(record: dict[str, Any]) -> bool:
    venue = venue_text(record).lower()
    key = str(record.get("key", "")).lower()
    return venue == "corr" or "journals/corr" in key


def record_quality_score(record: dict[str, Any]) -> tuple[int, int, int, int, int]:
    formal_score = 0 if is_corr_record(record) else 1
    doi_score = 1 if str(record.get("doi", "")).strip() else 0
    venue_score = 1 if venue_text(record) else 0
    url_score = 1 if str(record.get("url", "")).strip() else 0
    year_score = parse_year(record.get("year", ""))

    return formal_score, doi_score, venue_score, url_score, year_score


def merge_duplicate_records(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    old_score = record_quality_score(old)
    new_score = record_quality_score(new)

    if new_score > old_score:
        base = deepcopy(new)
        other = old
    else:
        base = deepcopy(old)
        other = new

    found_queries = []
    source_files = []

    for item in (old, new):
        query = item.get("query", "")
        if query and query not in found_queries:
            found_queries.append(query)

        for q in item.get("found_queries", []):
            if q and q not in found_queries:
                found_queries.append(q)

        source_file = item.get("source_file", "")
        if source_file and source_file not in source_files:
            source_files.append(source_file)

        for source in item.get("source_files", []):
            if source and source not in source_files:
                source_files.append(source)

    base["found_queries"] = found_queries
    base["source_files"] = source_files

    for field in ("query", "rank_in_query", "score"):
        if field in base:
            base[f"selected_{field}"] = base.get(field)

    base["duplicate_merged"] = True

    other_key = other.get("key") or other.get("doi") or other.get("url") or other.get("title", "")
    if other_key:
        merged_from = base.get("merged_from", [])
        if other_key not in merged_from:
            merged_from.append(other_key)
        base["merged_from"] = merged_from

    return base


def parse_year(value: Any) -> int:
    match = re.search(r"\d{4}", str(value or ""))
    return int(match.group(0)) if match else 0


def sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda r: (
            -parse_year(r.get("year", "")),
            venue_text(r).lower(),
            normalize_title(r.get("title", "")),
        ),
    )


def collect_jsonp_files(source_dir: Path) -> list[Path]:
    files = sorted(source_dir.glob("*.jsonp"))

    if not files:
        files = sorted(source_dir.glob("*.json"))

    return files


def load_all_records(source_dir: Path) -> tuple[list[dict[str, Any]], list[str], list[dict[str, str]], list[str]]:
    files = collect_jsonp_files(source_dir)

    if not files:
        raise FileNotFoundError(f"No .jsonp or .json files found in {source_dir}")

    all_records = []
    callbacks = []
    input_files = []
    errors = []

    for path in files:
        try:
            payload, callback = load_jsonp_file(path)

            if callback and callback not in callbacks:
                callbacks.append(callback)

            records = payload.get("records", [])

            if not isinstance(records, list):
                raise ValueError("Field 'records' is not a list")

            input_files.append(str(path))

            for record in records:
                if not isinstance(record, dict):
                    continue

                item = deepcopy(record)
                item["source_file"] = str(path)
                all_records.append(item)

            log_info(f"Loaded {len(records)} records from {path}")

        except Exception as exc:
            message = f"{path}: {exc}"
            log_warn(message)
            errors.append(message)

    return all_records, callbacks, errors, input_files


def deduplicate_all(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for record in records:
        key = make_dedup_key(record)

        if key not in merged:
            item = deepcopy(record)
            query = item.get("query", "")
            source_file = item.get("source_file", "")

            item["found_queries"] = [query] if query else []
            item["source_files"] = [source_file] if source_file else []

            merged[key] = item
        else:
            merged[key] = merge_duplicate_records(merged[key], record)

    return sort_records(list(merged.values()))


def safe_jsonp_callback(callbacks: list[str]) -> str:
    if callbacks:
        return callbacks[0]
    return "dblpCleanResults"


def write_jsonp(output_path: Path, payload: dict[str, Any], callback: str) -> None:
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    output_path.write_text(f"{callback}({json_text});\n", encoding="utf-8")


def markdown_escape(value: Any) -> str:
    text = html.unescape(str(value or "")).strip()
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.replace("|", r"\|")
    return text


def get_link(record: dict[str, Any]) -> str:
    for field in ("url", "ee", "doi"):
        value = str(record.get(field, "")).strip()
        if value:
            if field == "doi" and not value.startswith("http"):
                return f"https://doi.org/{value}"
            return value
    return ""


# def write_markdown_table(output_path: Path, records: list[dict[str, Any]]) -> None:
#     lines = []

#     for record in records:
#         year = markdown_escape(record.get("year", ""))
#         venue = markdown_escape(venue_text(record))
#         title = markdown_escape(record.get("title", ""))
#         link = markdown_escape(get_link(record))

#         lines.append(f"| {year} | {venue} | {title} | {link} |")

#     output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
def write_markdown_table(output_path: Path, records: list[dict[str, Any]]) -> None:
    lines = [
        "| Year | Venue | Title | Link |",
        "|---|---|---|---|",
    ]

    for record in records:
        year = markdown_escape(record.get("year", ""))
        venue = markdown_escape(venue_text(record))
        title = markdown_escape(record.get("title", ""))
        link = markdown_escape(get_link(record))

        lines.append(f"| {year} | {venue} | {title} | {link} |")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_output_dir(source_dir: Path, output_dir_arg: str | None) -> Path:
    if output_dir_arg:
        return Path(output_dir_arg).expanduser().resolve()

    return source_dir.parent / f"{source_dir.name}_cleaned"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean and merge DBLP JSONP result files"
    )

    parser.add_argument(
        "-s",
        "--source",
        required=True,
        help="Directory containing DBLP .jsonp files",
    )

    parser.add_argument(
        "-d",
        "--destination",
        default=None,
        help="Output directory. Default: a sibling directory named <source>_cleaned",
    )

    parser.add_argument(
        "-t",
        "--type",
        choices=["jsonp", "table"],
        default=None,
        help="Output type. jsonp: merged JSONP only; table: markdown table only; omitted: both",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    source_dir = Path(args.source).expanduser().resolve()

    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    if not source_dir.is_dir():
        raise NotADirectoryError(f"Source path is not a directory: {source_dir}")

    output_dir = resolve_output_dir(source_dir, args.destination)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_records, callbacks, errors, input_files = load_all_records(source_dir)
    unique_records = deduplicate_all(all_records)

    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    callback = safe_jsonp_callback(callbacks)

    payload = {
        "metadata": {
            "created_at": now.isoformat(timespec="seconds"),
            "source_dir": str(source_dir),
            "input_files": input_files,
            "input_file_count": len(input_files),
            "total_records_before_deduplication": len(all_records),
            "total_records_after_deduplication": len(unique_records),
            "error_count": len(errors),
            "errors": errors,
        },
        "records": unique_records,
    }

    output_paths = []

    if args.type in (None, "jsonp"):
        jsonp_path = output_dir / f"dblp_merged_{timestamp}.jsonp"
        write_jsonp(jsonp_path, payload, callback)
        output_paths.append(jsonp_path)

    if args.type in (None, "table"):
        table_path = output_dir / f"dblp_merged_{timestamp}.md"
        write_markdown_table(table_path, unique_records)
        output_paths.append(table_path)

    for path in output_paths:
        print(path)


if __name__ == "__main__":
    main()