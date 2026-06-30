#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DBLP publication searcher (self-contained).

Loads `dblp.yml` from the directory containing this file by default,
runs the search against the DBLP publication API, and writes the
result as JSONP.

Can be invoked directly or via the dispatcher:
    python dblp_search.py
    python dblp_search.py -c /path/to/dblp.yml
    python search.py dblp
    python search.py dblp -c /path/to/dblp.yml
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
import yaml


# =========================================================
# Logging
# =========================================================


def log_info(message: str) -> None:
    print(f"[INFO] {message}", file=sys.stderr)


def log_warn(message: str) -> None:
    print(f"[WARN] {message}", file=sys.stderr)


def log_error(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)


# =========================================================
# Config helpers
# =========================================================


def get_value(
    config: dict[str, Any], path: tuple[str, ...], default: Any = None
) -> Any:
    current: Any = config
    for key in path:
        if not isinstance(current, dict):
            return default
        if key not in current:
            return default
        current = current[key]
    return current


def build_proxies(proxy_enabled: bool, proxy_url: str) -> dict[str, str] | None:
    proxy_url = proxy_url.strip()
    if not proxy_enabled or not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def validate_jsonp_callback(callback: str) -> None:
    if not callback:
        return
    pattern = r"^[A-Za-z_$][A-Za-z0-9_$]*(\.[A-Za-z_$][A-Za-z0-9_$]*)*$"
    if not re.match(pattern, callback):
        raise ValueError(f"Invalid JSONP callback name: {callback}")


def parse_queries(config: dict[str, Any]) -> list[str]:
    queries = config.get("queries", [])
    if isinstance(queries, list):
        cleaned = [str(q).strip() for q in queries if str(q).strip()]
    elif isinstance(queries, dict):
        cleaned = [str(v).strip() for _, v in queries.items() if str(v).strip()]
    else:
        raise ValueError("queries must be a YAML list or mapping")
    if not cleaned:
        raise ValueError("No valid queries found in config")
    return cleaned


def load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if not isinstance(config, dict):
        raise ValueError("Config file must be a YAML mapping")
    return config


def default_config_path() -> Path:
    """`dblp.yml` next to this file."""
    return (Path(__file__).resolve().parent / "dblp.yml").resolve()


# =========================================================
# DBLP response parsing
# =========================================================


def normalize_authors(authors_obj: Any) -> list[str]:
    if not authors_obj:
        return []
    if isinstance(authors_obj, dict):
        authors_obj = authors_obj.get("author", authors_obj)
    if isinstance(authors_obj, list):
        authors: list[str] = []
        for item in authors_obj:
            if isinstance(item, dict):
                name = str(item.get("text", "")).strip()
            else:
                name = str(item).strip()
            if name:
                authors.append(name)
        return authors
    if isinstance(authors_obj, dict):
        name = str(authors_obj.get("text", "")).strip()
        return [name] if name else []
    if isinstance(authors_obj, str):
        name = authors_obj.strip()
        return [name] if name else []
    return []


def normalize_venue(venue_obj: Any) -> str:
    if not venue_obj:
        return ""
    if isinstance(venue_obj, list):
        return "; ".join(
            str(item).strip() for item in venue_obj if str(item).strip()
        )
    return str(venue_obj).strip()


def extract_hits(raw_result: dict[str, Any]) -> list[dict[str, Any]]:
    hits = raw_result.get("result", {}).get("hits", {}).get("hit", [])
    if isinstance(hits, list):
        return hits
    if isinstance(hits, dict):
        return [hits]
    return []


def normalize_record(
    hit: dict[str, Any], query: str, rank: int
) -> dict[str, Any]:
    info = hit.get("info", {})
    return {
        "query": query,
        "rank_in_query": rank,
        "score": hit.get("@score", ""),
        "dblp_id": hit.get("@id", ""),
        "title": info.get("title", ""),
        "authors": normalize_authors(info.get("authors")),
        "venue": normalize_venue(info.get("venue")),
        "year": info.get("year", ""),
        "type": info.get("type", ""),
        "access": info.get("access", ""),
        "pages": info.get("pages", ""),
        "volume": info.get("volume", ""),
        "number": info.get("number", ""),
        "publisher": info.get("publisher", ""),
        "doi": info.get("doi", ""),
        "ee": info.get("ee", ""),
        "url": info.get("url", ""),
        "key": info.get("key", ""),
        "raw_info": info,
    }


def make_dedup_key(record: dict[str, Any]) -> str:
    for field in ("key", "doi", "url"):
        value = str(record.get(field, "")).strip().lower()
        if value:
            return f"{field}:{value}"
    title = str(record.get("title", "")).strip().lower()
    year = str(record.get("year", "")).strip()
    return f"title_year:{title}|{year}"


def deduplicate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for record in records:
        key = make_dedup_key(record)
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


# =========================================================
# HTTP
# =========================================================


def search_once(
    api_url: str,
    query: str,
    results_per_query: int,
    year_filter: str,
    proxies: dict[str, str] | None,
    timeout: int,
) -> dict[str, Any]:
    headers = {
        "User-Agent": "dblp-search-script/1.0",
        "Accept": "application/json",
    }
    params: dict[str, str] = {
        "q": query,
        "format": "json",
        "h": str(results_per_query),
    }
    if year_filter:
        params["year"] = year_filter

    response = requests.get(
        api_url,
        params=params,
        headers=headers,
        proxies=proxies,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def search_with_retry(
    api_url: str,
    query: str,
    results_per_query: int,
    year_filter: str,
    proxies: dict[str, str] | None,
    timeout: int,
    retries: int,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            log_info(f"Searching query='{query}' attempt={attempt}")
            return search_once(
                api_url=api_url,
                query=query,
                results_per_query=results_per_query,
                year_filter=year_filter,
                proxies=proxies,
                timeout=timeout,
            )
        except Exception as exc:
            last_error = exc
            log_warn(f"Query failed query='{query}' error='{exc}'")
            if attempt < retries:
                sleep_seconds = 2 * attempt
                log_info(f"Retrying after {sleep_seconds} seconds")
                time.sleep(sleep_seconds)
    raise RuntimeError(
        f"Query failed after {retries} attempts: {query}"
    ) from last_error


# =========================================================
# Output
# =========================================================


def write_output(
    output_path: Path, payload: dict[str, Any], jsonp_callback: str
) -> None:
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    if jsonp_callback:
        content = f"{jsonp_callback}({json_text});\n"
    else:
        content = json_text + "\n"
    output_path.write_text(content, encoding="utf-8")


# =========================================================
# Main
# =========================================================


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dblp_search",
        description="Search DBLP publications and save results as JSONP.",
    )
    parser.add_argument(
        "-c",
        "--config",
        help="Path to YAML config (default: dblp.yml next to this script)",
    )
    args = parser.parse_args(argv)

    # Load config
    config_path = (
        Path(args.config).expanduser().resolve()
        if args.config
        else default_config_path()
    )
    config = load_config(config_path)

    # Read common config
    base_url = str(
        get_value(config, ("network", "base_url"), "https://dblp.org")
    ).strip()
    timeout = int(get_value(config, ("network", "timeout"), 30))
    retries = int(get_value(config, ("network", "retries"), 3))

    proxy_enabled = bool(get_value(config, ("proxy", "enabled"), False))
    proxy_url = str(get_value(config, ("proxy", "url"), "")).strip()
    proxies = build_proxies(proxy_enabled, proxy_url)

    # DBLP-specific
    results_per_query = int(
        get_value(config, ("search", "results_per_query"), 50)
    )
    year_filter = str(get_value(config, ("search", "year"), "")).strip()

    configured_output_dir = Path(
        str(get_value(config, ("output", "parent_dir"), "./results"))
    ).expanduser()
    output_dir = (
        configured_output_dir
        if configured_output_dir.is_absolute()
        else (config_path.parent / configured_output_dir).resolve()
    )
    jsonp_callback = str(
        get_value(config, ("output", "jsonp_callback"), "dblpSearchResults")
    ).strip()
    save_raw_results = bool(
        get_value(config, ("output", "save_raw_results"), True)
    )

    validate_jsonp_callback(jsonp_callback)
    queries = parse_queries(config)

    api_url = urljoin(base_url.rstrip("/") + "/", "search/publ/api")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Log startup
    log_info(f"Config file: {config_path}")
    log_info(f"Base URL: {base_url}")
    log_info(f"API URL: {api_url}")
    log_info(f"Proxy: {proxy_url if proxies else 'disabled'}")
    log_info(f"Output directory: {output_dir}")
    log_info(f"Query count: {len(queries)}")
    log_info(f"Results per query: {results_per_query}")
    if year_filter:
        log_info(f"Year filter: {year_filter}")

    # Run search
    all_records: list[dict[str, Any]] = []
    raw_results: dict[str, Any] = {}
    errors: list[dict[str, str]] = []

    for query in queries:
        try:
            raw_result = search_with_retry(
                api_url=api_url,
                query=query,
                results_per_query=results_per_query,
                year_filter=year_filter,
                proxies=proxies,
                timeout=timeout,
                retries=retries,
            )
            hits = extract_hits(raw_result)
            log_info(f"Hit count query='{query}': {len(hits)}")

            if save_raw_results:
                raw_results[query] = raw_result

            for rank, hit in enumerate(hits, start=1):
                all_records.append(normalize_record(hit, query, rank))
        except Exception as exc:
            log_error(f"Search failed query='{query}' error='{exc}'")
            errors.append({"query": query, "error": str(exc)})

    # Dedupe and write
    unique_records = deduplicate(all_records)
    created_at = datetime.now()
    timestamp = created_at.strftime("%Y%m%d_%H%M%S")
    ext = "jsonp" if jsonp_callback else "json"
    output_path = output_dir / f"dblp_search_{timestamp}.{ext}"

    payload: dict[str, Any] = {
        "metadata": {
            "created_at": created_at.isoformat(timespec="seconds"),
            "config_file": str(config_path),
            "base_url": base_url,
            "api_url": api_url,
            "proxy_enabled": bool(proxies),
            "proxy_url": proxy_url if proxies else "",
            "results_per_query": results_per_query,
            "year_filter": year_filter,
            "query_count": len(queries),
            "queries": queries,
            "total_records_before_deduplication": len(all_records),
            "total_records_after_deduplication": len(unique_records),
            "error_count": len(errors),
        },
        "records": unique_records,
        "errors": errors,
    }
    if save_raw_results:
        payload["raw_results"] = raw_results

    write_output(output_path, payload, jsonp_callback)

    log_info(f"Saved file: {output_path}")
    log_info(f"Total records before deduplication: {len(all_records)}")
    log_info(f"Total records after deduplication: {len(unique_records)}")
    if errors:
        log_warn(f"Finished with {len(errors)} query errors")

    print(output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
