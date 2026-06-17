# Architecture

## App Layer

`app/streamlit_app.py` will be the local Streamlit entrypoint. It should stay thin and delegate behavior to package modules under `src/ocr_tool/`.

The current Streamlit shell handles PDF upload, page extraction, OCR review,
and batch OCR controls. It calls storage helpers to save uploaded PDFs and
pipeline helpers to extract page images. OCR parser and layout analysis logic
should not live directly in the Streamlit entrypoint.

The UI can trigger OCR for one selected extracted page. It shows the selected original page image and raw OCR text side by side. It calls the OCR pipeline and displays raw OCR text, but does not parse OCR results directly.

The UI can also run batch OCR for the current document. Batch OCR is
sequential, local, and OOM-resilient: each page runs in an isolated subprocess
worker instead of holding PaddleOCR inside the Streamlit server process. Worker
exit releases PaddleOCR memory, and a worker crash or OOM can be recorded as a
page failure without killing the UI process. Targets can be missing-raw pages,
all pages, or a selected page range. Existing raw OCR is skipped by default and
overwritten only when the user chooses that option. Large PDFs should be
processed in small ranges; the UI defaults to one page per batch.

Batch OCR workers use lightweight PaddleOCR mode by default. When supported by
the installed PaddleOCR version, this disables document orientation
classification, document unwarping, and textline orientation classification so
the worker does not load those extra preprocessing models.

The UI writes corrected text through storage helpers. Corrected text is
human-reviewed output and stays separate from raw OCR. Saving corrected text can
optionally update review status to `reviewing` or `checked`; choosing `checked`
also clears the manual-review flag.

The Streamlit entrypoint initializes SQLite on startup and writes document/page
metadata after upload and extraction. It does not keep a global SQLite
connection and does not store raw/corrected text content in the database.

The Page Review view can update page review metadata in SQLite. Review status,
layout type, OCR mode, and manual-review flags are saved separately from
corrected text so a page can be classified even before text correction is done.
`layout_type` is manual metadata for now; no automatic layout detection exists.

The app shows a compact review progress summary from SQLite: total pages,
checked pages, unchecked pages, needs-review pages, manual-review count, and
layout counts. The next-review control chooses the next page whose review status
is `needs_review`, `unchecked`, or `reviewing`; pages marked `checked` are
skipped.

## Pipeline Layer

`src/ocr_tool/pipeline/` will own document processing steps:

- Extract PDF pages into local image files using PyMuPDF.
- Analyze scanned page layout with OpenCV.
- Write layout JSON for detected blocks and page structure.
- Crop detected blocks into local image assets.
- Preprocess page images before OCR.
- Run OCR engines on pages or blocks and return raw OCR output.

## Storage Layer

`src/ocr_tool/storage/` will own local persistence:

- File storage for uploaded documents, page images, raw OCR output, and corrected text.
- SQLite setup and access helpers when database-backed state is introduced.

SQLite currently stores document/page metadata and review/layout metadata. Text
contents still live in raw and corrected text files. Raw OCR remains draft
engine output; corrected text remains human-reviewed output.

## UI Review Layer

`src/ocr_tool/ui/review.py` will own review workflow rendering and coordination. It should call pipeline and storage helpers rather than embedding those concerns in Streamlit page code.

## Developer Scripts

`scripts/` contains developer-only manual utilities. These scripts are not part of the app runtime layer and should not own OCR, UI, or database behavior.

## Data Directory Policy

All study materials, extracted pages, OCR output, corrected text, and local database files stay under `data/`. These files are local-only and gitignored. Each data subdirectory includes a `.gitkeep` file so the directory layout remains trackable without committing private or generated content.

Path builder helpers return paths only and do not create directories. `ensure_data_directories()` creates the shared data directories when explicitly called. Write helpers such as text saving create parent directories for the target file at write time.

## Data Lifecycle

PDF and image inputs are stored under `data/input/` using local stored filenames. PDF pages are later extracted into page images under `data/pages/`. OCR output is saved as raw text under `data/ocr_raw/`. Human-reviewed text is saved separately under `data/corrected/`. SQLite metadata lives at `data/app.db`.

Uploaded files are saved as binary files under `data/input/`. Upload saving returns a `Document` dataclass, and the app can persist document/page metadata in SQLite after upload and extraction.

Raw OCR text should not be overwritten by corrected text. Raw output is the
engine result and remains useful for debugging and future OCR quality checks.
Corrected text is the human-approved version used for review completion and
later analysis. Page status tracks review progress, starting as unchecked and
moving through review states as a user verifies each page.

## Page Output Storage

Extracted page images are stored under `data/pages/{document_id}/`. Raw OCR text is stored separately under `data/ocr_raw/{document_id}/`. Corrected human-reviewed text is stored separately under `data/corrected/{document_id}/`.

Raw OCR text should remain immutable once generated unless the user explicitly re-runs OCR later. Corrected text is the trusted review result and should be kept separate so the original OCR output remains available for comparison and debugging.

## PDF Extraction Contract

PDF extraction starts from `Document.input_path`. The extractor uses PyMuPDF in `src/ocr_tool/pipeline/extract_pages.py` and keeps that backend isolated to the extraction layer. It renders each PDF page into an image under `data/pages/{document_id}/` and returns `Page` records with 1-based page numbers, unchecked status, empty raw OCR text, and empty corrected text.

Extraction only creates page images and page records. OCR, text correction, UI review, and database persistence are separate stages.

## OCR Pipeline Contract

OCR runs after page extraction. Its input is one extracted page image path, and its output is raw OCR text for that page. Raw OCR text is saved under `data/ocr_raw/{document_id}/`.

Batch OCR repeats the same single-page OCR contract across selected pages by
launching `python -m ocr_tool.ocr_worker` once per page. The Streamlit process
does not directly hold a PaddleOCR engine for batch runs. Batch OCR generates
raw OCR for selected pages but does not save corrected text, update review
status to `checked`, update layout metadata, create background jobs, or run
pages in parallel.

`create_paddle_ocr_engine()` accepts `lightweight=True` by default and filters
constructor kwargs against the available PaddleOCR signature. If a PaddleOCR
version rejects lightweight kwargs, engine creation falls back to `lang` only.

PaddleOCR is isolated to `src/ocr_tool/pipeline/run_ocr.py`. OCR reads page images and writes raw OCR text only. It must not overwrite corrected text under `data/corrected/{document_id}/`, must not contain UI logic, and must not update SQLite directly.

The PaddleOCR result parser is defensive because result shapes can vary by version. It may need adjustment after real sample OCR verification.

## SQLite Metadata

`data/app.db` stores metadata for imported documents and extracted pages. The
database tracks file paths, page review status, layout type, OCR mode, and
manual-review flags. It does not store raw OCR text or corrected text content.

When PDFs are uploaded through the app, document metadata is inserted or
updated. When pages are extracted, page metadata is inserted or updated. File
storage remains the source for uploaded PDFs, page images, raw OCR text, and
corrected text files. SQLite enables review workflow state and later
layout/block metadata.

Review progress helpers aggregate page metadata and find the next page to
inspect. They do not read OCR or corrected text file contents and do not change
layout/OCR behavior.

`layout_type` exists because pages may contain normal text, right sidebar notes,
tables, diagrams, mixed layouts, or questions. A future `page_assets` table can
track cropped table/diagram image assets, but asset cropping is not implemented
yet.

`needs_manual_review` helps identify pages that need extra attention, especially
tables, diagrams, mixed pages, or question pages. It is workflow metadata only
and does not change OCR or file storage behavior.

Corrected text save remains separate from raw OCR save. If a page is marked
`checked`, it is considered reviewed for downstream layout/OCR workflow.
