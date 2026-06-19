from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

from common.api_paths import get_processed_chunk_dir, get_processed_dir


DEFAULT_CLASS_NAME = "custom-block-text"
DEFAULT_THEME = [13, 83, 222]
IMPORTANT_IMAGE_KEYWORDS = (
    "Input期",
    "Output期",
    "推奨学習パターン",
    "トレーニング",
    "学習",
    "flow",
    "pattern",
)
ICON_IMAGE_KEYWORDS = (
    "アイコンについて",
    "補足",
    "用語",
    "参照",
    "MC",
    "TBS",
)
ALPHA_SECTION_RE = re.compile(r"^[a-z]\)\s*")
NUMBERED_SECTION_RE = re.compile(r"^\d+[）)]\s*")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build static HTML previews from processed MinerU render.json files.")
    parser.add_argument("chunks", nargs="*", help="Chunk IDs to preview.")
    parser.add_argument("--all", action="store_true", help="Build previews for every processed chunk with render.json.")
    return parser.parse_args()


def rel_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def load_render_json(chunk_id: str) -> tuple[Path, dict[str, Any]]:
    render_path = get_processed_chunk_dir(chunk_id) / "render.json"
    if not render_path.exists():
        raise FileNotFoundError(f"{rel_path(render_path)} not found. Run prepare_mineru_render.py first.")
    data = json.loads(render_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{rel_path(render_path)} root must be a JSON object.")
    return render_path, data


def theme_value(block: dict[str, Any], key: str) -> str:
    theme = block.get("theme") if isinstance(block.get("theme"), dict) else {}
    value = theme.get(key) or DEFAULT_THEME
    if not isinstance(value, list) or len(value) != 3:
        value = DEFAULT_THEME
    rgb = []
    for channel in value:
        try:
            rgb.append(str(max(0, min(255, int(channel)))))
        except (TypeError, ValueError):
            rgb.append("13")
    return ", ".join(rgb)


def block_content(block: dict[str, Any]) -> str:
    value = block.get("html")
    if isinstance(value, str) and value.strip():
        return value
    text = block.get("text")
    if text is None:
        return ""
    return f"<p>{html.escape(str(text))}</p>"


def image_variant(block: dict[str, Any], index: int, blocks: list[dict[str, Any]]) -> str:
    if block.get("block_type") != "image":
        return ""
    if block.get("imageClassName"):
        return str(block["imageClassName"])

    nearby = []
    start = max(0, index - 4)
    for item in blocks[start:index]:
        if not isinstance(item, dict) or item is block:
            continue
        text = str(item.get("text") or "")
        if text:
            nearby.append(text)

    context = "\n".join(nearby)
    context_lower = context.lower()
    if any(keyword in context for keyword in ICON_IMAGE_KEYWORDS):
        return "icon-image"
    if any(keyword in context for keyword in IMPORTANT_IMAGE_KEYWORDS) or any(
        keyword.lower() in context_lower for keyword in IMPORTANT_IMAGE_KEYWORDS
    ):
        return "important-image"
    return "normal-image"


def block_text(block: dict[str, Any]) -> str:
    return " ".join(str(block.get("text") or "").split())


def is_alpha_section(block: dict[str, Any]) -> bool:
    return bool(ALPHA_SECTION_RE.match(block_text(block)))


def is_numbered_section(block: dict[str, Any]) -> bool:
    return bool(NUMBERED_SECTION_RE.match(block_text(block)))


def block_indent_classes(block: dict[str, Any], index: int, blocks: list[dict[str, Any]]) -> str:
    metadata_classes = " ".join(
        str(value)
        for value in (block.get("sectionClassName"), block.get("indentClassName"))
        if value
    )
    if metadata_classes:
        return f" {metadata_classes}"

    block_type = str(block.get("block_type") or "")
    kind = str(block.get("kind") or "")
    role = str(block.get("role") or "content")
    if role == "decorative" or block_type in {"title", "table_body", "image"}:
        return ""

    alpha = is_alpha_section(block)
    numbered = is_numbered_section(block)
    if alpha:
        return " section-alpha"
    if numbered:
        return " section-numbered indent-level-1"
    if block_type != "text" or kind != "paragraph":
        return ""

    previous_numbered = False
    in_alpha_section = False
    for previous in reversed(blocks[:index]):
        if not isinstance(previous, dict):
            continue
        previous_type = str(previous.get("block_type") or "")
        previous_role = str(previous.get("role") or "content")
        if previous_role == "decorative" or previous_type in {"image", "table_body"}:
            continue
        if previous_type == "title":
            break
        if is_alpha_section(previous):
            in_alpha_section = True
            break
        if is_numbered_section(previous):
            previous_numbered = True
            continue

    if previous_numbered:
        return " indent-level-2"
    if in_alpha_section:
        return " indent-level-1"
    return ""


def render_block(block: dict[str, Any], index: int, blocks: list[dict[str, Any]]) -> str:
    block_id = html.escape(str(block.get("id") or ""))
    class_name = html.escape(str(block.get("className") or DEFAULT_CLASS_NAME))
    fill = theme_value(block, "fill")
    stroke = theme_value(block, "stroke")
    role = str(block.get("role") or "content")
    decorative_class = " decorative-block" if role == "decorative" else ""
    indent_class = block_indent_classes(block, index, blocks)
    image_class = image_variant(block, index, blocks)
    image_wrapper_class = f" image-block {image_class}" if image_class else ""
    image_container_class = f" {image_class}" if image_class else ""
    content = block_content(block)

    return f"""<hgroup class="relative md-wrapper{decorative_class}{indent_class}{image_wrapper_class}" data-block-id="{block_id}">
  <div class="markdown-container markdown-theme-base relative {class_name}{image_container_class}"
       style="--data-fill: {fill}; --data-stroke: {stroke};">
    <div class="markdownRender">
      {content}
    </div>
  </div>
</hgroup>"""


def blocks_by_page(blocks: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for block in blocks:
        if not isinstance(block, dict):
            continue
        try:
            page = int(block.get("page") or 1)
        except (TypeError, ValueError):
            page = 1
        grouped.setdefault(page, []).append(block)
    return grouped


def normalize_pages(data: dict[str, Any]) -> list[dict[str, Any]]:
    pages = data.get("pages")
    if isinstance(pages, list) and pages:
        normalized = []
        grouped = blocks_by_page(data.get("blocks") if isinstance(data.get("blocks"), list) else [])
        for index, page in enumerate(pages, start=1):
            if not isinstance(page, dict):
                continue
            try:
                page_num = int(page.get("page") or index)
            except (TypeError, ValueError):
                page_num = index
            blocks = page.get("blocks") if isinstance(page.get("blocks"), list) else grouped.get(page_num, [])
            title = str(page.get("title") or f"Page {page_num}")
            normalized.append({"page": page_num, "title": title, "blocks": blocks})
        return normalized

    grouped = blocks_by_page(data.get("blocks") if isinstance(data.get("blocks"), list) else [])
    return [{"page": page, "title": f"Page {page}", "blocks": grouped[page]} for page in sorted(grouped)] or [
        {"page": 1, "title": "Page 1", "blocks": []}
    ]


def render_sidebar(pages: list[dict[str, Any]], warnings: list[Any]) -> str:
    links = []
    for page in pages:
        page_num = int(page["page"])
        label = f"P{page_num} · {page.get('title') or f'Page {page_num}'}"
        links.append(f'<a class="page-link" href="#page-{page_num}">{html.escape(label)}</a>')

    warning_html = ""
    if warnings:
        items = "\n".join(f"<li>{html.escape(str(warning))}</li>" for warning in warnings)
        warning_html = f"""<div class="warning-box">
  <strong>Warnings</strong>
  <ul>{items}</ul>
</div>"""

    return f"""<aside class="sidebar">
  <div class="sidebar-title">MinerU Preview</div>
  <nav class="page-nav">
    {''.join(links)}
  </nav>
  <label class="debug-toggle">
    <input type="checkbox" id="toggleDecorative">
    show decorative blocks
  </label>
  {warning_html}
</aside>"""


def render_pages(pages: list[dict[str, Any]]) -> str:
    sections = []
    for page in pages:
        page_num = int(page["page"])
        blocks = page.get("blocks") if isinstance(page.get("blocks"), list) else []
        block_html = "\n".join(
            render_block(block, index, blocks) for index, block in enumerate(blocks) if isinstance(block, dict)
        )
        sections.append(f"""<section class="page-card" id="page-{page_num}">
  <div class="page-label">PAGE {page_num}</div>
  <div class="page-wrapper-content">
    {block_html}
  </div>
</section>""")
    return "\n".join(sections)


def build_html(data: dict[str, Any], chunk_id: str) -> str:
    pages = normalize_pages(data)
    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    sidebar = render_sidebar(pages, warnings)
    main = render_pages(pages)
    title = f"MinerU Render Preview - {chunk_id}"

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{
      margin: 0;
      background: #f3f4f6;
      color: #111827;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}

    .app-shell {{
      display: grid;
      grid-template-columns: 280px 1fr;
      min-height: 100vh;
    }}

    .sidebar {{
      position: sticky;
      top: 0;
      height: 100vh;
      overflow-y: auto;
      background: #0f172a;
      color: white;
      padding: 24px 18px;
      box-sizing: border-box;
    }}

    .sidebar-title {{
      font-size: 18px;
      font-weight: 700;
      margin: 0 0 18px;
    }}

    .page-nav {{
      display: grid;
      gap: 6px;
    }}

    .page-link {{
      display: block;
      color: #dbeafe;
      text-decoration: none;
      padding: 9px 10px;
      border-radius: 8px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .page-link:hover {{
      background: rgba(255, 255, 255, 0.1);
      color: white;
    }}

    .debug-toggle {{
      display: flex;
      gap: 8px;
      align-items: center;
      margin: 20px 0;
      color: #cbd5e1;
      font-size: 13px;
    }}

    .warning-box {{
      margin-top: 18px;
      padding: 12px;
      background: rgba(251, 191, 36, 0.12);
      border: 1px solid rgba(251, 191, 36, 0.35);
      border-radius: 8px;
      color: #fde68a;
      font-size: 13px;
    }}

    .warning-box ul {{
      margin: 8px 0 0;
      padding-left: 18px;
    }}

    .main-content {{
      padding: 32px;
    }}

    .page-card {{
      max-width: 900px;
      margin: 0 auto 32px;
      padding: 40px;
      background: white;
      border-radius: 16px;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
    }}

    .page-label {{
      color: #6b7280;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0;
      margin-bottom: 20px;
    }}

    .md-wrapper {{
      margin: 12px 0;
    }}

    .md-wrapper.indent-level-1 {{
      margin-left: 28px;
    }}

    .md-wrapper.indent-level-2 {{
      margin-left: 48px;
    }}

    .md-wrapper.section-alpha {{
      margin-top: 18px;
    }}

    .md-wrapper.section-numbered {{
      margin-top: 14px;
    }}

    .markdown-container {{
      position: relative;
    }}

    .custom-block-title {{
      padding-left: 14px;
      border-left: 4px solid rgb(var(--data-stroke));
    }}

    .custom-block-header,
    .custom-block-footer,
    .custom-block-page_number {{
      color: #6b7280;
      font-size: 13px;
    }}

    .custom-block-image {{
      margin: 18px 0;
    }}

    .custom-block-image.important-image img,
    .image-block.important-image img {{
      width: 75% !important;
      max-width: 720px;
      height: auto;
      display: block;
      margin: 18px auto 24px;
    }}

    .custom-block-image.icon-image img,
    .image-block.icon-image img {{
      width: 96px !important;
      max-width: 120px;
      height: auto;
      display: block;
      margin: 8px 0 12px;
    }}

    .custom-block-image.normal-image img,
    .image-block.normal-image img {{
      max-width: 100%;
      height: auto;
      display: block;
      margin: 12px 0;
    }}

    .markdownRender {{
      color: #111827;
      font-size: 16px;
      line-height: 1.75;
      overflow-wrap: anywhere;
    }}

    .markdownRender p {{
      line-height: 1.8;
      margin: 0.65em 0;
      white-space: pre-wrap;
    }}

    .markdownRender h1,
    .markdownRender h2,
    .markdownRender h3 {{
      line-height: 1.35;
      margin: 0.8em 0 0.45em;
      font-weight: 700;
    }}

    .markdownRender h1 {{
      font-size: 1.55rem;
    }}

    .markdownRender h2 {{
      font-size: 1.25rem;
    }}

    .markdownRender h3 {{
      font-size: 1.1rem;
    }}

    .markdownRender ol,
    .markdownRender ul {{
      display: block;
      margin: 0.75em 0 0.85em;
      padding-left: 2rem;
    }}

    .markdownRender ol {{
      list-style-type: decimal;
    }}

    .markdownRender ol[type="a"] {{
      list-style-type: lower-alpha;
    }}

    .markdownRender ol[type="A"] {{
      list-style-type: upper-alpha;
    }}

    .markdownRender ol[type="i"] {{
      list-style-type: lower-roman;
    }}

    .markdownRender ol[type="I"] {{
      list-style-type: upper-roman;
    }}

    .markdownRender ul {{
      list-style-type: disc;
    }}

    .markdownRender ul ul {{
      list-style-type: circle;
    }}

    .markdownRender ul ul ul {{
      list-style-type: square;
    }}

    .markdownRender li {{
      display: list-item;
      margin: 0.28em 0;
      padding-left: 0.2rem;
    }}

    .markdownRender li > p {{
      margin: 0.25em 0;
    }}

    .markdownRender blockquote {{
      margin: 0.9em 0;
      padding: 0.1em 0 0.1em 1rem;
      border-left: 4px solid rgba(var(--data-stroke), 0.35);
      color: #4b5563;
    }}

    .table-container {{
      max-width: 100%;
      overflow-x: auto;
    }}

    .math-block {{
      display: block;
      max-width: 100%;
      overflow-x: auto;
      margin: 14px auto;
      padding: 12px 14px;
      border: 1px solid rgba(var(--data-stroke), 0.28);
      border-radius: 8px;
      background: rgba(var(--data-fill), 0.06);
      color: rgb(var(--data-fill));
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size: 14px;
      line-height: 1.65;
      text-align: center;
      white-space: pre;
    }}

    .markdownRender table {{
      width: 100%;
      border-collapse: collapse;
      margin: 12px 0;
      font-size: 14px;
    }}

    .markdownRender td,
    .markdownRender th {{
      border: 1px solid #d0d7de;
      padding: 8px 10px;
      vertical-align: top;
    }}

    .markdownRender pre:not(.math-block) {{
      max-width: 100%;
      overflow-x: auto;
      margin: 0.9em 0;
      padding: 0.85rem 1rem;
      border: 1px solid #d1d5db;
      border-radius: 8px;
      background: #f8fafc;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size: 0.9rem;
      line-height: 1.6;
    }}

    .markdownRender code {{
      border-radius: 4px;
      background: #f1f5f9;
      padding: 0.08rem 0.25rem;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size: 0.92em;
    }}

    .markdownRender pre code {{
      background: transparent;
      padding: 0;
    }}

    .markdownRender img {{
      max-width: 100%;
      height: auto;
      display: block;
      margin: 12px 0;
    }}

    body:not(.show-decorative) .decorative-block {{
      display: none;
    }}

    @media (max-width: 900px) {{
      .app-shell {{
        grid-template-columns: 1fr;
      }}

      .sidebar {{
        position: static;
        height: auto;
      }}

      .main-content {{
        padding: 16px;
      }}

      .page-card {{
        padding: 24px;
      }}

      .md-wrapper.indent-level-1 {{
        margin-left: 18px;
      }}

      .md-wrapper.indent-level-2 {{
        margin-left: 28px;
      }}
    }}
  </style>
</head>
<body>
  <div class="app-shell">
    {sidebar}
    <main class="main-content">
      {main}
    </main>
  </div>
  <script>
    const toggle = document.getElementById("toggleDecorative");
    if (toggle) {{
      toggle.addEventListener("change", () => {{
        document.body.classList.toggle("show-decorative", toggle.checked);
      }});
    }}
  </script>
</body>
</html>
"""


def build_render_preview(chunk_id: str) -> Path:
    print(f"[input] {chunk_id}")
    render_path, data = load_render_json(chunk_id)
    print(f"[read] {rel_path(render_path)}")

    if data.get("schema_version") != 2:
        print(f"[warning] schema_version is {data.get('schema_version')}, expected 2")
    if data.get("render_model") != "mineru_block_v1":
        print(f"[warning] render_model is {data.get('render_model')}, expected mineru_block_v1")

    pages = normalize_pages(data)
    blocks = data.get("blocks") if isinstance(data.get("blocks"), list) else []
    output_path = render_path.with_name("render_preview.html")
    output_path.write_text(build_html(data, chunk_id), encoding="utf-8")

    print(f"[pages] {len(pages)}")
    print(f"[blocks] {len(blocks)}")
    print(f"[write] {rel_path(output_path)}")
    print("[done]")
    return output_path


def iter_all_chunk_ids() -> list[str]:
    root = get_processed_dir()
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir() and (path / "render.json").exists())


def main() -> int:
    args = parse_args()
    chunk_ids = iter_all_chunk_ids() if args.all else args.chunks
    if not chunk_ids:
        raise SystemExit("No chunks specified. Use --all or pass chunk IDs.")

    for chunk_id in chunk_ids:
        try:
            build_render_preview(chunk_id)
        except FileNotFoundError as exc:
            print(f"[error] {exc}")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
