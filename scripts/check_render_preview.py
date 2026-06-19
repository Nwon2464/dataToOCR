from __future__ import annotations

import argparse
import html as html_lib
import json
import re
from pathlib import Path
from typing import Any

from common.api_paths import get_processed_chunk_dir, get_processed_dir


SAMPLE_CHUNK_ID = "USCPA_REG1_p001_010"


class CheckResult:
    def __init__(self, chunk_id: str) -> None:
        self.chunk_id = chunk_id
        self.failures = 0
        self.warnings = 0

    def ok(self, message: str) -> None:
        print(f"[ok] {message}")

    def fail(self, message: str) -> None:
        self.failures += 1
        print(f"[fail] {message}")

    def warn(self, message: str) -> None:
        self.warnings += 1
        print(f"[warn] {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check render.json and render_preview.html regression invariants.")
    parser.add_argument("chunks", nargs="*", help="Chunk IDs to check.")
    parser.add_argument("--all", action="store_true", help="Check every processed chunk with render.json.")
    return parser.parse_args()


def rel_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def class_count(html: str, class_name: str) -> int:
    count = 0
    for value in re.findall(r'class="([^"]*)"', html):
        if class_name in value.split():
            count += 1
    return count


def has_class(html: str, class_name: str) -> bool:
    return class_count(html, class_name) > 0


def hgroup_md_wrapper_count(html: str) -> int:
    return len(re.findall(r"<hgroup\b[^>]*class=\"[^\"]*\bmd-wrapper\b[^\"]*\"", html))


def page_link_count(html: str) -> int:
    return class_count(html, "page-link")


def load_json(path: Path, result: CheckResult) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        result.fail(f"failed to parse render.json: {exc}")
        return None
    if not isinstance(data, dict):
        result.fail("render.json root is not an object")
        return None
    return data


def check_required_files(chunk_id: str, result: CheckResult) -> tuple[Path, Path, bool]:
    processed_dir = get_processed_chunk_dir(chunk_id)
    render_path = processed_dir / "render.json"
    preview_path = processed_dir / "render_preview.html"
    ok = True

    if render_path.exists():
        result.ok("render.json exists")
    else:
        result.fail(f"render.json not found: {rel_path(render_path)}")
        ok = False

    if preview_path.exists():
        result.ok("render_preview.html exists")
    else:
        result.fail(f"render_preview.html not found: {rel_path(preview_path)}")
        ok = False

    return render_path, preview_path, ok


def check_render_json(data: dict[str, Any], result: CheckResult) -> tuple[list[Any], list[Any], dict[str, Any]]:
    if data.get("schema_version") == 2:
        result.ok("schema_version: 2")
    else:
        result.fail(f"schema_version mismatch: expected 2, got {data.get('schema_version')}")

    if data.get("render_model") == "mineru_block_v1":
        result.ok("render_model: mineru_block_v1")
    else:
        result.fail(f"render_model mismatch: expected mineru_block_v1, got {data.get('render_model')}")

    pages = data.get("pages")
    blocks = data.get("blocks")
    stats = data.get("stats")

    if isinstance(pages, list) and pages:
        result.ok(f"pages: {len(pages)}")
    else:
        result.fail("pages[] missing or empty")
        pages = [] if not isinstance(pages, list) else pages

    if isinstance(blocks, list) and blocks:
        result.ok(f"blocks: {len(blocks)}")
    else:
        result.fail("blocks[] missing or empty")
        blocks = [] if not isinstance(blocks, list) else blocks

    if isinstance(stats, dict):
        result.ok("stats exists")
    else:
        result.fail("stats missing")
        stats = {}

    for index, page in enumerate(pages):
        if not isinstance(page, dict):
            result.fail(f"page {index} is not object")
            continue
        for key in ("page", "title", "blocks"):
            if key not in page:
                result.fail(f"page {index} missing {key}")
        if "blocks" in page and not isinstance(page.get("blocks"), list):
            result.fail(f"page {page.get('page', index)} blocks is not list")

    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            result.fail(f"block {index} is not object")
            continue
        for key in ("id", "page", "block_type", "kind", "role", "className"):
            if not block.get(key):
                result.fail(f"block {index} missing {key}")
        if not block.get("html") and not block.get("text"):
            result.fail(f"block {index} missing html/text")

    content_count = sum(1 for block in blocks if isinstance(block, dict) and block.get("role") == "content")
    expected_stats = {
        "page_count": len(pages),
        "block_count": len(blocks),
        "content_block_count": content_count,
    }
    for key, expected in expected_stats.items():
        actual = stats.get(key)
        if actual == expected:
            result.ok(f"stats.{key}: {actual}")
        else:
            result.fail(f"stats.{key} mismatch: expected {expected}, got {actual}")

    return pages, blocks, stats


def check_html_structure(html: str, expected_pages: int, result: CheckResult) -> None:
    if "<!doctype html" in html.lower() or "<html" in html.lower():
        result.ok("html document structure")
    else:
        result.fail("html doctype/html missing")

    for token in (".app-shell", ".sidebar", ".main-content", ".page-card", "page-wrapper-content"):
        if token in html:
            result.ok(f"{token} exists")
        else:
            result.fail(f"{token} missing")

    page_cards = class_count(html, "page-card")
    if page_cards == expected_pages:
        result.ok(f"page-card: {page_cards}")
    else:
        result.fail(f"page-card count mismatch: expected {expected_pages}, got {page_cards}")

    links = page_link_count(html)
    if links == expected_pages:
        result.ok(f"sidebar links: {links}")
    else:
        result.fail(f"sidebar links mismatch: expected {expected_pages}, got {links}")


def check_block_markup(html: str, blocks: list[Any], stats: dict[str, Any], result: CheckResult) -> None:
    for token in ("hgroup", "md-wrapper", "markdown-container", "markdown-theme-base", "markdownRender"):
        if token in html:
            result.ok(f"{token} exists")
        else:
            result.fail(f"{token} missing")

    hgroups = hgroup_md_wrapper_count(html)
    content_count = int(stats.get("content_block_count") or 0)
    if hgroups >= content_count:
        result.ok(f"hgroup.md-wrapper: {hgroups}")
    else:
        result.fail(f"hgroup.md-wrapper too few: expected >= {content_count}, got {hgroups}")

    if hgroups != len(blocks):
        result.warn(f"hgroup.md-wrapper count differs from blocks: blocks {len(blocks)}, hgroups {hgroups}")


def check_custom_classes(html: str, blocks: list[Any], result: CheckResult) -> None:
    required_classes = {
        str(block.get("className"))
        for block in blocks
        if isinstance(block, dict)
        and block.get("role") == "content"
        and str(block.get("className") or "").startswith("custom-block-")
    }

    for class_name in sorted(required_classes):
        if has_class(html, class_name):
            result.ok(f"{class_name} exists")
        else:
            result.fail(f"{class_name} missing")

    for class_name in ("custom-block-page_number", "custom-block-header", "custom-block-footer"):
        if has_class(html, class_name):
            result.ok(f"{class_name} exists")
        else:
            result.warn(f"{class_name} not found")


def check_decorative(html: str, result: CheckResult) -> None:
    if has_class(html, "decorative-block"):
        result.ok("decorative-block class exists")
    else:
        result.fail("decorative-block class missing")

    if "body:not(.show-decorative) .decorative-block" in html or ".decorative-block" in html and "display: none" in html:
        result.ok("decorative hidden CSS")
    else:
        result.fail("decorative hidden CSS missing")


def check_sidebar_titles(chunk_id: str, html: str, pages: list[Any], result: CheckResult) -> None:
    if chunk_id == SAMPLE_CHUNK_ID:
        count = html.count("P3 · U.S. CPA")
        if count == 1:
            result.ok("P3 · U.S. CPA appears once")
        else:
            result.fail(f"P3 · U.S. CPA count: expected 1, got {count}")
        return

    for page in pages:
        if not isinstance(page, dict):
            continue
        page_num = page.get("page")
        title = str(page.get("title") or "")
        label = html_lib.escape(f"P{page_num} · {title}")
        count = html.count(label)
        if count >= 1:
            result.ok(f"sidebar title: P{page_num}")
        else:
            result.fail(f"sidebar title missing: {label}")
        if count > 2:
            result.warn(f"sidebar title repeated: {label} count {count}")


def check_image_classes(chunk_id: str, html: str, blocks: list[Any], result: CheckResult) -> None:
    image_blocks = [block for block in blocks if isinstance(block, dict) and block.get("block_type") == "image"]
    if not image_blocks:
        result.warn("no image blocks")
        return

    if has_class(html, "custom-block-image"):
        result.ok("custom-block-image exists")
    else:
        result.fail("custom-block-image missing")

    important = class_count(html, "important-image")
    icon = class_count(html, "icon-image")
    normal = class_count(html, "normal-image")
    if important + icon + normal > 0:
        result.ok("image classes")
    else:
        result.fail("image classes missing")

    if chunk_id == SAMPLE_CHUNK_ID:
        if important >= 2:
            result.ok(f"important-image: {important}")
        else:
            result.fail(f"important-image count: expected >= 2, got {important}")
        if icon >= 3:
            result.ok(f"icon-image: {icon}")
        else:
            result.fail(f"icon-image count: expected >= 3, got {icon}")


def check_indentation(chunk_id: str, html: str, blocks: list[Any], result: CheckResult) -> None:
    expects_indent = any(isinstance(block, dict) and block.get("indentClassName") for block in blocks)
    expects_section = any(isinstance(block, dict) and block.get("sectionClassName") for block in blocks)
    has_indent = has_class(html, "indent-level-1") or has_class(html, "indent-level-2")
    has_section = has_class(html, "section-alpha") or has_class(html, "section-numbered")
    if not expects_indent:
        result.warn("no indentation classes expected")
    elif has_indent:
        result.ok("indentation classes")
    else:
        result.fail("indentation classes missing")
    if not expects_section:
        result.warn("no section classes expected")
    elif has_section:
        result.ok("section classes")
    else:
        result.fail("section classes missing")

    if chunk_id == SAMPLE_CHUNK_ID and not has_class(html, "section-numbered"):
        result.fail("section-numbered missing")


def check_table_css(html: str, blocks: list[Any], result: CheckResult) -> None:
    has_table = any(isinstance(block, dict) and block.get("block_type") == "table_body" for block in blocks)
    if not has_table:
        result.warn("no table_body blocks")
        return

    for token in ("border-collapse", ".table-container", ".markdownRender table"):
        if token in html:
            result.ok(f"table CSS: {token}")
        else:
            result.fail(f"table CSS missing: {token}")


def check_chunk(chunk_id: str) -> CheckResult:
    result = CheckResult(chunk_id)
    print(f"[check] {chunk_id}")
    render_path, preview_path, files_ok = check_required_files(chunk_id, result)
    if not files_ok:
        print(f"[done] checks failed: {result.failures}")
        return result

    data = load_json(render_path, result)
    if data is None:
        print(f"[done] checks failed: {result.failures}")
        return result

    html = preview_path.read_text(encoding="utf-8")
    pages, blocks, stats = check_render_json(data, result)
    check_html_structure(html, len(pages), result)
    check_block_markup(html, blocks, stats, result)
    check_custom_classes(html, blocks, result)
    check_decorative(html, result)
    check_sidebar_titles(chunk_id, html, pages, result)
    check_image_classes(chunk_id, html, blocks, result)
    check_indentation(chunk_id, html, blocks, result)
    check_table_css(html, blocks, result)

    if result.failures:
        print(f"[done] checks failed: {result.failures}")
    else:
        print("[done] checks passed")
    return result


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

    total_failures = 0
    for chunk_id in chunk_ids:
        result = check_chunk(chunk_id)
        total_failures += result.failures

    return 1 if total_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
