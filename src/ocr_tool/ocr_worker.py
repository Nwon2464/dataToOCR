"""One-page OCR worker entrypoint for subprocess batch OCR."""

import argparse
from pathlib import Path
import sys

from ocr_tool.pipeline.run_ocr import run_paddle_ocr


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OCR for one page.")
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--page-number", required=True, type=int)
    parser.add_argument("--image-path", required=True)
    parser.add_argument("--lang", default="japan")
    parser.add_argument("--lightweight", dest="lightweight", action="store_true")
    parser.add_argument("--no-lightweight", dest="lightweight", action="store_false")
    parser.set_defaults(lightweight=True)
    args = parser.parse_args()

    try:
        run_paddle_ocr(
            document_id=args.document_id,
            page_number=args.page_number,
            image_path=Path(args.image_path),
            lang=args.lang,
            lightweight=args.lightweight,
        )
    except Exception as error:
        print(f"OCR worker failed: {error}", file=sys.stderr)
        return 1

    print(f"OCR worker completed page {args.page_number}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
