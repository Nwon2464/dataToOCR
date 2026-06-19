from __future__ import annotations

from pathlib import Path


def get_project_root() -> Path:
    """Return the project root based on this file location."""
    return Path(__file__).resolve().parents[2]


def get_data_dir(root: Path | None = None) -> Path:
    """Return the data directory path."""
    project_root = root if root is not None else get_project_root()
    return project_root / "data"


def get_original_dir(root: Path | None = None) -> Path:
    """Return the original PDF storage directory path."""
    return get_data_dir(root) / "original"


def get_chunks_dir(root: Path | None = None) -> Path:
    """Return the chunked PDF storage directory path."""
    return get_data_dir(root) / "chunks"


def get_mineru_api_output_dir(root: Path | None = None) -> Path:
    """Return the MinerU Web API output directory path."""
    return get_data_dir(root) / "mineru_api_output"


def get_processed_dir(root: Path | None = None) -> Path:
    """Return the local post-processing output directory path."""
    return get_data_dir(root) / "processed"


def get_db_dir(root: Path | None = None) -> Path:
    """Return the SQLite database directory path."""
    return get_data_dir(root) / "db"


def ensure_project_dirs(root: Path | None = None) -> dict[str, Path]:
    """Create core project data directories and return their paths."""
    paths = {
        "data": get_data_dir(root),
        "original": get_original_dir(root),
        "chunks": get_chunks_dir(root),
        "mineru_api_output": get_mineru_api_output_dir(root),
        "processed": get_processed_dir(root),
        "db": get_db_dir(root),
    }

    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)

    return paths


def make_chunk_id(book_id: str, page_start: int, page_end: int) -> str:
    """Return a stable chunk ID using book ID and inclusive page range."""
    if page_start < 1:
        raise ValueError("page_start must be 1 or greater.")
    if page_end < 1:
        raise ValueError("page_end must be 1 or greater.")
    if page_start > page_end:
        raise ValueError("page_start must be less than or equal to page_end.")

    return f"{book_id}_p{page_start:03d}_{page_end:03d}"


def get_mineru_api_chunk_dir(chunk_id: str, root: Path | None = None) -> Path:
    """Return the MinerU Web API output directory for a chunk."""
    return get_mineru_api_output_dir(root) / chunk_id


def get_processed_chunk_dir(chunk_id: str, root: Path | None = None) -> Path:
    """Return the local post-processing output directory for a chunk."""
    return get_processed_dir(root) / chunk_id


def ensure_chunk_dirs(chunk_id: str, root: Path | None = None) -> dict[str, Path]:
    """Create chunk-level MinerU API and processed directories."""
    mineru_api_chunk = get_mineru_api_chunk_dir(chunk_id, root)
    paths = {
        "mineru_api_chunk": mineru_api_chunk,
        "mineru_api_images": mineru_api_chunk / "images",
        "processed_chunk": get_processed_chunk_dir(chunk_id, root),
    }

    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)

    return paths
