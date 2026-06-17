from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import ocr_tool.batch_ocr as batch_ocr
from ocr_tool.batch_ocr import (
    BATCH_OCR_MODE_ALL,
    BATCH_OCR_MODE_MISSING_RAW,
    BATCH_OCR_MODE_RANGE,
    BatchPageResult,
    build_ocr_worker_command,
    limit_pages_for_batch_ocr,
    run_batch_ocr_pages,
    run_page_ocr_subprocess,
    select_pages_for_batch_ocr,
)
from ocr_tool.models import Page


def _pages() -> list[Page]:
    return [
        Page(
            id=f"doc123_page_{page_number:04d}",
            document_id="doc123",
            page_number=page_number,
            image_path=Path(f"data/pages/doc123/page_{page_number:04d}.png"),
        )
        for page_number in [1, 2, 3, 4]
    ]


def _raw_exists(existing_pages: set[int]):
    return lambda _document_id, page_number: page_number in existing_pages


def test_missing_raw_only_selects_pages_without_raw():
    pages_to_run, pages_to_skip = select_pages_for_batch_ocr(
        _pages(),
        BATCH_OCR_MODE_MISSING_RAW,
        None,
        None,
        False,
        _raw_exists({1, 3}),
    )

    assert [page.page_number for page in pages_to_run] == [2, 4]
    assert [page.page_number for page in pages_to_skip] == [1, 3]


def test_all_pages_with_overwrite_false_skips_existing_raw():
    pages_to_run, pages_to_skip = select_pages_for_batch_ocr(
        _pages(),
        BATCH_OCR_MODE_ALL,
        None,
        None,
        False,
        _raw_exists({2, 4}),
    )

    assert [page.page_number for page in pages_to_run] == [1, 3]
    assert [page.page_number for page in pages_to_skip] == [2, 4]


def test_all_pages_with_overwrite_true_includes_all():
    pages_to_run, pages_to_skip = select_pages_for_batch_ocr(
        _pages(),
        BATCH_OCR_MODE_ALL,
        None,
        None,
        True,
        _raw_exists({2, 4}),
    )

    assert [page.page_number for page in pages_to_run] == [1, 2, 3, 4]
    assert pages_to_skip == []


def test_selected_range_respects_start_and_end():
    pages_to_run, pages_to_skip = select_pages_for_batch_ocr(
        _pages(),
        BATCH_OCR_MODE_RANGE,
        2,
        3,
        False,
        _raw_exists({3}),
    )

    assert [page.page_number for page in pages_to_run] == [2]
    assert [page.page_number for page in pages_to_skip] == [3]


def test_invalid_range_returns_empty_lists():
    pages_to_run, pages_to_skip = select_pages_for_batch_ocr(
        _pages(),
        BATCH_OCR_MODE_RANGE,
        4,
        2,
        False,
        _raw_exists(set()),
    )

    assert pages_to_run == []
    assert pages_to_skip == []


def test_max_page_limit_truncates_selected_pages():
    limited_pages, selected_count = limit_pages_for_batch_ocr(_pages(), 2)

    assert selected_count == 4
    assert [page.page_number for page in limited_pages] == [1, 2]


def test_worker_command_uses_sys_executable():
    command = build_ocr_worker_command(
        "doc123",
        2,
        Path("data/pages/doc123/page_0002.png"),
        "japan",
    )

    assert command == [
        sys.executable,
        "-m",
        "ocr_tool.ocr_worker",
        "--document-id",
        "doc123",
        "--page-number",
        "2",
        "--image-path",
        "data/pages/doc123/page_0002.png",
        "--lang",
        "japan",
        "--lightweight",
    ]


def test_subprocess_success_returns_success(monkeypatch):
    calls = []

    def fake_run(command, capture_output, text, timeout, env):
        calls.append((command, capture_output, text, timeout, env))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(batch_ocr.subprocess, "run", fake_run)

    result = run_page_ocr_subprocess("doc123", 1, "image.png", timeout_seconds=10)

    assert result.success is True
    assert result.returncode == 0
    assert calls[0][0][0] == sys.executable
    assert calls[0][1:4] == (True, True, 10)


def test_subprocess_non_zero_returns_failure(monkeypatch):
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="bad page")

    monkeypatch.setattr(batch_ocr.subprocess, "run", fake_run)

    result = run_page_ocr_subprocess("doc123", 1, "image.png")

    assert result.success is False
    assert result.returncode == 1
    assert result.stderr == "bad page"


def test_subprocess_timeout_returns_failure(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["python"],
            timeout=3,
            output="partial",
            stderr="still running",
        )

    monkeypatch.setattr(batch_ocr.subprocess, "run", fake_run)

    result = run_page_ocr_subprocess(
        "doc123",
        1,
        "image.png",
        timeout_seconds=3,
    )

    assert result.success is False
    assert result.timed_out is True
    assert "timed out after 3 seconds" in result.stderr


def test_subprocess_negative_returncode_reports_killed_process(monkeypatch):
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=-9, stdout="", stderr="")

    monkeypatch.setattr(batch_ocr.subprocess, "run", fake_run)

    result = run_page_ocr_subprocess("doc123", 1, "image.png")

    assert result.success is False
    assert result.returncode == -9
    assert result.stderr == "OCR worker killed by signal 9."


def test_subprocess_command_can_disable_lightweight():
    command = build_ocr_worker_command("doc123", 1, "image.png", lightweight=False)

    assert command[-1] == "--no-lightweight"


def test_batch_execution_page_failure_does_not_stop_remaining_pages():
    def run_page(document_id, page_number, image_path, lang, lightweight):
        if page_number == 2:
            return BatchPageResult(
                page_number=page_number,
                success=False,
                stderr="OCR page failed",
                returncode=1,
            )
        return BatchPageResult(page_number=page_number, success=True)

    result = run_batch_ocr_pages(
        _pages()[:3],
        run_page,
    )

    assert [page.page_number for page in result.successful_pages] == [1, 3]
    assert len(result.failures) == 1
    assert result.failures[0].page_number == 2
    assert result.failures[0].error == "OCR page failed"
