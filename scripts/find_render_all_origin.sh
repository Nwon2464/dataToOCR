#!/usr/bin/env bash
set -euo pipefail

TARGET_NAME="render_all.json"
ROOT="${1:-.}"

echo "======================================"
echo "Searching render_all.json origin"
echo "Root: $ROOT"
echo "======================================"
echo

echo "1) Existing render_all.json files"
echo "--------------------------------------"
find "$ROOT" -type f -name "$TARGET_NAME" -print
echo

echo "2) References to render_all.json"
echo "--------------------------------------"
grep -RIn --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=venv \
  --exclude='*.png' --exclude='*.jpg' --exclude='*.jpeg' --exclude='*.pdf' \
  "$TARGET_NAME" "$ROOT" || true
echo

echo "3) References to render_all without extension"
echo "--------------------------------------"
grep -RIn --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=venv \
  --exclude='*.png' --exclude='*.jpg' --exclude='*.jpeg' --exclude='*.pdf' \
  "render_all" "$ROOT" || true
echo

echo "4) Suspicious JSON write code"
echo "--------------------------------------"
grep -RIn --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=venv \
  --include='*.py' --include='*.js' --include='*.ts' --include='*.tsx' --include='*.mjs' --include='*.cjs' \
  -E "json\.dump|write_text|open\(.*w|fs\.writeFile|writeFileSync|JSON\.stringify|dump\(" "$ROOT" || true
echo

echo "5) Files that write render.json"
echo "--------------------------------------"
grep -RIn --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=venv \
  "render.json" "$ROOT" || true
echo

echo "6) Recently modified scripts"
echo "--------------------------------------"
find "$ROOT" \
  \( -path '*/.git' -o -path '*/node_modules' -o -path '*/.venv' -o -path '*/venv' \) -prune -o \
  -type f \( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.tsx' -o -name '*.sh' \) \
  -printf '%TY-%Tm-%Td %TH:%TM %p\n' | sort -r | head -80
echo

echo "7) Git history mentioning render_all.json"
echo "--------------------------------------"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git log --all --name-only --pretty=format:'commit %h %ad %s' --date=short -- "$TARGET_NAME" || true
  echo
  echo
  git grep -n "$TARGET_NAME" $(git rev-list --all) 2>/dev/null | head -100 || true
else
  echo "Not a git repository."
fi

echo
echo "Done."
