from __future__ import annotations

import argparse
import re
from pathlib import Path


def render_source_previews(
    text_study_root: Path,
    mineru_root: Path,
    scale: float = 1.0,
) -> None:
    try:
        import fitz
    except ImportError as exc:
        raise SystemExit(
            "PyMuPDF is required. Install it with: pip install pymupdf"
        ) from exc

    created = 0
    skipped = 0
    missing_origin: list[str] = []
    bad_chunks: list[tuple[str, int, int]] = []

    chunk_dirs = sorted(
        p
        for p in text_study_root.glob("*_p*")
        if p.is_dir() and re.search(r"_p\d{3}_\d{3}$", p.name)
    )

    for chunk_dir in chunk_dirs:
        m = re.search(r"_p(\d{3})_(\d{3})$", chunk_dir.name)
        if not m:
            continue

        start_page = int(m.group(1))
        end_page = int(m.group(2))

        mineru_dir = mineru_root / chunk_dir.name
        origin_pdfs = sorted(mineru_dir.glob("*_origin.pdf"))

        if not origin_pdfs:
            missing_origin.append(chunk_dir.name)
            continue

        assets_dir = chunk_dir / "assets"
        assets_dir.mkdir(exist_ok=True)

        doc = fitz.open(str(origin_pdfs[0]))
        try:
            expected_pages = end_page - start_page + 1
            if len(doc) != expected_pages:
                bad_chunks.append((chunk_dir.name, len(doc), expected_pages))

            for local_idx in range(len(doc)):
                page_no = start_page + local_idx
                out = assets_dir / f"source_page_{page_no:03d}_preview.png"

                if out.exists():
                    skipped += 1
                    continue

                pix = doc[local_idx].get_pixmap(
                    matrix=fitz.Matrix(scale, scale),
                    alpha=False,
                )
                pix.save(str(out))
                created += 1

                if created % 20 == 0:
                    print(f"created {created} previews...", flush=True)
        finally:
            doc.close()

    print("chunks:", len(chunk_dirs))
    print("created:", created)
    print("skipped:", skipped)
    print("missing_origin:", missing_origin)
    print("bad_chunks:", bad_chunks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--text-study-root",
        default="exports/text_study",
        type=Path,
    )
    parser.add_argument(
        "--mineru-root",
        default="data/mineru_api_output",
        type=Path,
    )
    parser.add_argument(
        "--scale",
        default=1.0,
        type=float,
    )
    args = parser.parse_args()

    render_source_previews(
        text_study_root=args.text_study_root,
        mineru_root=args.mineru_root,
        scale=args.scale,
    )


if __name__ == "__main__":
    main()
