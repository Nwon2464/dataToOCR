#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import html
import json
import shutil
from pathlib import Path
from typing import Any


CSS = """
:root {
  --bg:#f4f5f7;
  --paper:#fff;
  --text:#1f2937;
  --muted:#6b7280;
  --line:#d9dde5;
  --blue:#2563eb;
  --blue-soft:#eaf1ff;
  --green:#0f766e;
  --yellow:#fff7d6;
  --code:#0f172a;
}
* { box-sizing:border-box; }
body {
  margin:0;
  background:var(--bg);
  color:var(--text);
  font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans CJK JP","Noto Sans JP",sans-serif;
}
header {
  position:sticky;
  top:0;
  z-index:10;
  background:#fff;
  border-bottom:1px solid var(--line);
  padding:14px 22px;
  display:flex;
  align-items:center;
  justify-content:space-between;
}
.title { font-size:18px; font-weight:750; }
.sub { font-size:13px; color:var(--muted); margin-top:3px; }
.wrap {
  display:grid;
  grid-template-columns:38% 62%;
  gap:16px;
  padding:16px;
  max-width:1480px;
  margin:0 auto;
}
.panel {
  background:#fff;
  border:1px solid var(--line);
  border-radius:16px;
  box-shadow:0 1px 4px rgba(15,23,42,.05);
  overflow:hidden;
}
.panel-head {
  padding:12px 16px;
  border-bottom:1px solid var(--line);
  font-weight:700;
  background:#fafafa;
  display:flex;
  justify-content:space-between;
  align-items:center;
}
.panel-head span {
  font-size:12px;
  color:var(--muted);
  font-weight:500;
}
.preview {
  padding:16px;
  background:#e8ebef;
  max-height:calc(100vh - 105px);
  overflow:auto;
}
.preview img {
  width:100%;
  border-radius:6px;
  box-shadow:0 4px 18px rgba(0,0,0,.2);
  background:#fff;
}
.content {
  padding:26px 34px 48px;
  line-height:1.82;
  font-size:17px;
}
.badge {
  display:inline-block;
  background:var(--blue-soft);
  color:var(--blue);
  font-size:12px;
  font-weight:750;
  border-radius:999px;
  padding:5px 10px;
  margin-bottom:18px;
}
h1 {
  font-size:28px;
  line-height:1.35;
  margin:8px 0 24px;
}
h2 {
  font-size:22px;
  margin:28px 0 12px;
  padding-left:12px;
  border-left:5px solid var(--blue);
}
h3 {
  font-size:18px;
  margin:22px 0 10px;
}
p { margin:12px 0; }
.block {
  margin:15px 0;
  padding:15px 18px;
  border:1px solid var(--line);
  border-radius:14px;
  background:#fff;
}
.block-title {
  display:inline-block;
  font-size:12px;
  font-weight:800;
  color:var(--green);
  background:#e7f8f6;
  padding:3px 8px;
  border-radius:7px;
  margin-bottom:8px;
}
.side {
  background:var(--yellow);
  border-color:#f0d47a;
}
.figure {
  background:#f8fafc;
}
pre {
  white-space:pre-wrap;
  word-break:break-word;
  background:#f8fafc;
  color:var(--code);
  padding:14px;
  border-radius:10px;
  border:1px solid var(--line);
  font-size:14px;
  line-height:1.55;
}
ul { padding-left:1.3em; }
li { margin:8px 0; }
.figure img {
  max-width:100%;
  border:1px solid var(--line);
  border-radius:10px;
  background:white;
  margin-top:10px;
}
.meta {
  font-size:12px;
  color:var(--muted);
  border-top:1px dashed var(--line);
  margin-top:30px;
  padding-top:12px;
}
@media(max-width:900px) {
  .wrap { grid-template-columns:1fr; }
  .preview { max-height:460px; }
  .content { padding:22px; }
}
"""


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def find_one(mineru_dir: Path, pattern: str) -> Path:
    matches = sorted(mineru_dir.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"not found: {mineru_dir}/{pattern}")
    return matches[0]


def flatten_content(obj: Any) -> str:
    parts: list[str] = []

    def walk(x: Any) -> None:
        if x is None:
            return
        if isinstance(x, str):
            s = x.strip()
            if s:
                parts.append(s)
            return
        if isinstance(x, list):
            for y in x:
                walk(y)
            return
        if isinstance(x, dict):
            for key in ("content", "text"):
                v = x.get(key)
                if isinstance(v, str) and v.strip():
                    parts.append(v.strip())

            for key, value in x.items():
                if key in {"bbox", "image_source"}:
                    continue
                if key in {"content", "text"} and isinstance(value, str):
                    continue
                if key in {
                    "title_content",
                    "paragraph_content",
                    "item_content",
                    "list_items",
                    "image_caption",
                    "image_footnote",
                    "table_body",
                    "table_caption",
                    "table_footnote",
                    "page_header_content",
                    "page_footer_content",
                    "page_aside_text_content",
                    "aside_text_content",
                }:
                    walk(value)

    walk(obj)

    cleaned: list[str] = []
    for part in parts:
        if not cleaned or cleaned[-1] != part:
            cleaned.append(part)
    return "\n".join(cleaned).strip()


def extract_item_text(item: dict[str, Any]) -> str:
    item_type = item.get("type")
    content = item.get("content", {})

    if item_type == "title":
        return flatten_content(content.get("title_content", content))

    if item_type == "paragraph":
        return flatten_content(content.get("paragraph_content", content))

    if item_type == "list":
        items = content.get("list_items", []) if isinstance(content, dict) else []
        lines: list[str] = []
        for li in items:
            if isinstance(li, dict):
                text = flatten_content(li.get("item_content", li))
            else:
                text = flatten_content(li)
            if text:
                lines.append(text)
        return "\n".join(lines)

    if item_type in {"page_header", "page_footer"}:
        return flatten_content(content)

    if item_type == "image":
        if isinstance(content, dict):
            direct = content.get("content")
            if isinstance(direct, str) and direct.strip():
                return direct.strip()
            return flatten_content(content.get("image_caption", []))
        return ""

    if item_type == "table":
        return flatten_content(content)

    return flatten_content(content)


def copy_image_for_item(
    item: dict[str, Any],
    mineru_dir: Path,
    assets_dir: Path,
) -> str | None:
    content = item.get("content", {})
    if not isinstance(content, dict):
        return None

    image_source = content.get("image_source", {})
    if not isinstance(image_source, dict):
        return None

    rel_path = image_source.get("path")
    if not rel_path:
        return None

    src = mineru_dir / rel_path
    if not src.exists():
        return None

    dest = assets_dir / src.name
    if not dest.exists():
        shutil.copy2(src, dest)

    return f"assets/{dest.name}"


def classify_item(item: dict[str, Any]) -> str:
    item_type = item.get("type", "unknown")
    bbox = item.get("bbox") or [0, 0, 0, 0]
    x0 = bbox[0] if isinstance(bbox, list) and len(bbox) >= 4 else 0

    if item_type in {"page_header", "page_footer", "page_number"}:
        return "meta"

    if item_type in {"page_aside_text", "aside_text"}:
        return "meta"

    if item_type == "title":
        return "title"

    if item_type == "paragraph":
        # Heuristic: right-side narrow text is likely a side note.
        if x0 > 760:
            return "side_note"
        return "paragraph"

    if item_type == "list":
        return "list"

    if item_type == "table":
        return "table"

    if item_type == "image":
        sub_type = str(item.get("sub_type", "")).lower()
        text = extract_item_text(item)
        if "table" in sub_type or "\t" in text or ("|" in text and "\n" in text):
            return "table_or_figure"
        return "figure"

    return item_type


def render_origin_preview(origin_pdf: Path, page_idx: int, dest: Path) -> str | None:
    try:
        import fitz  # PyMuPDF
    except Exception:
        return None

    try:
        doc = fitz.open(str(origin_pdf))
        if page_idx < 0 or page_idx >= len(doc):
            doc.close()
            return None
        page = doc[page_idx]
        pix = page.get_pixmap(matrix=fitz.Matrix(0.45, 0.45), alpha=False)
        pix.save(str(dest))
        doc.close()
        return f"assets/{dest.name}"
    except Exception:
        return None


def normalize_page(
    page_items: list[dict[str, Any]],
    page_idx: int,
    page_no: int,
    mineru_dir: Path,
    assets_dir: Path,
    preview_image: str | None,
) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    side_notes: list[dict[str, Any]] = []
    meta: list[dict[str, Any]] = []

    for i, item in enumerate(page_items):
        block_type = classify_item(item)
        text = extract_item_text(item)
        image = copy_image_for_item(item, mineru_dir, assets_dir)

        content = item.get("content", {})
        level = None
        if item.get("type") == "title" and isinstance(content, dict):
            level = content.get("level", 2)

        block: dict[str, Any] = {
            "id": f"p{page_no:03d}_b{i + 1:03d}",
            "page": page_no,
            "type": block_type,
            "source_type": item.get("type"),
            "text": text,
            "bbox": item.get("bbox"),
        }

        if level:
            block["level"] = level

        if image:
            block["image"] = image

        if block_type == "meta":
            meta.append(block)
        elif block_type == "side_note":
            side_notes.append(block)
        else:
            blocks.append(block)

    return {
        "page": page_no,
        "page_idx": page_idx,
        "preview_image": preview_image,
        "blocks": blocks,
        "side_notes": side_notes,
        "meta": meta,
    }


def block_to_markdown(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    text = str(block.get("text") or "").strip()

    if block_type == "title":
        level = int(block.get("level", 2))
        level = min(max(level, 2), 4)
        return f"{'#' * level} {text}\n" if text else ""

    if block_type == "paragraph":
        return f"{text}\n" if text else ""

    if block_type == "list":
        lines = [f"- {line.strip()}" for line in text.splitlines() if line.strip()]
        return "\n".join(lines) + "\n" if lines else ""

    if block_type == "side_note":
        if not text:
            return ""
        return "> **補足 / Side Note**\n>\n" + "\n".join(
            "> " + line for line in text.splitlines()
        ) + "\n"

    if block_type in {"table", "table_or_figure"}:
        out = "### 表 / 図表\n\n"
        if text:
            out += f"```text\n{text}\n```\n"
        if block.get("image"):
            out += f"\n![image]({block['image']})\n"
        return out

    if block_type == "figure":
        out = "### 図 / Image\n\n"
        if text:
            out += f"```text\n{text}\n```\n"
        if block.get("image"):
            out += f"\n![image]({block['image']})\n"
        return out

    return f"{text}\n" if text else ""


def page_to_markdown(page: dict[str, Any]) -> str:
    lines = [f"# Page {page['page']}", ""]

    for block in page["blocks"]:
        md = block_to_markdown(block).strip()
        if md:
            lines.append(md)
            lines.append("")

    if page["side_notes"]:
        lines.append("## 補足 / Side Notes")
        lines.append("")
        for block in page["side_notes"]:
            md = block_to_markdown(block).strip()
            if md:
                lines.append(md)
                lines.append("")

    return "\n".join(lines).strip() + "\n"


def html_block(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    text = str(block.get("text") or "").strip()
    escaped = html.escape(text)

    if block_type == "title":
        level = int(block.get("level", 2))
        level = min(max(level, 2), 3)
        return f"<h{level}>{escaped}</h{level}>" if text else ""

    if block_type == "paragraph":
        if not text:
            return ""
        body = escaped.replace("\n", "<br>")
        return f'<div class="block"><span class="block-title">본문</span><p>{body}</p></div>'

    if block_type == "list":
        items = "".join(
            f"<li>{html.escape(line.strip())}</li>"
            for line in text.splitlines()
            if line.strip()
        )
        if not items:
            return ""
        return f'<div class="block"><span class="block-title">목록</span><ul>{items}</ul></div>'

    if block_type == "side_note":
        if not text:
            return ""
        body = escaped.replace("\n", "<br>")
        return f'<div class="block side"><span class="block-title">補足 / Side Note</span><p>{body}</p></div>'

    if block_type in {"table", "table_or_figure"}:
        body = f"<pre>{escaped}</pre>" if text else ""
        img = f'<img src="{html.escape(block["image"])}" />' if block.get("image") else ""
        return f'<div class="block figure"><span class="block-title">表 / 図表</span>{body}{img}</div>'

    if block_type == "figure":
        body = f"<pre>{escaped}</pre>" if text else ""
        img = f'<img src="{html.escape(block["image"])}" />' if block.get("image") else ""
        return f'<div class="block figure"><span class="block-title">図 / Image</span>{body}{img}</div>'

    if not text:
        return ""
    body = escaped.replace("\n", "<br>")
    return f'<div class="block"><span class="block-title">{html.escape(str(block_type))}</span><p>{body}</p></div>'


def page_to_html(page: dict[str, Any], book_label: str) -> str:
    blocks_html: list[str] = []

    for block in page["blocks"]:
        blocks_html.append(html_block(block))

    if page["side_notes"]:
        blocks_html.append("<h2>補足 / Side Notes</h2>")
        for block in page["side_notes"]:
            blocks_html.append(html_block(block))

    meta_html = ""
    if page["meta"]:
        meta_text = " / ".join(
            str(m.get("text") or "") for m in page["meta"] if m.get("text")
        )
        if meta_text:
            meta_html = f'<div class="meta">Header/Footer OCR: {html.escape(meta_text)}</div>'

    preview = page.get("preview_image")
    if preview:
        preview_html = f'<img src="{html.escape(preview)}" alt="source page preview">'
    else:
        preview_html = "<p>Preview unavailable. Install PyMuPDF to render source previews.</p>"

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Text Study Page {page['page']}</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <div>
    <div class="title">{html.escape(book_label)} - Page {page['page']}</div>
    <div class="sub">MinerU content_list_v2 기반 재구성 · 드래그/복사 우선</div>
  </div>
  <div class="sub">원본 배치보다 텍스트 보존 우선</div>
</header>
<main class="wrap">
  <aside class="panel">
    <div class="panel-head">원본 페이지 미리보기 <span>참조용</span></div>
    <div class="preview">{preview_html}</div>
  </aside>
  <section class="panel">
    <div class="panel-head">재구성 텍스트 <span>text_study 후보</span></div>
    <article class="content">
      <span class="badge">Page {page['page']}</span>
      {''.join(blocks_html)}
      {meta_html}
    </article>
  </section>
</main>
</body>
</html>
"""


def write_index(pages: list[dict[str, Any]], output_dir: Path, book_label: str) -> None:
    links = []
    for page in pages:
        n = page["page"]
        links.append(
            f'<li><a href="text_study_page{n:03d}.html">Page {n}</a> '
            f'· <a href="page{n:03d}_text_study.md">MD</a></li>'
        )

    index_html = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{html.escape(book_label)} Text Study</title>
<style>
body {{
  font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans CJK JP",sans-serif;
  padding:32px;
  line-height:1.8;
  color:#1f2937;
}}
a {{ color:#2563eb; }}
</style>
</head>
<body>
<h1>{html.escape(book_label)} Text Study</h1>
<p>MinerU content_list_v2 기반으로 생성한 text_study HTML/Markdown입니다.</p>
<ul>
{''.join(links)}
</ul>
</body>
</html>
"""
    (output_dir / "index.html").write_text(index_html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mineru-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--start-page", type=int, default=None)
    parser.add_argument("--book-label", default=None)
    args = parser.parse_args()

    mineru_dir = args.mineru_dir
    output_dir = args.output_dir
    assets_dir = output_dir / "assets"

    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    content_v2_path = find_one(mineru_dir, "*_content_list_v2.json")
    origin_pdf = find_one(mineru_dir, "*_origin.pdf")

    content_pages = read_json(content_v2_path)

    if not isinstance(content_pages, list):
        raise TypeError(f"expected list in {content_v2_path}")

    start_page = args.start_page
    if start_page is None:
        # Infer from folder name like uscpa_reg2_1_p022_024
        name = mineru_dir.name
        start_page = 1
        import re
        m = re.search(r"_p(\d{3})_", name)
        if m:
            start_page = int(m.group(1))

    book_label = args.book_label or mineru_dir.name

    pages: list[dict[str, Any]] = []
    for page_idx, page_items in enumerate(content_pages):
        page_no = start_page + page_idx
        preview_path = assets_dir / f"source_page_{page_no:03d}_preview.png"
        preview_image = render_origin_preview(origin_pdf, page_idx, preview_path)

        page = normalize_page(
            page_items=page_items,
            page_idx=page_idx,
            page_no=page_no,
            mineru_dir=mineru_dir,
            assets_dir=assets_dir,
            preview_image=preview_image,
        )
        pages.append(page)

        (output_dir / f"normalized_page{page_no:03d}.json").write_text(
            json.dumps(page, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        (output_dir / f"page{page_no:03d}_text_study.md").write_text(
            page_to_markdown(page),
            encoding="utf-8",
        )

        (output_dir / f"text_study_page{page_no:03d}.html").write_text(
            page_to_html(page, book_label=book_label),
            encoding="utf-8",
        )

    (output_dir / "normalized_pages.json").write_text(
        json.dumps({"book_label": book_label, "pages": pages}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    write_index(pages, output_dir, book_label)

    print(f"mineru_dir : {mineru_dir}")
    print(f"output_dir : {output_dir}")
    print(f"pages      : {len(pages)}")
    print("created    :")
    print(f"  {output_dir / 'index.html'}")
    print(f"  {output_dir / 'normalized_pages.json'}")


if __name__ == "__main__":
    main()
