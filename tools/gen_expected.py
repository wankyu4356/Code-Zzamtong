#!/usr/bin/env python3
"""워크북과 무관하게 발췌 레코드에서 기대값을 독립 계산해 TSV 로 뽑는다.

tools/verify_formulas.py 가 이 파일을 기준으로 실제 수식 계산 결과를 대조한다.
  python3 tools/gen_expected.py <공시목록.xlsx> <원문디렉터리> <출력.tsv>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import dart_extract as de  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402


def main() -> int:
    xlsx, raw, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    manifest = de.load_manifest(xlsx)
    records, prose, log, blank = de.extract(raw, manifest)

    collected = {l["접수번호"] for l in log}
    frame = {}
    for m in manifest.values():
        if m["rcp"] not in collected:
            continue
        y, q = de.report_period(m["name"], m["date"])
        if y and re.search(r"(사업|반기|분기)보고서", m["name"]):
            frame.setdefault((y, q), m)
    order = sorted(frame, key=lambda k: (k[0], de.QORDER[k[1]]))
    series = de.pick_series(records)

    lines: list[str] = []

    def add(sheet, coord, kind, val):
        lines.append(f"{sheet}\t{coord}\t{kind}\t{val}")

    summary = []
    for sc in series:
        price, rev = {}, {}
        tok = sc["token"]
        for r in records:
            if (r.get("역할") == "단가" and r["항목"] in sc["labels"] and r["연도"]):
                price.setdefault((r["연도"], r["분기"]), r["값"])
            if (r.get("역할") == "매출액" and r["연도"] and tok
                    and tok in r["항목"]):
                rev.setdefault((r["연도"], r["분기"]), r["값"])

        sh, quarter = sc["sheet"], {}
        for i, (y, q) in enumerate(order):
            r = i + 2
            p, v = price.get((y, q)), rev.get((y, q))
            add(sh, f"E{r}", "num" if p is not None else "blank", p if p is not None else "")
            add(sh, f"G{r}", "num" if v is not None else "blank", v if v is not None else "")
            add(sh, f"C{r}", "text", f"{y} {q}")
            add(sh, f"D{r}", "text", "공시" if p is not None else "미공시")
            if q == "1Q":
                qq = p
            else:
                pq = {"2Q": "1Q", "3Q": "2Q", "4Q": "3Q"}[q]
                pp, pv = price.get((y, pq)), rev.get((y, pq))
                qq = None
                if p and pp and v is not None and pv is not None:
                    dvol = v / p - pv / pp
                    qq = (v - pv) / dvol if dvol else None
            quarter[(y, q)] = qq
            add(sh, f"F{r}", "num" if qq else "blank", qq if qq else "")

        pub = [k for k in order if price.get(k)]
        if pub:
            hi = max(pub, key=lambda k: price[k])
            lo = min(pub, key=lambda k: price[k])
            la = pub[-1]
            summary.append((sc, len(pub), price[hi], hi, price[lo], lo, price[la], la,
                            price))

    r0 = 11
    for i, (sc, n, hv, hk, lv, lk, av, ak, price) in enumerate(summary):
        rr = r0 + 2 + i
        # 요약 품목별 표: B품목 C단위 D공시분기 E최고 F최고시점 G최저 H최저시점 I최근 J최근시점
        for col, kind, val in [("D", "num", n), ("E", "num", hv),
                               ("F", "text", f"{hk[0]} {hk[1]}"), ("G", "num", lv),
                               ("H", "text", f"{lk[0]} {lk[1]}"), ("I", "num", av),
                               ("J", "text", f"{ak[0]} {ak[1]}")]:
            add("요약", f"{col}{rr}", kind, val)

    r1 = r0 + len(series) + 4
    years = sorted({y for (y, q) in order})
    for i, (sc, *_rest) in enumerate(summary):
        price = _rest[-1]
        rr = r1 + 2 + i
        for j, y in enumerate(years):
            v = price.get((y, "4Q"))
            coord = f"{get_column_letter(4+j)}{rr}"
            add("요약", coord, "num" if v is not None else "blank",
                v if v is not None else "")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"기대값 {len(lines)}셀 · 품목 {len(series)}종 · 분기 {len(order)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
