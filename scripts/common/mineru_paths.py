from __future__ import annotations

from pathlib import Path


def get_project_root() -> Path:
    """Return project root containing data/ and scripts/."""
    current = Path(__file__).resolve()
    for directory in current.parents:
        if (directory / "data").is_dir() and (directory / "scripts").is_dir():
            return directory
    raise FileNotFoundError(
        f"Project root not found from {current}; expected parent with data/ and scripts/."
    )


def get_mineru_output_root(root: Path | None = None) -> Path:
    """Return data/mineru_output directory under project root."""
    project_root = root if root is not None else get_project_root()
    output_root = project_root / "data" / "mineru_output"
    if not output_root.is_dir():
        raise FileNotFoundError(f"MinerU output root not found: {output_root}")
    return output_root


def list_mineru_sample_dirs(output_root: Path | None = None) -> list[Path]:
    """Return MinerU sample output directories containing auto/ under output root."""
    root = output_root if output_root is not None else get_mineru_output_root()
    if not root.is_dir():
        raise FileNotFoundError(f"MinerU output root not found: {root}")

    return sorted(
        (
            path
            for path in root.iterdir()
            if path.is_dir() and (path / "auto").is_dir()
        ),
        key=lambda path: path.name,
    )


def resolve_sample_output_dir(
    sample: str | Path,
    output_root: Path | None = None,
) -> Path:
    """Resolve sample name or existing directory to MinerU sample output directory."""
    sample_path = Path(sample)
    if sample_path.is_dir():
        sample_output_dir = sample_path
    else:
        root = output_root if output_root is not None else get_mineru_output_root()
        sample_output_dir = root / sample_path

    if not sample_output_dir.is_dir():
        raise FileNotFoundError(
            f"MinerU sample output directory not found for sample={sample!s}: "
            f"{sample_output_dir}"
        )
    return sample_output_dir


def get_auto_dir(sample_output_dir: Path) -> Path:
    """Return auto/ directory inside MinerU sample output directory."""
    auto_dir = sample_output_dir / "auto"
    if not auto_dir.is_dir():
        raise FileNotFoundError(f"MinerU auto directory not found: {auto_dir}")
    return auto_dir


def find_mineru_markdown(
    sample: str | Path,
    output_root: Path | None = None,
) -> Path:
    """Find exactly one MinerU Markdown file under sample auto/ directory."""
    sample_output_dir = resolve_sample_output_dir(sample, output_root)
    auto_dir = get_auto_dir(sample_output_dir)
    markdown_files = sorted(auto_dir.rglob("*.md"))
    count = len(markdown_files)

    if count == 1:
        return markdown_files[0]

    message = (
        f"Expected exactly 1 MinerU Markdown file for sample={sample!s}; "
        f"searched auto_dir={auto_dir}; found md_count={count}."
    )
    if count == 0:
        raise FileNotFoundError(message)
    raise ValueError(message)


def find_mineru_images_dir(
    sample: str | Path,
    output_root: Path | None = None,
) -> Path | None:
    """Return auto/images directory for sample when it exists, otherwise None."""
    sample_output_dir = resolve_sample_output_dir(sample, output_root)
    images_dir = sample_output_dir / "auto" / "images"
    if images_dir.is_dir():
        return images_dir
    return None


def read_mineru_markdown(
    sample: str | Path,
    output_root: Path | None = None,
) -> str:
    """Read MinerU Markdown file for sample as UTF-8 text."""
    markdown_path = find_mineru_markdown(sample, output_root)
    return markdown_path.read_text(encoding="utf-8")
