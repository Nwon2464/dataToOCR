from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.split_pdf_chunks import DEFAULT_CHUNK_SIZE, derive_book_id  # noqa: E402






def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run full PDF -> MinerU -> render pipeline for one source PDF.")
    parser.add_argument("pdf", type=Path, help="Source PDF path, usually under data/original/.")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="Pages per chunk. Default: 10.")
    parser.add_argument("--chunks-dir", type=Path, default=Path("data/chunks"), help="Chunk output directory.")
    parser.add_argument("--skip-split", action="store_true", help="Use existing chunk PDFs instead of splitting.")
    parser.add_argument("--skip-api", action="store_true", help="Skip MinerU API and only build Text Study outputs.")
    parser.add_argument("--text-study-root", type=Path, default=Path("exports/text_study"), help="Text Study web app root.")
    parser.add_argument("--title", default=None, help="Text Study book title. Defaults to derived book id.")
    return parser.parse_args()


def rel_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_pdf(path: Path) -> Path:
    if path.is_absolute():
        return path
    direct = (Path.cwd() / path).resolve()
    if direct.exists():
        return direct
    parts = path.parts
    if parts and parts[0] == PROJECT_ROOT.name:
        return (PROJECT_ROOT / Path(*parts[1:])).resolve()
    return direct


def resolve_project_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0] == PROJECT_ROOT.name:
        return (PROJECT_ROOT / Path(*parts[1:])).resolve()
    return (PROJECT_ROOT / path).resolve()


def format_command(command: list[str]) -> str:
    return " ".join(command)


def run_command(
    stage: str,
    command: list[str],
    capture_stdout: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        return subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE if capture_stdout else None,
            stderr=subprocess.PIPE if capture_stdout else None,
            check=True,
            env=merged_env,
        )
    except subprocess.CalledProcessError as exc:
        print(f"[error] stage failed: {stage}", file=sys.stderr)
        print(f"[error] command: {format_command(command)}", file=sys.stderr)
        if exc.stdout:
            print(exc.stdout, file=sys.stderr, end="" if exc.stdout.endswith("\n") else "\n")
        if exc.stderr:
            print(exc.stderr, file=sys.stderr, end="" if exc.stderr.endswith("\n") else "\n")
        raise SystemExit(1) from exc


def log(message: str) -> None:
    print(message, flush=True)


def run_logged_stage(stage: str, command: list[str]) -> None:
    log(f"[start] {stage}")
    run_command(stage, command)
    log(f"[complete] {stage}")


def log_output_file(label: str, path: Path) -> None:
    if not path.is_file():
        print(f"[error] {label} not found: {rel_path(path)}", file=sys.stderr)
        raise SystemExit(1)
    size = path.stat().st_size
    if size < 1:
        print(f"[error] {label} is empty: {rel_path(path)}", file=sys.stderr)
        raise SystemExit(1)
    log(f"[{label}] {rel_path(path)}")
    log(f"[{label} size] {size} bytes")


def split_chunks(pdf_path: Path, chunk_size: int, chunks_dir: Path) -> list[Path]:
    command = [
        sys.executable,
        "scripts/split_pdf_chunks.py",
        str(pdf_path),
        "--chunk-size",
        str(chunk_size),
        "--output-dir",
        str(chunks_dir),
    ]
    result = run_command("split PDF into chunks", command, capture_stdout=True)
    chunk_paths: list[Path] = []
    for line in result.stdout.splitlines():
        value = line.strip()
        if not value:
            continue
        path = Path(value)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        chunk_paths.append(path)
        log(f"[split] created: {rel_path(path)}")
    if not chunk_paths:
        print("[error] split produced no chunk paths", file=sys.stderr)
        raise SystemExit(1)
    return chunk_paths


def find_existing_chunks(pdf_path: Path, chunks_dir: Path) -> list[Path]:
    book_id = derive_book_id(pdf_path)
    chunk_root = resolve_project_path(chunks_dir)
    chunks = sorted(chunk_root.glob(f"{book_id}_p*.pdf"))
    if not chunks:
        print(f"[error] no existing chunks found: {rel_path(chunk_root / f'{book_id}_p*.pdf')}", file=sys.stderr)
        raise SystemExit(1)
    for path in chunks:
        log(f"[split] existing: {rel_path(path)}")
    return chunks


def run_api_for_chunks(chunk_paths: list[Path]) -> None:
    total = len(chunk_paths)
    for index, chunk_path in enumerate(chunk_paths, start=1):
        log(f"[api {index}/{total}] {rel_path(chunk_path)}")
        run_command(
            "run MinerU API",
            [sys.executable, "scripts/run_mineru_api_batch.py", "run", str(chunk_path)],
        )


def text_study_document_title(book_id: str) -> str:
    return book_id.replace("_", " ").replace("-", " ").strip().title()


def text_study_book_root(text_study_root: Path, book_id: str) -> Path:
    return text_study_root / "books" / book_id


def fix_reader_home_link(reader_path: Path) -> None:
    if not reader_path.is_file():
        print(f"[error] reader not found: {rel_path(reader_path)}", file=sys.stderr)
        raise SystemExit(1)

    text = reader_path.read_text(encoding="utf-8")
    replacements = {
        'href="./index.html"': 'href="../../index.html"',
        'href="index.html"': 'href="../../index.html"',
        "href='./index.html'": "href='../../index.html'",
        "href='index.html'": "href='../../index.html'",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    reader_path.write_text(text, encoding="utf-8")


def count_reader_pages(reader_path: Path) -> int:
    if not reader_path.is_file():
        return 0
    return reader_path.read_text(encoding="utf-8").count('<section class="page"')


def write_book_registry(book_root: Path, book_id: str, title: str, reader_path: Path) -> Path:
    book_root.mkdir(parents=True, exist_ok=True)
    registry_path = book_root / "book.json"
    data = {
        "book_id": book_id,
        "title": title,
        "reader_href": f"./books/{book_id}/reader.html",
        "pages": count_reader_pages(reader_path),
        "status": "ready",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    registry_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return registry_path


def main() -> int:
    args = parse_args()
    pdf_path = resolve_pdf(args.pdf)
    chunks_dir = resolve_project_path(args.chunks_dir)
    book_id = derive_book_id(pdf_path)
    text_study_root = resolve_project_path(args.text_study_root)
    book_root = text_study_book_root(text_study_root, book_id)
    title = args.title or text_study_document_title(book_id)
    
    if args.chunk_size < 1:
        print("[error] --chunk-size must be 1 or greater", file=sys.stderr)
        return 1
    if not args.skip_api and not pdf_path.is_file():
        print(f"[error] source PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    log("[1/10] Split PDF into chunks")
    chunk_paths: list[Path] = []
    if args.skip_api:
        log("[warn] skip API requested; split not required")
    elif args.skip_split:
        chunk_paths = find_existing_chunks(pdf_path, chunks_dir)
    else:
        chunk_paths = split_chunks(pdf_path, args.chunk_size, chunks_dir)
    log("[complete] split PDF into chunks")

    log("[2/10] Run MinerU API for chunks")
    if args.skip_api:
        log("[warn] skip MinerU API; assume data/mineru_api_output already exists")
    else:
        run_api_for_chunks(chunk_paths)
    log("[complete] run MinerU API for chunks")

    log("[3/7] Export text study outputs")
    run_logged_stage(
        "export text study outputs",
        [
            sys.executable,
            "scripts/export_text_study_batch.py",
            "--mineru-root",
            "data/mineru_api_output",
            "--output-root",
            str(book_root),
            "--force",
        ],
    )

    log("[4/7] Render source previews")
    run_logged_stage(
        "render source previews",
        [
            sys.executable,
            "scripts/render_source_previews.py",
            "--text-study-root",
            str(book_root),
            "--mineru-root",
            "data/mineru_api_output",
            "--scale",
            "1.0",
        ],
    )

    log("[5/7] Build continuous reader")
    run_logged_stage(
        "build continuous reader",
        [
            sys.executable,
            "scripts/build_text_study_reader.py",
            "--text-study-root",
            str(book_root),
            "--title",
            title,
        ],
    )
    reader_path = book_root / "reader.html"
    fix_reader_home_link(reader_path)
    log_output_file("Text Study reader", reader_path)

    log("[6/7] Write book registry")
    registry_path = write_book_registry(book_root, book_id, title, reader_path)
    log_output_file("book registry", registry_path)

    log("[7/7] Rebuild text study home")
    run_logged_stage(
        "build text study home",
        [
            sys.executable,
            "scripts/build_text_study_home.py",
            "--text-study-root",
            str(text_study_root),
            "--title",
            "USCPA Text Study Home",
        ],
    )
    log_output_file("Text Study home", text_study_root / "index.html")

    log("[done] full pipeline completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
