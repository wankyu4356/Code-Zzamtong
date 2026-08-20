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
                # 한 칸짜리 짧은 표는 '(단위 : 천원/톤)' 같은 캡션이므로 살린다.
                # (코엔텍은 단위 표기를 별도 table 로 넣는다)
                cells = prev.xpath(".//td|.//th")
                txt = re.sub(r"\s+", " ", prev.text_content()).strip()
                if len(cells) <= 2 and len(txt) <= 60 and txt:
                    parts.append(txt)
                    break
                prev = prev.getprevious()   # 데이터 표는 문맥에서 배제
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


# 열머리에서 그 열이 무슨 값인지 판별한다. 회사마다 표기가 달라
# ('매출액' vs '제33기 금액') SUMIFS 기준을 이 역할값으로 통일한다.
# 표 앞의 '(단위 : 원/톤)' 같은 표기. 회사마다 원/톤·천원/톤으로 달라 반드시 읽어야 한다.
UNIT_RE = re.compile(r"단위\s*[:：]\s*([^)\]|]+)")
MONEY_COL = re.compile(r"금액|매출액")
QTY_COL = re.compile(r"수량|물량")


def role(kind: str, col: str, cur: bool) -> str:
    if not cur:
        return ""
    if kind == "단가":
        return "단가"
    if QTY_COL.search(col or ""):
        return "수량"
    if MONEY_COL.search(col or "") or not (col or "").strip():
        return "매출액"
    return ""


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
    """공시목록 엑셀을 접수번호 -> 메타 딕셔너리로 읽는다 (열 이름 배포차 흡수)."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from dart_fetch import read_manifest_rows
    return {rec["rcp"]: rec for rec in read_manifest_rows(xlsx)}


def extract(raw: Path, manifest: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """(표 발췌 셀, 산문 발췌 문장, 보고서별 로그) 반환.

    표 레코드에는 부문별 누계 매출액(단일분기 단가 역산용)도 '종류'='매출' 로 포함된다.
    """
    records: list[dict] = []
    prose: list[dict] = []
    log: list[dict] = []
    # (품목명, 접수번호) -> 그 행의 원문. 단가표에 품목 행은 있는데 당해연도
    # 열이 비어 있는 경우를 '미공시' 근거로 남긴다.
    blank_land: dict[tuple[str, str], str] = {}

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
                um = UNIT_RE.search(near) or UNIT_RE.search(ctx)
                unit = re.sub(r"\s+", "", um.group(1))[:12] if um else ""
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

                # 머리글 = 상단의 연속된 비수치 행. 중간에 값이 전부 '-' 인
                # 데이터 행을 머리글로 오인하지 않도록 첫 숫자 앞까지만 본다.
                hdr_i = 0
                for r in range(min(3, len(grid))):
                    if any(parse_num(c) is not None for c in grid[r]):
                        break
                    hdr_i = r
                # 열별 머리글을 상단 행들에서 합성한다.
                # 코엔텍 매출실적처럼 '제33기 / 수량·금액' 2단 머리글을 쓰는 표가 있다.
                ncol = max(len(g) for g in grid)
                header = []
                for c in range(ncol):
                    parts = [grid[r][c] for r in range(hdr_i + 1)
                             if c < len(grid[r]) and grid[r][c]]
                    header.append(" ".join(dict.fromkeys(parts)).strip())
                top = grid[0] if grid else []

                # 당기 열: 숫자가 처음 나오는 열과 최상단 머리글이 같은 열들.
                # (인선은 '2026년(제30기)', 코엔텍은 '제33기' 처럼 표기가 달라
                #  연도 문자열 매칭 대신 위치로 판정한다.)
                cur_col = None
                for c in range(ncol):
                    if any(c < len(grid[r]) and parse_num(grid[r][c]) is not None
                           for r in range(hdr_i + 1, len(grid))):
                        cur_col = c
                        break
                cur_top = top[cur_col] if (cur_col is not None
                                           and cur_col < len(top)) else None
                is_cur = [bool(cur_top) and c < len(top) and top[c] == cur_top
                          for c in range(ncol)]
                if cur_col is not None and not any(is_cur):
                    is_cur = [c == cur_col for c in range(ncol)]

                for r in range(hdr_i + 1, len(grid)):
                    row = grid[r]
                    # 빈칸 표시('-')는 품목명에 섞이지 않게 제외
                    label = " ".join(dict.fromkeys(
                        [c for c in row[:3]
                         if c and c not in ("-", "－", "—", "·")
                         and parse_num(c) is None])).strip()
                    if not label:
                        continue
                    # 단가표에 품목 행은 있는데 '당해연도 열'이 비어 있으면 미공시로 기록.
                    # 가격변동추이 표는 당기·전기·전전기를 함께 실으므로 당기 열만 본다.
                    if is_price_tbl and not NON_PRICE.search(label):
                        yr_col = next((c for c in range(ncol) if is_cur[c]), None)
                        raw_row = " | ".join(c for c in row if c)[:120]
                        if yr_col is not None and yr_col < len(row):
                            if parse_num(row[yr_col]) is None:
                                blank_land.setdefault(
                                    (label, rcp),
                                    f"{raw_row}  (당기 열 '{header[yr_col]}' = "
                                    f"'{row[yr_col] or ''}')")
                        elif not any(parse_num(c) is not None for c in row):
                            blank_land.setdefault((label, rcp), raw_row)
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
                            "종류": kind, "당기": "Y" if is_cur[c] else "",
                            "역할": role(kind, col, is_cur[c]),
                            "단위": unit,
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

# 품목명을 짧은 시트 키로 바꾼다 (시트 이름과 수식 참조에 쓰인다)
KEY_PATTERNS = [
    (re.compile(r"매립"), "매립"),
    (re.compile(r"소각"), "소각"),
    (re.compile(r"중간처리"), "중간처리"),
    (re.compile(r"순환골재|콘크리트용|도로공사용"), "순환골재"),
    (re.compile(r"스팀|증기|열공급"), "스팀"),
    (re.compile(r"수집.?운반"), "수집운반"),
    (re.compile(r"폐차|자동차"), "자동차재활용"),
    (re.compile(r"고철|비철|금속"), "금속재생"),
]
# 재무제표 항목이 단가표로 새어 들어온 경우를 시리즈 후보에서 제외
FINANCIAL = re.compile(
    r"자산|부채|자본|잉여금|영업이익|당기순|현금및|매출채권|재고자산|유형자산|무형자산")
MIN_QUARTERS = 8        # 시리즈로 뽑을 최소 공시 분기 수

# 단위 문자열 -> 원 단위 배율. 매출액과 단가의 단위가 달라 검증식에 환산이 필요하다.
MONEY_SCALE = [("억원", 1e8), ("백만원", 1e6), ("천원", 1e3), ("원", 1.0)]


def money_scale(unit: str) -> float | None:
    for tok, v in MONEY_SCALE:
        if tok in (unit or ""):
            return v
    return None


def series_key(label: str, taken: set[str]) -> str:
    # 품목 셀(마지막 토큰) -> 라벨 전체 순으로 본다.
    # '소각부분(내수) 스팀판매' 는 앞에 '소각'이 있어도 품목은 '스팀'이다.
    parts = label.split()
    base = None
    for probe in ([parts[-1]] if parts else []) + [label]:
        for pat, key in KEY_PATTERNS:
            if pat.search(probe):
                base = key
                break
        if base:
            break
    if base is None:
        base = re.sub(r"[^\w가-힣]", "", label)[:6] or "품목"
    key, i = base, 2
    while key in taken:                      # 같은 키가 겹치면 번호를 붙인다
        key, i = f"{base}{i}", i + 1
    taken.add(key)
    return key


def revenue_token(label: str, rev_index: dict[str, set]) -> str | None:
    """단가 품목명에 대응하는 매출 행을 찾을 '포함 검색어'를 고른다.

    회사마다 표기가 달라 고정 규칙을 쓸 수 없다.
      인선  단가 '매립폐기물 최종처리용역' <-> 매출 '매립폐기물최종처리 용역 …'
                                              (2016년엔 '최종처분' 표기)
      코엔텍 단가 '소각부분(내수) 소각처리' <-> 매출 '소각부문 처리매출 소각처리'
    후보 토큰의 앞부분을 길이별로 잘라보며, 분기당 1건만 잡히는 것 중
    가장 많은 분기를 덮는 검색어를 고른다.
    """
    cells = [c for c in label.split() if c]
    cands = []
    for base in ([cells[-1]] if cells else []) + ([cells[0]] if cells else []) \
            + [label]:
        t = base.replace(" ", "")
        if len(t) >= 4 and t not in cands:
            cands.append(t)

    best = None
    for t in cands:
        for L in range(len(t), 3, -1):
            pref = t[:L]
            periods: dict[tuple, int] = {}
            for item, keys in rev_index.items():
                if pref in item:
                    for k in keys:
                        periods[k] = periods.get(k, 0) + 1
            if not periods or max(periods.values()) > 1:
                continue
            score = (len(periods), L)
            if best is None or score > best[0]:
                best = (score, pref)
    return best[1] if best else None


def pick_series(records) -> list[dict]:
    """단가표에서 자체 시계열 시트를 만들 품목을 고른다.

    각 보고서의 '당기 열'(역할='단가') 값이 MIN_QUARTERS 분기 이상 잡히는 품목만.
    """
    from collections import Counter, defaultdict
    cnt = Counter()
    for r in records:
        if (r.get("역할") == "단가" and r["단가성"]
                and r["연도"] and ITEM_HINT.search(r["항목"])
                and not FINANCIAL.search(r["항목"])):
            cnt[r["항목"]] += 1

    # 매출액 행 색인: 항목명(원문 그대로) -> 등장한 (연도, 분기) 집합.
    # 엑셀 SUMIFS 는 셀 원문에 와일드카드를 걸므로, 공백을 뺀 문자열로 고르면
    # '건설폐기물중간처리용역' 처럼 실제 셀('…중간처리 용역 …')에 없는 검색어가
    # 나올 수 있다. 반드시 원문 기준으로 찾는다.
    rev_index: dict[str, set] = defaultdict(set)
    for r in records:
        if r.get("역할") == "매출액" and r["연도"]:
            rev_index[r["항목"]].add((r["연도"], r["분기"]))

    # 품목별 공시 단위 ('원/톤' vs '천원/톤') — 회사마다 다르므로 원문에서 읽는다
    units: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        if r.get("역할") == "단가" and r.get("단위"):
            units[r["항목"]][r["단위"]] += 1
    rev_units: Counter = Counter()
    qty_seen: set = set()
    for r in records:
        if r.get("역할") == "매출액" and r.get("단위"):
            rev_units[r["단위"]] += 1
        if r.get("역할") == "수량" and r["연도"]:
            qty_seen.add(r["항목"])
    rev_unit = rev_units.most_common(1)[0][0] if rev_units else ""

    taken: set[str] = set()
    out = []
    for label, n in cnt.most_common():
        if n < MIN_QUARTERS:
            continue
        u = units[label].most_common(1)
        key = series_key(label, taken)
        unit = u[0][0] if u else "원/톤"
        # 검증식 배율: (매출액 단위) / (단가 금액 단위)
        pm, rm = money_scale(unit), money_scale(rev_unit)
        factor = (rm / pm) if (pm and rm) else None
        tok = revenue_token(label, rev_index)
        has_qty = any(tok and tok in it for it in qty_seen) if tok else False
        out.append({"label": label, "n": n, "token": tok, "key": key,
                    "sheet": f"{key}단가_분기", "unit": unit,
                    "rev_unit": rev_unit, "factor": factor, "has_qty": has_qty})
    return out


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
    """공시목록 엑셀을 접수번호 -> 메타 딕셔너리로 읽는다 (열 이름 배포차 흡수)."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from dart_fetch import read_manifest_rows
    return {rec["rcp"]: rec for rec in read_manifest_rows(xlsx)}


def extract(raw: Path, manifest: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """(표 발췌 셀, 산문 발췌 문장, 보고서별 로그) 반환.

    표 레코드에는 부문별 누계 매출액(단일분기 단가 역산용)도 '종류'='매출' 로 포함된다.
    """
    records: list[dict] = []
    prose: list[dict] = []
    log: list[dict] = []
    # (품목명, 접수번호) -> 그 행의 원문. 단가표에 품목 행은 있는데 당해연도
    # 열이 비어 있는 경우를 '미공시' 근거로 남긴다.
    blank_land: dict[tuple[str, str], str] = {}

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
                um = UNIT_RE.search(near) or UNIT_RE.search(ctx)
                unit = re.sub(r"\s+", "", um.group(1))[:12] if um else ""
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

                # 머리글 = 상단의 연속된 비수치 행. 중간에 값이 전부 '-' 인
                # 데이터 행을 머리글로 오인하지 않도록 첫 숫자 앞까지만 본다.
                hdr_i = 0
                for r in range(min(3, len(grid))):
                    if any(parse_num(c) is not None for c in grid[r]):
                        break
                    hdr_i = r
                # 열별 머리글을 상단 행들에서 합성한다.
                # 코엔텍 매출실적처럼 '제33기 / 수량·금액' 2단 머리글을 쓰는 표가 있다.
                ncol = max(len(g) for g in grid)
                header = []
                for c in range(ncol):
                    parts = [grid[r][c] for r in range(hdr_i + 1)
                             if c < len(grid[r]) and grid[r][c]]
                    header.append(" ".join(dict.fromkeys(parts)).strip())
                top = grid[0] if grid else []

                # 당기 열: 숫자가 처음 나오는 열과 최상단 머리글이 같은 열들.
                # (인선은 '2026년(제30기)', 코엔텍은 '제33기' 처럼 표기가 달라
                #  연도 문자열 매칭 대신 위치로 판정한다.)
                cur_col = None
                for c in range(ncol):
                    if any(c < len(grid[r]) and parse_num(grid[r][c]) is not None
                           for r in range(hdr_i + 1, len(grid))):
                        cur_col = c
                        break
                cur_top = top[cur_col] if (cur_col is not None
                                           and cur_col < len(top)) else None
                is_cur = [bool(cur_top) and c < len(top) and top[c] == cur_top
                          for c in range(ncol)]
                if cur_col is not None and not any(is_cur):
                    is_cur = [c == cur_col for c in range(ncol)]

                for r in range(hdr_i + 1, len(grid)):
                    row = grid[r]
                    # 빈칸 표시('-')는 품목명에 섞이지 않게 제외
                    label = " ".join(dict.fromkeys(
                        [c for c in row[:3]
                         if c and c not in ("-", "－", "—", "·")
                         and parse_num(c) is None])).strip()
                    if not label:
                        continue
                    # 단가표에 품목 행은 있는데 '당해연도 열'이 비어 있으면 미공시로 기록.
                    # 가격변동추이 표는 당기·전기·전전기를 함께 실으므로 당기 열만 본다.
                    if is_price_tbl and not NON_PRICE.search(label):
                        yr_col = next((c for c in range(ncol) if is_cur[c]), None)
                        raw_row = " | ".join(c for c in row if c)[:120]
                        if yr_col is not None and yr_col < len(row):
                            if parse_num(row[yr_col]) is None:
                                blank_land.setdefault(
                                    (label, rcp),
                                    f"{raw_row}  (당기 열 '{header[yr_col]}' = "
                                    f"'{row[yr_col] or ''}')")
                        elif not any(parse_num(c) is not None for c in row):
                            blank_land.setdefault((label, rcp), raw_row)
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
                            "종류": kind, "당기": "Y" if is_cur[c] else "",
                            "역할": role(kind, col, is_cur[c]),
                            "단위": unit,
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


def build_workbook(records, prose, log, manifest, blank_land, out: Path,
                   company: str = "") -> None:
    """워크북을 만든다.

    원문에서 발췌한 값만 상수로 쓰고(파란 글씨 = 입력), 파생값은 전부 수식과
    시트 간 참조로 계산한다(검정 = 수식).

        원자료_발췌표 ─┬─> 단가항목_전체 ─┬─> 단가_품목별_분기
                       │                  └─> <품목>단가_분기 ─> 요약
                       └────────────────────> <품목>단가_분기 (누계 매출액)
    """
    import openpyxl
    from openpyxl.chart import LineChart, Reference
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    INK, SECTION, GOLD = "73531D", "523227", "AB955D"
    CARD, LINE, MUTED, INPUT = "F7EFDA", "A5AAAA", "8A8A8A", "0000FF"
    FONT = "Arial"
    SERIES_COLORS = [SECTION, GOLD, "7C6A46", "A8763C", "5E7A6B", "8C5B4A"]

    thin = Side(style="thin", color=LINE)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill("solid", fgColor=SECTION)
    hdr_font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
    body_font = Font(name=FONT, size=10)

    wb = openpyxl.Workbook()

    def sheet(title, headers, rows, widths=None, numfmt=None, wrap=(), freeze="A2"):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for c in range(1, len(headers) + 1):
            cell = ws.cell(1, c)
            cell.fill, cell.font, cell.border = hdr_fill, hdr_font, border
            cell.alignment = Alignment(horizontal="center", vertical="center",
                                       wrap_text=True)
        ws.row_dimensions[1].height = 32
        for r in rows:
            ws.append(r)
        # 원문에서 뽑은 텍스트가 '=' 로 시작하면 엑셀이 수식으로 읽어 깨진다
        # (예: 문맥 "= 960톤/일 3공장 …"). 발췌 텍스트는 전부 문자열로 고정한다.
        # 진짜 수식은 이 뒤에 따로 써 넣으므로 영향받지 않는다.
        for row_cells in ws.iter_rows(min_row=2):
            for cell in row_cells:
                if cell.data_type == "f":
                    cell.data_type = "s"
        for c in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(c)].width = (widths or {}).get(c, 14)
        if ws.max_row <= 2000:          # 큰 시트는 셀 서식을 생략 (파일 비대화 방지)
            for r in range(2, ws.max_row + 1):
                for c in range(1, len(headers) + 1):
                    cell = ws.cell(r, c)
                    cell.font = body_font
                    cell.alignment = Alignment(
                        wrap_text=c in wrap, vertical="top",
                        horizontal=("right" if isinstance(cell.value, (int, float))
                                    else "left"))
        for col, fmt in (numfmt or {}).items():
            for r in range(2, ws.max_row + 1):
                ws.cell(r, col).number_format = fmt
        ws.freeze_panes = freeze
        if ws.max_row > 1:
            ws.auto_filter.ref = ws.dimensions
        return ws

    def sumifs(val_rng, pairs):
        args = ",".join(f"{rng},{crit}" for rng, crit in pairs)
        return f'=IF(COUNTIFS({args})=0,"",SUMIFS({val_rng},{args}))'

    # ── 원자료 · 단가항목 (모든 참조의 뿌리) ─────────────────────────────────
    RAW = "원자료_발췌표"
    raw_rows = [[r["접수일자"], r["보고서명"], r["접수번호"], r["연도"], r["분기"],
                 r["종류"], r.get("역할", ""), r["표번호"], r["문맥"], r["항목"],
                 r["열머리"], r["값"], r["원문"], r["링크"]] for r in records]
    nR = len(raw_rows) + 1

    NOISE = re.compile(r"^증감|증감율|증감률|전년대비|비\s*율$")
    others = [r for r in records
              if r["단가성"] and not NOISE.search(r["항목"])
              and (ITEM_HINT.search(r["항목"]) or DANGA_HINT.search(r["항목"])
                   or DANGA_HINT.search(r["문맥"]))]
    nT = len(others) + 1

    # 단가항목_전체 열: A연도 B분기 C항목 D단가 E열머리 F역할 …
    T_ITEM, T_YEAR, T_Q, T_VAL, T_ROLE = (f"단가항목_전체!$C$2:$C${nT}",
                                          f"단가항목_전체!$A$2:$A${nT}",
                                          f"단가항목_전체!$B$2:$B${nT}",
                                          f"단가항목_전체!$D$2:$D${nT}",
                                          f"단가항목_전체!$F$2:$F${nT}")
    # 원자료 열: D연도 E분기 F종류 G역할 J항목 L열머리 M값 …
    R_ITEM, R_YEAR, R_Q, R_ROLE, R_VAL = (f"{RAW}!$J$2:$J${nR}",
                                          f"{RAW}!$D$2:$D${nR}",
                                          f"{RAW}!$E$2:$E${nR}",
                                          f"{RAW}!$G$2:$G${nR}",
                                          f"{RAW}!$L$2:$L${nR}")

    # ── 분기 프레임 ─────────────────────────────────────────────────────────
    collected = {l["접수번호"] for l in log}
    frame: dict[tuple[int, str], dict] = {}
    for m in manifest.values():
        if m["rcp"] not in collected:
            continue
        y, q = report_period(m["name"], m["date"])
        if y and re.search(r"(사업|반기|분기)보고서", m["name"]):
            frame.setdefault((y, q), m)
    order = sorted(frame, key=lambda k: (k[0], QORDER[k[1]]))
    addr = {k: i + 2 for i, k in enumerate(order)}
    nL = len(order) + 1

    series = pick_series(records)

    # 품목별 '당기 열머리'와 매출액 단위는 발췌값이므로 상수로 둔다
    def col_headers(label):
        out = {}
        for r in records:
            if r.get("역할") == "단가" and r["항목"] == label and r["연도"]:
                out.setdefault((r["연도"], r["분기"]), r["열머리"])
        return out

    def rev_units_by_period(token):
        """(연도,분기) -> 그 보고서 매출표의 금액 단위.

        같은 회사도 보고서에 따라 천원/백만원을 오가므로 분기마다 읽어야 한다.
        """
        out = {}
        for r in records:
            if (r.get("역할") == "매출액" and r["연도"] and token
                    and token in r["항목"] and r.get("단위")):
                out.setdefault((r["연도"], r["분기"]), r["단위"])
        return out

    # ── 품목별 분기 시계열 시트 ─────────────────────────────────────────────
    for si, sc in enumerate(series):
        hdrs = col_headers(sc["label"])
        runits = rev_units_by_period(sc["token"])
        price_scale = money_scale(sc["unit"]) or 1.0
        rows = []
        for (y, q) in order:
            m = frame[(y, q)]
            rows.append([y, q, None, None, None, None, None, None,
                         runits.get((y, q)), None, None,
                         None, hdrs.get((y, q)), None,
                         blank_land.get((sc["label"], m["rcp"])),
                         m["name"], m["date"], m["rcp"], m["url"]])

        name = sc["sheet"]
        ws = sheet(name,
                   ["연도", "분기", "기간", "상태",
                    f'공시 단가\n(누계, {sc["unit"]})',
                    f'단일분기 단가\n(역산, {sc["unit"]})',
                    "누계 매출액\n(공시 단위)", "누계 수량\n(톤)", "매출액 단위",
                    f'검증 단가\n(매출÷수량, {sc["unit"]})', "공시 대비\n괴리",
                    "집계기준", "공시 열머리", "비고", "미공시 원문 근거",
                    "출처 보고서", "접수일자", "접수번호", "DART 원문 링크"],
                   rows,
                   widths={1: 7, 2: 7, 3: 10, 4: 9, 5: 14, 6: 14, 7: 14, 8: 13,
                           9: 12, 10: 14, 11: 10, 12: 18, 13: 17, 14: 40, 15: 44,
                           16: 22, 17: 12, 18: 16, 19: 42},
                   numfmt={5: "#,##0.##", 6: "#,##0.##", 7: "#,##0", 8: "#,##0",
                           10: "#,##0.##", 11: "0.0%"}, wrap=(14, 15))

        for i, (y, q) in enumerate(order):
            r = i + 2
            ws.cell(r, 3).value = f'=$A{r}&" "&$B{r}'
            ws.cell(r, 4).value = f'=IF($E{r}="","미공시","공시")'
            ws.cell(r, 5).value = sumifs(T_VAL, [
                (T_ITEM, f'"{sc["label"]}"'), (T_YEAR, f"$A{r}"), (T_Q, f"$B{r}"),
                (T_ROLE, '"단가"')])
            ws.cell(r, 7).value = (sumifs(R_VAL, [
                (R_ITEM, f'"*{sc["token"]}*"'), (R_ROLE, '"매출액"'),
                (R_YEAR, f"$A{r}"), (R_Q, f"$B{r}")]) if sc["token"] else None)
            if q == "1Q":
                ws.cell(r, 6).value = f'=IF($E{r}="","",$E{r})'
            else:
                ws.cell(r, 6).value = (
                    f'=IF($A{r}<>$A{r-1},"",'
                    f'IFERROR(($G{r}-$G{r-1})/($G{r}/$E{r}-$G{r-1}/$E{r-1}),""))')
            # 누계 수량 (공시하는 회사만) 과 매출÷수량 검증 단가
            ws.cell(r, 8).value = (sumifs(R_VAL, [
                (R_ITEM, f'"*{sc["token"]}*"'), (R_ROLE, '"수량"'),
                (R_YEAR, f"$A{r}"), (R_Q, f"$B{r}")])
                if (sc["token"] and sc["has_qty"]) else None)
            # 검증 단가: 매출액 ÷ 수량. 매출액 단위(I열)가 보고서마다 천원/백만원으로
            # 바뀌므로 단위 문자열에서 배율을 뽑아 단가 단위로 환산한다.
            ws.cell(r, 10).value = (
                f'=IF(OR($G{r}="",$H{r}="",$H{r}=0,$I{r}=""),"",'
                f'IF(ISNUMBER(SEARCH("백만원",$I{r})),1000000,'
                f'IF(ISNUMBER(SEARCH("천원",$I{r})),1000,1))'
                f'/{price_scale:g}*$G{r}/$H{r})'
                if sc["has_qty"] else None)
            ws.cell(r, 11).value = f'=IF(OR($E{r}="",$J{r}=""),"",$E{r}/$J{r}-1)'
            ws.cell(r, 12).value = (
                f'=IF($B{r}="1Q","1분기 누계(1~3월)",IF($B{r}="2Q","반기 누계(1~6월)",'
                f'IF($B{r}="3Q","3분기 누계(1~9월)","연간 누계(1~12월)")))')
            # 역산은 직전 분기 누계에 의존하므로, 직전 분기 검증 괴리도 함께 경고한다
            prev_bad = (f'AND($B{r}<>"1Q",$A{r}=$A{r-1},$K{r-1}<>"",'
                        f'ABS($K{r-1})>0.05)') if i > 0 else "FALSE"
            ws.cell(r, 14).value = (
                f'=IF($E{r}="","해당 분기 보고서 단가표에 이 품목 수치가 없음",'
                f'IF(AND($K{r}<>"",ABS($K{r})>0.05),'
                f'"공시 단가가 매출÷수량 검증값과 "&TEXT($K{r},"0.0%")'
                f'&" 어긋남 — 원문 확인 필요",'
                f'IF({prev_bad},"직전 분기 매출·수량 공시가 검증값과 어긋나 역산 신뢰도 낮음",'
                f'IF($F{r}="","직전 분기 누계값이 없어 역산 불가",'
                f'IF($B{r}="1Q","1분기 누계 = 단일분기","직전 분기 누계 차분으로 역산")))))')
            for c in (3, 4, 12, 14):
                ws.cell(r, c).font = body_font
            for c in (9, 13, 15):
                ws.cell(r, c).font = Font(name=FONT, size=10, color=INPUT)
            if rows[i][14]:
                for c in range(1, 20):
                    ws.cell(r, c).fill = PatternFill("solid", fgColor=CARD)

    # ── 품목 × 분기 피벗 ────────────────────────────────────────────────────
    piv_items, periods, seen_p = [], [], set()
    for r in others:
        if not r["연도"] or r.get("역할") != "단가":
            continue
        if r["항목"] not in piv_items:
            piv_items.append(r["항목"])
        k = (r["연도"], r["분기"])
        if k not in seen_p:
            seen_p.add(k)
            periods.append(k)
    periods.sort(key=lambda k: (k[0], QORDER[k[1]]))
    piv_items.sort(key=lambda it: -sum(
        1 for r in others if r["항목"] == it and r["연도"]
        and r.get("역할") == "단가"))

    P = sheet("단가_품목별_분기",
              ["품목"] + [f"{y} {q}" for y, q in periods],
              [[it] + [None] * len(periods) for it in piv_items],
              widths={1: 34, **{c: 11 for c in range(2, len(periods) + 2)}},
              numfmt={c: "#,##0.##" for c in range(2, len(periods) + 2)}, freeze="B2")
    for i in range(len(piv_items)):
        for j, (y, q) in enumerate(periods):
            cell = P.cell(i + 2, j + 2)
            cell.value = sumifs(T_VAL, [
                (T_ITEM, f"$A{i+2}"), (T_YEAR, str(y)), (T_Q, f'"{q}"'),
                (T_ROLE, '"단가"')])
            cell.number_format = "#,##0.##"

    # ── 요약 ────────────────────────────────────────────────────────────────
    S = wb.create_sheet("요약", 0)
    S.sheet_properties.tabColor = INK
    S.sheet_view.showGridLines = False
    S.column_dimensions["A"].width = 3
    for col, w in zip("BCDEFGHI", (26, 15, 15, 15, 15, 15, 15, 15)):
        S.column_dimensions[col].width = w

    def put(cell, value, *, size=10, bold=False, color="000000", fill=None,
            fmt=None, align=None, wrap=False):
        c = S[cell]
        c.value = value
        c.font = Font(name=FONT, size=size, bold=bold, color=color)
        if fill:
            c.fill = PatternFill("solid", fgColor=fill)
        if fmt:
            c.number_format = fmt
        if align or wrap:
            c.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
        return c

    span = f"{order[0][0]} {order[0][1]} ~ {order[-1][0]} {order[-1][1]}"
    put("B2", f"{company} — 품목별 단가 분기 시계열", size=16, bold=True, color=INK)
    put("B3", f"DART 정기보고서 원문 발췌 · {span}", size=10, color=MUTED)

    put("B5", "수집 범위", size=11, bold=True, color=SECTION)
    put("B6", "대상 회사", bold=True)
    put("C6", company)
    put("B7", "수집 보고서", bold=True)
    put("C7", f'=COUNTA(수집로그!$A$2:$A${len(log)+1})&"건 — 정기보고서 원문 전량"')
    put("B8", "발췌 대상", bold=True)
    put("C8", "II. 사업의 내용 > 주요 제품 등의 가격변동추이 / 매출 및 수주상황")
    put("B9", "출처", bold=True)
    put("C9", "DART 전자공시시스템 (dart.fss.or.kr) 원문")

    # 품목별 요약 표
    r0 = 11
    put(f"B{r0}", "품목별 요약", size=11, bold=True, color=SECTION)
    heads = ["품목", "단위", "공시 분기", "최고 단가", "최고 시점", "최저 단가",
             "최저 시점", "최근 단가", "최근 시점"]
    for j, h in enumerate(heads):
        put(f"{get_column_letter(2+j)}{r0+1}", h, bold=True, color="FFFFFF",
            fill=SECTION, align="center")
    for i, sc in enumerate(series):
        rr = r0 + 2 + i
        sh = sc["sheet"]
        rE, rC = f"{sh}!$E$2:$E${nL}", f"{sh}!$C$2:$C${nL}"
        lastx = f'SUMPRODUCT(MAX(({rE}<>"")*ROW({rE})))-1'
        put(f"B{rr}", sc["label"], fill=CARD)
        put(f"C{rr}", sc["unit"], align="center")
        put(f"D{rr}", f"=COUNT({rE})", fmt='0"개"', align="right")
        put(f"E{rr}", f"=MAX({rE})", fmt="#,##0.##", align="right", bold=True)
        put(f"F{rr}", f"=INDEX({rC},MATCH(MAX({rE}),{rE},0))", align="center")
        put(f"G{rr}", f"=MIN({rE})", fmt="#,##0.##", align="right", bold=True)
        put(f"H{rr}", f"=INDEX({rC},MATCH(MIN({rE}),{rE},0))", align="center")
        put(f"I{rr}", f"=INDEX({rE},{lastx})", fmt="#,##0.##", align="right", bold=True)
        put(f"J{rr}", f"=INDEX({rC},{lastx})", align="center")
    for rr in range(r0 + 1, r0 + 2 + len(series)):
        for cc in range(2, 11):
            S.cell(rr, cc).border = border

    # 연도별 연간 누계 단가 (품목 × 연도)
    r1 = r0 + len(series) + 4
    put(f"B{r1}", "연도별 연간 누계 단가", size=11, bold=True, color=SECTION)
    years = sorted({y for (y, q) in order})
    put(f"B{r1+1}", "품목", bold=True, color="FFFFFF", fill=SECTION, align="center")
    put(f"C{r1+1}", "단위", bold=True, color="FFFFFF", fill=SECTION, align="center")
    for j, y in enumerate(years):
        put(f"{get_column_letter(4+j)}{r1+1}", y, bold=True, color="FFFFFF",
            fill=SECTION, align="center")
        S.column_dimensions[get_column_letter(4 + j)].width = 11
    for i, sc in enumerate(series):
        rr = r1 + 2 + i
        put(f"B{rr}", sc["label"], fill=CARD)
        put(f"C{rr}", sc["unit"], align="center")
        for j, y in enumerate(years):
            src = addr.get((y, "4Q"))
            put(f"{get_column_letter(4+j)}{rr}",
                f'={sc["sheet"]}!$E${src}' if src else None,
                fmt="#,##0.##", align="right")
    for rr in range(r1 + 1, r1 + 2 + len(series)):
        for cc in range(2, 4 + len(years)):
            S.cell(rr, cc).border = border

    nr = r1 + len(series) + 4
    put(f"B{nr}", "읽는 법", size=11, bold=True, color=SECTION)
    put(f"B{nr+1}", "파란 글씨", bold=True, color=INPUT)
    put(f"C{nr+1}", "원문에서 발췌한 입력값 (원자료_발췌표)", color=MUTED)
    put(f"B{nr+2}", "검정 글씨", bold=True)
    put(f"C{nr+2}", "수식으로 계산된 값 — 셀을 클릭하면 참조식이 보인다", color=MUTED)
    for i, t in enumerate([
            "정기보고서의 가격변동추이는 당해연도 누계 평균 단가로 공시된다. "
            "반기보고서 값은 1~6월 누계, 사업보고서 값은 연간 누계다.",
            "'단일분기 단가'는 누계 물량을 (매출액 ÷ 단가) 로 복원해 인접 분기 차분으로 "
            "역산한다:  (G2-G1) / (G2/E2 - G1/E1).  매출액 단위는 분자·분모에서 상쇄된다.",
            "품목별 시트의 '미공시' 분기는 추출 실패가 아니라 해당 보고서 단가표에 그 "
            "품목 수치가 없다는 뜻이다 (K열 원문 근거 참조).",
            "모든 수치는 원자료_발췌표 → 단가항목_전체 → 품목별 시트 → 요약 순으로 "
            "참조된다. 각 행에 출처 보고서·접수번호·DART 원문 링크가 붙어 있다."]):
        rr = nr + 4 + i
        c = put(f"B{rr}", f"· {t}", size=9, color="333333", wrap=True)
        S.merge_cells(f"B{rr}:I{rr}")
        c.alignment = Alignment(wrap_text=True, vertical="top")
        S.row_dimensions[rr].height = 26

    # 품목별 공시 누계 단가 추이
    if series:
        ch = LineChart()
        ch.title = "품목별 단가 추이 (공시 누계, 원/톤)"
        ch.height, ch.width = 10, 24
        us = {sc["unit"] for sc in series}
        ch.y_axis.title = us.pop() if len(us) == 1 else "단가"
        base = wb[series[0]["sheet"]]
        for i, sc in enumerate(series):
            w = wb[sc["sheet"]]
            ref = Reference(w, min_col=5, min_row=1, max_row=nL)
            ch.add_data(ref, titles_from_data=False)
            ch.series[-1].tx = None
        ch.set_categories(Reference(base, min_col=3, min_row=2, max_row=nL))
        from openpyxl.chart.series import SeriesLabel
        from openpyxl.chart.data_source import StrRef
        for i, sc in enumerate(series):
            sr = ch.series[i]
            sr.tx = SeriesLabel(strRef=StrRef(f'{sc["sheet"]}!$E$1'))
            sr.graphicalProperties.line.width = 22000
            sr.graphicalProperties.line.solidFill = SERIES_COLORS[i % len(SERIES_COLORS)]
            sr.smooth = False
        S.add_chart(ch, "K5")

    # ── 나머지 시트 ─────────────────────────────────────────────────────────
    sheet("단가항목_전체",
          ["연도", "분기", "항목", "단가", "공시 열머리", "역할", "집계기준", "문맥",
           "출처 보고서", "접수번호", "DART 링크"],
          [[r["연도"], r["분기"], r["항목"], r["값"], r["열머리"], r.get("역할", ""),
            r["집계기준"], r["문맥"], r["보고서명"], r["접수번호"], r["링크"]]
           for r in others],
          widths={1: 7, 2: 7, 3: 32, 4: 12, 5: 18, 6: 9, 7: 16, 8: 48, 9: 22,
                  10: 16, 11: 40},
          numfmt={4: "#,##0.##"}, wrap=(8,))

    prose_sorted = sorted(prose, key=lambda r: (not r["매립언급"], r["접수일자"]))
    sheet("산문_단가언급",
          ["연도", "분기", "주요품목", "단가 언급 문장", "추출 금액", "출처 보고서",
           "접수일자", "접수번호", "DART 링크"],
          [[r["연도"], r["분기"], "●" if r["매립언급"] else "", r["문장"],
            r["추출 금액"], r["보고서명"], r["접수일자"], r["접수번호"], r["링크"]]
           for r in prose_sorted],
          widths={1: 7, 2: 7, 3: 9, 4: 90, 5: 22, 6: 22, 7: 12, 8: 16, 9: 38},
          wrap=(4,))

    used = ({r["접수번호"] for r in records} | {r["접수번호"] for r in prose}
            or {l["접수번호"] for l in log})
    src = sorted((manifest[k] for k in used if k in manifest), key=lambda m: m["date"])
    sheet("출처_공시목록",
          ["접수일자", "보고서명", "제출인", "접수번호", "DART 원문 링크"],
          [[m["date"], m["name"], m["filer"], m["rcp"], m["url"]] for m in src],
          widths={1: 12, 2: 28, 3: 14, 4: 18, 5: 46})

    sheet("수집로그",
          ["접수일자", "보고서명", "접수번호", "표 총수", "단가 관련 표",
           "산문 단가언급", "DART 링크"],
          [[l["접수일자"], l["보고서명"], l["접수번호"], l["표 총수"],
            l["단가관련 표"], l["산문 단가언급"], l["링크"]] for l in log],
          widths={1: 12, 2: 28, 3: 18, 4: 10, 5: 13, 6: 13, 7: 44})

    sheet(RAW,
          ["접수일자", "보고서명", "접수번호", "연도", "분기", "종류", "역할", "표번호",
           "문맥", "항목", "열머리", "값", "원문", "DART 링크"],
          raw_rows,
          widths={1: 12, 2: 22, 3: 16, 7: 9, 9: 44, 10: 26, 13: 14, 14: 36})

    blue = Font(name=FONT, size=10, color=INPUT)
    for r in range(2, nT + 1):
        wb["단가항목_전체"].cell(r, 4).font = blue

    wb.remove(wb["Sheet"])
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"저장: {out}")
    print(f"  분기 프레임 {len(order)} ({span}) · 품목 시계열 {len(series)}종")
    for sc in series:
        print(f"     - {sc['label']}  {sc['n']}분기  -> 시트 '{sc['sheet']}'")
    print(f"  표 발췌 {len(records):,}셀 · 단가항목 {len(others)}행 · 산문 {len(prose)}문장")



def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=Path("data/raw"), type=Path)
    ap.add_argument("--xlsx", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--company", default="", help="요약 시트 제목에 쓸 회사명")
    args = ap.parse_args()

    if not args.raw.exists() or not any(args.raw.iterdir()):
        print(f"원문이 없습니다: {args.raw}  → 먼저 tools/dart_fetch.py 를 실행하세요.")
        return 2
    manifest = load_manifest(args.xlsx)
    records, prose, log, blank_land = extract(args.raw, manifest)
    build_workbook(records, prose, log, manifest, blank_land, args.out, args.company)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
