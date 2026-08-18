#!/usr/bin/env python3
"""워크북의 수식을 실제로 계산해 기대값과 대조한다.

이 환경의 LibreOffice 는 xlsx 를 로드하지 못해(source file could not be loaded)
skills 의 recalc.py 를 쓸 수 없다. 대신 formulas 라이브러리로 직접 계산한다.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")


def evaluate(path: Path) -> dict[tuple[str, str], object]:
    import formulas
    xl = formulas.ExcelModel().loads(str(path)).finish()
    sol = xl.calculate()
    out: dict[tuple[str, str], object] = {}
    for key, val in sol.items():
        if "!" not in key or "<" in key:
            continue
        sheet, _, coord = key.rpartition("!")
        sheet = sheet.strip("'").split("]")[-1]
        try:
            v = val.value[0, 0]
        except Exception:  # noqa: BLE001
            continue
        out[(sheet, coord)] = v
    return out


def num(v):
    if isinstance(v, str) and v.strip() in ("", "[]"):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def main() -> int:
    path = Path(sys.argv[1])
    expected_csv = Path(sys.argv[2])          # 파이썬으로 계산한 기대값
    got = evaluate(path)

    fails, checked = [], 0
    for line in expected_csv.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        sheet, coord, kind, exp = line.split("\t")
        checked += 1
        g = got.get((sheet, coord))
        if kind == "num":
            e, gv = float(exp), num(g)
            if gv is None or abs(gv - e) > max(1.0, abs(e) * 1e-6):
                fails.append(f"{sheet}!{coord}: 계산 {g!r} != 기대 {e:,.2f}")
        elif kind == "blank":
            if num(g) is not None:
                fails.append(f"{sheet}!{coord}: 비어야 하는데 {g!r}")
        else:
            if str(g).strip() != exp:
                fails.append(f"{sheet}!{coord}: 계산 {g!r} != 기대 {exp!r}")

    print(f"검증 {checked}셀 · 불일치 {len(fails)}건")
    for f in fails[:40]:
        print("   FAIL", f)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
