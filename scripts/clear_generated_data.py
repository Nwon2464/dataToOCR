#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"
ASSETS_ROOT = PROJECT_ROOT / "assets"

# New source PDF must not mix with files generated from previous source PDF.
CLEAR_ROOTS = (
    DATA_ROOT / "chunks",
    DATA_ROOT / "mineru_api_output",
    DATA_ROOT / "mineru_output",
    DATA_ROOT / "processed",
    DATA_ROOT / "toc",
)

# Generated asset files derived from the previous source PDF.
# Do not delete all of assets/ blindly.
CLEAR_ASSET_DIR_CONTENTS = (
    ASSETS_ROOT / "goodnotes_icons" / "candidates",
)

CLEAR_ASSET_FILES = (
    ASSETS_ROOT / "goodnotes_icons" / "candidates_manifest.json",
)

PRESERVED_ROOTS = (
    DATA_ROOT / "original",
    PROJECT_ROOT / "exports" / "goodnotes" / "raw",
    PROJECT_ROOT / "exports" / "goodnotes" / "final",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clear generated OCR data before adding a new source PDF."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Delete files. Without this flag, only show dry-run output.",
    )
    return parser.parse_args()


def assert_safe_root(root: Path) -> None:
    resolved = root.resolve()
    data_root = DATA_ROOT.resolve()

    if resolved == data_root or data_root not in resolved.parents:
        raise RuntimeError(f"Unsafe cleanup path: {resolved}")


def assert_safe_asset_path(path: Path) -> None:
    resolved = path.resolve()
    project_root = PROJECT_ROOT.resolve()
    assets_root = ASSETS_ROOT.resolve()

    if resolved in (project_root, assets_root):
        raise RuntimeError(f"Unsafe cleanup path: {resolved}")

    if project_root not in resolved.parents:
        raise RuntimeError(f"Path is outside project root: {resolved}")

    if assets_root not in resolved.parents:
        raise RuntimeError(f"Path is outside assets root: {resolved}")


def collect_entries(root: Path) -> list[Path]:
    if not root.exists():
        return []

    if root.is_file() or root.is_symlink():
        return [root]

    return sorted(entry for entry in root.iterdir() if entry.name != ".gitkeep")


def entry_size(entry: Path) -> int:
    if not entry.exists():
        return 0

    if entry.is_file() or entry.is_symlink():
        return entry.stat().st_size

    return sum(path.stat().st_size for path in entry.rglob("*") if path.is_file())


def remove_entry(entry: Path) -> None:
    if not entry.exists():
        return

    if entry.is_dir() and not entry.is_symlink():
        shutil.rmtree(entry)
    else:
        entry.unlink()


def relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def main() -> int:
    args = parse_args()
    entries: list[Path] = []

    for root in CLEAR_ROOTS:
        assert_safe_root(root)
        root_entries = collect_entries(root)
        entries.extend(root_entries)
        print(f"[target] {relative(root)}: {len(root_entries)} entries")

    for root in CLEAR_ASSET_DIR_CONTENTS:
        assert_safe_asset_path(root)
        root_entries = collect_entries(root)
        entries.extend(root_entries)
        print(f"[target] {relative(root)}/*: {len(root_entries)} entries")

    for file_path in CLEAR_ASSET_FILES:
        assert_safe_asset_path(file_path)
        file_entries = collect_entries(file_path)
        entries.extend(file_entries)
        print(f"[target] {relative(file_path)}: {len(file_entries)} entries")

    total_bytes = sum(entry_size(entry) for entry in entries)

    print(f"[summary] {len(entries)} entries, {total_bytes} bytes")

    for root in PRESERVED_ROOTS:
        print(f"[preserve] {relative(root)}")

    if not args.yes:
        print("[dry-run] nothing deleted. Run again with --yes to delete.")
        return 0

    for entry in entries:
        remove_entry(entry)

    for root in CLEAR_ROOTS:
        root.mkdir(parents=True, exist_ok=True)

    for root in CLEAR_ASSET_DIR_CONTENTS:
        root.mkdir(parents=True, exist_ok=True)

    print(f"[deleted] {len(entries)} entries, {total_bytes} bytes")
    print("[done] generated OCR data cleared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())