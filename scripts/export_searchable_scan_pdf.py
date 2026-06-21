from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mineru-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--debug-visible", action="store_true")
    parser.add_argument("--max-pages", type=int)
    parser.add_argument(
        "--include-discarded",
        dest="include_discarded",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--opacity", type=float, default=0.0)
    parser.add_argument(
        "--font-file",
        type=Path,
        help="Optional font file for CJK/Japanese text, e.g. NotoSansCJK-Medium.ttc",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"layout.json root must be object: {path}")
    return data


def find_origin_pdf(mineru_dir: Path) -> Path:
    candidates = sorted(mineru_dir.glob("*_origin.pdf"))
    if not candidates:
        raise FileNotFoundError(f"origin PDF not found in {mineru_dir}")
    if len(candidates) > 1:
        names = ", ".join(path.name for path in candidates)
        raise ValueError(f"Multiple origin PDFs found in {mineru_dir}: {names}")
    return candidates[0]


def iter_blocks(page_info: dict, include_discarded: bool) -> Iterable[dict]:
    for block in page_info.get("para_blocks") or []:
        if isinstance(block, dict):
            yield block

    if not include_discarded:
        return

    for block in page_info.get("discarded_blocks") or []:
        if isinstance(block, dict):
            yield block


def normalize_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.replace("\x00", "").strip()


def resolve_bbox(span: dict, line: dict, block: dict) -> list[float] | None:
    for source in (span, line, block):
        bbox = source.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue

        try:
            x0, y0, x1, y1 = [float(value) for value in bbox]
        except (TypeError, ValueError):
            continue

        if x1 <= x0 or y1 <= y0:
            continue

        return [x0, y0, x1, y1]

    return None


def to_pdf_rect(fitz_module, bbox: list[float], scale_x: float, scale_y: float, page_height: float):
    x0, y0, x1, y1 = bbox
    return fitz_module.Rect(
        x0 * scale_x,
        page_height - (y1 * scale_y),
        x1 * scale_x,
        page_height - (y0 * scale_y),
    )


def clamp_opacity(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def compute_fontsize(rect) -> float:
    return min(max(rect.height * 0.75, 3.0), 12.0)


def compute_insert_point(rect, fontsize: float) -> tuple[float, float]:
    x = rect.x0
    y = min(rect.y1, rect.y0 + fontsize)
    return (x, max(y, rect.y0 + 1))


def insert_span_text(page, rect, text: str, debug_visible: bool, opacity: float, font_file: Path | None) -> int:
    fontsize = compute_fontsize(rect)
    if fontsize <= 0:
        return 0

    point = compute_insert_point(rect, fontsize)

    if debug_visible:
        color = (1, 0, 0)
        fill_opacity = opacity if opacity > 0 else 0.8
        render_mode = 0
    elif opacity <= 0:
        color = (0, 0, 0)
        fill_opacity = 1.0
        render_mode = 3
    else:
        color = (0, 0, 0)
        fill_opacity = clamp_opacity(opacity)
        render_mode = 0

    try:
        insert_kwargs = {
            "fontsize": fontsize,
            "color": color,
            "render_mode": render_mode,
            "fill_opacity": fill_opacity,
            "overlay": True,
        }

        if font_file is not None:
            insert_kwargs["fontname"] = "cjk"
            insert_kwargs["fontfile"] = str(font_file)
        else:
            insert_kwargs["fontname"] = "helv"

        page.insert_text(
            point,
            text,
            **insert_kwargs,
        )
    except Exception as exc:
        print(
            f"[WARN] insert failed page={page.number} point=({point[0]:.2f},{point[1]:.2f}) "
            f"fontsize={fontsize:.2f} text={text!r} error={exc}"
        )
        return 0

    return 1


def export_searchable_pdf(
    mineru_dir: Path,
    output_path: Path,
    debug_visible: bool,
    max_pages: int | None,
    include_discarded: bool,
    opacity: float,
    font_file: Path | None,
) -> None:
    try:
        import fitz
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "PyMuPDF not installed. Install package providing `fitz` first."
        ) from exc

    layout_path = mineru_dir / "layout.json"
    if not layout_path.exists():
        raise FileNotFoundError(f"layout.json not found: {layout_path}")

    origin_pdf_path = find_origin_pdf(mineru_dir)
    layout = load_json(layout_path)
    pdf_info = layout.get("pdf_info")
    if not isinstance(pdf_info, list):
        raise ValueError("layout.json `pdf_info` must be list")

    if max_pages is not None and max_pages <= 0:
        raise ValueError("--max-pages must be positive")

    if font_file is not None:
        font_file = font_file.expanduser().resolve()
        if not font_file.exists():
            raise FileNotFoundError(f"font file not found: {font_file}")
        if not font_file.is_file():
            raise FileNotFoundError(f"font file is not a file: {font_file}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_inserted = 0
    total_skipped_pages = 0

    with fitz.open(origin_pdf_path) as doc:
        pages_to_process = len(pdf_info)
        if max_pages is not None:
            pages_to_process = min(pages_to_process, max_pages)

        for page_info in pdf_info[:pages_to_process]:
            if not isinstance(page_info, dict):
                continue

            page_idx = page_info.get("page_idx")
            if not isinstance(page_idx, int):
                print("[WARN] skip page with invalid page_idx")
                total_skipped_pages += 1
                continue

            if page_idx < 0 or page_idx >= doc.page_count:
                print(f"[WARN] skip page_idx={page_idx} outside PDF page_count={doc.page_count}")
                total_skipped_pages += 1
                continue

            page = doc[page_idx]
            page_rect = page.rect

            page_size = page_info.get("page_size")
            if (
                not isinstance(page_size, list)
                or len(page_size) != 2
                or not all(isinstance(value, (int, float)) for value in page_size)
            ):
                layout_width = page_rect.width
                layout_height = page_rect.height
            else:
                layout_width = float(page_size[0]) or page_rect.width
                layout_height = float(page_size[1]) or page_rect.height

            scale_x = page_rect.width / layout_width
            scale_y = page_rect.height / layout_height

            spans_found_on_page = 0
            inserted_on_page = 0

            for block in iter_blocks(page_info, include_discarded=include_discarded):
                lines = block.get("lines") or []
                if not isinstance(lines, list):
                    continue

                for line in lines:
                    if not isinstance(line, dict):
                        continue

                    spans = line.get("spans") or []
                    if not isinstance(spans, list):
                        continue

                    for span in spans:
                        if not isinstance(span, dict):
                            continue

                        text = normalize_text(span.get("content"))
                        if not text:
                            continue

                        bbox = resolve_bbox(span, line, block)
                        if bbox is None:
                            continue

                        spans_found_on_page += 1

                        rect = to_pdf_rect(
                            fitz,
                            bbox=bbox,
                            scale_x=scale_x,
                            scale_y=scale_y,
                            page_height=page_rect.height,
                        )

                        if rect.width <= 0 or rect.height <= 0:
                            continue

                        rect = fitz.Rect(
                            rect.x0,
                            rect.y0,
                            max(rect.x1, rect.x0 + 1),
                            max(rect.y1, rect.y0 + 1),
                        )

                        inserted = insert_span_text(
                            page,
                            rect=rect,
                            text=text,
                            debug_visible=debug_visible,
                            opacity=opacity,
                            font_file=font_file,
                        )
                        inserted_on_page += inserted

            total_inserted += inserted_on_page
            print(
                f"[PAGE] page_idx={page_idx} spans_found={spans_found_on_page} "
                f"spans_inserted={inserted_on_page} "
                f"scale_x={scale_x:.4f} scale_y={scale_y:.4f}"
            )

        doc.save(output_path, garbage=3, deflate=True)

    print()
    print("[OK] searchable scan PDF exported")
    print(f"mineru_dir    : {mineru_dir}")
    print(f"origin_pdf    : {origin_pdf_path}")
    print(f"layout_json   : {layout_path}")
    print(f"output        : {output_path}")
    print(f"pages_in_pdf  : {len(pdf_info)}")
    print(f"pages_skipped : {total_skipped_pages}")
    print(f"spans_inserted: {total_inserted}")
    print(f"discarded     : {include_discarded}")
    print(f"debug_visible : {debug_visible}")
    print(f"opacity       : {clamp_opacity(opacity) if opacity > 0 else opacity}")
    print(f"font_file     : {font_file}")


def main() -> None:
    args = parse_args()

    mineru_dir = Path(args.mineru_dir).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not mineru_dir.exists():
        raise FileNotFoundError(f"MinerU dir not found: {mineru_dir}")
    if not mineru_dir.is_dir():
        raise NotADirectoryError(f"MinerU path is not directory: {mineru_dir}")

    export_searchable_pdf(
        mineru_dir=mineru_dir,
        output_path=output_path,
        debug_visible=args.debug_visible,
        max_pages=args.max_pages,
        include_discarded=args.include_discarded,
        opacity=args.opacity,
        font_file=args.font_file,
    )


if __name__ == "__main__":
    main()
