from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_INPUT_ROOT = Path("data/mineru_api_output")
DEFAULT_OUTPUT_ROOT = Path("data/processed")
CHUNK_RANGE_RE = re.compile(r"_p(\d+)_(\d+)$")
PROTECTED_TAGS = ("<h1", "<h2", "<h3", "<p", "<table", "<ol", "<ul", "<img", "</body>", "</html>")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build HTML manifest from MinerU full.html files.")
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT, help="MinerU API output root.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help="Processed output root.")
    parser.add_argument("--pretty", action="store_true", help="Write pretty JSON.")
    return parser.parse_args()


def natural_key(value: str) -> tuple[Any, ...]:
    parts = re.split(r"(\d+)", value)
    key: list[Any] = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part)
    return tuple(key)


def find_full_html_files(input_root: Path) -> list[Path]:
    if not input_root.exists():
        return []
    html_files = [path for path in input_root.glob("*/full.html") if path.is_file()]
    return sorted(html_files, key=lambda path: natural_key(path.parent.name))


def parse_page_range(chunk_id: str) -> tuple[int | None, int | None]:
    match = CHUNK_RANGE_RE.search(chunk_id)
    if not match:
        return (None, None)
    return (int(match.group(1)), int(match.group(2)))


def first_protected_tag_position(line: str, start: int = 0) -> int:
    lower = line.lower()
    positions = [lower.find(tag, start) for tag in PROTECTED_TAGS]
    positions = [pos for pos in positions if pos != -1]
    return min(positions) if positions else -1


def strip_mermaid_blocks(html_text: str) -> tuple[str, int]:
    lines = html_text.splitlines(keepends=True)
    kept: list[str] = []
    removed_count = 0
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("mermaid graph "):
            removed_count += 1
            index += 1
            continue

        is_flowchart_open = stripped == "flowchart" and index + 1 < len(lines) and lines[index + 1].lstrip().startswith("```mermaid")
        is_mermaid_open = line.lstrip().startswith("```mermaid")

        if is_flowchart_open or is_mermaid_open:
            prefix_lines = [line] if is_flowchart_open else []
            open_index = index + 1 if is_flowchart_open else index
            open_line = lines[open_index]
            open_marker = open_line.lower().find("```mermaid")
            search_start = open_marker + len("```mermaid") if open_marker >= 0 else 0

            block_lines = prefix_lines + [open_line]
            scan_index = open_index
            first_line = True
            found_close = False
            rollback = False
            remainder = ""

            while scan_index < len(lines):
                current = lines[scan_index]
                search_from = search_start if first_line else 0
                closing_pos = current.find("```", search_from)
                protected_pos = first_protected_tag_position(current, search_from)

                if closing_pos == -1 and protected_pos == -1:
                    if scan_index != open_index:
                        block_lines.append(current)
                    scan_index += 1
                    first_line = False
                    continue

                if protected_pos != -1 and (closing_pos == -1 or protected_pos < closing_pos):
                    rollback = True
                    break

                removed_count += 1
                remainder = current[closing_pos + 3 :]
                found_close = True
                break

            if rollback:
                kept.extend(block_lines)
                if scan_index != open_index:
                    kept.append(lines[scan_index])
                index = scan_index + 1
                continue

            if found_close:
                if remainder:
                    lines[scan_index] = remainder
                    index = scan_index
                else:
                    index = scan_index + 1
                continue

            kept.extend(block_lines)
            index = len(lines)
            continue

        kept.append(line)
        index += 1

    return "".join(kept), removed_count


def build_chunk_entry(chunk_id: str, source_html: Path, output_root: Path) -> tuple[dict[str, Any], int]:
    html_text = source_html.read_text(encoding="utf-8")
    cleaned_html, removed_count = strip_mermaid_blocks(html_text)

    destination = output_root / chunk_id / "html" / "index.html"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(cleaned_html, encoding="utf-8")

    page_start, page_end = parse_page_range(chunk_id)
    entry = {
        "chunk_id": chunk_id,
        "title": chunk_id,
        "page_start": page_start,
        "page_end": page_end,
        "html_path": f"/processed/{chunk_id}/html/index.html",
        "source_html": source_html.as_posix(),
    }
    return entry, removed_count


def build_html_manifest(input_root: Path, output_root: Path, pretty: bool = False) -> Path:
    input_root = input_root.resolve()
    output_root = output_root.resolve()

    html_files = find_full_html_files(input_root)
    if not html_files:
        raise RuntimeError(f"No full.html files found under: {input_root}")
    
    chunks: list[dict[str, Any]] = []

    removed_counts: list[tuple[str, int]] = []

    for source_html in html_files:
        chunk_id = source_html.parent.name
        entry, removed_count = build_chunk_entry(chunk_id, source_html, output_root)
        chunks.append(entry)
        removed_counts.append((chunk_id, removed_count))

    manifest = {
        "schema_version": 1,
        "render_model": "mineru_html_v1",
        "chunks": chunks,
    }

    manifest_path = output_root / "html_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2 if pretty else None, separators=None if pretty else (",", ":"))
        + ("\n" if pretty else ""),
        encoding="utf-8",
    )

    print(f"[html] {len(html_files)}")
    print(f"[write] {manifest_path.as_posix()}")
    for chunk_id, removed_count in removed_counts:
        print(f"[mermaid] {chunk_id} {removed_count}")

    return manifest_path


def main() -> int:
    args = parse_args()
    build_html_manifest(args.input_root, args.output_root, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
