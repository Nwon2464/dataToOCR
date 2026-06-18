#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


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
        description="Run MinerU on files in data/samples and write outputs to data/mineru_output."
    )
    parser.add_argument(
        "--input",
        default="data/samples",
        help="Input file or directory. Defaults to data/samples.",
    )
    parser.add_argument(
        "--output",
        default="data/mineru_output",
        help="Output root directory. Defaults to data/mineru_output.",
    )
    parser.add_argument(
        "--backend",
        default="pipeline",
        help="MinerU backend. Use pipeline for CPU, or auto to omit -b. Defaults to pipeline.",
    )
    parser.add_argument(
        "--mineru-bin",
        default="mineru",
        help="MinerU executable name or path. Defaults to mineru.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete an existing per-file output directory before running.",
    )
    return parser.parse_args()


def iter_inputs(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() in SUPPORTED_EXTENSIONS else []

    if not input_path.is_dir():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    return sorted(
        path
        for path in input_path.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def build_command(mineru_bin: str, source: Path, output_dir: Path, backend: str) -> list[str]:
    command = [mineru_bin, "-p", str(source), "-o", str(output_dir)]
    if backend != "auto":
        command.extend(["-b", backend])
    return command


def run_one(mineru_bin: str, source: Path, output_root: Path, backend: str, force: bool) -> int:
    output_dir = output_root / source.stem
    if force and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    command = build_command(mineru_bin, source, output_dir, backend)
    print(f"[mineru] {source} -> {output_dir}", flush=True)
    print(f"[cmd] {' '.join(command)}", flush=True)
    return subprocess.run(command).returncode


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    input_path = (repo_root / args.input).resolve()
    output_root = (repo_root / args.output).resolve()

    if shutil.which(args.mineru_bin) is None:
        print(
            f"MinerU executable not found: {args.mineru_bin}\n"
            "Install dependencies and activate the environment first:\n"
            "  python3 -m venv .venv\n"
            "  source .venv/bin/activate\n"
            "  pip install uv\n"
            "  uv pip install -r requirements-mineru.txt",
            file=sys.stderr,
        )
        return 127

    try:
        sources = iter_inputs(input_path)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not sources:
        print(f"No supported input files found in {input_path}", file=sys.stderr)
        return 1

    output_root.mkdir(parents=True, exist_ok=True)

    failures: list[tuple[Path, int]] = []
    for source in sources:
        returncode = run_one(
            args.mineru_bin,
            source,
            output_root,
            args.backend,
            args.force,
        )
        if returncode != 0:
            failures.append((source, returncode))

    if failures:
        print("\nFailed files:", file=sys.stderr)
        for source, returncode in failures:
            print(f"  {source} exited with {returncode}", file=sys.stderr)
        return 1

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
