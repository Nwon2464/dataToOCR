from __future__ import annotations

import argparse
import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def load_toc(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        raise ValueError("TOC JSON must be a list.")

    toc = []
    for item in data:
        title = item.get("title")
        page = item.get("page")

        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"Invalid title in TOC item: {item}")

        if not isinstance(page, int):
            raise ValueError(f"Invalid page in TOC item: {item}")

        toc.append(
            {
                "title": title.strip(),
                "page": page,
            }
        )

    return toc


def add_bookmarks(input_pdf: Path, toc_json: Path, output_pdf: Path) -> None:
    reader = PdfReader(str(input_pdf))
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    toc = load_toc(toc_json)
    total_pages = len(reader.pages)

    added = 0
    skipped = 0

    for item in toc:
        title = item["title"]
        human_page = item["page"]
        page_index = human_page - 1

        if page_index < 0 or page_index >= total_pages:
            print(f"[SKIP] {title} -> page {human_page} is out of range")
            skipped += 1
            continue

        writer.add_outline_item(title, page_index)
        print(f"[ADD] {title} -> page {human_page}")
        added += 1

    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    with output_pdf.open("wb") as f:
        writer.write(f)

    print()
    print("[OK] bookmarks added")
    print(f"input  : {input_pdf}")
    print(f"toc    : {toc_json}")
    print(f"output : {output_pdf}")
    print(f"pages  : {total_pages}")
    print(f"added  : {added}")
    print(f"skipped: {skipped}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--toc", required=True)
    parser.add_argument("--output", required=True)

    args = parser.parse_args()

    input_pdf = Path(args.input).expanduser().resolve()
    toc_json = Path(args.toc).expanduser().resolve()
    output_pdf = Path(args.output).expanduser().resolve()

    if not input_pdf.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_pdf}")

    if not toc_json.exists():
        raise FileNotFoundError(f"TOC JSON not found: {toc_json}")

    add_bookmarks(input_pdf, toc_json, output_pdf)


if __name__ == "__main__":
    main()
