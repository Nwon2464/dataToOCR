"""OCR pipeline using PaddleOCR."""

import inspect
from pathlib import Path

from ocr_tool.storage.files import save_raw_ocr_text

MISSING_PADDLEOCR_MESSAGE = (
    "PaddleOCR is not installed. Install project dependencies before running OCR."
)


def run_paddle_ocr(
    document_id: str,
    page_number: int,
    image_path: Path | str,
    lang: str = "japan",
    lightweight: bool = True,
) -> str:
    """Run PaddleOCR for one extracted page image and save raw OCR text.

    Behavior:
    - Read one extracted page image from `image_path`.
    - Run PaddleOCR using `lang`, with Japanese OCR as the default.
    - Extract recognized text lines from PaddleOCR results.
    - Flatten recognized lines into one page-level text string.
    - Save raw OCR text under `data/ocr_raw/{document_id}/page_0001.txt`,
      `data/ocr_raw/{document_id}/page_0002.txt`, and so on.
    - Return the recognized text string.

    Parameters:
        document_id: Stable document identifier used for raw OCR output paths.
        page_number: 1-based page number.
        image_path: Path to an extracted page image.
        lang: PaddleOCR language code. Defaults to `japan`.

    Returns:
        Recognized page-level OCR text.

    Constraints:
        This function must not write corrected text, update SQLite, modify page
        images, run Tesseract comparison, contain UI logic, or perform search.
    """
    validate_page_number(page_number)
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Page image not found: {image_path}")

    engine = create_paddle_ocr_engine(lang, lightweight=lightweight)
    return run_ocr_with_engine(engine, document_id, page_number, image_path)


def create_paddle_ocr_engine(lang: str = "japan", lightweight: bool = True) -> object:
    """Create a PaddleOCR engine lazily."""
    try:
        from paddleocr import PaddleOCR
    except ImportError as error:
        raise RuntimeError(MISSING_PADDLEOCR_MESSAGE) from error

    options = build_paddle_ocr_options(PaddleOCR, lang, lightweight)
    try:
        return PaddleOCR(**options)
    except TypeError:
        if options == {"lang": lang}:
            raise
        return PaddleOCR(lang=lang)


def build_paddle_ocr_options(
    paddle_ocr_class: object,
    lang: str = "japan",
    lightweight: bool = True,
) -> dict[str, object]:
    """Build constructor options without forcing unsupported kwargs."""
    options: dict[str, object] = {"lang": lang}
    if not lightweight:
        return options

    lightweight_options = {
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
    }

    try:
        signature = inspect.signature(paddle_ocr_class)
    except (TypeError, ValueError):
        options.update(lightweight_options)
        return options

    parameters = signature.parameters
    accepts_any_keyword = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    if accepts_any_keyword:
        options.update(lightweight_options)
        return options

    for name, value in lightweight_options.items():
        if name in parameters:
            options[name] = value
    return options


def run_ocr_with_engine(
    ocr_engine: object,
    document_id: str,
    page_number: int,
    image_path: Path | str,
) -> str:
    """Run OCR with an existing engine and save raw OCR text."""
    validate_page_number(page_number)
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Page image not found: {image_path}")

    result = ocr_engine.ocr(str(image_path))
    lines = extract_ordered_text_lines_from_paddle_result(result)
    text = flatten_ocr_lines(lines)
    save_raw_ocr_text(document_id, page_number, text)
    return text


def extract_ordered_text_lines_from_paddle_result(result: object) -> list[str]:
    """Extract OCR text with a simple main-text-before-side-note order.

    PaddleOCR v3 / PaddleX may return `rec_texts` with `rec_boxes`. For scanned
    textbook pages, raw detection order can mix main body and margin notes, so
    this applies a small reading-order heuristic before falling back.
    """
    source = _find_rec_texts_and_boxes(result)
    if source is None:
        return extract_text_lines_from_paddle_result(result)

    rec_texts, rec_boxes = source
    try:
        rec_texts_count = len(rec_texts)
        rec_boxes_count = len(rec_boxes)
    except TypeError:
        return extract_text_lines_from_paddle_result(result)

    if rec_texts_count != rec_boxes_count:
        return extract_text_lines_from_paddle_result(result)

    parsed_lines = []
    for text, box in zip(rec_texts, rec_boxes):
        if not isinstance(text, str):
            continue
        stripped_text = text.strip()
        if not stripped_text:
            continue

        parsed_box = normalize_box(box)
        if parsed_box is None:
            continue

        x_min, y_min, x_max, _ = parsed_box
        parsed_lines.append((stripped_text, x_min, y_min, x_max))

    if not parsed_lines:
        return extract_text_lines_from_paddle_result(result)

    page_width = max(x_max for _, _, _, x_max in parsed_lines)
    side_note_threshold = page_width * 0.72
    main_lines = []
    side_note_lines = []

    for text, x_min, y_min, _ in parsed_lines:
        item = (y_min, x_min, text)
        if x_min >= side_note_threshold:
            side_note_lines.append(item)
        else:
            main_lines.append(item)

    ordered_main = [text for _, _, text in sorted(main_lines)]
    ordered_side_notes = [text for _, _, text in sorted(side_note_lines)]
    if not ordered_side_notes:
        return ordered_main

    return [*ordered_main, "", "[SIDE NOTE]", *ordered_side_notes]


def extract_text_lines_from_paddle_result(result: object) -> list[str]:
    """Extract text strings from common PaddleOCR nested result shapes.

    PaddleOCR v3 / PaddleX may return OCRResult objects with `rec_texts`.
    Older versions return nested box/text structures. This parser is defensive
    and may need adjustment after real sample OCR verification.
    """
    lines: list[str] = []

    def add_rec_texts(node: object) -> bool:
        try:
            rec_texts = node["rec_texts"]
        except (KeyError, TypeError, AttributeError):
            get = getattr(node, "get", None)
            if get is None:
                return False
            rec_texts = get("rec_texts")

        if not isinstance(rec_texts, list):
            return False

        for item in rec_texts:
            if not isinstance(item, str):
                continue
            text = item.strip()
            if text:
                lines.append(text)
        return True

    def visit(node: object) -> None:
        if add_rec_texts(node):
            return

        if not isinstance(node, (list, tuple)):
            return

        if (
            len(node) >= 2
            and isinstance(node[0], str)
            and isinstance(node[1], (int, float))
        ):
            text = node[0].strip()
            if text:
                lines.append(text)
            return

        for child in node:
            visit(child)

    visit(result)
    return lines


def _find_rec_texts_and_boxes(result: object) -> tuple[object, object] | None:
    def visit(node: object) -> tuple[object, object] | None:
        rec_texts = _get_result_value(node, "rec_texts")
        rec_boxes = _get_result_value(node, "rec_boxes")
        if rec_texts is not None or rec_boxes is not None:
            if rec_texts is not None and _has_sequence_access(rec_boxes):
                return rec_texts, rec_boxes
            return None

        if isinstance(node, (list, tuple)):
            for child in node:
                found = visit(child)
                if found is not None:
                    return found

        return None

    return visit(result)


def _has_sequence_access(value: object) -> bool:
    try:
        len(value)
        value[0]
    except (TypeError, IndexError, KeyError):
        return False
    return True


def _get_result_value(node: object, key: str) -> object:
    try:
        return node[key]
    except (KeyError, TypeError, AttributeError):
        get = getattr(node, "get", None)
        if get is None:
            return None
        return get(key)


def normalize_box(box: object) -> tuple[float, float, float, float] | None:
    """Normalize list/tuple/ndarray-row-like OCR box coordinates."""
    try:
        if len(box) < 4:
            return None
        x_min = float(box[0])
        y_min = float(box[1])
        x_max = float(box[2])
        y_max = float(box[3])
    except (TypeError, ValueError, IndexError):
        return None

    return x_min, y_min, x_max, y_max


def flatten_ocr_lines(lines: list[str]) -> str:
    """Strip, drop empty lines, and join OCR text lines."""
    return "\n".join(line.strip() for line in lines if line.strip())


def validate_page_number(page_number: int) -> int:
    """Validate 1-based page number."""
    if page_number < 1:
        raise ValueError("page_number must be 1 or greater")
    return page_number
