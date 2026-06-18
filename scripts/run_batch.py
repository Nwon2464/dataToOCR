#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.mineru_paths import (
    find_mineru_images_dir,
    find_mineru_markdown,
    get_project_root,
    list_mineru_sample_dirs,
)


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run full local batch pipeline for files in data/samples."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/samples"),
        help="Input directory containing PDF/image files. Default: data/samples.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/mineru_output"),
        help="MinerU output root. Default: data/mineru_output.",
    )
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        default=Path("data/manifests"),
        help="Directory for batch manifest JSONL files. Default: data/manifests.",
    )
    parser.add_argument(
        "--backend",
        default="pipeline",
        help="MinerU backend. Use pipeline for CPU, or auto to omit -b. Default: pipeline.",
    )
    parser.add_argument(
        "--mineru-bin",
        default="mineru",
        help="MinerU executable name or path. Default: mineru.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run MinerU even when sample output auto/ already exists.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned work and write no manifest.",
    )
    return parser.parse_args()


def resolve_under_root(root: Path, path: Path) -> Path:
    """Resolve relative path under project root."""
    if path.is_absolute():
        return path
    return (root / path).resolve()


def iter_input_files(input_dir: Path) -> list[Path]:
    """Return supported input files in deterministic name order."""
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    return sorted(
        (
            path
            for path in input_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ),
        key=lambda path: path.name,
    )


def sha256_file(path: Path) -> str:
    """Return SHA-256 hex digest for file content."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_mineru_command(
    mineru_bin: str,
    source: Path,
    output_dir: Path,
    backend: str,
) -> list[str]:
    """Build MinerU CLI command."""
    command = [mineru_bin, "-p", str(source), "-o", str(output_dir)]
    if backend != "auto":
        command.extend(["-b", backend])
    return command


def find_optional_markdown(sample_dir: Path) -> Path | None:
    """Return Markdown path when exactly one exists, otherwise None."""
    try:
        return find_mineru_markdown(sample_dir)
    except (FileNotFoundError, ValueError):
        return None


def make_manifest_path(manifest_dir: Path) -> Path:
    """Return timestamped manifest JSONL path."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return manifest_dir / f"batch_{stamp}.jsonl"


def write_manifest_record(manifest_path: Path, record: dict[str, Any]) -> None:
    """Append one JSON record to manifest file."""
    with manifest_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        file.write("\n")


def build_record(
    *,
    batch_id: str,
    source: Path,
    output_dir: Path,
    status: str,
    input_sha256: str,
    command: list[str],
    returncode: int | None,
    markdown_path: Path | None,
    images_dir: Path | None,
) -> dict[str, Any]:
    """Build manifest record for one input file."""
    auto_dir = output_dir / "auto"
    return {
        "batch_id": batch_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "input_path": str(source),
        "input_name": source.name,
        "sample_name": source.stem,
        "input_sha256": input_sha256,
        "output_dir": str(output_dir),
        "auto_dir": str(auto_dir),
        "auto_dir_exists": auto_dir.is_dir(),
        "markdown_path": str(markdown_path) if markdown_path is not None else None,
        "images_dir": str(images_dir) if images_dir is not None else None,
        "command": command,
        "status": status,
        "returncode": returncode,
    }


def run_batch(args: argparse.Namespace) -> int:
    project_root = get_project_root()
    input_dir = resolve_under_root(project_root, args.input_dir)
    output_root = resolve_under_root(project_root, args.output_root)
    manifest_dir = resolve_under_root(project_root, args.manifest_dir)

    sources = iter_input_files(input_dir)
    if not sources:
        print(f"No supported input files found: {input_dir}", file=sys.stderr)
        return 1

    if not args.dry_run and shutil.which(args.mineru_bin) is None:
        missing_outputs = [
            source
            for source in sources
            if args.force or not (output_root / source.stem / "auto").is_dir()
        ]
        if missing_outputs:
            print(
                f"MinerU executable not found: {args.mineru_bin}",
                file=sys.stderr,
            )
            return 127

    output_root.mkdir(parents=True, exist_ok=True)
    if not args.dry_run:
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = make_manifest_path(manifest_dir)
    else:
        manifest_path = manifest_dir / "dry-run.jsonl"

    batch_id = manifest_path.stem
    failures = 0

    print(f"Input files: {len(sources)}")
    print(f"Output root: {output_root}")
    print(f"Manifest: {manifest_path if not args.dry_run else 'dry-run'}")

    for source in sources:
        output_dir = output_root / source.stem
        auto_dir = output_dir / "auto"
        command = build_mineru_command(args.mineru_bin, source, output_dir, args.backend)
        input_sha256 = sha256_file(source)

        if auto_dir.is_dir() and not args.force:
            markdown_path = find_optional_markdown(output_dir)
            images_dir = find_mineru_images_dir(output_dir)
            status = "skipped_existing"
            returncode = None
            print(f"[skip] {source.name}")
        elif args.dry_run:
            markdown_path = None
            images_dir = None
            status = "planned"
            returncode = None
            print(f"[plan] {' '.join(command)}")
        else:
            if args.force and output_dir.exists():
                shutil.rmtree(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            print(f"[run] {source.name}")
            print(f"[cmd] {' '.join(command)}")
            completed = subprocess.run(command)
            returncode = completed.returncode
            markdown_path = find_optional_markdown(output_dir)
            images_dir = find_mineru_images_dir(output_dir) if auto_dir.is_dir() else None
            status = "success" if returncode == 0 and auto_dir.is_dir() else "failed"
            if status == "failed":
                failures += 1

        record = build_record(
            batch_id=batch_id,
            source=source,
            output_dir=output_dir,
            status=status,
            input_sha256=input_sha256,
            command=command,
            returncode=returncode,
            markdown_path=markdown_path,
            images_dir=images_dir,
        )
        if not args.dry_run:
            write_manifest_record(manifest_path, record)

    sample_dirs = list_mineru_sample_dirs(output_root)
    print(f"MinerU sample outputs: {len(sample_dirs)}")

    if failures:
        print(f"Failed files: {failures}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    args = parse_args()
    try:
        return run_batch(args)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
