#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

from build_text_study_review_index import classify_page_quality, is_tiny_empty_figure


CSS = """
:root {
  --bg: #f3efe7;
  --panel: #fffdf9;
  --panel-2: #f8f1e4;
  --line: #ddcfba;
  --line-strong: #c3ae8a;
  --text: #2a241d;
  --muted: #6f6252;
  --accent: #0f766e;
  --accent-2: #9a3412;
  --shadow: 0 12px 28px rgba(74, 55, 31, 0.08);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background:
    radial-gradient(circle at top, rgba(246, 230, 199, 0.75), transparent 36%),
    linear-gradient(180deg, #f6f0e5 0%, var(--bg) 18%, #f7f3eb 100%);
  color: var(--text);
  font-family: Georgia, "Iowan Old Style", "Palatino Linotype", "Noto Serif CJK JP", serif;
  line-height: 1.65;
}
a { color: inherit; }
.topbar {
  position: sticky;
  top: 0;
  z-index: 50;
  backdrop-filter: blur(14px);
  background: rgba(250, 246, 239, 0.92);
  border-bottom: 1px solid rgba(195, 174, 138, 0.7);
  box-shadow: 0 8px 18px rgba(74, 55, 31, 0.06);
}
.topbar-inner {
  max-width: 1400px;
  margin: 0 auto;
  padding: 16px 22px;
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr);
  gap: 18px;
  align-items: center;
}
.eyebrow {
  text-transform: uppercase;
  letter-spacing: .16em;
  font-size: 11px;
  color: var(--accent-2);
  font-weight: 700;
}
h1 {
  margin: 4px 0 0;
  font-size: clamp(26px, 3.2vw, 38px);
  line-height: 1.08;
}
.sub {
  margin-top: 6px;
  color: var(--muted);
  font-size: 14px;
}
.controls {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
  align-items: center;
}
.control, .button, select {
  border: 1px solid var(--line-strong);
  background: rgba(255, 253, 249, 0.95);
  color: var(--text);
  border-radius: 999px;
  min-height: 42px;
  padding: 0 14px;
  font: inherit;
}
.button {
  cursor: pointer;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
}
.button.primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.button.ghost.active {
  background: #efe4d0;
  border-color: #b99f78;
}
.current {
  min-width: 112px;
  text-align: center;
  font-weight: 700;
}
main {
  max-width: 1400px;
  margin: 0 auto;
  padding: 22px;
}
.page {
  display: grid;
  grid-template-columns: minmax(320px, .9fr) minmax(400px, 1.1fr);
  gap: 18px;
  align-items: start;
  margin-bottom: 22px;
  scroll-margin-top: 104px;
}
.page-pane {
  background: rgba(255, 253, 249, 0.92);
  border: 1px solid var(--line);
  border-radius: 24px;
  box-shadow: var(--shadow);
  overflow: hidden;
}
.pane-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  padding: 14px 18px;
  background: linear-gradient(180deg, rgba(244, 233, 212, 0.9), rgba(255, 253, 249, 0.95));
  border-bottom: 1px solid var(--line);
}
.pane-title {
  font-size: 15px;
  font-weight: 700;
}
.pane-meta {
  color: var(--muted);
  font-size: 12px;
}
.preview-wrap {
  padding: 16px;
}
.preview-wrap img {
  width: 100%;
  display: block;
  border-radius: 18px;
  border: 1px solid #d7cab9;
  background: #fff;
}
.empty-state {
  border: 1px dashed var(--line-strong);
  border-radius: 18px;
  padding: 28px 22px;
  background: var(--panel-2);
  color: var(--muted);
  text-align: center;
}
.text-pane {
  padding: 18px 18px 22px;
}
.page-tag {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  border-radius: 999px;
  background: #f1e6d4;
  color: #5d4a30;
  font-size: 12px;
  font-weight: 700;
}
.state {
  display: inline-flex;
  margin-left: 8px;
  padding: 7px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}
.state.image-only { background: #efe6ff; color: #6d28d9; }
.state.blank { background: #eef2f7; color: #475569; }
.meta-line {
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 13px;
}
.study-block {
  margin-top: 16px;
}
.study-block h2,
.study-block h3,
.study-block h4 {
  margin: 0 0 8px;
  line-height: 1.25;
}
.study-block h2 { font-size: 28px; }
.study-block h3 { font-size: 23px; }
.study-block h4 { font-size: 19px; }
.study-block p {
  margin: 0;
  font-size: 17px;
}
.study-block + .study-block {
  padding-top: 14px;
  border-top: 1px solid rgba(221, 207, 186, 0.75);
}
.study-block ul {
  margin: 0;
  padding-left: 22px;
}
.study-block li + li { margin-top: 8px; }
.media {
  margin-top: 10px;
}
.media img {
  width: 100%;
  max-width: 100%;
  display: block;
  border-radius: 16px;
  border: 1px solid #d7cab9;
  background: #fff;
}
.media-note {
  margin-bottom: 10px;
  color: var(--muted);
  font-size: 14px;
}
.note {
  padding: 14px 16px;
  border-radius: 16px;
  background: #faf2dd;
  border: 1px solid #e4d4ae;
}
.placeholder {
  padding: 12px 14px;
  border-radius: 14px;
  background: #f8f3ea;
  border: 1px dashed var(--line);
  color: var(--muted);
  font-size: 14px;
}
body[data-view="source"] .page {
  grid-template-columns: 1fr;
}
body[data-view="source"] .page-pane.text-pane-wrap {
  display: none;
}
body[data-view="text"] .page {
  grid-template-columns: 1fr;
}
body[data-view="text"] .page-pane.source-pane {
  display: none;
}
@media (max-width: 980px) {
  .topbar-inner {
    grid-template-columns: 1fr;
  }
  .controls {
    justify-content: flex-start;
  }
  .page {
    grid-template-columns: 1fr;
  }
}
"""


JS = """
(() => {
  const pages = Array.from(document.querySelectorAll('.page'));
  const jump = document.getElementById('page-jump');
  const current = document.getElementById('current-page');
  const prev = document.getElementById('prev-page');
  const next = document.getElementById('next-page');
  const viewButtons = Array.from(document.querySelectorAll('[data-view-mode]'));
  let activeIndex = 0;

  const updateNav = () => {
    const page = pages[activeIndex];
    if (!page) return;
    const label = page.dataset.pageLabel;
    current.textContent = label;
    jump.value = page.id;
    prev.disabled = activeIndex === 0;
    next.disabled = activeIndex === pages.length - 1;
  };

  const goToIndex = (index) => {
    if (index < 0 || index >= pages.length) return;
    activeIndex = index;
    updateNav();
    pages[index].scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  jump.addEventListener('change', () => {
    const index = pages.findIndex((page) => page.id === jump.value);
    goToIndex(index);
  });

  prev.addEventListener('click', () => goToIndex(activeIndex - 1));
  next.addEventListener('click', () => goToIndex(activeIndex + 1));

  viewButtons.forEach((button) => {
    button.addEventListener('click', () => {
      const mode = button.dataset.viewMode;
      document.body.dataset.view = mode;
      viewButtons.forEach((item) => item.classList.toggle('active', item === button));
    });
  });

  const observer = new IntersectionObserver((entries) => {
    const visible = entries
      .filter((entry) => entry.isIntersecting)
      .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!visible) return;
    const index = pages.indexOf(visible.target);
    if (index >= 0) {
      activeIndex = index;
      updateNav();
    }
  }, { rootMargin: '-20% 0px -55% 0px', threshold: [0.2, 0.45, 0.7] });

  pages.forEach((page) => observer.observe(page));
  updateNav();
})();
"""


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def page_anchor(page_no: int) -> str:
    return f"page-{page_no:03d}"


def page_label(page_no: int) -> str:
    return f"Page {page_no:03d}"


def chunk_asset_path(chunk_name: str, rel_path: str | None) -> str | None:
    if not rel_path:
        return None
    return f"{chunk_name}/{rel_path}".replace("\\", "/")


def clean_text(text: str | None) -> str:
    return (text or "").strip()


def contains_mermaid_fence(text: str | None) -> bool:
    value = clean_text(text).lower()
    return "```mermaid" in value or value.startswith("graph td") or value.startswith("flowchart")


def is_tiny_visual_block(block: dict[str, Any]) -> bool:
    bbox = block.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        return False

    try:
        width = abs(float(bbox[2]) - float(bbox[0]))
        height = abs(float(bbox[3]) - float(bbox[1]))
    except (TypeError, ValueError):
        return False

    block_type = str(block.get("type") or "")
    source_type = str(block.get("source_type") or "")

    if block_type not in {"figure", "image", "table_or_figure", "chart"} and source_type != "image":
        return False

    # Small visual boxes are usually decorative icons, arrows, pins, or markers.
    return width <= 80 and height <= 80


def resolve_source_preview_path(chunk_dir: Path, page: dict[str, Any]) -> str | None:
    """Return a chunk-relative full-page source preview path.

    The left source pane must use only full-page preview images.
    It must not fall back to table, figure, or fallback crop images.
    """
    page_no = page.get("page")
    candidates: list[Path] = []

    raw_preview = page.get("preview_image")
    if isinstance(raw_preview, str) and raw_preview.strip():
        raw = raw_preview.strip()
        candidates.append(chunk_dir / raw)
        candidates.append(chunk_dir / "assets" / raw)

    if page_no is not None:
        try:
            n = int(page_no)
        except (TypeError, ValueError):
            n = None

        if n is not None:
            names = [
                f"source_page_{n:03d}_preview.png",
                f"source_page_{n}_preview.png",
                f"source_page_{n:03d}_preview.jpg",
                f"source_page_{n}_preview.jpg",
            ]
            for name in names:
                candidates.append(chunk_dir / "assets" / name)
                candidates.append(chunk_dir / name)

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            try:
                return candidate.relative_to(chunk_dir).as_posix()
            except ValueError:
                return candidate.as_posix()

    return None


def meta_summary(page: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in page.get("meta", []):
        source_type = item.get("source_type")
        if source_type == "page_number":
            continue
        text = clean_text(item.get("text"))
        if text:
            parts.append(text)
    return " / ".join(parts)


def first_media_path(page: dict[str, Any]) -> str | None:
    for group in ("blocks", "side_notes", "meta"):
        for block in page.get(group, []):
            image = block.get("image")
            if image:
                return image
    return None


def escape_with_breaks(text: str) -> str:
    return "<br>".join(html.escape(part) for part in text.splitlines())


def render_media(image_path: str, alt_text: str) -> str:
    return (
        f'<div class="media">'
        f'<img src="{html.escape(image_path)}" alt="{html.escape(alt_text)}" loading="lazy">'
        f"</div>"
    )


def render_block(block: dict[str, Any], chunk_name: str) -> str:
    if is_tiny_empty_figure(block):
        return ""

    block_type = str(block.get("type") or "block")
    text = clean_text(block.get("text"))
    image = chunk_asset_path(chunk_name, block.get("image"))
    has_mermaid = contains_mermaid_fence(text)

    # Do not show tiny decorative icons as large study images.
    if image and is_tiny_visual_block(block):
        return ""

    # Mermaid source is implementation detail, not learner-facing content.
    if has_mermaid and image:
        text = ""
    elif has_mermaid and not image:
        return '<section class="study-block"><div class="placeholder">Diagram is available in the source view.</div></section>'

    if block_type == "title" and text:
        level = int(block.get("level") or 2)
        tag = "h2" if level <= 2 else "h3" if level == 3 else "h4"
        return f'<section class="study-block"><{tag}>{html.escape(text)}</{tag}></section>'

    if block_type == "list" and text:
        items = "".join(
            f"<li>{escape_with_breaks(item.strip())}</li>"
            for item in text.splitlines()
            if item.strip()
        )
        return f'<section class="study-block"><ul>{items}</ul></section>' if items else ""

    if block_type == "side_note" and text:
        return f'<section class="study-block note"><p>{escape_with_breaks(text)}</p></section>'

    if block_type in {"table", "table_or_figure", "chart", "figure"}:
        parts: list[str] = ['<section class="study-block">']
        if text:
            parts.append(f'<p>{escape_with_breaks(text)}</p>')
        if image:
            parts.append(render_media(image, f"{block_type} image"))
        elif not text:
            parts.append('<div class="placeholder">Reference figure/table omitted from text flow.</div>')
        parts.append("</section>")
        return "".join(parts)

    if image and not text:
        return f'<section class="study-block">{render_media(image, f"{block_type} image")}</section>'

    if text:
        return f'<section class="study-block"><p>{escape_with_breaks(text)}</p></section>'

    return ""


def render_text_pane(page: dict[str, Any], chunk_name: str, quality: str) -> str:
    parts: list[str] = []

    for block in page.get("blocks", []):
        rendered = render_block(block, chunk_name)
        if rendered:
            parts.append(rendered)

    for block in page.get("side_notes", []):
        rendered = render_block(block, chunk_name)
        if rendered:
            parts.append(rendered)

    if quality == "BLANK" and not parts:
        parts.append(
            '<section class="study-block note"><p>This page is blank in source. Keeping place in study flow.</p></section>'
        )
    elif quality == "IMAGE_ONLY" and not any("img " in part for part in parts):
        parts.append(
            '<section class="study-block note"><p>This page is image-only. Study from source pane.</p></section>'
        )
    elif quality == "IMAGE_ONLY":
        parts.insert(
            0,
            '<section class="study-block note"><p>This page is image-only. Extracted text not available.</p></section>',
        )

    if not parts:
        parts.append('<section class="study-block"><div class="placeholder">No study text extracted for this page.</div></section>')

    return "".join(parts)


def render_page(page: dict[str, Any], chunk_name: str) -> str:
    page_no = int(page["page"])
    quality, _ = classify_page_quality(page)
    preview = chunk_asset_path(chunk_name, page.get("preview_image"))
    source_image = preview
    meta = meta_summary(page)

    state_html = ""
    if quality == "IMAGE_ONLY":
        state_html = '<span class="state image-only">Image Only</span>'
    elif quality == "BLANK":
        state_html = '<span class="state blank">Blank Page</span>'

    if source_image:
        preview_html = render_media(source_image, f"Source for {page_label(page_no)}")
    else:
        preview_html = '<div class="empty-state">Source preview not available for this page.</div>'
    meta_html = f'<div class="meta-line">{html.escape(meta)}</div>' if meta else ""

    return f"""
<section class="page" id="{page_anchor(page_no)}" data-page="{page_no}" data-page-label="{page_label(page_no)}">
  <aside class="page-pane source-pane">
    <div class="pane-head">
      <div class="pane-title">{page_label(page_no)} source</div>
      <div class="pane-meta">Original page view</div>
    </div>
    <div class="preview-wrap">
      {preview_html}
    </div>
  </aside>
  <article class="page-pane text-pane-wrap">
    <div class="pane-head">
      <div class="pane-title">Study text</div>
      <div class="pane-meta">{html.escape(chunk_name)}</div>
    </div>
    <div class="text-pane">
      <span class="page-tag">{page_label(page_no)}</span>{state_html}
      {meta_html}
      {render_text_pane(page, chunk_name, quality)}
    </div>
  </article>
</section>
"""


def collect_pages(root: Path) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []

    for normalized_path in sorted(root.glob("uscpa_reg2_1_p*/normalized_pages.json")):
        chunk_name = normalized_path.parent.name
        data = read_json(normalized_path)
        for page in data.get("pages", []):
            page_copy = dict(page)
            page_copy["_chunk_name"] = chunk_name

            resolved_preview = resolve_source_preview_path(normalized_path.parent, page_copy)
            if resolved_preview:
                page_copy["preview_image"] = resolved_preview

            if not page_copy.get("preview_image") and page_copy.get("page") is not None:
                page_no = int(page_copy["page"])
                preview_candidate = normalized_path.parent / "assets" / f"source_page_{page_no:03d}_preview.png"
                if preview_candidate.exists():
                    page_copy["preview_image"] = f"assets/source_page_{page_no:03d}_preview.png"

            pages.append(page_copy)

    pages.sort(key=lambda item: int(item["page"]))

    page_numbers = [int(item["page"]) for item in pages]
    if not page_numbers:
        raise ValueError("No pages found under text study root")

    expected = list(range(page_numbers[0], page_numbers[-1] + 1))
    if page_numbers != expected:
        raise ValueError(
            f"Page sequence mismatch. Expected contiguous pages {expected[0]:03d}-{expected[-1]:03d}, got {page_numbers[:5]}...{page_numbers[-5:]}"
        )

    return pages


def build_html(title: str, pages: list[dict[str, Any]]) -> str:
    page_options = "".join(
        f'<option value="{page_anchor(int(page["page"]))}">{page_label(int(page["page"]))}</option>'
        for page in pages
    )
    page_sections = "".join(render_page(page, str(page["_chunk_name"])) for page in pages)

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body data-view="both">
  <header class="topbar">
    <div class="topbar-inner">
      <div>
        <div class="eyebrow">Continuous Study Reader</div>
        <h1>{html.escape(title)}</h1>
        <div class="sub">{len(pages)} pages in one scroll. Left: source. Right: cleaned study text.</div>
      </div>
      <div class="controls">
        <button class="control button" id="prev-page" type="button">Previous</button>
        <div class="control current" id="current-page">Page 001</div>
        <button class="control button" id="next-page" type="button">Next</button>
        <select id="page-jump" aria-label="Jump to page">
          {page_options}
        </select>
        <button class="control button ghost active" data-view-mode="both" type="button">Both</button>
        <button class="control button ghost" data-view-mode="source" type="button">Source Only</button>
        <button class="control button ghost" data-view-mode="text" type="button">Text Only</button>
        <a class="button primary" href="index.html">Study Home</a>
      </div>
    </div>
  </header>
  <main>
    {page_sections}
  </main>
  <script>{JS}</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text-study-root", type=Path, required=True)
    parser.add_argument("--title", default="Text Study Reader")
    args = parser.parse_args()

    root = args.text_study_root
    if not root.exists():
        raise FileNotFoundError(f"text study root not found: {root}")

    pages = collect_pages(root)
    output_path = root / "reader.html"
    output_path.write_text(build_html(args.title, pages), encoding="utf-8")

    print(f"text_study_root : {root}")
    print(f"pages           : {len(pages)}")
    print(f"created         : {output_path}")


if __name__ == "__main__":
    main()
