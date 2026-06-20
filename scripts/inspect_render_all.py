#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PAGE_KEY_RE = re.compile(r"page|page_idx|page_no|page_number|pageid", re.I)
TEXT_KEY_RE = re.compile(r"text|content|html|markdown|md", re.I)
IMAGE_KEY_RE = re.compile(r"src|image|img|path|url", re.I)
CHAPTER_RE = re.compile(r"Chapter\s+\d+", re.I)


def short(v: Any, limit: int = 300) -> str:
    s = repr(v)
    s = s.replace("\\n", " ")
    if len(s) > limit:
        return s[:limit] + "..."
    return s


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def walk(
    obj: Any,
    path: str = "$",
    depth: int = 0,
    max_depth: int = 8,
    stats: dict[str, Any] | None = None,
):
    if stats is None:
        stats = {
            "types": Counter(),
            "keys": Counter(),
            "page_keys": Counter(),
            "text_keys": Counter(),
            "image_keys": Counter(),
            "list_paths": [],
            "dict_paths": [],
            "chapter_hits": [],
            "marker_hits": [],
            "text_samples": [],
            "image_samples": [],
        }

    stats["types"][type(obj).__name__] += 1

    if depth > max_depth:
        return stats

    if isinstance(obj, dict):
        stats["dict_paths"].append((path, list(obj.keys())[:30]))

        for k, v in obj.items():
            stats["keys"][k] += 1

            if PAGE_KEY_RE.search(k):
                stats["page_keys"][k] += 1

            if TEXT_KEY_RE.search(k):
                stats["text_keys"][k] += 1
                if isinstance(v, str) and len(v.strip()) > 0:
                    stats["text_samples"].append((path + "." + k, v[:500]))
                    if CHAPTER_RE.search(v):
                        stats["chapter_hits"].append((path + "." + k, v[:500]))
                    if "本章のポイント" in v:
                        stats["marker_hits"].append((path + "." + k, v[:500]))

            if IMAGE_KEY_RE.search(k):
                stats["image_keys"][k] += 1
                if isinstance(v, str):
                    stats["image_samples"].append((path + "." + k, v[:300]))

            walk(v, f"{path}.{k}", depth + 1, max_depth, stats)

    elif isinstance(obj, list):
        stats["list_paths"].append((path, len(obj)))

        # 너무 크면 앞부분만 구조 분석
        for i, item in enumerate(obj[:50]):
            walk(item, f"{path}[{i}]", depth + 1, max_depth, stats)

    elif isinstance(obj, str):
        if CHAPTER_RE.search(obj):
            stats["chapter_hits"].append((path, obj[:500]))
        if "本章のポイント" in obj:
            stats["marker_hits"].append((path, obj[:500]))

    return stats


def print_top_structure(data: Any):
    print("=== TOP STRUCTURE ===")
    print("root type:", type(data).__name__)

    if isinstance(data, dict):
        print("top keys:", list(data.keys())[:80])
        for k, v in data.items():
            print()
            print(f"key: {k}")
            print("  type:", type(v).__name__)
            if isinstance(v, list):
                print("  len:", len(v))
                if v:
                    print("  first item type:", type(v[0]).__name__)
                    print("  first item sample:", short(v[0], 1200))
            elif isinstance(v, dict):
                print("  keys:", list(v.keys())[:50])
                print("  sample:", short(v, 1200))
            else:
                print("  sample:", short(v, 500))

    elif isinstance(data, list):
        print("list len:", len(data))
        if data:
            print("first item type:", type(data[0]).__name__)
            print("first item sample:", short(data[0], 1500))

    print()


def print_stats(stats: dict[str, Any]):
    print("=== TYPE COUNTS ===")
    for k, v in stats["types"].most_common():
        print(f"{k}: {v}")
    print()

    print("=== COMMON KEYS ===")
    for k, v in stats["keys"].most_common(80):
        print(f"{k}: {v}")
    print()

    print("=== PAGE-LIKE KEYS ===")
    for k, v in stats["page_keys"].most_common():
        print(f"{k}: {v}")
    print()

    print("=== TEXT-LIKE KEYS ===")
    for k, v in stats["text_keys"].most_common():
        print(f"{k}: {v}")
    print()

    print("=== IMAGE/PATH-LIKE KEYS ===")
    for k, v in stats["image_keys"].most_common():
        print(f"{k}: {v}")
    print()

    print("=== LIST PATHS ===")
    for p, n in stats["list_paths"][:80]:
        print(f"{p}: len={n}")
    print()

    print("=== DICT PATHS SAMPLE ===")
    for p, keys in stats["dict_paths"][:40]:
        print(f"{p}: keys={keys}")
    print()


def print_hits(stats: dict[str, Any], limit: int):
    print("=== CHAPTER HITS ===")
    for p, text in stats["chapter_hits"][:limit]:
        print("---")
        print("path:", p)
        print(text.replace("\n", " ")[:500])
    print(f"total chapter hits sampled: {len(stats['chapter_hits'])}")
    print()

    print("=== 本章のポイント HITS ===")
    for p, text in stats["marker_hits"][:limit]:
        print("---")
        print("path:", p)
        print(text.replace("\n", " ")[:500])
    print(f"total marker hits sampled: {len(stats['marker_hits'])}")
    print()

    print("=== TEXT SAMPLES ===")
    for p, text in stats["text_samples"][:limit]:
        print("---")
        print("path:", p)
        print(text.replace("\n", " ")[:500])
    print()

    print("=== IMAGE/PATH SAMPLES ===")
    for p, text in stats["image_samples"][:limit]:
        print("---")
        print("path:", p)
        print(text)
    print()


def find_possible_page_objects(data: Any, limit: int = 30):
    """
    Heuristic:
    print dicts that contain both page-like key and text/html-like key.
    """
    found = []

    def rec(obj: Any, path: str):
        if len(found) >= limit:
            return

        if isinstance(obj, dict):
            keys = list(obj.keys())
            has_page = any(PAGE_KEY_RE.search(k) for k in keys)
            has_text = any(TEXT_KEY_RE.search(k) for k in keys)
            has_img = any(IMAGE_KEY_RE.search(k) for k in keys)

            if has_page and (has_text or has_img):
                found.append((path, obj))
                return

            for k, v in obj.items():
                rec(v, f"{path}.{k}")

        elif isinstance(obj, list):
            for i, v in enumerate(obj[:100]):
                rec(v, f"{path}[{i}]")

    rec(data, "$")

    print("=== POSSIBLE PAGE/BLOCK OBJECTS ===")
    print("count shown:", len(found))
    for p, obj in found:
        print("---")
        print("path:", p)
        print("keys:", list(obj.keys())[:50])
        print(short(obj, 1200))
    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        nargs="?",
        default="data/processed/render_all.json",
        help="Path to render_all.json",
    )
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--hit-limit", type=int, default=20)
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    data = load_json(path)

    print(f"file: {path}")
    print(f"size_mb: {path.stat().st_size / 1024 / 1024:.2f}")
    print()

    print_top_structure(data)

    stats = walk(data, max_depth=args.max_depth)

    print_stats(stats)
    print_hits(stats, args.hit_limit)
    find_possible_page_objects(data)


if __name__ == "__main__":
    main()
