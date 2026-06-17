# jp-accounting-ocr

Local OCR review tool for scanned Japanese accounting study PDFs.

## Goal

Create a local-first workflow for scanned PDF layout analysis, page/block image extraction, OCR, and human review. The project direction is OpenCV-based page layout analysis, cropped content blocks, block-level OCR, and page-by-page correction.

## MVP Scope

- Local file-based source material handling.
- PyMuPDF-based PDF to page image rendering.
- PaddleOCR-only OCR pipeline.
- Basic review workflow for OCR text correction.
- Raw OCR and corrected text stored separately.
- SQLite metadata for documents, pages, review status, layout type, OCR mode, and manual-review flags.
- Local data storage only.

## Non-Goals For Now

- Production OCR accuracy tuning.
- Cloud storage or hosted deployment.
- User accounts or authentication.
- Full-text search indexing.
- Accounting dictionary or keyword indexing.
- Tesseract comparison.
- Diff/risk highlighting.

## Development Phases

1. PDF upload and page extraction.
2. SQLite document/page/review metadata.
3. PaddleOCR raw text generation.
4. Page-by-page review UI with corrected text save.
5. OpenCV page layout analysis.
6. Layout JSON export.
7. Block crop generation.
8. Block-level OCR and review workflow.

## Current Focus

- OpenCV page layout analysis for scanned PDFs.
- Layout JSON that records detected blocks and page structure.
- Block crop output for text/table/diagram/question regions.
- Block OCR that can run after crop generation.
- Review UI that keeps raw OCR separate from corrected text and tracks page review state.

This cleanup removes corrected-text search UI and keyword dictionary storage so the codebase can shift toward layout analysis, block crops, and OCR review workflow.

## App Entrypoint

`app/streamlit_app.py` is the MVP UI entrypoint. It currently uploads a PDF, saves it under `data/input/`, triggers PDF page extraction, provides a side-by-side selected page image plus raw OCR view, and can run sequential batch OCR for current document pages.

It also supports editing and saving corrected text for one selected page. Full-document correction is not implemented yet.

After saving corrected text, the user can keep the current review status, mark the page as reviewing, or mark it as checked. Marking checked clears the manual-review flag.

Each extracted page can also be classified with review status, layout type, OCR mode, and a manual-review flag. Layout classification is manual for now.

The app shows review progress counts and can jump to the next page needing review. Pages marked `checked` are skipped by next-review navigation.

The app can run batch OCR for the current document. Batch OCR is sequential and local, runs PaddleOCR in one-page worker subprocesses, shows progress, collects per-page failures, and does not save or overwrite corrected text. Worker OCR uses lightweight mode by default to disable extra orientation/unwarping models when supported. For low-memory machines or large PDFs, run one page at a time or use small ranges.

## OCR Status

PaddleOCR is used for local OCR in `src/ocr_tool/pipeline/run_ocr.py`. The default language is Japanese: `lang="japan"`. Single-page OCR runs in the app process for now; batch OCR runs one page image at a time in isolated worker subprocesses. Raw text is written only under `data/ocr_raw/`.

Corrected text is saved separately under `data/corrected/` and does not overwrite raw OCR text.

## SQLite Metadata

`data/app.db` is created when database initialization is called. SQLite stores document/page metadata, review status, layout type, OCR mode, and manual-review flags. Raw OCR and corrected text contents remain in files under `data/ocr_raw/` and `data/corrected/`.

Uploading and extracting pages through the Streamlit app now creates or updates `data/app.db` metadata for the document and extracted pages.

The app can update page review metadata in `data/app.db`; text contents still remain in files.

## Manual PDF Extraction Check

Place a real sample PDF under `data/input/`, then run:

```bash
python scripts/manual_check_extract.py data/input/sample_real_textbook_3pages.pdf
```

Expected result: page images are created under `data/pages/{document_id}/`, and the script prints the generated `document_id`, page count, and saved image paths.

This only verifies PDF to image extraction. It does not perform OCR yet.

## Future / Backlog

- Persistent OCR job logs, failed page tracking, retry failed pages, and resume workflow.
- Tesseract comparison.
- Diff and risk highlighting.
- Accounting dictionary.
- Chapter/keyword indexing.
