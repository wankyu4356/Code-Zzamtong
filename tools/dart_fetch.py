#!/usr/bin/env python3
"""
인선이엔티(060150) DART 정기보고서·감사보고서 원문 수집기.

업로드된 'DART 공시목록' 엑셀의 공시 링크(dsaf001/main.do?rcpNo=...)를 그대로 사용한다.

동작
  1) main.do 에서 목차 트리(node1['eleId'] / ['offset'] / ['length'])를 파싱
  2) 자식 구간을 모두 포함하는 최상위 노드만 골라 (II. 사업의 내용 등)
     report/viewer.do 로 원문 HTML 을 내려받는다 — 문서 전체를 8~10회 요청으로 커버
  3) 섹션별로 gzip 저장

DART 는 기본 User-Agent 요청에 응답하지 않으므로 브라우저 UA 를 사용한다.

사용법
  python3 tools/dart_fetch.py --xlsx "DART 공시목록.xlsx" --outdir data/raw --since 2016-01-01
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

DART = "https://dart.fss.or.kr"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# 수집 대상: 정기보고서 3종 + 감사보고서 (거래소 '감사보고서제출' 신고는 제외)
REPORT_RE = re.compile(r"(사업보고서|반기보고서|분기보고서|감사보고서)")
NODE_RE = re.compile(r"""node\d+\['(\w+)'\]\s*=\s*['"]?([^'";]*)['"]?\s*;""")


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": DART + "/",
                      "Accept-Language": "ko-KR,ko;q=0.9"})
    ca = "/root/.ccr/ca-bundle.crt"
    if os.path.exists(ca):
        s.verify = ca
    return s


def get(s: requests.Session, url: str, **kw) -> requests.Response:
    """네트워크 오류에만 지수 백오프 재시도 (2s, 4s, 8s, 16s)."""
    last = None
    for wait in (2, 4, 8, 16, 0):
        try:
            r = s.get(url, timeout=120, **kw)
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            if wait:
                time.sleep(wait)
    raise RuntimeError(f"GET 실패: {url} ({last})")


def parse_nodes(html: str) -> list[dict]:
    """main.do 의 목차 트리를 노드 목록으로 파싱."""
    nodes, cur = [], None
    for k, v in NODE_RE.findall(html):
        if k == "text":
            if cur:
                nodes.append(cur)
            cur = {}
        if cur is not None:
            cur[k] = v.strip()
    if cur:
        nodes.append(cur)
    out = []
    for n in nodes:
        try:
            n["_off"] = int(n.get("offset") or 0)
            n["_len"] = int(n.get("length") or 0)
        except ValueError:
            continue
        if n.get("eleId") and n["_len"] > 0:
            out.append(n)
    return out


def root_nodes(nodes: list[dict]) -> list[dict]:
    """다른 노드 구간에 포함되지 않는 최상위 노드만 반환.

    DART 목차는 부모 노드의 offset~length 가 자식 구간 전체를 덮으므로,
    최상위만 받으면 문서 전체를 훨씬 적은 요청으로 커버할 수 있다.
    """
    roots = []
    for n in nodes:
        a, b = n["_off"], n["_off"] + n["_len"]
        covered = any(m is not n and m["_off"] <= a and m["_off"] + m["_len"] >= b
                      and m["_len"] > n["_len"] for m in nodes)
        if not covered:
            roots.append(n)
    roots.sort(key=lambda n: n["_off"])
    return roots


def decode(raw: bytes) -> str:
    head = raw[:600].lower()
    order = ("utf-8", "cp949") if b"utf-8" in head else ("cp949", "utf-8")
    for enc in order:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def fetch_report(s: requests.Session, t: dict, outdir: Path) -> dict:
    dest = outdir / f"{t['date']}_{t['rcp']}"
    marker = dest / "_done.json"
    if marker.exists():
        return {**t, "status": "skip", "sections": json.loads(marker.read_text())["sections"]}

    dest.mkdir(parents=True, exist_ok=True)
    main = get(s, f"{DART}/dsaf001/main.do", params={"rcpNo": t["rcp"]}).text
    nodes = parse_nodes(main)
    if not nodes:
        raise RuntimeError("목차 트리 파싱 실패")
    roots = root_nodes(nodes)

    saved = []
    for i, n in enumerate(roots):
        try:
            r = get(s, f"{DART}/report/viewer.do", params={
                "rcpNo": n.get("rcpNo", t["rcp"]), "dcmNo": n.get("dcmNo", ""),
                "eleId": n["eleId"], "offset": n["_off"], "length": n["_len"],
                "dtd": n.get("dtd", "dart4.xsd")})
        except Exception as e:  # noqa: BLE001
            print(f"      섹션 실패 [{n['text'][:22]}]: {e}", file=sys.stderr)
            continue
        safe = re.sub(r"[^\w가-힣.\-]", "_", n["text"])[:50]
        p = dest / f"{i:02d}_{safe}.html.gz"
        with gzip.open(p, "wt", encoding="utf-8") as fh:
            fh.write(decode(r.content))
        saved.append(n["text"])
        time.sleep(0.35)

    if not saved:
        raise RuntimeError("섹션을 하나도 받지 못함")
    marker.write_text(json.dumps({"sections": saved}, ensure_ascii=False))
    return {**t, "status": "ok", "sections": saved}


def load_targets(xlsx: Path, since: str) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    ws = wb["공시목록"]
    head = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx = {n: head.index(n) for n in ("접수일자", "보고서명", "제출인", "접수번호", "공시 링크")}
    targets = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        name = (row[idx["보고서명"]] or "").strip()
        date = row[idx["접수일자"]] or ""
        if not REPORT_RE.search(name) or name.endswith("제출"):
            continue
        if date < since:
            continue
        targets.append({"date": date, "name": name, "filer": row[idx["제출인"]],
                        "rcp": str(row[idx["접수번호"]]).strip(),
                        "url": row[idx["공시 링크"]]})
    targets.sort(key=lambda t: t["date"])
    return targets


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True, type=Path)
    ap.add_argument("--outdir", default=Path("data/raw"), type=Path)
    ap.add_argument("--since", default="2016-01-01")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()

    targets = load_targets(args.xlsx, args.since)
    print(f"수집 대상 {len(targets)}건 ({args.since} 이후)\n", flush=True)

    ok = fail = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_report, session(), t, args.outdir): t for t in targets}
        for fu in as_completed(futs):
            t = futs[fu]
            try:
                res = fu.result()
                tag = "skip" if res["status"] == "skip" else "OK  "
                print(f"  {tag} {t['date']} {t['name'][:28]:<30} 섹션 {len(res['sections'])}개",
                      flush=True)
                ok += 1
            except Exception as e:  # noqa: BLE001
                print(f"  FAIL {t['date']} {t['name'][:28]:<30} {e}", file=sys.stderr, flush=True)
                fail += 1

    print(f"\n완료: 성공 {ok} / 실패 {fail}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
