# Roadmap

## Phase 1: PaddleOCR-only Review UI

Build the first local review workflow with PaddleOCR output and manual correction.

Before OCR implementation, establish the local foundation:

- Stable path policy for generated files under `data/`.
- Stable dataclass data model for documents, pages, OCR text, corrected text, and review status.
- Local generated files policy so private source files and outputs stay out of git.
- PDF page extraction after the path and model foundations are in place.
- PDF-to-page extraction contract is defined.
- Current extraction step adds PyMuPDF dependency and implementation.
- Current focus adds a manual extraction verification utility.
- Current UI shell supports PDF upload and page extraction trigger.
- OCR contract is defined.
- Current step adds PaddleOCR implementation.
- Current UI step adds single-page OCR trigger.
- Current UI step shows selected page image and raw OCR side by side.
- Current UI step adds single-page corrected text editing and saving.
- Current storage step adds SQLite metadata for documents, pages, review state, and layout state.
- Current app step wires upload and page extraction metadata into SQLite.
- Current UI step adds page review metadata controls for review status, layout type, OCR mode, and manual-review flags.
- Current UI step adds review progress summary and next-page review navigation.
- Current UI step connects corrected-text save with optional review-status updates.
- Current OCR step adds sequential batch OCR for missing-raw, all, or selected-range pages with explicit raw OCR overwrite behavior and per-page failure collection.
- Previous OCR hotfix reused one PaddleOCR engine per batch and capped default batch size, but in-process PaddleOCR still proved memory-risky.
- Current OCR hotfix replaces in-process batch OCR with subprocess-isolated one-page OCR workers so PaddleOCR OOM does not kill the Streamlit process.
- Current OCR hotfix enables lightweight PaddleOCR worker mode by default to avoid loading document orientation, unwarping, and textline orientation models when supported.
- Current cleanup removes corrected-text search UI and keyword dictionary storage to prepare for scanned PDF layout analysis.
- Future page/block assets table can track cropped text/table/diagram/question images, but cropping is not implemented yet.
- Next planned work: OpenCV page layout analysis, layout JSON, block crop output, block OCR, persistent OCR job logs, failed page tracking, retry failed pages, and resume workflow.

## Phase 2: SQLite Storage

Persist documents, pages, OCR results, correction status, and review metadata in SQLite.

## Phase 3: Page Layout Analysis

Detect scanned PDF page regions with OpenCV and save layout JSON.

## Phase 4: Block Crops

Crop detected layout blocks into reusable local image assets.

## Phase 5: Block OCR

Run OCR on cropped blocks while preserving raw OCR and corrected text separation.

## Phase 6: Review Workflow

Review page/block OCR output, save corrections, and track review status.

## Backlog

- Tesseract comparison.
- Diff and risk highlighting.
- Accounting dictionary.
- Chapter/keyword indexing.
