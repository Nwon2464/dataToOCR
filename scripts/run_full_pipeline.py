from __future__ import annotations

import argparse
import subprocess
import sys
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
    parser.add_argument("--skip-api", action="store_true", help="Skip MinerU API and only build render outputs.")
    parser.add_argument("--no-preview", action="store_true", help="Skip preview HTML generation.")
    parser.add_argument("--pretty", action="store_true", help="Write pretty render_all.json.")
    parser.add_argument("--skip-check", action="store_true", help="Skip render preview checks.")
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


def run_command(stage: str, command: list[str], capture_stdout: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE if capture_stdout else None,
            stderr=subprocess.PIPE if capture_stdout else None,
            check=True,
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


def build_chunk_render(no_preview: bool) -> None:
    command = [sys.executable, "scripts/prepare_mineru_render.py", "--all"]
    if not no_preview:
        command.append("--preview")
    run_command("build chunk render outputs", command)


def build_render_all(pretty: bool) -> None:
    command = [sys.executable, "scripts/build_render_all.py"]
    if pretty:
        command.append("--pretty")
    run_command("build combined render_all.json", command)


def check_render_previews(skip_check: bool, no_preview: bool) -> None:
    if skip_check:
        log("[warn] skip check requested")
        return
    if no_preview:
        log("[warn] preview generation disabled; skip check_render_preview.py --all")
        return
    run_command("check render previews", [sys.executable, "scripts/check_render_preview.py", "--all"])


def check_render_images(skip_check: bool) -> None:
    if skip_check:
        log("[warn] skip check requested")
        return
    run_command("check render images", [sys.executable, "scripts/check_render_images.py"])


def main() -> int:
    args = parse_args()
    pdf_path = resolve_pdf(args.pdf)
    chunks_dir = resolve_project_path(args.chunks_dir)

    if args.chunk_size < 1:
        print("[error] --chunk-size must be 1 or greater", file=sys.stderr)
        return 1
    if not args.skip_api and not pdf_path.is_file():
        print(f"[error] source PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    log("[1/5] Split PDF into chunks")
    chunk_paths: list[Path] = []
    if args.skip_api:
        log("[warn] skip API requested; split not required")
    elif args.skip_split:
        chunk_paths = find_existing_chunks(pdf_path, chunks_dir)
    else:
        chunk_paths = split_chunks(pdf_path, args.chunk_size, chunks_dir)

    log("[2/5] Run MinerU API for chunks")
    if args.skip_api:
        log("[warn] skip MinerU API; assume data/mineru_api_output already exists")
    else:
        run_api_for_chunks(chunk_paths)

    log("[3/5] Build chunk render.json and preview")
    build_chunk_render(args.no_preview)

    log("[4/5] Build combined render_all.json")
    build_render_all(args.pretty)

    log("[5/6] Check render previews")
    check_render_previews(args.skip_check, args.no_preview)

    log("[6/6] Check render images")
    check_render_images(args.skip_check)

    log("[done] full pipeline completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
