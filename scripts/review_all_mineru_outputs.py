from __future__ import annotations

import argparse
from pathlib import Path

from common.mineru_paths import (
    find_mineru_images_dir,
    find_mineru_markdown,
    list_mineru_sample_dirs,
    read_mineru_markdown,
)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect all MinerU output samples and print Markdown summary."
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
    return parser


def make_preview(text: str, max_chars: int) -> str:
    preview = text.strip().replace("\r\n", "\n")
    if len(preview) <= max_chars:
        return preview
    return preview[:max_chars] + "\n..."


def print_sample_summary(index: int, sample_dir: Path, preview_chars: int) -> None:
    md_path = find_mineru_markdown(sample_dir)
    images_dir = find_mineru_images_dir(sample_dir)
    markdown = read_mineru_markdown(sample_dir)
    print("-" * 50)
    print(f"[{index}] {sample_dir.name}")
    print(f"Markdown: {md_path}")
    print(f"Images: {images_dir}")
    print(f"Chars: {len(markdown)}")
    print("-" * 50)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    sample_dirs = list_mineru_sample_dirs(args.output_root)

    if args.limit is not None:
        if args.limit < 0:
            raise ValueError("--limit must be >= 0")
        sample_dirs = sample_dirs[: args.limit]

    for index, sample_dir in enumerate(sample_dirs, start=1):
        print_sample_summary(index, sample_dir, args.preview_chars)

    print(f"Total samples: {len(sample_dirs)}")


if __name__ == "__main__":
    main()