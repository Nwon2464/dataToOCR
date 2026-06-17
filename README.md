# jp-accounting-ocr

Local OCR review tool for Japanese accounting study materials that include English terms.

## Goal

Create a local-first workflow for importing study PDFs/images, extracting page images, running OCR, reviewing recognized text, and saving corrections for later search and analysis.

## MVP Scope

- Local file-based source material handling.
- PyMuPDF-based PDF to page image rendering.
- PaddleOCR-only OCR pipeline.
- Basic review workflow for OCR text correction.
- Local data storage only.
- Minimal Python project scaffold for future implementation.

## Non-Goals For Now

- Production OCR accuracy tuning.
- Streamlit UI implementation.
- Cloud storage or hosted deployment.
- User accounts or authentication.
- Tesseract comparison.
- Full-text search indexing, diffing, risk highlighting, or automatic keyword-to-page mapping.

## Development Phases

1. PaddleOCR-only review UI.
2. SQLite storage.
3. Search.
4. Tesseract comparison.
5. Diff and risk highlighting.
6. Accounting dictionary.
7. Chapter and keyword indexing.

## Current Step

This step makes batch OCR more OOM-resilient. The app can run OCR over pages missing raw OCR, all pages, or a selected page range. Existing raw OCR is skipped by default and overwritten only when the user enables the overwrite option. Batch OCR runs each page in an isolated worker subprocess, uses lightweight PaddleOCR mode by default, and defaults to 1 page per batch.

The previous step added a textbook Index keyword dictionary foundation. Index terms and section-style references can be parsed into SQLite keyword tables, while full corrected-text search remains separate. Textbook Index refs are stored as section refs, not PDF page numbers. FTS5 indexing, automatic section-to-page mapping, automatic layout detection, build/run steps, and package installation are not part of this step.

## App Entrypoint

`app/streamlit_app.py` is the MVP UI entrypoint. It currently uploads a PDF, saves it under `data/input/`, triggers PDF page extraction, provides a side-by-side selected page image plus raw OCR view, and can run sequential batch OCR for current document pages.

It also supports editing and saving corrected text for one selected page. Full-document correction is not implemented yet.

After saving corrected text, the user can keep the current review status, mark the page as reviewing, or mark it as checked. Marking checked clears the manual-review flag.

Each extracted page can also be classified with review status, layout type, OCR mode, and a manual-review flag. Layout classification is manual for now.

The app shows review progress counts and can jump to the next page needing review. Pages marked `checked` are skipped by next-review navigation.

The app can search corrected text files for the current document. Each result can jump Page Review to the matching page. Raw OCR text is not searched by default.

The app can run batch OCR for the current document. Batch OCR is sequential and local, runs PaddleOCR in one-page worker subprocesses, shows progress, collects per-page failures, and does not save or overwrite corrected text. Worker OCR uses lightweight mode by default to disable extra orientation/unwarping models when supported. For low-memory machines or large PDFs, run one page at a time or use small ranges.

The backend can parse simple textbook Index lines such as `Strict liability 1-3, 3-9, 3-12` into keyword dictionary entries. Index refs are stored as textbook section references and are not treated as PDF page numbers yet. Automatic page mapping and keyword-assisted FTS5 search/ranking are future work.

## OCR Status

PaddleOCR is used for local OCR in `src/ocr_tool/pipeline/run_ocr.py`. The default language is Japanese: `lang="japan"`. Single-page OCR runs in the app process for now; batch OCR runs one page image at a time in isolated worker subprocesses. Raw text is written only under `data/ocr_raw/`.

Corrected text is saved separately under `data/corrected/` and does not overwrite raw OCR text.

## SQLite Metadata

`data/app.db` is created when database initialization is called. SQLite stores document/page metadata, review status, layout type, OCR mode, manual-review flags, and keyword dictionary metadata. Raw OCR and corrected text contents remain in files under `data/ocr_raw/` and `data/corrected/`.

Uploading and extracting pages through the Streamlit app now creates or updates `data/app.db` metadata for the document and extracted pages.

The app can update page review metadata in `data/app.db`; text contents still remain in files.

## Manual PDF Extraction Check

Place a real sample PDF under `data/input/`, then run:

```bash
python scripts/manual_check_extract.py data/input/sample_real_textbook_3pages.pdf
```

Expected result: page images are created under `data/pages/{document_id}/`, and the script prints the generated `document_id`, page count, and saved image paths.

This only verifies PDF to image extraction. It does not perform OCR yet.
