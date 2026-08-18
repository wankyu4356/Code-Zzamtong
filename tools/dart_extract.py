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
import gzip
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
    r"용량|처리량|반입량|생산량|판매량|매출액|면적|톤수|인원|명|㎡|㎥|"
    r"자본|자산|부채|이익잉여금|영업이익|당기순|주식|지분|합\s*계|소\s*계|총\s*계")
NUM = re.compile(r"^-?[\d,]+(?:\.\d+)?$")

# 표가 아니라 서술형 문장 속에 들어 있는 단가 언급을 잡기 위한 패턴
PROSE_HINT = re.compile(
    r"단가|톤당|톤\s*당|원/톤|원\s*/\s*톤|처리비|처리비용|반입료|반입\s*단가|"
    r"판가|매립\s*가격|가격\s*(인상|인하|상승|하락|변동|경쟁)|"
    r"요율|수수료율|평균\s*가격|평균\s*단가|공급\s*가격")
# 산문에서 뽑아낼 금액·비율 표현
MONEY = re.compile(
    r"[\d,]+(?:\.\d+)?\s*(?:원\s*/\s*톤|원/톤|천원|백만원|억원|원|%|퍼센트)")
SENT_SPLIT = re.compile(r"(?<=[.。!?])\s+|\n+")

# 단일분기 역산에 쓸 부문별 누계 매출액 표
REV_HINT = re.compile(r"매출\s*실적|매출\s*및\s*수주|매출액|생산\s*및\s*매출|부문별\s*매출")
REV_ROW = re.compile(r"매출|수익")

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


def preceding_context(tbl, limit: int = 400) -> tuple[str, str]:
    """표 직전의 제목/문단 텍스트를 (근접문맥, 전체문맥) 으로 반환.

    근접문맥 = 표 바로 앞 2개 문단. 표 종류(단가표/매출표) 판정에 쓴다.
    전체문맥 = 최대 limit 자. 사람이 읽는 출처 표기에 쓴다.
    앞선 '표'의 내용은 문맥에서 제외한다 (인접 표끼리 오염되는 문제 방지).
    """
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
    near = " | ".join(parts[:2])
    return near, " | ".join(reversed(parts))[-limit:]


def extract_prose(doc) -> list[tuple[str, str]]:
    """표를 제거한 뒤 본문에서 단가를 언급한 문장을 (문장, 추출된 금액) 으로 반환."""
    import copy
    d = copy.deepcopy(doc)
    for t in d.xpath("//table"):
        parent = t.getparent()
        if parent is not None:
            parent.remove(t)

    chunks: list[str] = []
    leaves = d.xpath("//p|//li|//div|//span")
    for el in leaves:
        if el.xpath(".//p|.//li|.//div"):      # 컨테이너는 건너뛰고 말단만
            continue
        t = re.sub(r"\s+", " ", el.text_content()).strip()
        if t:
            chunks.append(t)
    if not chunks:                              # 태그가 빈약한 옛 문서 대비
        raw = re.sub(r"[ \t]+", " ", d.text_content())
        chunks = [c.strip() for c in raw.split("\n") if c.strip()]

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for chunk in chunks:
        for sent in SENT_SPLIT.split(chunk):
            sent = sent.strip()
            if len(sent) < 8 or len(sent) > 600:
                continue
            if not PROSE_HINT.search(sent):
                continue
            if sent in seen:
                continue
            # 숫자 없는 짧은 표 제목·단위 표기는 문장으로 보지 않음
            if len(sent) < 20 and not re.search(r"\d", sent):
                continue
            seen.add(sent)
            out.append((sent, ", ".join(dict.fromkeys(MONEY.findall(sent)))))
    return out


# 2016~2018년 보고서는 셀 안에 단위를 함께 적었다: "32,043원/톤"
UNIT_SUFFIX = re.compile(
    r"(원/(톤|대|kg|ℓ|L|리터)|원|천원|백만원|억원|톤|대|배|주|건|명)+$")
PERCENT = re.compile(r"[%％]|퍼센트")


def parse_num(s: str) -> float | None:
    s = s.strip().replace(" ", "").replace("\xa0", "")
    if not s or s in ("-", "－", "—", "·"):
        return None
    if PERCENT.search(s):        # 비율 셀은 단가·매출액이 아니므로 수치로 보지 않음
        return None
    neg = s.startswith("(") and s.endswith(")")     # 회계 표기 음수 (1,234)
    if neg:
        s = s[1:-1]
    s = UNIT_SUFFIX.sub("", s)
    if not s or not NUM.match(s):
        return None
    try:
        v = float(s.replace(",", ""))
    except ValueError:
        return None
    return -v if neg else v


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


def extract(raw: Path, manifest: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """(표 발췌 셀, 산문 발췌 문장, 보고서별 로그) 반환.

    표 레코드에는 부문별 누계 매출액(단일분기 단가 역산용)도 '종류'='매출' 로 포함된다.
    """
    records: list[dict] = []
    prose: list[dict] = []
    log: list[dict] = []
    blank_land: dict[str, str] = {}      # 접수번호 -> 매립 행 원문 ('-' 등)

    for d in sorted(p for p in raw.iterdir() if p.is_dir()):
        rcp = d.name.split("_")[-1]
        meta = manifest.get(rcp, {"date": d.name.split("_")[0], "name": "?",
                                  "rcp": rcp, "url": ""})
        year, q = report_period(meta["name"], meta["date"])
        n_tables = n_hit = n_prose = 0

        for f in sorted(d.glob("*")):
            if not re.search(r"\.(xml|html?)(\.gz)?$", f.name, re.I) or f.name.startswith("_"):
                continue
            try:
                if f.name.endswith(".gz"):
                    with gzip.open(f, "rt", encoding="utf-8") as fh:
                        text = fh.read()
                else:
                    text = f.read_text(encoding="utf-8")
                if not text.strip():
                    continue
                doc = lxml.html.fromstring(text)
            except Exception:  # noqa: BLE001
                continue

            for sent, money in extract_prose(doc):
                n_prose += 1
                prose.append({
                    "접수일자": meta["date"], "보고서명": meta["name"],
                    "접수번호": rcp, "링크": meta["url"],
                    "연도": year, "분기": q, "집계기준": basis_of(meta["name"]),
                    "파일": f.name, "문장": sent, "추출 금액": money,
                    "매립언급": bool(LANDFILL.search(sent)),
                })

            for ti, tbl in enumerate(doc.xpath("//table")):
                n_tables += 1
                grid = table_to_grid(tbl)
                if len(grid) < 2:
                    continue
                flat = " ".join(" ".join(r) for r in grid)
                near, ctx = preceding_context(tbl)
                # 표 종류 판정: 표 본문 > 바로 앞 문단 순으로 가중 (먼 제목에 끌려가지 않게)
                d_flat, r_flat = DANGA_HINT.search(flat), REV_HINT.search(flat)
                d_near, r_near = DANGA_HINT.search(near), REV_HINT.search(near)
                if d_flat and not r_flat:
                    kind = "단가"
                elif r_flat and not d_flat:
                    kind = "매출"
                elif d_near and not r_near:
                    kind = "단가"
                elif r_near and not d_near:
                    kind = "매출"
                elif d_flat or d_near:
                    kind = "단가"
                elif r_flat or r_near:
                    kind = "매출"
                else:
                    continue
                is_price_tbl = kind == "단가"
                if is_price_tbl:
                    n_hit += 1

                # 헤더 행 = 숫자가 가장 적은 상단 1~3행 중 마지막
                hdr_i = 0
                for r in range(min(3, len(grid))):
                    if any(parse_num(c) is not None for c in grid[r]):
                        break        # 숫자가 나오면 그 앞까지가 머리글
                    hdr_i = r
                header = grid[hdr_i]

                for r in range(hdr_i + 1, len(grid)):
                    row = grid[r]
                    # 빈칸 표시('-')는 품목명에 섞이지 않게 제외
                    label = " ".join(dict.fromkeys(
                        [c for c in row[:3]
                         if c and c not in ("-", "－", "—", "·")
                         and parse_num(c) is None])).strip()
                    if not label:
                        continue
                    # 단가표에 매립 행은 있는데 '당해연도 열'이 비어 있으면 미공시로 기록.
                    # 가격변동추이 표는 당기·전기·전전기를 함께 실으므로 당기 열만 본다.
                    if (is_price_tbl and LANDFILL.search(label)
                            and not NON_PRICE.search(label)):
                        yr_col = next((c for c in range(len(row))
                                       if c < len(header) and year
                                       and str(year) in (header[c] or "")), None)
                        raw_row = " | ".join(c for c in row if c)[:120]
                        if yr_col is not None:
                            if parse_num(row[yr_col]) is None:
                                blank_land.setdefault(
                                    rcp, f"{raw_row}  (당기 열 '{header[yr_col]}' = "
                                         f"'{row[yr_col] or ''}')")
                        elif not any(parse_num(c) is not None for c in row):
                            blank_land.setdefault(rcp, raw_row)
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
                            "종류": kind,
                            # NON_PRICE_ROW(매출액·물량 등)는 '단가표'에서만 배제한다.
                            # 매출표에서는 '매립 매출액' 행이 역산 입력이므로 살려야 한다.
                            "매립여부": bool(
                                LANDFILL.search(label)
                                and not NON_PRICE.search(label)
                                and not (is_price_tbl and NON_PRICE_ROW.search(label))),
                            "단가성": is_price_tbl and not bool(
                                NON_PRICE_ROW.search(label) or NON_PRICE.search(label)),
                        })

        log.append({"접수일자": meta["date"], "보고서명": meta["name"], "접수번호": rcp,
                    "표 총수": n_tables, "단가관련 표": n_hit,
                    "산문 단가언급": n_prose, "링크": meta["url"]})
    return records, prose, log, blank_land



QORDER = {"1Q": 1, "2Q": 2, "3Q": 3, "4Q": 4}
# 정기보고서 공시 수치의 누계 구간
BASIS = {"1Q": "1분기 누계(1~3월)", "2Q": "반기 누계(1~6월)",
         "3Q": "3분기 누계(1~9월)", "4Q": "연간 누계(1~12월)"}


def backout_quarterly(price_cum: dict, rev_cum: dict) -> dict:
    """누계 단가 + 누계 매출액에서 단일 분기 단가를 역산한다.

    정기보고서의 가격변동추이는 당해연도 누계 평균 단가(= 누계 매출액 ÷ 누계 처리량)다.
    따라서 누계 물량은 rev / price 로 복원할 수 있고, 인접 분기 차분을 취하면

        p_Q(n) = (rev(n) - rev(n-1)) / (rev(n)/p(n) - rev(n-1)/p(n-1))

    이 된다. 매출액 단위(원·천원·백만원)는 분자·분모에서 상쇄되므로 단위 환산이 필요 없다.
    1분기는 누계 = 단일분기이므로 공시값을 그대로 쓴다.
    반환값: {(연도, 분기): {"단가": float|None, "물량": float|None, "사유": str}}
    """
    out: dict = {}
    for (y, q), p_cum in price_cum.items():
        prev_q = {"2Q": "1Q", "3Q": "2Q", "4Q": "3Q"}.get(q)
        if prev_q is None:                       # 1분기: 누계 = 단일분기
            out[(y, q)] = {"단가": p_cum, "물량": None, "사유": "1분기 = 누계와 동일"}
            continue

        p_prev = price_cum.get((y, prev_q))
        r_now, r_prev = rev_cum.get((y, q)), rev_cum.get((y, prev_q))
        if p_prev is None:
            out[(y, q)] = {"단가": None, "물량": None, "사유": f"직전 {prev_q} 누계단가 없음"}
            continue
        if r_now is None or r_prev is None:
            out[(y, q)] = {"단가": None, "물량": None, "사유": "부문별 누계 매출액 미확보"}
            continue
        if not p_cum or not p_prev:
            out[(y, q)] = {"단가": None, "물량": None, "사유": "단가 0 또는 결측"}
            continue

        v_now, v_prev = r_now / p_cum, r_prev / p_prev
        d_rev, d_vol = r_now - r_prev, v_now - v_prev
        if d_vol <= 0 or d_rev <= 0:
            out[(y, q)] = {"단가": None, "물량": None,
                           "사유": "차분 물량/매출이 0 이하 (공시 정정·기준 변경 의심)"}
            continue
        note = f"{prev_q} 누계 차분으로 역산"
        # 공시 누계단가는 정수 반올림돼 있어, 분기 물량 비중이 작으면 오차가 증폭된다.
        share = d_vol / v_now if v_now else 0
        if share < 0.10:
            note += f" (분기 물량비중 {share:.1%} — 반올림 오차 증폭 주의)"
        out[(y, q)] = {"단가": d_rev / d_vol, "물량": d_vol, "사유": note}
    return out


def build_workbook(records, prose, log, manifest, blank_land, out: Path) -> None:
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

    # 1) 매립단가 분기 시계열 — 공시 누계 원값 + 단일분기 역산
    #    보고서가 존재하는 모든 분기를 빠짐없이 싣고, 값이 없으면 사유를 남긴다.
    land = [r for r in records
            if r["매립여부"] and r["연도"] and r["종류"] == "단가"]
    series: dict[tuple[int, str], dict] = {}
    for r in land:
        # 가격변동추이 표는 [당기 | 전기 | 전전기] 3개 연도를 나란히 싣는다.
        # '행에서 처음 나오는 숫자'를 쓰면 당기가 '-' 일 때 몇 해 전 값을 잘못
        # 집어오므로, 열머리에 보고서 당해연도가 박힌 열만 채택한다.
        if str(r["연도"]) not in (r["열머리"] or ""):
            continue
        k = (r["연도"], r["분기"])
        cur = series.get(k)
        if cur is None or r["표번호"] < cur["표번호"]:
            series[k] = r

    rev_rows = [r for r in records
                if r["매립여부"] and r["연도"] and r["종류"] == "매출"]
    rev_series: dict[tuple[int, str], float] = {}
    for r in rev_rows:
        k = (r["연도"], r["분기"])
        if k not in rev_series:
            rev_series[k] = r["값"]

    price_cum = {k: v["값"] for k, v in series.items()}
    bo = backout_quarterly(price_cum, rev_series)

    # 실제로 원문을 수집한 정기보고서의 분기만 프레임으로 삼는다
    collected = {l["접수번호"] for l in log}
    frame: dict[tuple[int, str], dict] = {}
    for m in manifest.values():
        if m["rcp"] not in collected:
            continue
        y, q = report_period(m["name"], m["date"])
        if y and re.search(r"(사업|반기|분기)보고서", m["name"]):
            frame.setdefault((y, q), m)

    rows = []
    for (y, q) in sorted(frame, key=lambda k: (k[0], QORDER[k[1]])):
        m = frame[(y, q)]
        r = series.get((y, q))
        b = bo.get((y, q), {})
        if r is not None:
            rows.append([y, q, f"{y} {q}", r["항목"], r["값"], r["열머리"], BASIS[q],
                         rev_series.get((y, q)), b.get("단가"), b.get("물량"),
                         b.get("사유"), "공시", m["name"], m["date"], m["rcp"], m["url"]])
        else:
            raw = blank_land.get(m["rcp"])
            why = (f"보고서 단가표에 매립 행이 '{raw}' 로 비어 있음 (해당 사업 단가 미공시)"
                   if raw else "보고서 단가표에서 매립 단가 항목을 찾지 못함")
            rows.append([y, q, f"{y} {q}", "매립폐기물 최종처리용역", None, None, BASIS[q],
                         rev_series.get((y, q)), None, None, why,
                         "미공시", m["name"], m["date"], m["rcp"], m["url"]])

    sheet("매립단가_분기",
          ["연도", "분기", "기간", "항목", "공시 단가(누계)", "공시 열머리", "집계기준",
           "누계 매출액(공시단위)", "단일분기 단가(역산)", "단일분기 물량(상대값)", "비고",
           "상태", "출처 보고서", "접수일자", "접수번호", "DART 링크"],
          rows, widths={3: 12, 4: 24, 5: 16, 6: 16, 7: 18, 8: 20, 9: 18, 10: 20,
                        11: 52, 12: 10, 13: 24, 16: 46},
          numfmt={5: "#,##0", 8: "#,##0", 9: "#,##0", 10: "#,##0"})
    ws_l = wb["매립단가_분기"]
    for rr in range(2, ws_l.max_row + 1):
        ws_l.cell(rr, 11).alignment = Alignment(wrap_text=True, vertical="top")

    # 2) 매립 외 전 품목 단가
    NOISE = re.compile(r"^증감|증감율|증감률|전년대비|비\s*율$")
    others = [r for r in records
              if r["단가성"] and not NOISE.search(r["항목"])
              and (ITEM_HINT.search(r["항목"]) or DANGA_HINT.search(r["항목"])
                   or DANGA_HINT.search(r["문맥"]))]
    sheet("단가항목_전체",
          ["연도", "분기", "항목", "단가", "공시 열머리", "집계기준", "문맥",
           "출처 보고서", "접수번호", "DART 링크"],
          [[r["연도"], r["분기"], r["항목"], r["값"], r["열머리"], r["집계기준"],
            r["문맥"], r["보고서명"], r["접수번호"], r["링크"]] for r in others],
          widths={3: 28, 7: 60, 8: 24, 10: 46}, numfmt={4: "#,##0.##"})

    # 2-2) 품목 × 분기 피벗 — 각 보고서의 '당해연도 열' 값만 사용
    piv: dict[str, dict[tuple[int, str], float]] = {}
    for r in records:
        if not r["단가성"] or not r["연도"] or NOISE.search(r["항목"]):
            continue
        if str(r["연도"]) not in (r["열머리"] or ""):
            continue
        if not (ITEM_HINT.search(r["항목"]) or DANGA_HINT.search(r["항목"])):
            continue
        piv.setdefault(r["항목"], {}).setdefault((r["연도"], r["분기"]), r["값"])
    periods = sorted({k for v in piv.values() for k in v},
                     key=lambda k: (k[0], QORDER[k[1]]))
    sheet("단가_품목별_분기",
          ["품목"] + [f"{y} {q}" for y, q in periods],
          [[item] + [vals.get(k) for k in periods]
           for item, vals in sorted(piv.items(), key=lambda kv: -len(kv[1]))],
          widths={1: 36}, numfmt={c: "#,##0.##" for c in range(2, len(periods) + 2)})

    # 3) 원자료 전량
    sheet("원자료_발췌표",
          ["접수일자", "보고서명", "접수번호", "연도", "분기", "종류", "표번호", "문맥",
           "항목", "열머리", "값", "원문", "DART 링크"],
          [[r["접수일자"], r["보고서명"], r["접수번호"], r["연도"], r["분기"], r["종류"],
            r["표번호"], r["문맥"], r["항목"], r["열머리"], r["값"], r["원문"], r["링크"]]
           for r in records],
          widths={2: 24, 8: 60, 9: 28, 13: 46})

    # 3-2) 산문 속 단가 언급
    prose_sorted = sorted(prose, key=lambda r: (not r["매립언급"], r["접수일자"]))
    sheet("산문_단가언급",
          ["연도", "분기", "매립 언급", "단가 언급 문장", "추출 금액",
           "출처 보고서", "접수일자", "접수번호", "파일", "DART 링크"],
          [[r["연도"], r["분기"], "O" if r["매립언급"] else "", r["문장"],
            r["추출 금액"], r["보고서명"], r["접수일자"], r["접수번호"],
            r["파일"], r["링크"]] for r in prose_sorted],
          widths={3: 10, 4: 90, 5: 24, 6: 24, 10: 46})
    ws = wb["산문_단가언급"]
    for r in range(2, ws.max_row + 1):
        ws.cell(r, 4).alignment = Alignment(wrap_text=True, vertical="top")

    # 4) 출처 공시목록
    used = ({r["접수번호"] for r in records} | {r["접수번호"] for r in prose}
            or {l["접수번호"] for l in log})
    src = [manifest[k] for k in sorted(used) if k in manifest]
    src.sort(key=lambda m: m["date"])
    sheet("출처_공시목록",
          ["접수일자", "보고서명", "제출인", "접수번호", "DART 원문 링크"],
          [[m["date"], m["name"], m["filer"], m["rcp"], m["url"]] for m in src],
          widths={2: 30, 5: 52})

    # 5) 수집 로그
    sheet("수집로그",
          ["접수일자", "보고서명", "접수번호", "표 총수", "단가관련 표",
           "산문 단가언급", "DART 링크"],
          [[l["접수일자"], l["보고서명"], l["접수번호"], l["표 총수"],
            l["단가관련 표"], l["산문 단가언급"], l["링크"]] for l in log],
          widths={2: 30, 7: 46})

    wb.remove(wb["Sheet"])
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"저장: {out}  (매립 {len(rows)}분기 / 표 발췌 {len(records)}셀 / "
          f"산문 발췌 {len(prose)}문장)")


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
    records, prose, log, blank_land = extract(args.raw, manifest)
    build_workbook(records, prose, log, manifest, blank_land, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
