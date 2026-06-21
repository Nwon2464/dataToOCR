#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def is_mineru_output_dir(path: Path) -> bool:
    if not path.is_dir():
        return False

    has_content_v2 = bool(list(path.glob("*_content_list_v2.json")))
    has_origin_pdf = bool(list(path.glob("*_origin.pdf")))

    return has_content_v2 and has_origin_pdf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mineru-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--force", action="store_true", help="Re-export even if output directory already exists.")
    parser.add_argument("--dry-run", action="store_true", help="Print targets without exporting.")
    args = parser.parse_args()

    mineru_root = args.mineru_root
    output_root = args.output_root

    if not mineru_root.exists():
        raise FileNotFoundError(f"mineru root not found: {mineru_root}")

    script_path = Path(__file__).resolve().parent / "export_text_study.py"
    if not script_path.exists():
        raise FileNotFoundError(f"export script not found: {script_path}")

    targets = [p for p in sorted(mineru_root.iterdir()) if is_mineru_output_dir(p)]

    print(f"mineru_root : {mineru_root}")
    print(f"output_root : {output_root}")
    print(f"targets     : {len(targets)}")

    if not targets:
        print("No MinerU output directories found.")
        return

    ok = 0
    skipped = 0
    failed = 0

    for mineru_dir in targets:
        output_dir = output_root / mineru_dir.name

        if output_dir.exists() and not args.force:
            print(f"[skip] {mineru_dir.name} -> {output_dir} already exists")
            skipped += 1
            continue

        cmd = [
            sys.executable,
            str(script_path),
            "--mineru-dir",
            str(mineru_dir),
            "--output-dir",
            str(output_dir),
        ]

        print(f"[run] {mineru_dir.name}")
        print("      " + " ".join(cmd))

        if args.dry_run:
            continue

        result = subprocess.run(cmd)

        if result.returncode == 0:
            print(f"[ok]  {mineru_dir.name}")
            ok += 1
        else:
            print(f"[ng]  {mineru_dir.name} returncode={result.returncode}")
            failed += 1

    print()
    print("summary")
    print(f"  ok      : {ok}")
    print(f"  skipped : {skipped}")
    print(f"  failed  : {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
