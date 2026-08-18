#!/usr/bin/env python3
"""
인선이엔티(060150) DART 정기보고서 원문 수집기.

업로드된 'DART 공시목록' 엑셀의 '공시 링크'(dsaf001/main.do?rcpNo=...)를 그대로 사용해서
사업보고서 / 반기보고서 / 분기보고서 / 감사보고서 원문(ZIP 안의 XML)을 내려받는다.

수집 경로 (우선순위)
  1) OpenDART API  : DART_API_KEY 환경변수가 있으면 document.xml 사용 (가장 안정적)
  2) 공개 DART 뷰어: main.do 에서 dcmNo 를 파싱한 뒤 pdf/download/zip.do 로 원문 ZIP 취득
  3) 폴백          : report/viewer.do 로 목차(eleId) 별 HTML 조각을 순회 수집

사용법
  python3 tools/dart_fetch.py --xlsx <공시목록.xlsx> --outdir data/raw
  python3 tools/dart_fetch.py --xlsx <공시목록.xlsx> --outdir data/raw --since 2016-01-01
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import requests

DART = "https://dart.fss.or.kr"
OPENDART_DOC = "https://opendart.fss.or.kr/api/document.xml"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# 수집 대상 보고서: 정기보고서 3종 + 감사보고서
REPORT_RE = re.compile(r"(사업보고서|반기보고서|분기보고서|감사보고서)")


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": DART + "/"})
    ca = "/root/.ccr/ca-bundle.crt"
    if os.path.exists(ca):
        s.verify = ca
    return s


def get(s: requests.Session, url: str, **kw) -> requests.Response:
    """네트워크 오류에 대해서만 지수 백오프 재시도 (2s, 4s, 8s, 16s)."""
    last = None
    for attempt, wait in enumerate([2, 4, 8, 16, 0]):
        try:
            r = s.get(url, timeout=60, **kw)
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            if wait:
                time.sleep(wait)
    raise RuntimeError(f"GET 실패: {url} ({last})")


def find_dcm_no(html: str) -> str | None:
    """dsaf001/main.do 응답에서 dcmNo 를 뽑는다. 뷰어 버전별 표기를 모두 커버."""
    for pat in (r"dcmNo\s*=\s*['\"]?(\d+)",
                r"viewDoc\(\s*'\d+'\s*,\s*'(\d+)'",
                r"[?&]dcmNo=(\d+)"):
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


def decode(raw: bytes) -> str:
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def save_zip_members(zbytes: bytes, dest: Path) -> list[Path]:
    out: list[Path] = []
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        for name in z.namelist():
            if not re.search(r"\.(xml|html?)$", name, re.I):
                continue
            text = decode(z.read(name))
            p = dest / re.sub(r"[^\w.\-]", "_", name)
            p.write_text(text, encoding="utf-8")
            out.append(p)
    return out


def fetch_via_opendart(s: requests.Session, rcp: str, dest: Path, key: str) -> list[Path]:
    r = get(s, OPENDART_DOC, params={"crtfc_key": key, "rcept_no": rcp})
    if r.content[:2] != b"PK":                     # 오류 시 XML 로 상태코드가 온다
        raise RuntimeError(f"OpenDART 응답이 ZIP 이 아님: {decode(r.content)[:200]}")
    return save_zip_members(r.content, dest)


def fetch_via_viewer(s: requests.Session, rcp: str, dest: Path) -> list[Path]:
    main = get(s, f"{DART}/dsaf001/main.do", params={"rcpNo": rcp}).text
    dcm = find_dcm_no(main)
    if not dcm:
        raise RuntimeError("dcmNo 파싱 실패")
    (dest / "_main.html").write_text(main, encoding="utf-8")

    # 1순위: 원문 ZIP 통째로
    try:
        z = get(s, f"{DART}/pdf/download/zip.do",
                params={"rcp_no": rcp, "dcm_no": dcm, "lang": "ko"})
        if z.content[:2] == b"PK":
            files = save_zip_members(z.content, dest)
            if files:
                return files
    except Exception:  # noqa: BLE001  ZIP 이 막히면 조각 수집으로 폴백
        pass

    # 2순위: 목차(eleId) 별 HTML 조각
    nodes = re.findall(
        r"viewDoc\(\s*'(\d+)'\s*,\s*'(\d+)'\s*,\s*'([^']*)'\s*,"
        r"\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*\)", main)
    files: list[Path] = []
    for i, (rno, dno, ele, off, length, dtd) in enumerate(nodes):
        try:
            part = get(s, f"{DART}/report/viewer.do",
                       params={"rcpNo": rno, "dcmNo": dno, "eleId": ele,
                               "offset": off, "length": length, "dtd": dtd})
        except Exception:  # noqa: BLE001
            continue
        p = dest / f"part_{i:03d}_ele{ele}.html"
        p.write_text(decode(part.content), encoding="utf-8")
        files.append(p)
        time.sleep(0.4)
    if not files:
        raise RuntimeError("원문 조각을 하나도 받지 못함")
    return files


def load_targets(xlsx: Path, since: str) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    ws = wb["공시목록"]
    head = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx = {name: head.index(name) for name in
           ("접수일자", "보고서명", "제출인", "접수번호", "공시 링크")}
    targets = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        name = row[idx["보고서명"]] or ""
        date = row[idx["접수일자"]] or ""
        # '감사보고서제출'은 거래소 단순 신고라 원문에 단가 정보가 없어 제외
        if not REPORT_RE.search(name) or name.strip().endswith("제출"):
            continue
        if date < since:
            continue
        targets.append({"date": date, "name": name.strip(),
                        "filer": row[idx["제출인"]],
                        "rcp": str(row[idx["접수번호"]]).strip(),
                        "url": row[idx["공시 링크"]]})
    targets.sort(key=lambda t: t["date"])
    return targets


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True, type=Path)
    ap.add_argument("--outdir", default=Path("data/raw"), type=Path)
    ap.add_argument("--since", default="2016-01-01")
    args = ap.parse_args()

    key = os.environ.get("DART_API_KEY", "").strip()
    s = session()
    targets = load_targets(args.xlsx, args.since)
    print(f"수집 대상 {len(targets)}건 ({args.since} 이후)", flush=True)

    ok = fail = 0
    for t in targets:
        dest = args.outdir / f"{t['date']}_{t['rcp']}"
        if dest.exists() and any(dest.iterdir()):
            print(f"  skip {t['date']} {t['name']}")
            ok += 1
            continue
        dest.mkdir(parents=True, exist_ok=True)
        try:
            files = (fetch_via_opendart(s, t["rcp"], dest, key) if key
                     else fetch_via_viewer(s, t["rcp"], dest))
            print(f"  OK   {t['date']} {t['name']}  ({len(files)} files)")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL {t['date']} {t['name']}: {e}", file=sys.stderr)
            fail += 1
        time.sleep(1.0)      # DART 부하 배려

    print(f"\n완료: 성공 {ok} / 실패 {fail}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
