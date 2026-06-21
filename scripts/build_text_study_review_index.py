#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


CSS = """
body {
  margin: 0;
  background: #f4f5f7;
  color: #1f2937;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans CJK JP", sans-serif;
}
header {
  background: #fff;
  border-bottom: 1px solid #d9dde5;
  padding: 22px 28px;
}
h1 {
  margin: 0 0 6px;
  font-size: 26px;
}
.sub {
  color: #6b7280;
  font-size: 14px;
}
main {
  padding: 24px 28px 44px;
  max-width: 1280px;
  margin: 0 auto;
}
.summary {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}
.card {
  background: #fff;
  border: 1px solid #d9dde5;
  border-radius: 14px;
  padding: 14px 16px;
  box-shadow: 0 1px 4px rgba(15,23,42,.05);
}
.card .num {
  font-size: 24px;
  font-weight: 800;
}
.card .label {
  color: #6b7280;
  font-size: 13px;
  margin-top: 3px;
}
table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  border: 1px solid #d9dde5;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(15,23,42,.05);
}
th, td {
  border-bottom: 1px solid #e5e7eb;
  padding: 10px 12px;
  text-align: left;
  font-size: 14px;
  vertical-align: top;
}
th {
  background: #f8fafc;
  color: #374151;
  font-weight: 750;
}
tr:hover td {
  background: #f9fbff;
}
a {
  color: #2563eb;
  text-decoration: none;
  font-weight: 650;
}
a:hover {
  text-decoration: underline;
}
.badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 999px;
  background: #eaf1ff;
  color: #2563eb;
  font-size: 12px;
  font-weight: 750;
}
.warn {
  color: #b45309;
  font-weight: 700;
}
.ok {
  color: #0f766e;
  font-weight: 700;
}
.small {
  color: #6b7280;
  font-size: 12px;
}
.section-title {
  margin: 30px 0 12px;
  font-size: 20px;
  font-weight: 850;
}
.bad {
  color: #b91c1c;
  font-weight: 800;
}
.check {
  color: #b45309;
  font-weight: 800;
}
.quality-ok {
  color: #0f766e;
  font-weight: 800;
}
.reason {
  color: #6b7280;
  font-size: 12px;
}
@media(max-width: 900px) {
  .summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  table {
    font-size: 13px;
  }
}
"""


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_image_count(page: dict[str, Any]) -> int:
    count = 0
    for group in ("blocks", "side_notes", "meta"):
        for block in page.get(group, []):
            if block.get("image"):
                count += 1
    return count


def collect_empty_text_blocks(page: dict[str, Any]) -> int:
    count = 0
    for block in page.get("blocks", []):
        block_type = block.get("type")
        text = (block.get("text") or "").strip()
        has_image = bool(block.get("image"))
        if block_type in {"figure", "table", "table_or_figure", "chart"} and has_image:
            continue
        if not text:
            count += 1
    return count


def summarize_chunk(chunk_dir: Path, root: Path) -> dict[str, Any] | None:
    normalized_path = chunk_dir / "normalized_pages.json"
    index_path = chunk_dir / "index.html"

    if not normalized_path.exists() or not index_path.exists():
        return None

    data = read_json(normalized_path)
    pages = data.get("pages", [])

    page_count = len(pages)
    block_count = sum(len(p.get("blocks", [])) for p in pages)
    side_note_count = sum(len(p.get("side_notes", [])) for p in pages)
    meta_count = sum(len(p.get("meta", [])) for p in pages)
    image_count = sum(collect_image_count(p) for p in pages)
    empty_text_blocks = sum(collect_empty_text_blocks(p) for p in pages)

    page_numbers = [p.get("page") for p in pages if p.get("page") is not None]
    if page_numbers:
        page_range = f"{min(page_numbers):03d}-{max(page_numbers):03d}"
    else:
        page_range = "-"

    return {
        "name": chunk_dir.name,
        "page_range": page_range,
        "page_count": page_count,
        "block_count": block_count,
        "side_note_count": side_note_count,
        "meta_count": meta_count,
        "image_count": image_count,
        "empty_text_blocks": empty_text_blocks,
        "index_href": index_path.relative_to(root).as_posix(),
        "normalized_href": normalized_path.relative_to(root).as_posix(),
    }


def block_text_length(block: dict[str, Any]) -> int:
    return len((block.get("text") or "").strip())


def page_text_length(page: dict[str, Any]) -> int:
    total = 0
    for group in ("blocks", "side_notes"):
        for block in page.get(group, []):
            total += block_text_length(block)
    return total


def page_image_count(page: dict[str, Any]) -> int:
    return collect_image_count(page)


def classify_page_quality(page: dict[str, Any]) -> tuple[str, list[str]]:
    blocks = page.get("blocks", [])
    side_notes = page.get("side_notes", [])
    text_len = page_text_length(page)
    images = page_image_count(page)
    empty_blocks = collect_empty_text_blocks(page)

    reasons: list[str] = []

    if text_len == 0 and images == 0:
        reasons.append("no text and no image")

    if blocks and empty_blocks >= max(3, len(blocks) // 2):
        reasons.append("many empty blocks")

    if text_len < 40 and images == 0:
        reasons.append("very short text without image")

    for block in blocks:
        block_type = block.get("type")
        block_text = (block.get("text") or "").strip()
        block_image = block.get("image")
        if block_type in {"table", "chart", "table_or_figure", "figure"} and not block_text and not block_image:
            reasons.append(f"empty {block_type}")
            break

    # Many side notes alone usually means the page has rich marginal notes,
    # not that OCR/export quality is bad. Keep it as an informational signal only
    # when another quality issue already exists.
    if len(side_notes) >= 8 and reasons:
        reasons.append("many side notes")

    if any(r in reasons for r in ["no text and no image"]):
        return "BAD", reasons

    if reasons:
        return "CHECK", reasons

    return "OK", []


def collect_page_quality_rows(summaries: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for summary in summaries:
        chunk_dir = root / summary["name"]
        normalized_path = chunk_dir / "normalized_pages.json"
        if not normalized_path.exists():
            continue

        data = read_json(normalized_path)
        for page in data.get("pages", []):
            page_no = page.get("page")
            if page_no is None:
                continue

            quality, reasons = classify_page_quality(page)
            page_html = chunk_dir / f"text_study_page{int(page_no):03d}.html"

            rows.append({
                "chunk": summary["name"],
                "page": int(page_no),
                "quality": quality,
                "reasons": reasons,
                "text_len": page_text_length(page),
                "blocks": len(page.get("blocks", [])),
                "side_notes": len(page.get("side_notes", [])),
                "images": page_image_count(page),
                "empty_blocks": collect_empty_text_blocks(page),
                "href": page_html.relative_to(root).as_posix() if page_html.exists() else summary["index_href"],
            })

    return rows


def build_html(summaries: list[dict[str, Any]], title: str, root: Path) -> str:
    total_chunks = len(summaries)
    total_pages = sum(s["page_count"] for s in summaries)
    total_blocks = sum(s["block_count"] for s in summaries)
    total_side_notes = sum(s["side_note_count"] for s in summaries)
    total_images = sum(s["image_count"] for s in summaries)

    rows = []
    for s in summaries:
        if s["empty_text_blocks"]:
            status = f'<span class="warn">check {s["empty_text_blocks"]}</span>'
        else:
            status = '<span class="ok">ok</span>'

        rows.append(
            "<tr>"
            f'<td><a href="{html.escape(s["index_href"])}">{html.escape(s["name"])}</a></td>'
            f'<td><span class="badge">{html.escape(s["page_range"])}</span></td>'
            f'<td>{s["page_count"]}</td>'
            f'<td>{s["block_count"]}</td>'
            f'<td>{s["side_note_count"]}</td>'
            f'<td>{s["image_count"]}</td>'
            f'<td>{status}</td>'
            f'<td><a href="{html.escape(s["normalized_href"])}">JSON</a></td>'
            "</tr>"
        )

    page_quality_rows = collect_page_quality_rows(summaries, root)

    risky_rows = [
        row for row in page_quality_rows
        if row["quality"] in {"BAD", "CHECK"}
    ]

    # Show risk pages first. Limit keeps the index readable for large books.
    risky_rows = sorted(
        risky_rows,
        key=lambda r: (0 if r["quality"] == "BAD" else 1, r["page"])
    )

    quality_trs = []
    for r in risky_rows:
        if r["quality"] == "BAD":
            q = '<span class="bad">BAD</span>'
        elif r["quality"] == "CHECK":
            q = '<span class="check">CHECK</span>'
        else:
            q = '<span class="quality-ok">OK</span>'

        reasons = ", ".join(r["reasons"]) if r["reasons"] else "-"
        quality_trs.append(
            "<tr>"
            f'<td>{q}</td>'
            f'<td><a href="{html.escape(r["href"])}">page {r["page"]:03d}</a></td>'
            f'<td>{html.escape(r["chunk"])}</td>'
            f'<td>{r["text_len"]}</td>'
            f'<td>{r["blocks"]}</td>'
            f'<td>{r["side_notes"]}</td>'
            f'<td>{r["images"]}</td>'
            f'<td>{r["empty_blocks"]}</td>'
            f'<td><span class="reason">{html.escape(reasons)}</span></td>'
            "</tr>"
        )

    if not quality_trs:
        quality_table = "<p class=\"small\">No risky pages detected.</p>"
    else:
        quality_table = f"""
  <table>
    <thead>
      <tr>
        <th>Quality</th>
        <th>Page</th>
        <th>Chunk</th>
        <th>Text Length</th>
        <th>Blocks</th>
        <th>Side Notes</th>
        <th>Images</th>
        <th>Empty Blocks</th>
        <th>Reason</th>
      </tr>
    </thead>
    <tbody>
      {''.join(quality_trs)}
    </tbody>
  </table>
"""

    bad_count = sum(1 for r in page_quality_rows if r["quality"] == "BAD")
    check_count = sum(1 for r in page_quality_rows if r["quality"] == "CHECK")
    ok_count = sum(1 for r in page_quality_rows if r["quality"] == "OK")

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>{html.escape(title)}</h1>
  <div class="sub">Generated text_study chunks review index</div>
</header>
<main>
  <section class="summary">
    <div class="card"><div class="num">{total_chunks}</div><div class="label">Chunks</div></div>
    <div class="card"><div class="num">{total_pages}</div><div class="label">Pages</div></div>
    <div class="card"><div class="num">{total_blocks}</div><div class="label">Blocks</div></div>
    <div class="card"><div class="num">{total_side_notes}</div><div class="label">Side Notes</div></div>
    <div class="card"><div class="num">{total_images}</div><div class="label">Images</div></div>
  </section>

  <section class="summary">
    <div class="card"><div class="num">{ok_count}</div><div class="label">OK Pages</div></div>
    <div class="card"><div class="num">{check_count}</div><div class="label">CHECK Pages</div></div>
    <div class="card"><div class="num">{bad_count}</div><div class="label">BAD Pages</div></div>
    <div class="card"><div class="num">{len(page_quality_rows)}</div><div class="label">Total Pages Scanned</div></div>
    <div class="card"><div class="num">{len(risky_rows)}</div><div class="label">Risky Rows Listed</div></div>
  </section>

  <div class="section-title">Chunk Summary</div>

  <table>
    <thead>
      <tr>
        <th>Chunk</th>
        <th>Pages</th>
        <th>Page Count</th>
        <th>Blocks</th>
        <th>Side Notes</th>
        <th>Images</th>
        <th>Empty Text Check</th>
        <th>Data</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>

  <p class="small">
    Empty Text Check is not always an error. Figure/table/image-only pages may be valid.
  </p>

  <div class="section-title">Page Quality Report</div>
  <p class="small">
    CHECK/BAD pages should be reviewed manually. They often indicate empty OCR blocks, image-only tables, or weak OCR extraction.
  </p>
  {quality_table}
</main>
</body>
</html>
"""

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text-study-root", type=Path, required=True)
    parser.add_argument("--title", default="Text Study Review Index")
    args = parser.parse_args()

    root = args.text_study_root

    if not root.exists():
        raise FileNotFoundError(f"text study root not found: {root}")

    summaries = []
    for chunk_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        summary = summarize_chunk(chunk_dir, root)
        if summary is not None:
            summaries.append(summary)

    output_path = root / "index.html"
    output_path.write_text(build_html(summaries, args.title, root), encoding="utf-8")

    print(f"text_study_root : {root}")
    print(f"chunks          : {len(summaries)}")
    print(f"created         : {output_path}")


if __name__ == "__main__":
    main()
