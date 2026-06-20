from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import shutil
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"
GOODNOTES_ROOT = PROJECT_ROOT / "assets" / "goodnotes_icons"
CANDIDATE_DIR = GOODNOTES_ROOT / "candidates"
MANIFEST_PATH = GOODNOTES_ROOT / "candidates_manifest.json"
REFERENCE_DIR = PROJECT_ROOT / "_review_exclude_assets"

ICON_CLASS = "goodnotes-small-icon"
STYLE_ID = "goodnotes-icon-rules"
DEFAULT_THRESHOLD = 8
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
LANCZOS = getattr(Image, "Resampling", Image).LANCZOS

ICON_CSS = f""".{ICON_CLASS} {{
  width: 22px !important;
  max-width: 22px !important;
  height: auto !important;
  display: inline-block !important;
  vertical-align: middle !important;
  margin: 0 4px !important;
  object-fit: contain !important;
}}

@media print {{
  .{ICON_CLASS} {{
    width: 18px !important;
    max-width: 18px !important;
    height: auto !important;
  }}
}}"""

_DCT_COSINES = tuple(
    tuple(math.cos((2 * x + 1) * frequency * math.pi / 64) for x in range(32))
    for frequency in range(8)
)


def safe_rel(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT).as_posix()


def is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def image_phash(image: Image.Image) -> str:
    """Return standard 64-bit pHash as 16 lowercase hexadecimal characters."""
    grayscale = image.convert("L").resize((32, 32), LANCZOS)
    pixels = list(grayscale.getdata())
    coefficients: list[float] = []

    for vertical_frequency in range(8):
        vertical_cosines = _DCT_COSINES[vertical_frequency]
        for horizontal_frequency in range(8):
            horizontal_cosines = _DCT_COSINES[horizontal_frequency]
            value = 0.0
            for y in range(32):
                row_offset = y * 32
                vertical_factor = vertical_cosines[y]
                value += vertical_factor * sum(
                    pixels[row_offset + x] * horizontal_cosines[x]
                    for x in range(32)
                )
            if vertical_frequency == 0:
                value /= math.sqrt(2)
            if horizontal_frequency == 0:
                value /= math.sqrt(2)
            coefficients.append(value)

    comparison_values = sorted(coefficients[1:])
    median = comparison_values[len(comparison_values) // 2]
    bits = 0
    for coefficient in coefficients:
        bits = (bits << 1) | int(coefficient > median)
    return f"{bits:016x}"


def phash_file(path: Path) -> str:
    with Image.open(path) as image:
        return image_phash(image)


def phash_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def image_dimensions(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def parse_data_uri(src: str) -> bytes | None:
    if not src.startswith("data:image/") or "," not in src:
        return None
    metadata, payload = src.split(",", 1)
    try:
        if ";base64" in metadata.lower():
            return base64.b64decode(payload, validate=False)
        return unquote(payload).encode("latin1")
    except (ValueError, UnicodeEncodeError):
        return None


def resolve_file_src(src: str, html_path: Path) -> Path | None:
    parsed = urlparse(src.strip())
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None

    if parsed.path.startswith("/processed/"):
        candidate = PROJECT_ROOT / "data" / parsed.path.lstrip("/")
    elif parsed.path.startswith("/"):
        return None
    else:
        candidate = html_path.parent / unquote(parsed.path)

    candidate = candidate.resolve()
    try:
        candidate.relative_to(PROCESSED_ROOT.resolve())
    except ValueError:
        return None
    return candidate if is_image(candidate) else None


def chunk_image_index(html_path: Path) -> dict[str, Path]:
    chunk_root = html_path.parents[1]
    index: dict[str, Path] = {}
    for path in sorted(chunk_root.rglob("*")):
        if is_image(path):
            index.setdefault(sha1_file(path), path)
    return index


def source_image_for_img(
    src: str,
    html_path: Path,
    hash_index: dict[str, Path],
) -> Path | None:
    direct_path = resolve_file_src(src, html_path)
    if direct_path:
        return direct_path

    embedded = parse_data_uri(src)
    if embedded is None:
        return None
    return hash_index.get(sha1_bytes(embedded))


def candidate_name(source_path: Path, sha1: str) -> str:
    return f"{source_path.stem}__{sha1[:10]}{source_path.suffix.lower()}"


def find_html_files(chunk_id: str | None = None) -> list[Path]:
    if chunk_id:
        target = PROCESSED_ROOT / chunk_id / "html" / "index.html"
        return [target] if target.is_file() else []
    return sorted(PROCESSED_ROOT.glob("*/html/index.html"))


def write_manifest(payload: dict) -> None:
    GOODNOTES_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_manifest() -> dict:
    if not MANIFEST_PATH.is_file():
        raise SystemExit(f"Manifest not found: {safe_rel(MANIFEST_PATH)}")
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise SystemExit("Invalid candidates manifest: expected object with items list.")
    return payload


def refresh_candidates() -> None:
    html_files = find_html_files()
    if not html_files:
        raise SystemExit("No data/processed/**/html/index.html files found.")

    if CANDIDATE_DIR.exists():
        shutil.rmtree(CANDIDATE_DIR)
    CANDIDATE_DIR.mkdir(parents=True, exist_ok=True)

    items: list[dict] = []
    copied_by_source: dict[Path, Path] = {}
    skipped = 0

    for html_path in html_files:
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
        hash_index = chunk_image_index(html_path)

        for img in soup.find_all("img"):
            src = str(img.get("src") or "").strip()
            source_path = source_image_for_img(src, html_path, hash_index)
            if source_path is None:
                skipped += 1
                continue

            digest = sha1_file(source_path)
            candidate_path = copied_by_source.get(source_path)
            if candidate_path is None:
                candidate_path = CANDIDATE_DIR / candidate_name(source_path, digest)
                if candidate_path.exists() and sha1_file(candidate_path) != digest:
                    candidate_path = CANDIDATE_DIR / f"{digest}{source_path.suffix.lower()}"
                shutil.copy2(source_path, candidate_path)
                copied_by_source[source_path] = candidate_path

            width, height = image_dimensions(source_path)
            items.append(
                {
                    "source_html": safe_rel(html_path),
                    "source_img_src": src,
                    "source_path": safe_rel(source_path),
                    "candidate_path": safe_rel(candidate_path),
                    "width": width,
                    "height": height,
                    "sha1": digest,
                    "phash": phash_file(source_path),
                }
            )

    write_manifest(
        {
            "source_root": safe_rel(PROCESSED_ROOT),
            "candidate_dir": safe_rel(CANDIDATE_DIR),
            "total_source_images": len(items),
            "copied_unique_images": len(copied_by_source),
            "unresolved_images": skipped,
            "items": items,
        }
    )
    print(f"HTML files: {len(html_files)}")
    print(f"manifest items: {len(items)}")
    print(f"copied unique images: {len(copied_by_source)}")
    print(f"unresolved img tags: {skipped}")


def mark_small_icons(threshold: int) -> None:
    payload = load_manifest()
    references = sorted(path for path in REFERENCE_DIR.rglob("*") if is_image(path))
    if not references:
        raise SystemExit(f"No reference images found in {safe_rel(REFERENCE_DIR)}/")

    reference_hashes = [(path, phash_file(path)) for path in references]
    marked = 0
    for item in payload["items"]:
        candidate_path = PROJECT_ROOT / item["candidate_path"]
        candidate_hash = item.get("phash") or phash_file(candidate_path)
        item["phash"] = candidate_hash

        matched_path, distance = min(
            (
                (reference_path, phash_distance(candidate_hash, reference_hash))
                for reference_path, reference_hash in reference_hashes
            ),
            key=lambda match: match[1],
        )
        is_small = distance <= threshold
        item["small_icon"] = is_small
        item["matched_reference"] = safe_rel(matched_path) if is_small else None
        item["match_distance"] = distance if is_small else None
        if is_small:
            marked += 1

    payload["phash_threshold"] = threshold
    payload["reference_dir"] = safe_rel(REFERENCE_DIR)
    payload["reference_images"] = len(reference_hashes)
    write_manifest(payload)
    print(f"reference images: {len(reference_hashes)}")
    print(f"manifest items: {len(payload['items'])}")
    print(f"small icons: {marked}")
    print(f"threshold: {threshold}")


def remove_size_from_style(style: str | None) -> str | None:
    if not style:
        return None
    kept: list[str] = []
    for declaration in style.split(";"):
        declaration = declaration.strip()
        if not declaration:
            continue
        property_name = declaration.partition(":")[0].strip().lower()
        if property_name not in {"width", "height", "max-width", "max-height"}:
            kept.append(declaration)
    return "; ".join(kept) or None


def ensure_icon_style(soup: BeautifulSoup) -> None:
    styles = soup.find_all("style", id=STYLE_ID)
    if styles:
        style = styles[0]
        style.string = ICON_CSS
        for duplicate in styles[1:]:
            duplicate.decompose()
    else:
        style = soup.new_tag("style", id=STYLE_ID)
        style.string = ICON_CSS

    if soup.head is None:
        head = soup.new_tag("head")
        if soup.html:
            soup.html.insert(0, head)
        else:
            soup.insert(0, head)
    if style.parent is not soup.head:
        soup.head.append(style.extract())


def phash_bytes(data: bytes) -> str:
    with Image.open(BytesIO(data)) as image:
        return image_phash(image)


def matches_small_icon(
    digest: str,
    perceptual_hash: str,
    small_icon_sha1s: set[str],
    small_icon_phashes: set[str],
    threshold: int,
) -> bool:
    if digest in small_icon_sha1s:
        return True
    return any(
        phash_distance(perceptual_hash, reference_hash) <= threshold
        for reference_hash in small_icon_phashes
    )


def apply_icon_attributes(img) -> None:
    """Add icon class and remove only sizing data; preserve all other attributes."""
    classes = list(img.get("class") or [])
    if ICON_CLASS not in classes:
        classes.append(ICON_CLASS)
    img["class"] = classes
    img.attrs.pop("width", None)
    img.attrs.pop("height", None)

    cleaned_style = remove_size_from_style(img.get("style"))
    if cleaned_style:
        img["style"] = cleaned_style
    else:
        img.attrs.pop("style", None)


def apply_to_html(
    html_path: Path,
    small_icon_sha1s: set[str],
    small_icon_phashes: set[str],
    threshold: int,
    dry_run: bool,
) -> dict[str, int]:
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    stats = {
        "file_img_tags": 0,
        "data_uri_img_tags": 0,
        "matched_file_imgs": 0,
        "matched_data_uri_imgs": 0,
    }

    for img in soup.find_all("img"):
        src = str(img.get("src") or "").strip()
        matched = False

        if src.lower().startswith("data:image/"):
            stats["data_uri_img_tags"] += 1
            image_data = parse_data_uri(src)
            if image_data is not None:
                try:
                    matched = matches_small_icon(
                        sha1_bytes(image_data),
                        phash_bytes(image_data),
                        small_icon_sha1s,
                        small_icon_phashes,
                        threshold,
                    )
                except (OSError, ValueError):
                    matched = False
            if matched:
                stats["matched_data_uri_imgs"] += 1
        else:
            stats["file_img_tags"] += 1
            image_path = resolve_file_src(src, html_path)
            if image_path is not None:
                try:
                    matched = matches_small_icon(
                        sha1_file(image_path),
                        phash_file(image_path),
                        small_icon_sha1s,
                        small_icon_phashes,
                        threshold,
                    )
                except (OSError, ValueError):
                    matched = False
            if matched:
                stats["matched_file_imgs"] += 1

        if matched:
            apply_icon_attributes(img)

    matched_total = stats["matched_file_imgs"] + stats["matched_data_uri_imgs"]
    if matched_total:
        ensure_icon_style(soup)
        if not dry_run:
            html_path.write_text(str(soup), encoding="utf-8")
    return stats


def apply_rules(chunk_id: str | None, dry_run: bool) -> None:
    payload = load_manifest()
    small_icon_items = [item for item in payload["items"] if item.get("small_icon") is True]
    small_icon_sha1s = {
        str(item["sha1"]) for item in small_icon_items if item.get("sha1")
    }
    small_icon_phashes = {
        str(item["phash"]) for item in small_icon_items if item.get("phash")
    }
    threshold = int(payload.get("phash_threshold", DEFAULT_THRESHOLD))
    targets = find_html_files(chunk_id)

    if chunk_id and not targets:
        raise SystemExit(f"Chunk HTML not found: {chunk_id}")
    if not small_icon_sha1s and not small_icon_phashes:
        raise SystemExit("No small_icon: true fingerprints found in manifest.")

    totals = {
        "file_img_tags": 0,
        "data_uri_img_tags": 0,
        "matched_file_imgs": 0,
        "matched_data_uri_imgs": 0,
    }
    for html_path in targets:
        stats = apply_to_html(
            html_path,
            small_icon_sha1s,
            small_icon_phashes,
            threshold,
            dry_run,
        )
        for key, value in stats.items():
            totals[key] += value

    print(f"target HTML files: {len(targets)}")
    print(f"file img tags: {totals['file_img_tags']}")
    print(f"data uri img tags: {totals['data_uri_img_tags']}")
    print(f"matched file imgs: {totals['matched_file_imgs']}")
    print(f"matched data uri imgs: {totals['matched_data_uri_imgs']}")
    print(f"threshold: {threshold}")
    print(f"dry run: {dry_run}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GoodNotes image cleanup pipeline.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("refresh-candidates", help="Collect images referenced by processed HTML.")

    mark = commands.add_parser("mark-small-icons", help="Classify candidates using pHash similarity.")
    mark.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_THRESHOLD,
        help=f"Maximum 64-bit pHash Hamming distance (default: {DEFAULT_THRESHOLD}).",
    )

    apply = commands.add_parser("apply", help="Apply classified icon rules to processed HTML.")
    apply.add_argument("--dry-run", action="store_true", help="Report without modifying HTML.")
    apply.add_argument("--chunk", help="Process one chunk ID only.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "refresh-candidates":
        refresh_candidates()
    elif args.command == "mark-small-icons":
        if not 0 <= args.threshold <= 64:
            raise SystemExit("--threshold must be between 0 and 64.")
        mark_small_icons(args.threshold)
    elif args.command == "apply":
        apply_rules(args.chunk, args.dry_run)


if __name__ == "__main__":
    main()
