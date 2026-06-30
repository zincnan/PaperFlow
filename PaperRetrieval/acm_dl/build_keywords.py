#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import re
from pathlib import Path


BEGIN_MARKER = "# ===== ACM_SEARCH_QUERY_BEGIN ====="
END_MARKER = "# ===== ACM_SEARCH_QUERY_END ====="


def remove_generated_block(text: str) -> str:
    pattern = re.compile(
        rf"\n*{re.escape(BEGIN_MARKER)}.*?{re.escape(END_MARKER)}\n*",
        flags=re.DOTALL,
    )
    return pattern.sub("\n", text).rstrip() + "\n"


def is_comment(line: str) -> bool:
    return line.strip().startswith("#")


def clean_line(line: str) -> str:
    return line.strip()


def needs_quote(term: str) -> bool:
    if not term:
        return False

    if term.startswith('"') and term.endswith('"'):
        return False

    if term.startswith("(") and term.endswith(")"):
        return False

    if any(op in term.upper().split() for op in ["AND", "OR", "NOT"]):
        return False

    return bool(re.search(r"\s", term))


def quote_term(term: str) -> str:
    term = term.strip()

    if not term:
        return term

    if term.startswith('"') and term.endswith('"'):
        return term

    if needs_quote(term):
        escaped = term.replace('"', r'\"')
        return f'"{escaped}"'

    return term


def parse_keyword_file(text: str) -> tuple[list[list[str]], list[str]]:
    text = remove_generated_block(text)

    positive_groups: list[list[str]] = []
    current_group: list[str] = []
    negative_terms: list[str] = []

    for raw_line in text.splitlines():
        line = clean_line(raw_line)

        if not line:
            if current_group:
                positive_groups.append(current_group)
                current_group = []
            continue

        if is_comment(line):
            continue

        if line.startswith("!"):
            term = line[1:].strip()
            if term:
                negative_terms.append(term)
            continue

        current_group.append(line)

    if current_group:
        positive_groups.append(current_group)

    return positive_groups, negative_terms


def build_or_group(terms: list[str]) -> str:
    quoted_terms = [quote_term(term) for term in terms if term.strip()]

    if not quoted_terms:
        return ""

    if len(quoted_terms) == 1:
        return quoted_terms[0]

    return "(" + " OR ".join(quoted_terms) + ")"


def build_acm_query(positive_groups: list[list[str]], negative_terms: list[str]) -> str:
    positive_parts = []

    for group in positive_groups:
        group_query = build_or_group(group)
        if group_query:
            positive_parts.append(group_query)

    if not positive_parts:
        raise ValueError("No positive keyword groups found")

    query = " AND ".join(positive_parts)

    if negative_terms:
        negative_query = build_or_group(negative_terms)
        if negative_query:
            query = f"{query} AND NOT {negative_query}"

    return query


def wrap_query(query: str) -> str:
    return (
        f"\n{BEGIN_MARKER}\n"
        # f"# Copy the following query into ACM Digital Library Advanced Search.\n"
        # f"# Different keyword blocks are combined by AND.\n"
        # f"# Lines within one block are combined by OR.\n"
        # f"# Lines starting with ! are combined as global NOT terms.\n"
        f"\n"
        f"{query}\n"
        f"\n"
        f"{END_MARKER}\n"
        
    )


def update_keyword_file(keyword_file: Path) -> str:
    if not keyword_file.exists():
        raise FileNotFoundError(f"Keyword file not found: {keyword_file}")

    original_text = keyword_file.read_text(encoding="utf-8")
    cleaned_text = remove_generated_block(original_text)

    positive_groups, negative_terms = parse_keyword_file(cleaned_text)
    query = build_acm_query(positive_groups, negative_terms)

    updated_text = cleaned_text.rstrip() + "\n" + wrap_query(query)
    keyword_file.write_text(updated_text, encoding="utf-8")

    return query


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build ACM Digital Library boolean search query from keyword file"
    )

    parser.add_argument(
        "keyword_file_positional",
        nargs="?",
        help="Path to keyword file",
    )

    parser.add_argument(
        "-k",
        "--keyword-file",
        default=None,
        help="Path to keyword file",
    )

    args = parser.parse_args(argv)

    keyword_file_arg = args.keyword_file or args.keyword_file_positional

    if not keyword_file_arg:
        parser.error(
            "Please provide a keyword file, for example: "
            "python build_keywords.py keywords/test.txt"
        )

    keyword_file = Path(keyword_file_arg).expanduser().resolve()
    query = update_keyword_file(keyword_file)

    print(query)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


if __name__ == "__main__":
    main()