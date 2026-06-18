#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path


def sanitize_zip_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^A-Za-z0-9_\-가-힣ぁ-んァ-ン一-龥]", "_", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("_") or "mineru_output"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Zip one MinerU output directory under data/mineru_output/{input_filename}."
    )
    parser.add_argument(
        "input_filename",
        help="Directory name under data/mineru_output. Example: 'Screenshot from 2026-06-18 03-13-06'",
    )
    parser.add_argument(
        "--root",
        default="data/mineru_output",
        help="MinerU output root directory. Defaults to data/mineru_output.",
    )
    parser.add_argument(
        "--zip-dir",
        default=".",
        help="Directory where the zip file will be created. Defaults to current directory.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing zip file.",
    )
    return parser.parse_args()


def zip_directory(source_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                arcname = path.relative_to(source_dir.parent)
                zf.write(path, arcname=str(arcname))


def main() -> int:
    args = parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    output_root = (repo_root / args.root).resolve()
    source_dir = output_root / args.input_filename

    if not source_dir.exists():
        print(f"ERROR: directory not found: {source_dir}", file=sys.stderr)
        return 2

    if not source_dir.is_dir():
        print(f"ERROR: not a directory: {source_dir}", file=sys.stderr)
        return 2

    zip_dir = (repo_root / args.zip_dir).resolve()
    zip_dir.mkdir(parents=True, exist_ok=True)

    zip_name = f"mineru_output_{sanitize_zip_name(args.input_filename)}.zip"
    zip_path = zip_dir / zip_name

    if zip_path.exists() and not args.force:
        print(f"ERROR: zip already exists: {zip_path}", file=sys.stderr)
        print("Use --force to overwrite.", file=sys.stderr)
        return 1

    if zip_path.exists():
        zip_path.unlink()

    print(f"[zip] {source_dir}")
    print(f"[out] {zip_path}")

    zip_directory(source_dir, zip_path)

    print("Done.")
    print(zip_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())