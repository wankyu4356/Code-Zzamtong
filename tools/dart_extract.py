#!/usr/bin/env python3
"""
수집된 인선이엔티 정기보고서 원문에서 '단가' 관련 항목을 전량 발췌하고,
매립단가를 2016년 이후 분기별로 정리해 엑셀로 출력한다.

  python3 tools/dart_extract.py --raw data/raw --xlsx <공시목록.xlsx> --out out/인선이엔티_매립단가_분기.xlsx

출력 시트
  1. 매립단가_분기      : 2016 1Q ~ 최신 분기 매립단가 시계열 (보고서 공시 기준)
  2. 단가항목_전체      : 매립 외 전 품목 단가 (소각/중간처리/순환골재/폐차/원재료 등)
  3. 원자료_발췌표      : '단가/가격변동' 관련 표를 원본 그대로 셀 단위 발췌
  4. 출처_공시목록      : 발췌에 사용한 공시 목록 + DART 원문 링크
  5. 수집로그          : 보고서별 수집·발췌 성공 여부
"""
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

import lxml.html

# ── 발췌 대상 판별 ────────────────────────────────────────────────────────────
DANGA_HINT = re.compile(r"단가|가격\s*변동|가격변동추이|판매\s*가격|매입\s*가격")
# 표 안에서 뽑아낼 품목 라벨
ITEM_HINT = re.compile(
    r"매립|소각|중간처리|건설폐기물|순환골재|폐차|자동차\s*재활용|해체|수집\s*운반|"
    r"수집운반|지정폐기물|사업장|생활폐기물|고철|비철|재활용|운반|처리")
LANDFILL = re.compile(r"매립")
# 매립'량'·매립'시설' 등 단가가 아닌 행을 걸러내기 위한 보조 패턴
NON_PRICE = re.compile(
    r"(잔여|누적|총)?\s*매립\s*(량|용량|시설|면적|가능)|매립가능|매립잔여")
# 단가 표가 아닌 수량·금액 행 (요약 시트에서 제외)
NON_PRICE_ROW = re.compile(
    r"용량|처리량|반입량|생산량|판매량|매출액|매출액|면적|톤수|인원|명|㎡|㎥|"
    r"자본금|자산|부채|주식|지분|합\s*계|소\s*계")
NUM = re.compile(r"^-?[\d,]+(?:\.\d+)?$")

QMAP = {"03": "1Q", "06": "2Q", "09": "3Q", "12": "4Q"}


# ── 표 파싱 (rowspan/colspan 전개) ────────────────────────────────────────────
def table_to_grid(tbl) -> list[list[str]]:
    grid: dict[tuple[int, int], str] = {}
    occupied: set[tuple[int, int]] = set()
    for r, tr in enumerate(tbl.xpath(".//tr")):
        c = 0
        for cell in tr.xpath("./td|./th"):
            while (r, c) in occupied:
                c += 1
            text = re.sub(r"\s+", " ", cell.text_content()).strip()
            try:
                rs = max(1, int(cell.get("rowspan") or 1))
                cs = max(1, int(cell.get("colspan") or 1))
            except ValueError:
                rs = cs = 1
            for dr in range(rs):
                for dc in range(cs):
                    occupied.add((r + dr, c + dc))
                    grid[(r + dr, c + dc)] = text
            c += cs
    if not grid:
        return []
    rows = max(k[0] for k in grid) + 1
    cols = max(k[1] for k in grid) + 1
    return [[grid.get((r, c), "") for c in range(cols)] for r in range(rows)]


def preceding_context(tbl, limit: int = 400) -> str:
    """표 직전의 제목/문단 텍스트만 문맥으로 수집 (앞선 표 내용은 제외)."""
    parts: list[str] = []
    node = tbl
    while node is not None and len(" ".join(parts)) < limit:
        prev = node.getprevious()
        while prev is not None:
            if prev.tag == "table" or prev.xpath(".//table"):
                prev = prev.getprevious()   # 표는 문맥에서 배제
                continue
            t = re.sub(r"\s+", " ", prev.text_content()).strip()
            if t:
                parts.append(t)
                break
            prev = prev.getprevious()
        if prev is None:
            node = node.getparent()
            continue
        node = prev
    return " | ".join(reversed(parts))[-limit:]


def parse_num(s: str) -> float | None:
    s = s.strip().replace(" ", "")
    if not s or not NUM.match(s):
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


# ── 보고서 기간 판정 ──────────────────────────────────────────────────────────
def report_period(name: str, date: str) -> tuple[int, str] | tuple[None, None]:
    """'분기보고서 (2016.03)' → (2016, '1Q')"""
    m = re.search(r"\((\d{4})\.(\d{2})\)", name)
    if m:
        y, mm = int(m.group(1)), m.group(2)
        if mm in QMAP:
            return y, QMAP[mm]
    m = re.search(r"(\d{4})[.\-](\d{2})", name)
    if m and m.group(2) in QMAP:
        return int(m.group(1)), QMAP[m.group(2)]
    return None, None


def basis_of(name: str) -> str:
    """공시 수치의 집계 기준(누계/연간)을 표기."""
    if "사업보고서" in name:
        return "연간 누계"
    if "반기보고서" in name:
        return "반기 누계(1~6월)"
    if "(09)" in name or ".09)" in name:
        return "3분기 누계(1~9월)"
    if "분기보고서" in name:
        return "분기 누계"
    return ""


# ── 메인 ─────────────────────────────────────────────────────────────────────
def load_manifest(xlsx: Path) -> dict[str, dict]:
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    ws = wb["공시목록"]
    head = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    i = {n: head.index(n) for n in ("접수일자", "보고서명", "제출인", "접수번호", "공시 링크")}
    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        rcp = str(row[i["접수번호"]]).strip()
        out[rcp] = {"date": row[i["접수일자"]], "name": (row[i["보고서명"]] or "").strip(),
                    "filer": row[i["제출인"]], "rcp": rcp, "url": row[i["공시 링크"]]}
    return out


def extract(raw: Path, manifest: dict) -> tuple[list[dict], list[dict]]:
    """(발췌 셀 레코드, 보고서별 로그) 반환."""
    records: list[dict] = []
    log: list[dict] = []

    for d in sorted(p for p in raw.iterdir() if p.is_dir()):
        rcp = d.name.split("_")[-1]
        meta = manifest.get(rcp, {"date": d.name.split("_")[0], "name": "?",
                                  "rcp": rcp, "url": ""})
        year, q = report_period(meta["name"], meta["date"])
        n_tables = n_hit = 0

        for f in sorted(d.glob("*")):
            if f.suffix.lower() not in (".xml", ".html", ".htm") or f.name == "_main.html":
                continue
            try:
                doc = lxml.html.fromstring(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue

            for ti, tbl in enumerate(doc.xpath("//table")):
                n_tables += 1
                grid = table_to_grid(tbl)
                if len(grid) < 2:
                    continue
                flat = " ".join(" ".join(r) for r in grid)
                ctx = preceding_context(tbl)
                is_price_tbl = bool(DANGA_HINT.search(flat) or DANGA_HINT.search(ctx))
                if not is_price_tbl:
                    continue
                n_hit += 1

                # 헤더 행 = 숫자가 가장 적은 상단 1~3행 중 마지막
                hdr_i = 0
                for r in range(min(3, len(grid))):
                    if sum(1 for c in grid[r] if parse_num(c) is not None) == 0:
                        hdr_i = r
                header = grid[hdr_i]

                for r in range(hdr_i + 1, len(grid)):
                    row = grid[r]
                    label = " ".join(dict.fromkeys(
                        [c for c in row[:3] if c and parse_num(c) is None])).strip()
                    if not label:
                        continue
                    for c, cell in enumerate(row):
                        v = parse_num(cell)
                        if v is None:
                            continue
                        col = header[c] if c < len(header) else ""
                        records.append({
                            "접수일자": meta["date"], "보고서명": meta["name"],
                            "접수번호": rcp, "링크": meta["url"],
                            "연도": year, "분기": q, "집계기준": basis_of(meta["name"]),
                            "문맥": ctx[-180:], "표번호": f"{f.name}#{ti}",
                            "항목": label, "열머리": col, "값": v, "원문": cell,
                            "매립여부": bool(LANDFILL.search(label)
                                          and not NON_PRICE.search(label)
                                          and not NON_PRICE_ROW.search(label)),
                            "단가성": not bool(NON_PRICE_ROW.search(label)
                                            or NON_PRICE.search(label)),
                        })

        log.append({"접수일자": meta["date"], "보고서명": meta["name"], "접수번호": rcp,
                    "표 총수": n_tables, "단가관련 표": n_hit, "링크": meta["url"]})
    return records, log


def build_workbook(records, log, manifest, out: Path) -> None:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    hdr_fill = PatternFill("solid", fgColor="D6D2C4")
    hdr_font = Font(bold=True, color="000000")
    thin = Side(style="thin", color="A5AAAA")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def sheet(title, headers, rows, widths=None, numfmt=None):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for c in range(1, len(headers) + 1):
            cell = ws.cell(1, c)
            cell.fill, cell.font, cell.border = hdr_fill, hdr_font, border
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for r in rows:
            ws.append(r)
        for c in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(c)].width = (widths or {}).get(c, 16)
        if numfmt:
            for col, fmt in numfmt.items():
                for r in range(2, ws.max_row + 1):
                    ws.cell(r, col).number_format = fmt
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        return ws

    # 1) 매립단가 분기 시계열
    land = [r for r in records if r["매립여부"] and r["연도"]]
    series: dict[tuple[int, str], dict] = {}
    for r in land:
        # 각 보고서의 '당기(첫 수치 열)' 값을 해당 분기 값으로 채택
        k = (r["연도"], r["분기"])
        cur = series.get(k)
        if cur is None or r["표번호"] < cur["표번호"]:
            series[k] = r
    qorder = ["1Q", "2Q", "3Q", "4Q"]
    rows = []
    for (y, q) in sorted(series, key=lambda k: (k[0], qorder.index(k[1]))):
        r = series[(y, q)]
        rows.append([y, q, f"{y} {q}", r["항목"], r["값"], r["열머리"], r["집계기준"],
                     r["보고서명"], r["접수일자"], r["접수번호"], r["링크"]])
    sheet("매립단가_분기",
          ["연도", "분기", "기간", "항목", "단가", "공시 열머리", "집계기준",
           "출처 보고서", "접수일자", "접수번호", "DART 링크"],
          rows, widths={3: 12, 4: 22, 5: 14, 6: 20, 7: 16, 8: 24, 11: 46},
          numfmt={5: "#,##0"})

    # 2) 매립 외 전 품목 단가
    others = [r for r in records
              if not r["매립여부"] and r["단가성"]
              and (ITEM_HINT.search(r["항목"]) or DANGA_HINT.search(r["항목"])
                   or DANGA_HINT.search(r["문맥"]))]
    sheet("단가항목_전체",
          ["연도", "분기", "항목", "단가", "공시 열머리", "집계기준", "문맥",
           "출처 보고서", "접수번호", "DART 링크"],
          [[r["연도"], r["분기"], r["항목"], r["값"], r["열머리"], r["집계기준"],
            r["문맥"], r["보고서명"], r["접수번호"], r["링크"]] for r in others],
          widths={3: 28, 7: 60, 8: 24, 10: 46}, numfmt={4: "#,##0.##"})

    # 3) 원자료 전량
    sheet("원자료_발췌표",
          ["접수일자", "보고서명", "접수번호", "연도", "분기", "표번호", "문맥",
           "항목", "열머리", "값", "원문", "DART 링크"],
          [[r["접수일자"], r["보고서명"], r["접수번호"], r["연도"], r["분기"],
            r["표번호"], r["문맥"], r["항목"], r["열머리"], r["값"], r["원문"], r["링크"]]
           for r in records],
          widths={2: 24, 7: 60, 8: 28, 12: 46})

    # 4) 출처 공시목록
    used = {r["접수번호"] for r in records} or {l["접수번호"] for l in log}
    src = [manifest[k] for k in sorted(used) if k in manifest]
    src.sort(key=lambda m: m["date"])
    sheet("출처_공시목록",
          ["접수일자", "보고서명", "제출인", "접수번호", "DART 원문 링크"],
          [[m["date"], m["name"], m["filer"], m["rcp"], m["url"]] for m in src],
          widths={2: 30, 5: 52})

    # 5) 수집 로그
    sheet("수집로그",
          ["접수일자", "보고서명", "접수번호", "표 총수", "단가관련 표", "DART 링크"],
          [[l["접수일자"], l["보고서명"], l["접수번호"], l["표 총수"],
            l["단가관련 표"], l["링크"]] for l in log],
          widths={2: 30, 6: 46})

    wb.remove(wb["Sheet"])
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"저장: {out}  (매립 {len(rows)}분기 / 전체 발췌 {len(records)}셀)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=Path("data/raw"), type=Path)
    ap.add_argument("--xlsx", required=True, type=Path)
    ap.add_argument("--out", default=Path("out/인선이엔티_매립단가_분기.xlsx"), type=Path)
    args = ap.parse_args()

    if not args.raw.exists() or not any(args.raw.iterdir()):
        print(f"원문이 없습니다: {args.raw}  → 먼저 tools/dart_fetch.py 를 실행하세요.")
        return 2
    manifest = load_manifest(args.xlsx)
    records, log = extract(args.raw, manifest)
    build_workbook(records, log, manifest, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
