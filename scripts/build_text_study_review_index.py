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


def build_html(summaries: list[dict[str, Any]], title: str) -> str:
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
    output_path.write_text(build_html(summaries, args.title), encoding="utf-8")

    print(f"text_study_root : {root}")
    print(f"chunks          : {len(summaries)}")
    print(f"created         : {output_path}")


if __name__ == "__main__":
    main()
