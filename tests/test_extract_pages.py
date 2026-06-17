import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import ocr_tool.pipeline.extract_pages as extract_pages
from ocr_tool.models import PAGE_STATUS_UNCHECKED
from ocr_tool.pipeline.extract_pages import (
    extract_pages_from_pdf,
    normalize_image_format,
    validate_dpi,
)


def test_normalize_image_format_accepts_supported_formats():
    assert normalize_image_format("png") == "png"
    assert normalize_image_format(".PNG") == "png"
    assert normalize_image_format("jpeg") == "jpeg"


def test_normalize_image_format_rejects_unsupported_format():
    with pytest.raises(ValueError):
        normalize_image_format("gif")


def test_validate_dpi_accepts_valid_dpi():
    assert validate_dpi(300) == 300


def test_validate_dpi_rejects_too_low_dpi():
    with pytest.raises(ValueError):
        validate_dpi(71)


def test_validate_dpi_rejects_too_high_dpi():
    with pytest.raises(ValueError):
        validate_dpi(601)


def test_extract_pages_from_pdf_validates_image_format_before_rendering():
    with pytest.raises(ValueError):
        extract_pages_from_pdf("doc123", Path("missing.pdf"), image_format="gif")


def test_extract_pages_from_pdf_validates_dpi_before_rendering():
    with pytest.raises(ValueError):
        extract_pages_from_pdf("doc123", Path("missing.pdf"), dpi=601)


def test_extract_pages_from_pdf_raises_file_not_found_after_validation():
    with pytest.raises(FileNotFoundError):
        extract_pages_from_pdf("doc123", Path("missing.pdf"))


def test_extract_pages_from_pdf_saves_pages_and_returns_unchecked_records(
    tmp_path, monkeypatch
):
    pdf_path = tmp_path / "input.pdf"
    pdf_path.write_bytes(b"%PDF")
    saved_calls = []

    class FakePixmap:
        def __init__(self, page_number):
            self.page_number = page_number

        def tobytes(self, output):
            return f"page-{self.page_number}-{output}".encode()

    class FakePage:
        def __init__(self, page_number):
            self.page_number = page_number

        def get_pixmap(self, dpi, alpha):
            assert dpi == 300
            assert alpha is False
            return FakePixmap(self.page_number)

    class FakeDocument:
        def __enter__(self):
            return [FakePage(1), FakePage(2)]

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_open(path):
        assert path == str(pdf_path)
        return FakeDocument()

    def fake_save_page_image(document_id, page_number, image_bytes, extension):
        saved_calls.append((document_id, page_number, image_bytes, extension))
        return tmp_path / "pages" / document_id / f"page_{page_number:04d}{extension}"

    monkeypatch.setitem(sys.modules, "fitz", SimpleNamespace(open=fake_open))
    monkeypatch.setattr(extract_pages, "save_page_image", fake_save_page_image)

    pages = extract_pages_from_pdf("doc123", pdf_path)

    assert saved_calls == [
        ("doc123", 1, b"page-1-png", ".png"),
        ("doc123", 2, b"page-2-png", ".png"),
    ]
    assert [page.page_number for page in pages] == [1, 2]
    assert [page.status for page in pages] == [
        PAGE_STATUS_UNCHECKED,
        PAGE_STATUS_UNCHECKED,
    ]
    assert [page.raw_ocr_text for page in pages] == ["", ""]
    assert [page.corrected_text for page in pages] == ["", ""]


def test_extract_pages_from_pdf_returns_empty_list_for_zero_page_pdf(
    tmp_path, monkeypatch
):
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(b"%PDF")

    class FakeDocument:
        def __enter__(self):
            return []

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setitem(
        sys.modules,
        "fitz",
        SimpleNamespace(open=lambda path: FakeDocument()),
    )

    assert extract_pages_from_pdf("doc123", pdf_path) == []
