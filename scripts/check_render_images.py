from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from common.api_paths import get_processed_dir


IMG_SRC_RE = re.compile(r"<img\b[^>]*\bsrc=(['\"])(.*?)\1", re.IGNORECASE)
IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
STYLE_ATTR_RE = re.compile(r"\sstyle=(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL)
WIDTH_STYLE_RE = re.compile(r"^\s*(?:min-|max-)?width\s*:", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check render_all.json image src files exist.")
    parser.add_argument(
        "--render-all",
        type=Path,
        default=get_processed_dir() / "render_all.json",
        help="Path to combined render_all.json.",
    )
    return parser.parse_args()


def img_srcs(value: Any) -> list[str]:
    if not isinstance(value, str) or "<img" not in value.lower():
        return []
    return [match.group(2) for match in IMG_SRC_RE.finditer(value)]


def img_width_styles(value: Any) -> list[str]:
    if not isinstance(value, str) or "<img" not in value.lower():
        return []
    offenders: list[str] = []
    for tag_match in IMG_TAG_RE.finditer(value):
        tag = tag_match.group(0)
        style_match = STYLE_ATTR_RE.search(tag)
        if not style_match:
            continue
        declarations = [declaration.strip() for declaration in style_match.group(2).split(";") if declaration.strip()]
        if any(WIDTH_STYLE_RE.match(declaration) for declaration in declarations):
            offenders.append(tag)
    return offenders


def local_path_for_src(src: str, processed_root: Path) -> Path | None:
    if src.startswith("/processed/"):
        return processed_root / src.removeprefix("/processed/")
    if src.startswith("processed/"):
        return processed_root / src.removeprefix("processed/")
    return None


def main() -> int:
    args = parse_args()
    render_all_path = args.render_all
    processed_root = render_all_path.parent
    data = json.loads(render_all_path.read_text(encoding="utf-8"))
    blocks = data.get("blocks") if isinstance(data, dict) else []

    total = 0
    missing: list[str] = []
    width_styles: list[str] = []
    external = 0
    for block in blocks if isinstance(blocks, list) else []:
        if not isinstance(block, dict):
            continue
        width_styles.extend(img_width_styles(block.get("html")))
        for src in img_srcs(block.get("html")):
            total += 1
            local_path = local_path_for_src(src, processed_root)
            if local_path is None:
                external += 1
                continue
            if not local_path.exists():
                missing.append(src)

    print(f"image src total: {total}")
    print(f"external src: {external}")
    print(f"missing files: {len(missing)}")
    print(f"img width inline styles: {len(width_styles)}")
    for src in missing[:20]:
        print(f"- {src}")
    if len(missing) > 20:
        print(f"... {len(missing) - 20} more")
    for tag in width_styles[:20]:
        print(f"- {tag}")
    if len(width_styles) > 20:
        print(f"... {len(width_styles) - 20} more")
    return 1 if missing or width_styles else 0


if __name__ == "__main__":
    raise SystemExit(main())
