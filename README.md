# dataToOCR

USCPA scan PDF processing pipeline.

Current flow:

```text
original PDF -> 10-page PDF chunks -> MinerU Web API output -> Markdown segments -> DB index
```

## Status

Done:

```text
Phase 0: project data layout and path helpers
Phase 1: PDF chunk splitting
Phase 2: MinerU Web API batch script
```

Next:

```text
Phase 4: process Markdown into segments
Phase 5: index documents in SQLite
```

## Data Layout

```text
data/
  original/
    USCPA REG1 1.pdf
  chunks/
    USCPA_REG1_p001_010.pdf
    USCPA_REG1_p011_020.pdf
    ...
    USCPA_REG1_p251_252.pdf
  mineru_api_output/
    USCPA_REG1_p001_010/
      raw.zip
      full.md
      content_list.json
      middle.json
      images/
  processed/
    USCPA_REG1_p001_010/
      segments.json
      document.json
      review.html
  db/
    ocr_documents.sqlite3
```

## Scripts

Current:

```text
scripts/split_pdf_chunks.py
scripts/run_mineru_api_batch.py
scripts/review_all_mineru_outputs.py
scripts/common/api_paths.py
scripts/common/project_paths.py
scripts/common/mineru_paths.py
scripts/common/md_segments.py
```

Planned:

```text
scripts/submit_mineru_api.py
scripts/poll_mineru_api.py
scripts/download_mineru_result.py
scripts/process_mineru_markdown.py
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-mineru.txt
```

## Split PDF Chunks

Put source PDF in:

```text
data/original/
```

Run:

```bash
python3 scripts/split_pdf_chunks.py "USCPA REG1 1.pdf"
```

Default chunk size is 10 pages. Output goes to:

```text
data/chunks/
```

Examples:

```text
data/chunks/USCPA_REG1_p001_010.pdf
data/chunks/USCPA_REG1_p011_020.pdf
data/chunks/USCPA_REG1_p251_252.pdf
```

Use custom chunk size:

```bash
python3 scripts/split_pdf_chunks.py "USCPA REG1 1.pdf" --chunk-size 5
```

Override inferred book ID:

```bash
python3 scripts/split_pdf_chunks.py "USCPA REG1 1.pdf" --book-id USCPA_REG1
```

## Run MinerU Web API

Set token:

```bash
export MINERU_API_TOKEN="..."
```

Submit one 10-page chunk:

```bash
python3 scripts/run_mineru_api_batch.py submit USCPA_REG1_p001_010.pdf
```

Poll status:

```bash
python3 scripts/run_mineru_api_batch.py poll USCPA_REG1_p001_010
```

Wait until done:

```bash
python3 scripts/run_mineru_api_batch.py wait USCPA_REG1_p001_010
```

Download and extract result zip:

```bash
python3 scripts/run_mineru_api_batch.py download USCPA_REG1_p001_010
```

Submit, wait, download, and extract in one command:

```bash
python3 scripts/run_mineru_api_batch.py run USCPA_REG1_p001_010.pdf
```

Extract manually:

```bash
python3 scripts/run_mineru_api_batch.py extract data/mineru_api_output/USCPA_REG1_p001_010/raw.zip
python3 scripts/run_mineru_api_batch.py data/mineru_api_output/USCPA_REG1_p001_010/raw.zip
```

Outputs:

```text
data/mineru_api_output/USCPA_REG1_p001_010/api_task.json
data/mineru_api_output/USCPA_REG1_p001_010/api_status.json
data/mineru_api_output/USCPA_REG1_p001_010/raw.zip
```
