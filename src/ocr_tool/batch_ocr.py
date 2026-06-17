"""Helpers for selecting pages for batch OCR."""

from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys

from ocr_tool.models import Page

DEFAULT_MAX_PAGES_PER_BATCH = 1
MAX_PAGES_PER_BATCH = 20
DEFAULT_OCR_WORKER_TIMEOUT_SECONDS = 300
BATCH_OCR_MODE_MISSING_RAW = "unchecked/missing raw OCR pages only"
BATCH_OCR_MODE_ALL = "all pages"
BATCH_OCR_MODE_RANGE = "selected page range"
BATCH_OCR_MODES = [
    BATCH_OCR_MODE_MISSING_RAW,
    BATCH_OCR_MODE_ALL,
    BATCH_OCR_MODE_RANGE,
]


@dataclass
class BatchOCRFailure:
    page_number: int
    error: str
    returncode: int | None = None


@dataclass
class BatchOCRRunResult:
    successful_pages: list[Page]
    failures: list[BatchOCRFailure]

    @property
    def success_count(self) -> int:
        return len(self.successful_pages)


@dataclass
class BatchPageResult:
    page_number: int
    success: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    timed_out: bool = False


def select_pages_for_batch_ocr(
    pages: list[Page],
    mode: str,
    start_page: int | None,
    end_page: int | None,
    overwrite_existing_raw_ocr: bool,
    raw_ocr_exists_func: Callable[[str, int], bool],
) -> tuple[list[Page], list[Page]]:
    """Return pages to run and pages skipped because raw OCR already exists."""
    candidate_pages = _candidate_pages(pages, mode, start_page, end_page)
    pages_to_run = []
    pages_to_skip = []

    for page in candidate_pages:
        has_raw_ocr = raw_ocr_exists_func(page.document_id, page.page_number)
        if has_raw_ocr and not overwrite_existing_raw_ocr:
            pages_to_skip.append(page)
            continue
        pages_to_run.append(page)

    return pages_to_run, pages_to_skip


def limit_pages_for_batch_ocr(
    pages: list[Page],
    max_pages: int,
) -> tuple[list[Page], int]:
    """Return first max_pages pages and original selected count."""
    selected_count = len(pages)
    return pages[:max_pages], selected_count


def run_batch_ocr_pages(
    pages: list[Page],
    page_ocr_func: Callable[[str, int, object, str, bool], BatchPageResult],
    lang: str = "japan",
    lightweight: bool = True,
    progress_callback: Callable[[int, int, Page], None] | None = None,
) -> BatchOCRRunResult:
    """Run batch OCR sequentially through isolated one-page workers."""
    successful_pages = []
    failures = []
    total_pages = len(pages)

    for index, page in enumerate(pages, start=1):
        if progress_callback is not None:
            progress_callback(index, total_pages, page)
        try:
            result = page_ocr_func(
                page.document_id,
                page.page_number,
                page.image_path,
                lang,
                lightweight,
            )
        except Exception as error:
            failures.append(
                BatchOCRFailure(
                    page_number=page.page_number,
                    error=f"OCR worker launch failed: {error}",
                )
            )
            continue
        if result.success:
            successful_pages.append(page)
            continue
        failures.append(
            BatchOCRFailure(
                page_number=page.page_number,
                error=_page_result_error(result),
                returncode=result.returncode,
            )
        )

    return BatchOCRRunResult(successful_pages=successful_pages, failures=failures)


def run_page_ocr_subprocess(
    document_id: str,
    page_number: int,
    image_path: Path | str,
    lang: str = "japan",
    lightweight: bool = True,
    timeout_seconds: int = DEFAULT_OCR_WORKER_TIMEOUT_SECONDS,
) -> BatchPageResult:
    """Run one page OCR in an isolated Python subprocess."""
    command = build_ocr_worker_command(
        document_id,
        page_number,
        image_path,
        lang,
        lightweight=lightweight,
    )
    env = _subprocess_env()
    try:
        completed_process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired as error:
        stderr = (
            f"OCR worker timed out after {timeout_seconds} seconds"
            + (f": {error.stderr}" if error.stderr else "")
        )
        return BatchPageResult(
            page_number=page_number,
            success=False,
            stdout=str(error.stdout or ""),
            stderr=stderr,
            returncode=None,
            timed_out=True,
        )
    except Exception as error:
        return BatchPageResult(
            page_number=page_number,
            success=False,
            stderr=f"OCR worker launch failed: {error}",
            returncode=None,
        )

    if completed_process.returncode == 0:
        return BatchPageResult(
            page_number=page_number,
            success=True,
            stdout=completed_process.stdout,
            stderr=completed_process.stderr,
            returncode=completed_process.returncode,
        )

    stderr = completed_process.stderr.strip()
    if completed_process.returncode < 0:
        signal_number = abs(completed_process.returncode)
        stderr = (
            f"OCR worker killed by signal {signal_number}."
            + (f" stderr: {stderr}" if stderr else "")
        )

    return BatchPageResult(
        page_number=page_number,
        success=False,
        stdout=completed_process.stdout,
        stderr=stderr,
        returncode=completed_process.returncode,
    )


def build_ocr_worker_command(
    document_id: str,
    page_number: int,
    image_path: Path | str,
    lang: str = "japan",
    lightweight: bool = True,
) -> list[str]:
    """Build one-page OCR worker command."""
    command = [
        sys.executable,
        "-m",
        "ocr_tool.ocr_worker",
        "--document-id",
        document_id,
        "--page-number",
        str(page_number),
        "--image-path",
        str(image_path),
        "--lang",
        lang,
    ]
    if lightweight:
        command.append("--lightweight")
    else:
        command.append("--no-lightweight")
    return command


def _page_result_error(result: BatchPageResult) -> str:
    if result.timed_out:
        return result.stderr
    if result.stderr.strip():
        return result.stderr.strip()
    if result.returncode is not None:
        return f"OCR worker failed with return code {result.returncode}"
    return "OCR worker failed"


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    src_dir = str(Path(__file__).resolve().parents[1])
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        env["PYTHONPATH"] = os.pathsep.join([src_dir, existing_pythonpath])
    else:
        env["PYTHONPATH"] = src_dir
    return env


def _candidate_pages(
    pages: list[Page],
    mode: str,
    start_page: int | None,
    end_page: int | None,
) -> list[Page]:
    ordered_pages = sorted(pages, key=lambda page: page.page_number)
    if mode == BATCH_OCR_MODE_RANGE:
        if start_page is None or end_page is None or start_page > end_page:
            return []
        return [
            page
            for page in ordered_pages
            if start_page <= page.page_number <= end_page
        ]
    return ordered_pages
