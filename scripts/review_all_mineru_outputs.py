from __future__ import annotations

import argparse
from pathlib import Path

from common.mineru_paths import (
    find_mineru_images_dir,
    find_mineru_markdown,
    list_mineru_sample_dirs,
    read_mineru_markdown,
)
from common.md_segments import extract_markdown_segments


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect all MinerU output samples and print Markdown/segment summary."
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="MinerU output root. Default: data/mineru_output",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of samples to inspect.",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=300,
        help="Number of Markdown characters to preview.",
    )
    parser.add_argument(
        "--segment-preview",
        type=int,
        default=10,
        help="Number of extracted segments to preview.",
    )
    return parser


def make_preview(text: str, max_chars: int) -> str:
    preview = text.strip().replace("\r\n", "\n")
    if len(preview) <= max_chars:
        return preview
    return preview[:max_chars] + "\n..."


def count_segment_types(segments) -> dict[str, int]:
    counts: dict[str, int] = {}
    for segment in segments:
        counts[segment.type] = counts.get(segment.type, 0) + 1
    return counts


def print_segment_preview(segments, limit: int) -> None:
    print("Segment preview:")
    for segment in segments[:limit]:
        text = segment.text.replace("\n", "\\n")
        if len(text) > 120:
            text = text[:120] + "..."
        print(
            f"  line={segment.line_no:<4} "
            f"type={segment.type:<12} "
            f"checkable={str(segment.checkable):<5} "
            f"text={text}"
        )


def print_sample_summary(index: int, sample_dir: Path, preview_chars: int, segment_preview: int) -> None:
    md_path = find_mineru_markdown(sample_dir)
    images_dir = find_mineru_images_dir(sample_dir)
    markdown = read_mineru_markdown(sample_dir)
    segments = extract_markdown_segments(markdown)

    checkable_count = sum(1 for segment in segments if segment.checkable)
    type_counts = count_segment_types(segments)

    print("-" * 80)
    print(f"[{index}] {sample_dir.name}")
    print(f"Markdown: {md_path}")
    print(f"Images: {images_dir}")
    print(f"Chars: {len(markdown)}")
    print(f"Segments: {len(segments)}")
    print(f"Checkable segments: {checkable_count}")
    print(f"Segment types: {type_counts}")
    print("Markdown preview:")
    print(make_preview(markdown, preview_chars))
    print()
    print_segment_preview(segments, segment_preview)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    sample_dirs = list_mineru_sample_dirs(args.output_root)

    if args.limit is not None:
        if args.limit < 0:
            raise ValueError("--limit must be >= 0")
        sample_dirs = sample_dirs[: args.limit]

    for index, sample_dir in enumerate(sample_dirs, start=1):
        print_sample_summary(
            index=index,
            sample_dir=sample_dir,
            preview_chars=args.preview_chars,
            segment_preview=args.segment_preview,
        )

    print("-" * 80)
    print(f"Total samples: {len(sample_dirs)}")


if __name__ == "__main__":
    main()