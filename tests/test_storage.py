import importlib
from pathlib import Path

import pytest

import ocr_tool.config as config
import ocr_tool.storage.files as files
from ocr_tool.config import CORRECTED_DIR, INPUT_DIR, OCR_RAW_DIR, PAGES_DIR
from ocr_tool.models import DOCUMENT_STATUS_IMPORTED, PAGE_STATUS_UNCHECKED, Document, Page
from ocr_tool.storage.files import (
    build_page_record,
    build_stored_input_filename,
    get_corrected_text_path,
    get_input_path,
    get_page_image_path,
    get_raw_ocr_text_path,
    load_corrected_text,
    load_raw_ocr_text,
    raw_ocr_exists,
    read_text,
    save_corrected_text,
    save_page_image,
    save_raw_ocr_text,
    save_uploaded_file,
    sanitize_filename,
    save_text,
)


def test_sanitize_filename_removes_directory_components():
    assert sanitize_filename("../sample.pdf") == "sample.pdf"
    assert sanitize_filename("nested\\sample.pdf") == "sample.pdf"


def test_sanitize_filename_preserves_common_safe_characters():
    assert sanitize_filename("財務 会計.pdf") == "財務 会計.pdf"
    assert sanitize_filename("chapter:1?.pdf") == "chapter_1_.pdf"


def test_sanitize_filename_falls_back_when_empty():
    assert sanitize_filename("") == "uploaded_file"
    assert sanitize_filename("../") == "uploaded_file"


def test_build_stored_input_filename_prefixes_sanitized_name():
    assert (
        build_stored_input_filename("abc123", "財務会計.pdf")
        == "abc123_財務会計.pdf"
    )


def test_path_builders_return_expected_shapes():
    assert get_input_path("abc123_source.pdf") == INPUT_DIR / "abc123_source.pdf"
    assert get_page_image_path("abc123", 1) == PAGES_DIR / "abc123" / "page_0001.png"
    assert (
        get_raw_ocr_text_path("abc123", 12)
        == OCR_RAW_DIR / "abc123" / "page_0012.txt"
    )
    assert (
        get_corrected_text_path("abc123", 12)
        == CORRECTED_DIR / "abc123" / "page_0012.txt"
    )


def test_page_image_extension_is_normalized():
    assert get_page_image_path("abc123", 2, "jpg") == (
        PAGES_DIR / "abc123" / "page_0002.jpg"
    )
    assert get_page_image_path("abc123", 2, ".jpeg") == (
        PAGES_DIR / "abc123" / "page_0002.jpeg"
    )


@pytest.mark.parametrize(
    "path_builder",
    [get_page_image_path, get_raw_ocr_text_path, get_corrected_text_path],
)
def test_page_number_must_be_one_based(path_builder):
    with pytest.raises(ValueError):
        path_builder("abc123", 0)


def test_save_text_and_read_text_roundtrip(tmp_path):
    path = Path(tmp_path) / "nested" / "page_0001.txt"

    save_text(path, "財務会計\nOCR text")

    assert read_text(path) == "財務会計\nOCR text"


def test_save_uploaded_file_returns_document_and_saves_bytes(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"

    monkeypatch.setattr(files, "INPUT_DIR", input_dir)
    monkeypatch.setattr(files, "OCR_RAW_DIR", tmp_path / "ocr_raw")
    monkeypatch.setattr(files, "CORRECTED_DIR", tmp_path / "corrected")
    monkeypatch.setattr(files, "generate_document_id", lambda: "abc123")

    document = save_uploaded_file("../chapter:1?.pdf", b"%PDF bytes")

    assert isinstance(document, Document)
    assert document.id == "abc123"
    assert document.original_filename == "chapter_1_.pdf"
    assert document.stored_filename == "abc123_chapter_1_.pdf"
    assert document.stored_filename.startswith(f"{document.id}_")
    assert document.input_path == input_dir / "abc123_chapter_1_.pdf"
    assert document.status == DOCUMENT_STATUS_IMPORTED
    assert document.input_path.read_bytes() == b"%PDF bytes"
    assert not (tmp_path / "ocr_raw").exists()
    assert not (tmp_path / "corrected").exists()


def test_save_page_image_writes_bytes_to_expected_path(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "PAGES_DIR", tmp_path / "pages")
    monkeypatch.setattr(files, "OCR_RAW_DIR", tmp_path / "ocr_raw")
    monkeypatch.setattr(files, "CORRECTED_DIR", tmp_path / "corrected")

    path = save_page_image("doc123", 3, b"image bytes")

    assert path == tmp_path / "pages" / "doc123" / "page_0003.png"
    assert path.read_bytes() == b"image bytes"
    assert not (tmp_path / "ocr_raw").exists()
    assert not (tmp_path / "corrected").exists()


def test_save_page_image_normalizes_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "PAGES_DIR", tmp_path / "pages")

    path = save_page_image("doc123", 4, b"jpg bytes", "jpg")

    assert path == tmp_path / "pages" / "doc123" / "page_0004.jpg"
    assert path.read_bytes() == b"jpg bytes"


def test_save_page_image_rejects_invalid_page_number(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "PAGES_DIR", tmp_path / "pages")

    with pytest.raises(ValueError):
        save_page_image("doc123", 0, b"image bytes")

    assert not (tmp_path / "pages").exists()


def test_save_and_load_raw_ocr_text_only(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "OCR_RAW_DIR", tmp_path / "ocr_raw")
    monkeypatch.setattr(files, "CORRECTED_DIR", tmp_path / "corrected")

    path = save_raw_ocr_text("doc123", 1, "raw OCR")

    assert path == tmp_path / "ocr_raw" / "doc123" / "page_0001.txt"
    assert load_raw_ocr_text("doc123", 1) == "raw OCR"
    assert not (tmp_path / "corrected").exists()


def test_raw_ocr_exists_requires_non_empty_text(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "OCR_RAW_DIR", tmp_path / "ocr_raw")

    assert raw_ocr_exists("doc123", 1) is False

    save_raw_ocr_text("doc123", 1, "   \n")
    assert raw_ocr_exists("doc123", 1) is False

    save_raw_ocr_text("doc123", 1, "raw OCR")
    assert raw_ocr_exists("doc123", 1) is True


def test_save_and_load_corrected_text_only(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "OCR_RAW_DIR", tmp_path / "ocr_raw")
    monkeypatch.setattr(files, "CORRECTED_DIR", tmp_path / "corrected")

    path = save_corrected_text("doc123", 1, "corrected text")

    assert path == tmp_path / "corrected" / "doc123" / "page_0001.txt"
    assert load_corrected_text("doc123", 1) == "corrected text"
    assert not (tmp_path / "ocr_raw").exists()


def test_raw_ocr_and_corrected_text_paths_are_separate(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "OCR_RAW_DIR", tmp_path / "ocr_raw")
    monkeypatch.setattr(files, "CORRECTED_DIR", tmp_path / "corrected")

    raw_path = save_raw_ocr_text("doc123", 2, "raw")
    corrected_path = save_corrected_text("doc123", 2, "corrected")

    assert raw_path != corrected_path
    assert raw_path.read_text(encoding="utf-8") == "raw"
    assert corrected_path.read_text(encoding="utf-8") == "corrected"


def test_build_page_record_returns_unchecked_page(tmp_path):
    image_path = tmp_path / "pages" / "doc123" / "page_0001.png"

    page = build_page_record(
        "doc123",
        1,
        image_path,
        raw_ocr_text="raw",
        corrected_text="corrected",
    )

    assert isinstance(page, Page)
    assert page.id == "doc123_page_0001"
    assert page.document_id == "doc123"
    assert page.page_number == 1
    assert page.image_path == image_path
    assert page.raw_ocr_text == "raw"
    assert page.corrected_text == "corrected"
    assert page.status == PAGE_STATUS_UNCHECKED


def test_path_builders_do_not_create_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "PAGES_DIR", tmp_path / "pages")
    monkeypatch.setattr(files, "OCR_RAW_DIR", tmp_path / "ocr_raw")
    monkeypatch.setattr(files, "CORRECTED_DIR", tmp_path / "corrected")

    get_page_image_path("doc123", 1)
    get_raw_ocr_text_path("doc123", 1)
    get_corrected_text_path("doc123", 1)

    assert not (tmp_path / "pages").exists()
    assert not (tmp_path / "ocr_raw").exists()
    assert not (tmp_path / "corrected").exists()


def test_importing_files_module_does_not_create_directories(tmp_path, monkeypatch):
    original_paths = {
        "DATA_DIR": config.DATA_DIR,
        "INPUT_DIR": config.INPUT_DIR,
        "PAGES_DIR": config.PAGES_DIR,
        "OCR_RAW_DIR": config.OCR_RAW_DIR,
        "CORRECTED_DIR": config.CORRECTED_DIR,
    }

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "INPUT_DIR", tmp_path / "data" / "input")
    monkeypatch.setattr(config, "PAGES_DIR", tmp_path / "data" / "pages")
    monkeypatch.setattr(config, "OCR_RAW_DIR", tmp_path / "data" / "ocr_raw")
    monkeypatch.setattr(config, "CORRECTED_DIR", tmp_path / "data" / "corrected")

    importlib.reload(files)

    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "data" / "input").exists()
    assert not (tmp_path / "data" / "pages").exists()
    assert not (tmp_path / "data" / "ocr_raw").exists()
    assert not (tmp_path / "data" / "corrected").exists()

    for name, value in original_paths.items():
        setattr(config, name, value)
    importlib.reload(files)
