#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

from text_study_quality_rules import classify_page_quality, is_tiny_empty_figure
import re


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

/* Natural study text rendering: type labels are internal, not learner-facing. */
.text-pane {
  padding: 22px 24px 28px;
}

.text-pane .study-block {
  margin-top: 0;
}

.text-pane .study-block + .study-block {
  padding-top: 0;
  border-top: 0;
}

.text-pane h2 {
  font-size: 26px;
  line-height: 1.45;
  margin: 24px 0 12px;
}

.text-pane h3 {
  font-size: 21px;
  line-height: 1.5;
  margin: 22px 0 10px;
}

.text-pane h4 {
  font-size: 18px;
  line-height: 1.5;
  margin: 18px 0 8px;
}

.text-pane p {
  margin: 12px 0;
  font-size: 17px;
  line-height: 1.9;
  color: #1f2937;
}

.text-pane ul,
.text-pane ol {
  margin: 12px 0 16px 24px;
  padding-left: 22px;
}

.text-pane li {
  margin: 6px 0;
  line-height: 1.75;
}

.text-pane pre {
  white-space: pre-wrap;
  background: #f8f3ea;
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 12px 14px;
  overflow-x: auto;
  line-height: 1.65;
}

.text-pane .study-table-wrap {
  overflow-x: auto;
  margin: 16px 0;
}

.text-pane .study-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 15px;
  line-height: 1.6;
}

.text-pane .study-table td,
.text-pane .study-table th {
  border: 1px solid #d7cab9;
  padding: 8px 10px;
  vertical-align: top;
}

.text-pane .study-table tr:nth-child(odd) td {
  background: #fbf7ef;
}

.text-pane .note,
.text-pane .side-note {
  margin: 16px 0;
  padding: 12px 14px;
  border-radius: 14px;
  background: #faf2dd;
  border: 1px solid #e4d4ae;
  color: #4b5563;
}

.text-pane figure {
  margin: 16px 0;
  padding: 12px 14px;
  border-radius: 14px;
  background: #f8f3ea;
  border: 1px solid var(--line);
  color: var(--muted);
}


/* In comparison mode, keep right text pane aligned to the source page height. */
.page-pane {
  min-height: 0;
}

.page-pane.text-pane-wrap {
  display: flex;
  flex-direction: column;
}

.page-pane.text-pane-wrap .text-pane {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

body[data-view="both"] .page-pane.text-pane-wrap,
body[data-view="source"] .page-pane.text-pane-wrap {
  height: var(--source-pane-height, auto);
}

body[data-view="text"] .page-pane.text-pane-wrap {
  height: auto !important;
}

body[data-view="text"] .page-pane.text-pane-wrap .text-pane {
  overflow-y: visible;
}


.copy-block {
  position: relative;
  margin: 0;
  padding-right: 42px;
}

.copy-block:hover .copy-block-button,
.copy-block:focus-within .copy-block-button {
  opacity: 1;
}

.copy-block-button {
  position: absolute;
  top: 2px;
  right: 0;
  opacity: 0.18;
  padding: 4px 8px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: #fffaf2;
  color: #5d4a30;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: opacity 0.12s ease, background 0.12s ease;
}

.copy-block-button:hover {
  opacity: 1;
  background: #f1e6d4;
}

.copy-block-button.copied {
  opacity: 1;
  background: #dcfce7;
  color: #166534;
  border-color: #86efac;
}

body[data-view="text"] .copy-block-button {
  opacity: 0.28;
}


/* Copy icon UI override */
.copy-block {
  position: relative;
  padding: 3px 42px 3px 8px;
  border-radius: 12px;
  border: 1px solid transparent;
  transition: background 0.12s ease, border-color 0.12s ease;
}

.copy-block.copy-hover {
  background: #fff7e6;
  border-color: #ead7b7;
}

.copy-block-button {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  opacity: 0.24;
  padding: 0;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: #fffaf2;
  color: #5d4a30;
  font-size: 15px;
  font-weight: 800;
  line-height: 1;
  cursor: pointer;
  transition: opacity 0.12s ease, background 0.12s ease, transform 0.12s ease;
}

.copy-block:hover .copy-block-button,
.copy-block:focus-within .copy-block-button {
  opacity: 1;
}

.copy-block-button:hover {
  opacity: 1;
  background: #f1e6d4;
  transform: translateY(-1px);
}

.copy-block-button.copied {
  opacity: 1;
  background: #dcfce7;
  color: #166534;
  border-color: #86efac;
}


/* Highlight whole copy block on block hover, not only icon hover. */
.copy-block:hover {
  background: #fff7e6;
  border-color: #ead7b7;
}

.copy-block:hover .copy-block-button {
  opacity: 1;
}




/* Header UI polish */
.control.current,
#current-page {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  min-height: 38px;
  box-sizing: border-box;
}

.study-home-icon {
  position: fixed;
  top: 18px;
  left: 18px;
  z-index: 1000;
  width: 42px;
  height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: rgba(255, 250, 242, 0.94);
  color: #5d4a30;
  box-shadow: 0 10px 28px rgba(68, 49, 26, 0.12);
  text-decoration: none;
  transition: transform 0.14s ease, background 0.14s ease, box-shadow 0.14s ease;
}

.study-home-icon:hover {
  background: #f1e6d4;
  transform: translateY(-1px);
  box-shadow: 0 14px 34px rgba(68, 49, 26, 0.18);
}

.study-home-icon svg {
  width: 20px;
  height: 20px;
  display: block;
}

.topbar-inner {
  padding-left: 54px;
}


/* iPad/tablet layout: keep Both view as two panes. */
@media (max-width: 980px) {
  body[data-view="both"] .page {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 14px;
  }

  body[data-view="both"] .page-pane {
    min-width: 0;
  }

  body[data-view="both"] .preview-wrap {
    padding: 12px;
  }

  body[data-view="both"] .text-pane {
    padding: 14px 14px 18px;
  }

  body[data-view="both"] .pane-title {
    font-size: 13px;
  }

  body[data-view="both"] .pane-meta {
    font-size: 11px;
  }

  body[data-view="both"] .text-pane p {
    font-size: 15px;
    line-height: 1.75;
  }

  body[data-view="both"] .text-pane h2 {
    font-size: 21px;
  }

  body[data-view="both"] .text-pane h3 {
    font-size: 18px;
  }

  body[data-view="both"] .copy-block {
    padding-right: 34px;
  }

  body[data-view="both"] .copy-block-button {
    width: 24px;
    height: 24px;
    font-size: 13px;
  }
}

/* Very small phones: allow stacking because two panes become unusable. */
@media (max-width: 640px) {
  body[data-view="both"] .page {
    grid-template-columns: 1fr;
  }
}



.topbar-inner {
  max-width: min(1560px, calc(100vw - 28px));
}

@media (max-width: 980px) {
  main,
  .reader,
  .content,
  .pages,
  .page,
  .topbar-inner {
    max-width: calc(100vw - 18px);
  }
}




/* Safe pane spacing adjustment */
body[data-view="both"] .page {
  gap: 14px;
}

@media (max-width: 980px) {
  body[data-view="both"] .page {
    gap: 8px;
  }
}




/* Safe compact reader spacing */
* {
  box-sizing: border-box;
}

body {
  overflow-x: hidden;
}

.topbar,
main {
  padding-left: 8px;
  padding-right: 8px;
}

.page {
  max-width: none;
}

body[data-view="both"] .page {
  gap: 10px;
}

body[data-view="both"] .page-pane,
body[data-view="both"] .source-pane,
body[data-view="both"] .text-pane,
body[data-view="both"] .preview-wrap {
  min-width: 0;
}

@media (max-width: 980px) {
  .topbar,
  main {
    padding-left: 4px;
    padding-right: 4px;
  }

  body[data-view="both"] .page {
    gap: 6px;
  }
}


/* Smaller side note text */
.side-note {
  font-size: 13px;
  line-height: 1.55;
}

.side-note p {
  font-size: 13px;
  line-height: 1.55;
  margin: 0;
}

body[data-view="both"] .side-note,
body[data-view="both"] .side-note p {
  font-size: 12.5px;
}


/* Compact consecutive side notes */
.side-note {
  margin-top: 8px;
  margin-bottom: 8px;
}

.side-note + .side-note {
  margin-top: -2px;
}

.copy-block:has(.side-note) {
  margin-top: 4px;
  margin-bottom: 4px;
}

.copy-block:has(.side-note) + .copy-block:has(.side-note) {
  margin-top: -4px;
}


/* Smaller side note padding */
.side-note {
  padding: 6px 8px;
}

body[data-view="both"] .side-note {
  padding: 5px 7px;
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

  let updateNav = () => {
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

  const getPageClosestToViewportCenter = () => {
    if (!pages.length) return null;

    const viewportCenter = window.innerHeight / 2;
    let bestPage = pages[0];
    let bestDistance = Infinity;

    pages.forEach((page) => {
      const rect = page.getBoundingClientRect();
      const pageCenter = rect.top + rect.height / 2;
      const distance = Math.abs(pageCenter - viewportCenter);

      if (distance < bestDistance) {
        bestDistance = distance;
        bestPage = page;
      }
    });

    return bestPage;
  };

  const restorePageAfterViewSwitch = (page) => {
    if (!page) return;

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        page.scrollIntoView({ behavior: 'auto', block: 'start' });
        syncPaneHeights();
      });
    });
  };

  viewButtons.forEach((button) => {
    button.addEventListener('click', () => {
      const pageBeforeSwitch = getPageClosestToViewportCenter();
      const mode = button.dataset.viewMode;

      document.body.dataset.view = mode;
      viewButtons.forEach((item) => item.classList.toggle('active', item === button));

      requestAnimationFrame(syncPaneHeights);
      restorePageAfterViewSwitch(pageBeforeSwitch);
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

  const syncPaneHeights = () => {
    const mode = document.body.dataset.view || 'both';

    pages.forEach((page) => {
      const sourcePane = page.querySelector('.source-pane');
      const textPaneWrap = page.querySelector('.text-pane-wrap');

      if (!sourcePane || !textPaneWrap) return;

      if (mode === 'text') {
        textPaneWrap.style.removeProperty('--source-pane-height');
        return;
      }

      const height = sourcePane.getBoundingClientRect().height;

      if (height > 0) {
        textPaneWrap.style.setProperty('--source-pane-height', `${Math.ceil(height)}px`);
      }
    });
  };

  window.addEventListener('resize', syncPaneHeights);

  document.querySelectorAll('.source-pane img').forEach((img) => {
    if (img.complete) return;
    img.addEventListener('load', syncPaneHeights, { once: true });
  });

  const originalUpdateNav = updateNav;
  updateNav = () => {
    originalUpdateNav();
    syncPaneHeights();
  };

  syncPaneHeights();

  updateNav();
  document.addEventListener('mouseover', (event) => {
    const button = event.target.closest('[data-copy-block]');
    if (!button) return;

    const block = button.closest('.copy-block');
    if (block) block.classList.add('copy-hover');
  });

  document.addEventListener('mouseout', (event) => {
    const button = event.target.closest('[data-copy-block]');
    if (!button) return;

    const block = button.closest('.copy-block');
    if (block) block.classList.remove('copy-hover');
  });


  const showCopyToast = (message = "Copied") => {};

  const normalizeBlockCopyText = (text) => {
    return String(text || '')
      .split(/\\r?\\n/)
      .map((line) => line.trimEnd())
      .join('\\n')
      .replace(/\\n{3,}/g, '\\n\\n')
      .trim();
  };

  const copyBlockTextToClipboard = async (text) => {
    const normalized = normalizeBlockCopyText(text);
    if (!normalized) return false;

    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(normalized);
      return true;
    }

    const textarea = document.createElement('textarea');
    textarea.value = normalized;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    textarea.style.top = '-9999px';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();

    const ok = document.execCommand('copy');
    textarea.remove();
    return ok;
  };

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-copy-block]');
    if (!button) return;

    const block = button.closest('.copy-block');
    if (!block) return;

    const text = block.dataset.copyText || '';

    try {
      const ok = await copyBlockTextToClipboard(text);
      if (!ok) {
        return;
      }

      button.textContent = '✓';
      button.classList.add('copied');

      window.setTimeout(() => {
        button.textContent = '⧉';
        button.classList.remove('copied');
      }, 2000);
    } catch (error) {
    }
  });


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


def split_natural_list_items(text: str) -> list[str]:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if len(lines) >= 2:
        return lines

    # Preserve original numbering. Do not rewrite tax/accounting text.
    parts = re.split(r"(?=(?:\d+[）\)]|[a-zA-Z][）\)]))", str(text or ""))
    parts = [part.strip() for part in parts if part.strip()]
    return parts if len(parts) >= 2 else lines


def looks_like_journal_or_formula(text: str) -> bool:
    if "\n" not in text:
        return False

    markers = ["(Dr)", "(Cr)", " Dr", " Cr", "$", "×××", "\t"]
    return any(marker in text for marker in markers)


def render_table_rows_natural(rows: Any) -> str:
    if not isinstance(rows, list) or not rows:
        return ""

    rendered_rows: list[str] = []

    for row in rows:
        if not isinstance(row, list):
            continue

        cells = []
        for cell in row:
            cell_text = clean_text(cell)
            cells.append(f"<td>{html.escape(cell_text)}</td>")

        if cells:
            rendered_rows.append("<tr>" + "".join(cells) + "</tr>")

    if not rendered_rows:
        return ""

    return (
        '<div class="study-table-wrap">'
        '<table class="study-table">'
        '<tbody>'
        + "".join(rendered_rows)
        + '</tbody>'
        '</table>'
        '</div>'
    )



def looks_like_ocr_math_garbage(text: str) -> bool:
    """Detect obvious OCR garbage from formula/diagram regions."""
    text = str(text or "").strip()
    if not text:
        return False

    math_tokens = [
        "\\begin{array}",
        "\\end{array}",
        "\\lVert",
        "\\rVert",
        "\\mathcal",
        "\\lesssim",
        "\\equiv",
        "\\otimes",
        "\\sharp",
        "\\Xi",
        "\\Psi",
        "\\varphi",
        "\\lambda",
    ]

    hits = sum(1 for token in math_tokens if token in text)
    backslash_count = text.count("\\")

    # Long broken formula block.
    if len(text) >= 120 and hits >= 2:
        return True

    # Very backslash-heavy block.
    if len(text) >= 120 and backslash_count >= 8:
        return True

    # Short residue after a larger broken formula block.
    # Example: ( \\lambda \\equiv \\ " , 7 2 )
    if "\\lambda" in text or "\\equiv" in text:
        return True

    # Isolated LaTeX/math-looking residue with almost no normal language.
    normal_letters = re.findall(r"[A-Za-zぁ-んァ-ン一-龥]", text)
    if backslash_count >= 2 and len(normal_letters) <= 4:
        return True

    return False


def looks_like_figure_ocr_dump(text: str) -> bool:
    """Detect long OCR dumps from source figures/forms.

    These are usually not useful as right-pane study text because the source
    image is already shown on the left.
    """
    text = str(text or "").strip()
    if not text:
        return False

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    if len(text) < 600:
        return False

    form_markers = [
        "Filing Status",
        "Form 1040",
        "social security number",
        "Standard Deduction",
        "Dependents",
        "Wages, salaries",
        "Taxable interest",
        "Qualified dividends",
        "Taxable income",
        "Schedule",
    ]

    marker_hits = sum(1 for marker in form_markers if marker.lower() in text.lower())

    # A long OCR dump from a tax form or source figure.
    if len(lines) >= 20 and marker_hits >= 3:
        return True

    # Generic dense figure OCR dump: many short lines, checkbox/form symbols,
    # and lots of repeated labels.
    checkbox_like = text.count("□") + text.count("▶") + text.count("...")
    if len(lines) >= 35 and checkbox_like >= 5:
        return True

    return False


def render_block(block: dict[str, Any], chunk_name: str) -> str:
    """Render a normalized block as natural reading HTML.

    Block type remains internal metadata. The right pane should not repeatedly
    show labels such as body/list/table; it should render semantic HTML.
    """
    if is_tiny_empty_figure(block):
        return ""

    block_type = str(block.get("type") or "block")
    text = clean_text(block.get("text"))
    image = chunk_asset_path(chunk_name, block.get("image"))
    has_mermaid = contains_mermaid_fence(text)

    # Tiny decorative icons should not appear in the study text flow.
    if image and is_tiny_visual_block(block):
        return ""

    # Mermaid source is implementation detail. Source visual remains on the left.
    if has_mermaid:
        return ""

    if looks_like_ocr_math_garbage(text):
        return ""

    if block_type == "title" and text:
        level = int(block.get("level") or 2)
        tag = "h2" if level <= 2 else "h3" if level == 3 else "h4"
        return f"<{tag}>{html.escape(text)}</{tag}>"

    if block_type == "list" and text:
        items = split_natural_list_items(text)
        lis = "".join(f"<li>{escape_with_breaks(item.strip())}</li>" for item in items if item.strip())
        return f"<ul>{lis}</ul>" if lis else ""

    if block_type == "side_note" and text:
        return f'<aside class="side-note"><p>{escape_with_breaks(text)}</p></aside>'

    if block_type in {"table", "table_or_figure", "chart"}:
        rows_html = render_table_rows_natural(block.get("rows"))
        if rows_html:
            return rows_html

        if text:
            return f"<pre>{html.escape(text)}</pre>"

        return ""

    if block_type == "figure":
        # Empty figures are noise in the right pane. Source pane covers visuals.
        if not text:
            return ""

        # Long OCR dumps from forms/figures should be studied from the source pane.
        if looks_like_figure_ocr_dump(text):
            return ""

        return f"<figure><figcaption>{escape_with_breaks(text)}</figcaption></figure>"

    if image and not text:
        return ""

    if text:
        if looks_like_journal_or_formula(text):
            return f"<pre>{html.escape(text)}</pre>"
        return f"<p>{escape_with_breaks(text)}</p>"

    return ""



def block_copy_text(block: dict[str, Any]) -> str:
    """Build plain text copied from one normalized block.

    This uses the block boundary preserved from normalized_pages/content_list_v2.
    It does not use visible labels such as body/list/table.
    """
    block_type = str(block.get("type") or "")
    text = clean_text(block.get("text"))

    if block_type in {"table", "table_or_figure", "chart"}:
        rows = block.get("rows")
        if isinstance(rows, list) and rows:
            lines = []
            for row in rows:
                if isinstance(row, list):
                    cells = [clean_text(cell) for cell in row]
                    if any(cells):
                        lines.append("\t".join(cells))
            if lines:
                return "\n".join(lines)

    if block_type == "list" and text:
        items = split_natural_list_items(text)
        return "\n".join(item.strip() for item in items if item.strip())

    return text


def render_copy_block(rendered_html: str, copy_text: str, block_index: int, block_type: str) -> str:
    if not rendered_html:
        return ""

    copy_text = clean_text(copy_text)
    if not copy_text:
        return rendered_html

    return (
        f'<div class="copy-block" data-block-index="{block_index}" '
        f'data-block-type="{html.escape(block_type)}" '
        f'data-copy-text="{html.escape(copy_text, quote=True)}">'
        '<button class="copy-block-button" type="button" data-copy-block title="Copy this block" aria-label="Copy this block">⧉</button>'
        f'{rendered_html}'
        '</div>'
    )


def render_text_pane(page: dict[str, Any], chunk_name: str, quality: str) -> str:
    parts: list[str] = []
    block_index = 0

    for block in page.get("blocks", []):
        rendered = render_block(block, chunk_name)
        if rendered:
            parts.append(
                render_copy_block(
                    rendered,
                    block_copy_text(block),
                    block_index,
                    str(block.get("type") or "block"),
                )
            )
            block_index += 1

    for block in page.get("side_notes", []):
        rendered = render_block(block, chunk_name)
        if rendered:
            parts.append(
                render_copy_block(
                    rendered,
                    block_copy_text(block),
                    block_index,
                    str(block.get("type") or "side_note"),
                )
            )
            block_index += 1

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

    for normalized_path in sorted(root.glob("*_p*/normalized_pages.json")):
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
        <a class="button primary study-home-icon" href="./index.html" aria-label="Study home" title="Study home"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
  <path d="M3.5 11.2 12 4l8.5 7.2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M5.8 10.2V20h4.5v-5.5h3.4V20h4.5v-9.8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg></a>
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
