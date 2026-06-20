from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.api_paths import get_processed_dir


CHUNK_RANGE_RE = re.compile(r"_p(\d+)_(\d+)$")
IMAGE_SRC_RE = re.compile(r'src=(["\'])images/')
IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
LOADING_ATTR_RE = re.compile(r"\sloading=(['\"])[^'\"]*\1", re.IGNORECASE)
STYLE_ATTR_RE = re.compile(r"\sstyle=(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL)
WIDTH_STYLE_RE = re.compile(r"^\s*(?:min-|max-)?width\s*:", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Combine per-chunk render.json files into data/processed/render_all.json.")
    parser.add_argument("--processed-root", type=Path, default=get_processed_dir(), help="Directory containing processed chunk folders.")
    parser.add_argument("--pretty", action="store_true", help="Write indented JSON.")
    return parser.parse_args()


def chunk_sort_key(chunk_dir: Path) -> tuple[int, int, str]:
    match = CHUNK_RANGE_RE.search(chunk_dir.name)
    if not match:
        return (10**9, 10**9, chunk_dir.name)
    return (int(match.group(1)), int(match.group(2)), chunk_dir.name)


def find_chunk_dirs(processed_root: Path, warnings: list[str]) -> list[Path]:
    dirs = [path for path in processed_root.iterdir() if path.is_dir() and (path / "render.json").exists()]
    for path in dirs:
        if not CHUNK_RANGE_RE.search(path.name):
            warnings.append(f"chunk sort range parse failed: {path.name}")
    return sorted(dirs, key=chunk_sort_key)


def rewrite_image_src(html: Any, chunk_id: str, warnings: list[str], block_id: str | None) -> Any:
    if not isinstance(html, str) or "src=" not in html:
        return html
    rewritten, count = IMAGE_SRC_RE.subn(rf'src=\1/processed/{chunk_id}/images/', html)
    if "src=\"images/" in rewritten or "src='images/" in rewritten:
        warnings.append(f"image src rewrite failed: {chunk_id} {block_id or ''}".strip())
    return rewritten


def add_lazy_loading(html: Any, warnings: list[str], chunk_id: str, block_id: str | None) -> Any:
    if not isinstance(html, str) or "<img" not in html.lower():
        return html

    def replace(match: re.Match[str]) -> str:
        tag = match.group(0)
        loading = LOADING_ATTR_RE.search(tag)
        if loading:
            if "lazy" not in loading.group(0).lower():
                warnings.append(f"image loading attr not lazy: {chunk_id} {block_id or ''}".strip())
            return tag
        return tag[:-1].rstrip() + ' loading="lazy">'

    return IMG_TAG_RE.sub(replace, html)


def remove_img_width_styles(html: Any) -> Any:
    if not isinstance(html, str) or "<img" not in html.lower():
        return html

    def replace_img(match: re.Match[str]) -> str:
        tag = match.group(0)

        def replace_style(style_match: re.Match[str]) -> str:
            quote = style_match.group(1)
            declarations = [
                declaration.strip()
                for declaration in style_match.group(2).split(";")
                if declaration.strip() and not WIDTH_STYLE_RE.match(declaration)
            ]
            if not declarations:
                return ""
            return f' style={quote}{"; ".join(declarations)}{quote}'

        return STYLE_ATTR_RE.sub(replace_style, tag)

    return IMG_TAG_RE.sub(replace_img, html)


def page_block_objects(page: dict[str, Any], flat_blocks_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    page_blocks = page.get("blocks")
    if not isinstance(page_blocks, list):
        return []
    result: list[dict[str, Any]] = []
    for block in page_blocks:
        if not isinstance(block, dict):
            continue
        block_id = block.get("id")
        source = flat_blocks_by_id.get(block_id) if block_id else None
        result.append(copy.deepcopy(source or block))
    return result


def combine_chunk(
    chunk_id: str,
    data: dict[str, Any],
    global_page_start: int,
    warnings: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    pages = data.get("pages") if isinstance(data.get("pages"), list) else []
    flat_blocks = data.get("blocks") if isinstance(data.get("blocks"), list) else []
    flat_blocks_by_id = {block.get("id"): block for block in flat_blocks if isinstance(block, dict)}

    combined_pages: list[dict[str, Any]] = []
    combined_blocks: list[dict[str, Any]] = []
    global_page = global_page_start

    for page in pages:
        if not isinstance(page, dict):
            continue
        source_page = int(page.get("page") or len(combined_pages) + 1)
        source_blocks = page_block_objects(page, flat_blocks_by_id)
        next_blocks: list[dict[str, Any]] = []

        for block_index, source_block in enumerate(source_blocks, start=1):
            block = copy.deepcopy(source_block)
            source_block_id = block.get("id")
            block["source_page"] = source_page
            block["source_block_id"] = source_block_id
            block["chunk_id"] = chunk_id
            block["page"] = global_page
            block["id"] = f"p{global_page:03d}-{block_index:04d}"
            block_id_text = str(source_block_id) if source_block_id else None
            block["html"] = rewrite_image_src(block.get("html"), chunk_id, warnings, block_id_text)
            block["html"] = remove_img_width_styles(block.get("html"))
            block["html"] = add_lazy_loading(block.get("html"), warnings, chunk_id, block_id_text)
            next_blocks.append(block)
            combined_blocks.append(block)

        combined_pages.append(
            {
                "page": global_page,
                "source_page": source_page,
                "chunk_id": chunk_id,
                "title": str(page.get("title") or f"Page {global_page}"),
                "blocks": next_blocks,
            }
        )
        global_page += 1

    return combined_pages, combined_blocks, global_page


def read_chunk_render(path: Path, warnings: list[str]) -> dict[str, Any] | None:
    chunk_id = path.parent.name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warnings.append(f"failed to parse render.json: {chunk_id}: {exc}")
        return None
    if not isinstance(data, dict):
        warnings.append(f"render.json root is not object: {chunk_id}")
        return None
    if data.get("schema_version") != 2:
        warnings.append(f"schema_version is not 2: {chunk_id}")
    if data.get("render_model") != "mineru_block_v1":
        warnings.append(f"render_model is not mineru_block_v1: {chunk_id}")
    if not isinstance(data.get("pages"), list):
        warnings.append(f"pages[] missing: {chunk_id}")
    if not isinstance(data.get("blocks"), list):
        warnings.append(f"blocks[] missing: {chunk_id}")
    return data


def build_render_all(processed_root: Path, pretty: bool = False) -> Path:
    processed_root = processed_root.resolve()
    warnings: list[str] = []
    source_chunks: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    next_global_page = 1

    if not processed_root.exists():
        raise FileNotFoundError(f"{processed_root} not found")

    for chunk_dir in find_chunk_dirs(processed_root, warnings):
        chunk_id = chunk_dir.name
        data = read_chunk_render(chunk_dir / "render.json", warnings)
        if data is None:
            continue

        chunk_pages, chunk_blocks, next_global_page = combine_chunk(chunk_id, data, next_global_page, warnings)
        source_chunks.append(
            {
                "chunk_id": chunk_id,
                "page_count": len(chunk_pages),
                "block_count": len(chunk_blocks),
            }
        )
        pages.extend(chunk_pages)
        blocks.extend(chunk_blocks)

    if not source_chunks:
        raise RuntimeError(f"No render.json chunks found under: {processed_root}")

    payload = {
        "schema_version": 2,
        "render_model": "mineru_block_v1",
        "document_type": "combined_render",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_chunks": source_chunks,
        "stats": {
            "chunk_count": len(source_chunks),
            "page_count": len(pages),
            "block_count": len(blocks),
            "content_block_count": sum(1 for block in blocks if block.get("role") == "content"),
        },
        "pages": pages,
        "blocks": blocks,
        "warnings": warnings,
    }

    output_path = processed_root / "render_all.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None, separators=None if pretty else (",", ":")),
        encoding="utf-8",
    )

    print(f"[chunks] {len(source_chunks)}")
    print(f"[pages] {len(pages)}")
    print(f"[blocks] {len(blocks)}")
    print(f"[write] {output_path.as_posix()}")
    if warnings:
        print(f"[warnings] {len(warnings)}")
        for warning in warnings:
            print(f"- {warning}")
    print("[done]")
    return output_path


def main() -> int:
    args = parse_args()
    build_render_all(args.processed_root, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
