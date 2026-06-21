#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def has_mineru_result(output_dir: Path) -> bool:
    if not output_dir.exists():
        return False

    has_content_v2 = bool(list(output_dir.glob("*_content_list_v2.json")))
    has_layout = (output_dir / "layout.json").exists()
    has_status = (output_dir / "api_status.json").exists()

    return has_content_v2 and has_layout and has_status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks-dir", type=Path, default=Path("data/chunks_10"))
    parser.add_argument("--mineru-root", type=Path, default=Path("data/mineru_api_output"))
    parser.add_argument("--language", default=None, help="Override MinerU language. If omitted, run_mineru_api_batch.py default is used.")
    parser.add_argument("--extra-format", default="html")
    parser.add_argument("--interval-seconds", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--force", action="store_true", help="Run even if output already exists.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    chunks_dir = args.chunks_dir
    mineru_root = args.mineru_root

    if not chunks_dir.exists():
        raise FileNotFoundError(f"chunks dir not found: {chunks_dir}")

    script_path = Path(__file__).resolve().parent / "run_mineru_api_batch.py"
    if not script_path.exists():
        raise FileNotFoundError(f"MinerU runner not found: {script_path}")

    chunk_pdfs = sorted(chunks_dir.glob("*.pdf"))

    print(f"chunks_dir  : {chunks_dir}")
    print(f"mineru_root : {mineru_root}")
    print(f"chunks      : {len(chunk_pdfs)}")
    print(f"force       : {args.force}")
    print(f"dry_run     : {args.dry_run}")
    print()

    if not chunk_pdfs:
        print("No chunk PDFs found.")
        return

    ok = 0
    skipped = 0
    failed = 0

    for chunk_pdf in chunk_pdfs:
        chunk_name = chunk_pdf.stem
        output_dir = mineru_root / chunk_name

        if has_mineru_result(output_dir) and not args.force:
            print(f"[skip] {chunk_name} already has MinerU result")
            skipped += 1
            continue

        cmd = [
            sys.executable,
            str(script_path),
            "run",
            str(chunk_pdf),
            "--extra-format",
            args.extra_format,
            "--interval-seconds",
            str(args.interval_seconds),
            "--timeout-seconds",
            str(args.timeout_seconds),
        ]

        if args.language:
            cmd.extend(["--language", args.language])

        print(f"[run] {chunk_name}")
        print("      " + " ".join(cmd))

        if args.dry_run:
            continue

        result = subprocess.run(cmd)

        if result.returncode == 0:
            print(f"[ok]  {chunk_name}")
            ok += 1
        else:
            print(f"[ng]  {chunk_name} returncode={result.returncode}")
            failed += 1
            break

        print()

    print()
    print("summary")
    print(f"  ok      : {ok}")
    print(f"  skipped : {skipped}")
    print(f"  failed  : {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
