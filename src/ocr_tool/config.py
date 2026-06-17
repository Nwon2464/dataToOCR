"""Project path constants with no import-time side effects."""

from pathlib import Path

# Repository root for resolving all local project paths.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Local generated data root. Directory creation is handled by storage code later.
DATA_DIR = PROJECT_ROOT / "data"

# Uploaded source PDFs/images are copied here.
INPUT_DIR = DATA_DIR / "input"

# Extracted page images are written here.
PAGES_DIR = DATA_DIR / "pages"

# Raw OCR text output is written here and kept separate from corrections.
OCR_RAW_DIR = DATA_DIR / "ocr_raw"

# Human-reviewed corrected text is written here.
CORRECTED_DIR = DATA_DIR / "corrected"

# Future SQLite metadata/index database.
DATABASE_PATH = DATA_DIR / "app.db"
