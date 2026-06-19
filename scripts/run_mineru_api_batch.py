from __future__ import annotations

import argparse
import json
import os
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.common.api_paths import (  # noqa: E402
    ensure_chunk_dirs,
    get_chunks_dir,
    get_mineru_api_chunk_dir,
)

DEFAULT_BASE_URL = "https://mineru.net"
DEFAULT_MODEL_VERSION = "vlm"
DEFAULT_LANGUAGE = "en"
TASK_METADATA_FILENAME = "api_task.json"
STATUS_METADATA_FILENAME = "api_status.json"
RAW_ZIP_FILENAME = "raw.zip"
DONE_STATE = "done"
FAILED_STATE = "failed"
ACTIVE_STATES = {"waiting-file", "pending", "running", "converting"}


def utc_now() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write a JSON object to disk with stable formatting."""
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_dotenv_value(key: str, dotenv_path: Path | None = None) -> str | None:
    """Read one value from a simple .env file without requiring export."""
    path = dotenv_path if dotenv_path is not None else PROJECT_ROOT / ".env"
    if not path.is_file():
        return None

    prefix = f"{key}="
    export_prefix = f"export {key}="
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(export_prefix):
            value = line[len(export_prefix) :]
        elif line.startswith(prefix):
            value = line[len(prefix) :]
        else:
            continue
        return value.strip().strip('"').strip("'") or None
    return None


def resolve_token(token_arg: str | None = None) -> str:
    """Resolve MinerU API token from CLI, environment, or .env."""
    token = token_arg or os.getenv("MINERU_API_TOKEN") or read_dotenv_value("MINERU_API_TOKEN")
    if not token:
        raise RuntimeError("Set MINERU_API_TOKEN in .env, export it, or pass --token.")
    return token


def auth_headers(token: str) -> dict[str, str]:
    """Return MinerU API authorization headers."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "*/*",
    }


def api_url(base_url: str, path: str) -> str:
    """Build an absolute MinerU API URL."""
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def ensure_api_response(response: requests.Response) -> dict[str, Any]:
    """Validate MinerU JSON response and return decoded payload."""
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"MinerU API error: {payload.get('code')} {payload.get('msg')}")
    return payload


def resolve_chunk_pdf(chunk_pdf: Path) -> Path:
    """Resolve a chunk PDF path against data/chunks when only filename is given."""
    if chunk_pdf.is_absolute():
        return chunk_pdf
    if chunk_pdf.parent != Path("."):
        return chunk_pdf
    return get_chunks_dir() / chunk_pdf


def chunk_id_from_pdf(chunk_pdf: Path) -> str:
    """Return chunk ID from a chunk PDF filename."""
    return chunk_pdf.stem


def resolve_chunk_id(value: str) -> str:
    """Resolve chunk ID from chunk ID, PDF filename, or path."""
    path = Path(value)
    if path.suffix.lower() == ".pdf":
        return path.stem
    return value


def task_metadata_path(chunk_id: str) -> Path:
    """Return task metadata path for a chunk."""
    return get_mineru_api_chunk_dir(chunk_id) / TASK_METADATA_FILENAME


def status_metadata_path(chunk_id: str) -> Path:
    """Return status metadata path for a chunk."""
    return get_mineru_api_chunk_dir(chunk_id) / STATUS_METADATA_FILENAME


def raw_zip_path(chunk_id: str) -> Path:
    """Return raw result zip path for a chunk."""
    return get_mineru_api_chunk_dir(chunk_id) / RAW_ZIP_FILENAME


def resolve_raw_zip(raw_zip: Path) -> Path:
    """Resolve a raw.zip path from explicit path or chunk ID."""
    if raw_zip.suffix.lower() == ".zip":
        if raw_zip.is_absolute() or raw_zip.parent != Path("."):
            return raw_zip
        direct_path = PROJECT_ROOT / raw_zip
        if direct_path.is_file():
            return direct_path
        matches = sorted((PROJECT_ROOT / "data" / "mineru_api_output").glob(f"*/{raw_zip.name}"))
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise RuntimeError(f"Multiple {raw_zip.name} files found; pass explicit path.")
        return PROJECT_ROOT / raw_zip
    return raw_zip_path(resolve_chunk_id(str(raw_zip)))


def safe_extract_raw_zip(raw_zip: Path, output_dir: Path | None = None) -> list[Path]:
    """Extract raw.zip safely into a chunk output directory."""
    resolved_zip = resolve_raw_zip(raw_zip)
    if not resolved_zip.is_file():
        raise FileNotFoundError(f"raw.zip not found: {resolved_zip}")

    destination = output_dir if output_dir is not None else resolved_zip.parent
    destination.mkdir(parents=True, exist_ok=True)
    destination_root = destination.resolve()
    extracted_paths: list[Path] = []

    with zipfile.ZipFile(resolved_zip) as archive:
        for member in archive.infolist():
            member_path = destination / member.filename
            resolved_member_path = member_path.resolve()
            if not resolved_member_path.is_relative_to(destination_root):
                raise RuntimeError(f"Unsafe zip member path: {member.filename}")
            archive.extract(member, destination)
            extracted_paths.append(member_path)

    return extracted_paths


def submit_chunk(
    chunk_pdf: Path,
    token: str,
    base_url: str = DEFAULT_BASE_URL,
    model_version: str = DEFAULT_MODEL_VERSION,
    language: str = DEFAULT_LANGUAGE,
    is_ocr: bool = True,
    enable_formula: bool = True,
    enable_table: bool = True,
    page_ranges: str | None = None,
    extra_formats: list[str] | None = None,
) -> dict[str, Any]:
    """Request upload URL, upload chunk PDF, and save batch metadata."""
    resolved_pdf = resolve_chunk_pdf(chunk_pdf)
    if not resolved_pdf.is_file():
        raise FileNotFoundError(f"Chunk PDF not found: {resolved_pdf}")

    chunk_id = chunk_id_from_pdf(resolved_pdf)
    paths = ensure_chunk_dirs(chunk_id)
    task_path = task_metadata_path(chunk_id)

    file_spec: dict[str, Any] = {
        "name": resolved_pdf.name,
        "data_id": chunk_id,
        "is_ocr": is_ocr,
    }
    if page_ranges:
        file_spec["page_ranges"] = page_ranges

    request_payload: dict[str, Any] = {
        "files": [file_spec],
        "model_version": model_version,
        "language": language,
        "enable_formula": enable_formula,
        "enable_table": enable_table,
    }
    if extra_formats:
        request_payload["extra_formats"] = extra_formats

    submit_response = requests.post(
        api_url(base_url, "/api/v4/file-urls/batch"),
        headers=auth_headers(token),
        json=request_payload,
        timeout=60,
    )
    submit_payload = ensure_api_response(submit_response)
    data = submit_payload["data"]
    file_urls = data.get("file_urls") or []
    if len(file_urls) != 1:
        raise RuntimeError(f"Expected exactly one upload URL, got {len(file_urls)}.")

    with resolved_pdf.open("rb") as pdf_file:
        upload_response = requests.put(file_urls[0], data=pdf_file, timeout=300)
    upload_response.raise_for_status()

    metadata = {
        "batch_id": data["batch_id"],
        "chunk_id": chunk_id,
        "chunk_pdf": str(resolved_pdf),
        "created_at": utc_now(),
        "model_version": model_version,
        "language": language,
        "output_dir": str(paths["mineru_api_chunk"]),
        "request": request_payload,
        "submit_trace_id": submit_payload.get("trace_id"),
        "upload_http_status": upload_response.status_code,
    }
    write_json(task_path, metadata)
    return metadata


def poll_batch_once(
    chunk_id: str,
    token: str,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """Poll MinerU batch status once and save response metadata."""
    task = read_json(task_metadata_path(chunk_id))
    batch_id = task["batch_id"]
    response = requests.get(
        api_url(base_url, f"/api/v4/extract-results/batch/{batch_id}"),
        headers=auth_headers(token),
        timeout=60,
    )
    payload = ensure_api_response(response)
    status = {
        "chunk_id": chunk_id,
        "polled_at": utc_now(),
        "response": payload,
    }
    write_json(status_metadata_path(chunk_id), status)
    return status


def get_extract_result(status: dict[str, Any], chunk_id: str) -> dict[str, Any]:
    """Return matching extract_result item from a batch status payload."""
    results = status["response"]["data"].get("extract_result") or []
    if not results:
        raise RuntimeError("No extract_result found in MinerU status response.")
    for result in results:
        if result.get("data_id") == chunk_id or Path(result.get("file_name", "")).stem == chunk_id:
            return result
    return results[0]


def wait_until_done(
    chunk_id: str,
    token: str,
    base_url: str = DEFAULT_BASE_URL,
    interval_seconds: int = 10,
    timeout_seconds: int = 3600,
) -> dict[str, Any]:
    """Poll MinerU batch status until done or failed."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        status = poll_batch_once(chunk_id, token=token, base_url=base_url)
        result = get_extract_result(status, chunk_id)
        state = result.get("state")
        print(f"{chunk_id} state={state}")
        if state == DONE_STATE:
            return status
        if state == FAILED_STATE:
            raise RuntimeError(f"MinerU task failed: {result.get('err_msg')}")
        if state not in ACTIVE_STATES:
            raise RuntimeError(f"Unexpected MinerU task state: {state}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for MinerU batch: {chunk_id}")
        time.sleep(interval_seconds)


def download_raw_zip(
    chunk_id: str,
    token: str,
    base_url: str = DEFAULT_BASE_URL,
) -> Path:
    """Download MinerU result zip for a completed chunk."""
    if not status_metadata_path(chunk_id).is_file():
        poll_batch_once(chunk_id, token=token, base_url=base_url)

    status = read_json(status_metadata_path(chunk_id))
    result = get_extract_result(status, chunk_id)
    if result.get("state") != DONE_STATE:
        raise RuntimeError(f"Chunk not done yet: {chunk_id} state={result.get('state')}")

    zip_url = result.get("full_zip_url")
    if not zip_url:
        raise RuntimeError(f"No full_zip_url found for chunk: {chunk_id}")

    ensure_chunk_dirs(chunk_id)
    output_path = raw_zip_path(chunk_id)
    with requests.get(zip_url, stream=True, timeout=600) as response:
        response.raise_for_status()
        with output_path.open("wb") as output_file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output_file.write(chunk)
    return output_path


def add_common_api_args(parser: argparse.ArgumentParser) -> None:
    """Add common MinerU API arguments to a subcommand parser."""
    parser.add_argument("--token", default=None, help="MinerU API token.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="MinerU API base URL.")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    if len(sys.argv) >= 2 and sys.argv[1].lower().endswith(".zip"):
        sys.argv.insert(1, "extract")

    parser = argparse.ArgumentParser(description="Run MinerU Web API batch workflow.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    submit_parser = subparsers.add_parser("submit", help="Submit one chunk PDF.")
    submit_parser.add_argument("chunk_pdf", type=Path, help="Chunk PDF filename or path.")
    submit_parser.add_argument("--model-version", default=DEFAULT_MODEL_VERSION)
    submit_parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    submit_parser.add_argument("--page-ranges", default=None)
    submit_parser.add_argument("--no-ocr", action="store_true")
    submit_parser.add_argument("--disable-formula", action="store_true")
    submit_parser.add_argument("--disable-table", action="store_true")
    submit_parser.add_argument("--extra-format", action="append", default=None, help="Add extra output format.")
    add_common_api_args(submit_parser)

    poll_parser = subparsers.add_parser("poll", help="Poll one chunk once.")
    poll_parser.add_argument("chunk", help="Chunk ID, PDF filename, or path.")
    add_common_api_args(poll_parser)

    wait_parser = subparsers.add_parser("wait", help="Poll until done.")
    wait_parser.add_argument("chunk", help="Chunk ID, PDF filename, or path.")
    wait_parser.add_argument("--interval-seconds", type=int, default=10)
    wait_parser.add_argument("--timeout-seconds", type=int, default=3600)
    add_common_api_args(wait_parser)

    download_parser = subparsers.add_parser("download", help="Download and extract raw.zip.")
    download_parser.add_argument("chunk", help="Chunk ID, PDF filename, or path.")
    download_parser.add_argument("--no-extract", action="store_true")
    add_common_api_args(download_parser)

    extract_parser = subparsers.add_parser("extract", help="Extract raw.zip manually.")
    extract_parser.add_argument("raw_zip", type=Path, help="raw.zip path or chunk ID.")
    extract_parser.add_argument("--output-dir", type=Path, default=None)

    run_parser = subparsers.add_parser("run", help="Submit, wait, download, and extract raw.zip.")
    run_parser.add_argument("chunk_pdf", type=Path, help="Chunk PDF filename or path.")
    run_parser.add_argument("--model-version", default=DEFAULT_MODEL_VERSION)
    run_parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    run_parser.add_argument("--page-ranges", default=None)
    run_parser.add_argument("--no-ocr", action="store_true")
    run_parser.add_argument("--disable-formula", action="store_true")
    run_parser.add_argument("--disable-table", action="store_true")
    run_parser.add_argument("--extra-format", action="append", default=None, help="Add extra output format.")
    run_parser.add_argument("--interval-seconds", type=int, default=10)
    run_parser.add_argument("--timeout-seconds", type=int, default=3600)
    run_parser.add_argument("--no-extract", action="store_true")
    add_common_api_args(run_parser)

    return parser.parse_args()


def main() -> None:
    """Run selected MinerU Web API command."""
    args = parse_args()
    token = None if args.command == "extract" else resolve_token(args.token)

    if args.command == "submit":
        assert token is not None
        metadata = submit_chunk(
            chunk_pdf=args.chunk_pdf,
            token=token,
            base_url=args.base_url,
            model_version=args.model_version,
            language=args.language,
            is_ocr=not args.no_ocr,
            enable_formula=not args.disable_formula,
            enable_table=not args.disable_table,
            page_ranges=args.page_ranges,
            extra_formats=args.extra_format,
        )
        print(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True))
        return

    if args.command == "poll":
        assert token is not None
        chunk_id = resolve_chunk_id(args.chunk)
        status = poll_batch_once(chunk_id, token=token, base_url=args.base_url)
        print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
        return

    if args.command == "wait":
        assert token is not None
        chunk_id = resolve_chunk_id(args.chunk)
        status = wait_until_done(
            chunk_id,
            token=token,
            base_url=args.base_url,
            interval_seconds=args.interval_seconds,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
        return

    if args.command == "download":
        assert token is not None
        chunk_id = resolve_chunk_id(args.chunk)
        output_path = download_raw_zip(chunk_id, token=token, base_url=args.base_url)
        if not args.no_extract:
            safe_extract_raw_zip(output_path)
        print(output_path)
        return

    if args.command == "extract":
        extracted_paths = safe_extract_raw_zip(args.raw_zip, output_dir=args.output_dir)
        for path in extracted_paths:
            print(path)
        return

    if args.command == "run":
        assert token is not None
        metadata = submit_chunk(
            chunk_pdf=args.chunk_pdf,
            token=token,
            base_url=args.base_url,
            model_version=args.model_version,
            language=args.language,
            is_ocr=not args.no_ocr,
            enable_formula=not args.disable_formula,
            enable_table=not args.disable_table,
            page_ranges=args.page_ranges,
            extra_formats=args.extra_format,
        )
        chunk_id = metadata["chunk_id"]
        wait_until_done(
            chunk_id,
            token=token,
            base_url=args.base_url,
            interval_seconds=args.interval_seconds,
            timeout_seconds=args.timeout_seconds,
        )
        output_path = download_raw_zip(chunk_id, token=token, base_url=args.base_url)
        if not args.no_extract:
            safe_extract_raw_zip(output_path)
        print(output_path)
        return

    raise RuntimeError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
