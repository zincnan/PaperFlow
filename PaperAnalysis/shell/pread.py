#!/usr/bin/env python3
import sys
import re
import csv
import argparse
import subprocess
import shutil
from io import StringIO


def split_markdown_row(line: str) -> list[str]:
    line = line.strip()

    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]

    cells = []
    current = []
    escaped = False

    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            current.append(char)
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)

    cells.append("".join(current).strip())
    return cells


def is_separator_row(cells: list[str]) -> bool:
    if not cells:
        return False

    for cell in cells:
        text = cell.strip().replace(" ", "")
        if not text:
            return False
        if set(text) - set("-:"):
            return False
        if "-" not in text:
            return False

    return True


def find_markdown_tables(text: str) -> list[list[str]]:
    lines = text.splitlines()
    tables = []
    current = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("|") and stripped.count("|") >= 2:
            current.append(line)
        else:
            if len(current) >= 2:
                tables.append(current)
            current = []

    if len(current) >= 2:
        tables.append(current)

    return tables


def extract_column(text: str, column_name: str = "内容") -> list[str]:
    tables = find_markdown_tables(text)

    for table in tables:
        rows = [split_markdown_row(line) for line in table]

        if len(rows) < 2:
            continue

        header = rows[0]
        separator = rows[1]

        if column_name not in header:
            continue

        if not is_separator_row(separator):
            continue

        column_index = header.index(column_name)
        values = []

        for row in rows[2:]:
            if len(row) <= column_index:
                continue

            value = row[column_index].strip()
            if value:
                values.append(value)

        return values

    return []


def normalize_cell(value: str) -> str:
    value = value.replace("<br>", "\n")
    value = value.replace("<br/>", "\n")
    value = value.replace("<br />", "\n")
    return value


def output_values(values: list[str], output_format: str) -> str:
    values = [normalize_cell(value) for value in values]

    if output_format == "tsv":
        buffer = StringIO()
        writer = csv.writer(
            buffer,
            delimiter="\t",
            quoting=csv.QUOTE_MINIMAL,
            lineterminator=""
        )
        writer.writerow(values)
        return buffer.getvalue()

    if output_format == "csv":
        buffer = StringIO()
        writer = csv.writer(buffer, lineterminator="")
        writer.writerow(values)
        return buffer.getvalue()

    if output_format == "markdown":
        return "| " + " | ".join(values) + " |"

    raise ValueError(f"Unsupported output format: {output_format}")

def copy_to_clipboard(text: str) -> None:
    if shutil.which("clip.exe"):
        subprocess.run(
            ["clip.exe"],
            input=text.encode("utf-16le"),
            check=True
        )
        return

    if shutil.which("pbcopy"):
        subprocess.run(
            ["pbcopy"],
            input=text,
            text=True,
            check=True
        )
        return

    if shutil.which("wl-copy"):
        subprocess.run(
            ["wl-copy"],
            input=text,
            text=True,
            check=True
        )
        return

    if shutil.which("xclip"):
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text,
            text=True,
            check=True
        )
        return

    if shutil.which("xsel"):
        subprocess.run(
            ["xsel", "--clipboard", "--input"],
            input=text,
            text=True,
            check=True
        )
        return

    raise RuntimeError("No clipboard tool found.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract a column from a Markdown table and copy it as one horizontal row."
    )
    parser.add_argument(
        "-c",
        "--column",
        default="内容",
        help="Column name to extract. Default: 内容"
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["tsv", "csv", "markdown"],
        default="tsv",
        help="Output format. Default: tsv"
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print result to stdout as well."
    )
    parser.add_argument(
        "--no-copy",
        action="store_true",
        help="Do not copy result to clipboard."
    )

    args = parser.parse_args()
    text = sys.stdin.read()

    values = extract_column(text, args.column)

    if not values:
        print("No valid Markdown table with the target column was found.", file=sys.stderr)
        return 1

    result = output_values(values, args.format)

    if not args.no_copy:
        copy_to_clipboard(result)
        print("Copied to clipboard.", file=sys.stderr)

    if args.print or args.no_copy:
        print(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())