# dataToOCR

MinerU API로 PDF를 OCR/HTML 변환한 뒤, React 기반 GoodNotes Reader 화면으로 렌더링하고, Playwright로 최종 PDF를 export하는 로컬 파이프라인입니다.

최종 목표:

```text
원본 PDF
→ chunk 분할
→ MinerU API OCR
→ render.json / HTML 생성
→ GoodNotes용 React 화면 렌더링
→ Playwright PDF export
→ toc_pdf.json 기반 PDF bookmark 삽입
→ 최종 bookmarked PDF 생성
```

---

## 1. 최초 세팅

### Python venv

```bash
cd /home/wonn/projects/auth/dataToOCR

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-mineru.txt
```

### Node packages

```bash
npm install
```

### Playwright browser 설치

```bash
npx playwright install chromium
```

---

## 2. 환경변수 설정

MinerU API를 사용하려면 `.env` 파일이 필요합니다.

```bash
cp .env.example .env
```

`.env` 안에 MinerU API token을 설정합니다.

```env
MINERU_API_TOKEN=your_token_here
```

---

## 3. 원본 PDF 넣는 위치

원본 PDF는 아래 폴더에 넣습니다.

```text
data/original/
```

예:

```text
data/original/USCPA_REG1_2.pdf
```

`data/original/` 안의 PDF는 Git에 올리지 않습니다.

---

## 4. 전체 파이프라인 실행

가장 기본 실행:

```bash
cd /home/wonn/projects/auth/dataToOCR
source .venv/bin/activate

python3 scripts/run_full_pipeline.py data/original/USCPA_REG1_2.pdf
```

로그까지 남기면서 실행:

```bash
cd /home/wonn/projects/auth/dataToOCR
source .venv/bin/activate

mkdir -p logs
LOG_FILE="logs/full_pipeline_$(date +%Y%m%d_%H%M%S).log"

{
  echo "===== FULL PIPELINE START ====="
  date
  echo

  python3 scripts/run_full_pipeline.py data/original/USCPA_REG1_2.pdf

  STATUS=$?

  echo
  echo "===== FULL PIPELINE END ====="
  date
  echo "exit status: $STATUS"

  exit $STATUS
} 2>&1 | tee "$LOG_FILE"
```

---

## 5. 최종 결과물 위치

입력 PDF가 다음이면:

```text
data/original/USCPA_REG1_2.pdf
```

최종 결과물은 다음 위치에 생성됩니다.

### Raw PDF

```text
exports/goodnotes/raw/USCPA_REG1_2_goodnotes_no_header.pdf
```

### Bookmark 포함 최종 PDF

```text
exports/goodnotes/final/USCPA_REG1_2_goodnotes_no_header_bookmarked.pdf
```

### PDF bookmark용 TOC

```text
data/processed/toc_pdf.json
```

---

## 6. 전체 파이프라인 흐름

`run_full_pipeline.py`는 아래 순서로 실행됩니다.

```text
[1] Split PDF into chunks
[2] Run MinerU API for chunks
[3] Build chunk render.json and preview
[4] Build processed HTML and apply GoodNotes icon rules
[5] Build combined render_all.json
[6] Check render previews
[7] Check render images
[8] Build web app
[9] Export GoodNotes PDF and toc_pdf.json
[10] Add PDF bookmarks
```

---

## 7. 각 단계별 주요 파일

### Chunk PDF

```text
data/chunks/
```

### MinerU API 결과

```text
data/mineru_api_output/<chunk_id>/raw.zip
data/mineru_api_output/<chunk_id>/full.html
data/mineru_api_output/<chunk_id>/*content_list_v2.json
```

### Chunk별 render 결과

```text
data/processed/<chunk_id>/render.json
data/processed/<chunk_id>/render_preview.html
```

### HTML manifest

```text
data/processed/html_manifest.json
```

### GoodNotes icon 후보

```text
assets/goodnotes_icons/candidates/
assets/goodnotes_icons/candidates_manifest.json
```

### 전체 React 렌더링용 데이터

```text
data/processed/render_all.json
```

---

## 8. 단일 chunk 테스트

API 호출만 테스트:

```bash
cd /home/wonn/projects/auth/dataToOCR
source .venv/bin/activate

python3 scripts/run_mineru_api_batch.py run data/chunks/USCPA_REG1_2_p001_010.pdf
```

단일 chunk 후처리 테스트:

```bash
cd /home/wonn/projects/auth/dataToOCR
source .venv/bin/activate

CHUNK_ID="USCPA_REG1_2_p001_010"

python3 scripts/prepare_mineru_render.py "$CHUNK_ID" --preview
python3 scripts/build_html_manifest.py --pretty
python3 scripts/apply_goodnotes_icon_rules.py refresh-candidates
python3 scripts/apply_goodnotes_icon_rules.py mark-small-icons
python3 scripts/apply_goodnotes_icon_rules.py apply
python3 scripts/build_render_all.py --pretty
```

확인:

```bash
python3 - <<'PY'
import json
from pathlib import Path

p = Path("data/processed/render_all.json")
data = json.loads(p.read_text())

print("chunk_count:", data["stats"]["chunk_count"])
print("page_count:", data["stats"]["page_count"])
print("block_count:", data["stats"]["block_count"])
PY
```

---

## 9. HTML 생성 확인

MinerU API 결과에 `full.html`이 있어야 합니다.

```bash
find data/mineru_api_output -name "full.html" | sort | wc -l
```

예상:

```text
21
```

`[html] 0`이면 실패입니다.

---

## 10. render_all 생성 확인

```bash
python3 scripts/build_render_all.py --pretty
```

정상 예:

```text
[chunks] 21
[pages] 204
[blocks] ...
```

`[chunks] 0`이면 실패입니다.

---

## 11. PDF export만 다시 실행하고 싶을 때

이미 `data/processed/render_all.json`이 정상 생성되어 있다면, 프론트 빌드와 PDF export만 다시 실행할 수 있습니다.

```bash
cd /home/wonn/projects/auth/dataToOCR

npm run build
npm run export:goodnotes-pdf
```

단, 특정 문서명을 지정해야 할 때는 환경변수를 사용합니다.

```bash
GOODNOTES_DOCUMENT_TITLE="USCPA REG1 2" \
GOODNOTES_OUTPUT_PATH="exports/goodnotes/raw/USCPA_REG1_2_goodnotes_no_header.pdf" \
GOODNOTES_TOC_OUTPUT_PATH="data/processed/toc_pdf.json" \
npm run export:goodnotes-pdf
```

---

## 12. Bookmark만 다시 넣고 싶을 때

```bash
python3 scripts/add_pdf_bookmarks.py \
  --input exports/goodnotes/raw/USCPA_REG1_2_goodnotes_no_header.pdf \
  --toc data/processed/toc_pdf.json \
  --output exports/goodnotes/final/USCPA_REG1_2_goodnotes_no_header_bookmarked.pdf
```

---

## 13. 생성 데이터 초기화

전체 파이프라인을 처음부터 다시 실행하려면 생성 데이터를 지웁니다.

먼저 dry-run:

```bash
python3 scripts/clear_generated_data.py
```

실제 삭제:

```bash
python3 scripts/clear_generated_data.py --yes
```

삭제 대상:

```text
data/chunks/
data/mineru_api_output/
data/mineru_output/
data/processed/
data/toc/
assets/goodnotes_icons/candidates/
assets/goodnotes_icons/candidates_manifest.json
exports/goodnotes/
```

`data/original/`의 원본 PDF는 직접 관리합니다.

---

## 14. 자주 나는 문제

### 문제: `[html] 0`

원인:

```text
MinerU API 결과에 full.html이 없음
```

확인:

```bash
find data/mineru_api_output -name "full.html" | sort
```

해결:

```text
run_mineru_api_batch.py에서 extra_formats=['html']이 들어가는지 확인
API를 다시 실행
```

---

### 문제: `[chunks] 0`

원인:

```text
data/processed/<chunk_id>/render.json이 없음
```

확인:

```bash
find data/processed -name "render.json" | sort | wc -l
```

해결:

```bash
python3 scripts/prepare_mineru_render.py --all --preview
python3 scripts/build_render_all.py --pretty
```

---

### 문제: PDF export 단계에서 문서를 못 찾음

원인:

```text
GOODNOTES_DOCUMENT_TITLE과 실제 문서명이 다름
```

예:

```text
PDF 파일명: USCPA_REG1_2.pdf
문서명: USCPA REG1 2
```

해결:

```bash
GOODNOTES_DOCUMENT_TITLE="USCPA REG1 2" npm run export:goodnotes-pdf
```

현재 `run_full_pipeline.py`는 입력 PDF 파일명 기준으로 문서명을 자동 계산합니다.

---

### 문제: GoodNotes small icon이 적용되지 않음

확인:

```bash
python3 scripts/apply_goodnotes_icon_rules.py refresh-candidates
python3 scripts/apply_goodnotes_icon_rules.py mark-small-icons
python3 scripts/apply_goodnotes_icon_rules.py apply
```

`_review_exclude_assets/`는 기준 이미지 폴더입니다. 삭제하지 않습니다.

---

## 15. Git에 올리지 않는 파일

다음 파일들은 `.gitignore` 대상입니다.

```text
.venv/
node_modules/
.env
data/original/*.pdf
data/chunks/*
data/mineru_api_output/*
data/processed/*
assets/goodnotes_icons/candidates/*
assets/goodnotes_icons/candidates_manifest.json
exports/
logs/
*.pdf
*.zip
```

Git에는 코드와 기준 리소스만 올립니다.

커밋해도 되는 주요 파일:

```text
scripts/
src/
package.json
package-lock.json
requirements-mineru.txt
README.md
.gitignore
_review_exclude_assets/
data/**/.gitkeep
assets/goodnotes_icons/candidates/.gitkeep
exports/**/.gitkeep
```

---

## 16. 전체 실행 전 체크리스트

```bash
python3 -m py_compile scripts/run_full_pipeline.py
python3 -m py_compile scripts/build_html_manifest.py
python3 -m py_compile scripts/build_render_all.py
python3 -m py_compile scripts/run_mineru_api_batch.py
node --check scripts/export_goodnotes_pdf_with_playwright.js
npm run build
```

원본 PDF 확인:

```bash
ls -lh data/original/
```

환경변수 확인:

```bash
test -f .env
```

---

## 17. 가장 자주 쓰는 명령

처음부터 전체 실행:

```bash
source .venv/bin/activate
python3 scripts/run_full_pipeline.py data/original/USCPA_REG1_2.pdf
```

생성물 초기화:

```bash
python3 scripts/clear_generated_data.py --yes
```

최종 PDF 확인:

```bash
ls -lh exports/goodnotes/final/
```
