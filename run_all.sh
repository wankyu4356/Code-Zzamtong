#!/usr/bin/env bash
# 인선이엔티 매립단가 분기 시계열 — 전체 파이프라인 한 번에 실행
#   사용법: DART_API_KEY=<키> ./run_all.sh "DART 공시목록.xlsx"
set -euo pipefail

XLSX="${1:?사용법: DART_API_KEY=<키> ./run_all.sh \"DART 공시목록.xlsx\"}"
: "${DART_API_KEY:=}"

python3 -m pip install --quiet openpyxl lxml requests

echo "[1/3] 분기 <-> 출처 보고서 매핑 프레임 생성"
python3 tools/build_frame.py --xlsx "$XLSX" \
  --out "out/인선이엔티_매립단가_분기_수집프레임.xlsx"

echo "[2/3] DART 원문 수집 (2016년 이후 정기보고서 + 감사보고서)"
python3 tools/dart_fetch.py --xlsx "$XLSX" --outdir data/raw --since 2016-01-01

echo "[3/3] 단가 발췌 및 엑셀 출력"
python3 tools/dart_extract.py --raw data/raw --xlsx "$XLSX" \
  --out "out/인선이엔티_매립단가_분기.xlsx"

echo
echo "완료 → out/인선이엔티_매립단가_분기.xlsx"
