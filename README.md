# dataocr MinerU Runner

This repository is a small local wrapper around the open-source MinerU CLI.

Put input files in:

```text
data/samples/
```

Supported inputs for this wrapper:

```text
.pdf .png .jpg .jpeg .webp .bmp .tif .tiff
```

Outputs are written to:

```text
data/mineru_output/<input-file-stem>/
```

## Install

MinerU currently supports Python 3.10-3.13. For the simplest local setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install uv
uv pip install -r requirements-mineru.txt
```

The first run can take a long time because MinerU may download model files.

## Run

One-command batch:

```bash
python scripts/run_batch.py
```

The batch command scans `data/samples/`, skips files that already have
`data/mineru_output/<input-file-stem>/auto/`, runs MinerU for missing outputs, and writes a
manifest to `data/manifests/`.

CPU-compatible default:

```bash
python scripts/run_mineru.py
```

Run one file:

```bash
python scripts/run_mineru.py --input "data/samples/example.pdf"
```

Use a different backend:

```bash
python scripts/run_mineru.py --backend pipeline
python scripts/run_mineru.py --backend auto
```

`pipeline` is the conservative CPU-friendly backend. `auto` omits `-b` and lets MinerU pick the backend.

## Notes

The wrapper shells out to the official MinerU CLI:

```bash
mineru -p <input_path> -o <output_path> -b pipeline
```

If `mineru` is not found, activate the virtual environment or install the dependencies above.
