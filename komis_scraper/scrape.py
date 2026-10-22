"""KOMIS 핵심광물지도(대한민국/글로벌) 내부 AJAX API를 호출해 희소금속 6종의 수출입 데이터를 JSON으로 저장.
사용: REQUESTS_CA_BUNDLE=... python3 scrape.py  (결과: ./data/*.json, 이미 받은 파일은 건너뜀)
"""
import json, os, sys, time, random, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

OUT = os.environ.get("KOMIS_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
os.makedirs(OUT, exist_ok=True)
BASE = "https://www.komis.or.kr"
KREF = BASE + "/Komis/MnrlMap/Korea"
NREF = BASE + "/Komis/MnrlMap/Nation"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

METALS = {
    "MNRL0026": ("Ta", "탄탈륨"),
    "MNRL0007": ("Nb", "니오븀"),
    "MNRL0025": ("In", "인듐"),
    "MNRL0024": ("Ga", "갈륨"),
    "MNRL0040": ("Hf", "하프늄"),
    "MNRL0042": ("Re", "레늄"),
}
HS_KR = {
    "MNRL0026": ["2615902000","8103201000","8103202000","8103300000","8103900000","8103990000"],
    "MNRL0007": ["2615901000","7202930000","8112926000","8112996000"],
    "MNRL0025": ["8112925000","8112995000"],
    "MNRL0024": ["8112923000","8112993000"],
    "MNRL0040": ["8112390000","8112310000"],
    "MNRL0042": ["8112490000","8112410000"],
}
HS_UN = {
    "MNRL0026": ["261590","810320","810330","810399"],
    "MNRL0007": ["261590","720293","811292","811299"],
    "MNRL0025": ["811292","811299"],
    "MNRL0024": ["811292","811299"],
    "MNRL0040": ["811231","811239"],
    "MNRL0042": ["811241","811249"],
}
MF = ["001","002","003","004"]
YEARS = list(range(2020, 2027))
MONTHS = [f"{y}{m:02d}" for y in YEARS for m in range(1,13) if (y,m) <= (2026,9)]

tl = threading.local()
def sess():
    if not hasattr(tl, "s"):
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"})
        tl.s = s
    return tl.s

def post(url, data, ref, key):
    path = os.path.join(OUT, key + ".json")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return "skip"
    last = None
    for attempt in range(7):
        try:
            r = sess().post(url, data=data, headers={"Referer": ref}, timeout=90)
            if r.status_code == 200:
                txt = r.text
                if txt.lstrip().startswith("{") or txt.lstrip().startswith("["):
                    j = json.loads(txt)
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump({"_req": data, "_url": url, "_ts": time.strftime("%Y-%m-%d %H:%M:%S"), "resp": j}, f, ensure_ascii=False)
                    return "ok"
                last = f"non-json {txt[:80]!r}"
            else:
                last = f"http {r.status_code}"
        except Exception as e:
            last = repr(e)[:120]
        time.sleep(min(2 ** attempt, 30) + random.random())
    return f"FAIL {last}"

def yr(y):
    return dict(srchCrtrYmd="Y", srchDateS=f"{y}0101", srchDateE=f"{y}1231",
                srchDatePS=f"{y-1}0101", srchDatePE=f"{y-1}1231")
def mo(ym):
    y, m = int(ym[:4]), int(ym[4:])
    py, pm = (y-1, 12) if m == 1 else (y, m-1)
    return dict(srchCrtrYmd="M", srchDateS=f"{ym}01", srchDateE=f"{ym}31",
                srchDatePS=f"{py}{pm:02d}01", srchDatePE=f"{py}{pm:02d}31")

def kbase(m, **kw):
    d = dict(srchIncmExp="I", srchTypeAW="A", srchMnrkndUnqCd=m, srchMttrFlowCd="", srchMttrFlowDtlCd="",
             srchHsCd="", srchNtnCd="", page=1, orderBy="realPrdctnQuty1", orderSort="DESC", listCount=300)
    d.update(kw); return d

def nbase(m, y, **kw):
    d = dict(srchImxprtSeCd="I", srchTypeAW="A", srchTypeIE="I", srchMnrkndUnqCd=m, srchMttrFlowCd="", srchMttrFlowDtlCd="",
             srchHsCd="", srchExpNtnCd="", srchIncmNtnCd="", page=1, orderBy="", orderSort="DESC", listCount=300,
             srchDateChartS=f"{y-4}0101", srchDateChartE=f"{y}1231")
    d.update(yr(y)); d.update(kw); return d

KL = BASE + "/Komis/MnrlMap/MapKorea/ajax/getListKoreaData"
KLINE = BASE + "/Komis/MnrlMap/MapKorea/ajax/getLineChartDataKorea"
KTOP5 = BASE + "/Komis/MnrlMap/MapKorea/ajax/getTop5TableDataKorea"
KMAP = BASE + "/Komis/MnrlMap/MapKorea/ajax/getListMapKoreaData"
NL = BASE + "/Komis/MnrlMap/MapNation/ajax/getListDataNation"
NBAR = BASE + "/Komis/MnrlMap/MapNation/ajax/getBarChartDataNation"
NMAP = BASE + "/Komis/MnrlMap/MapNation/ajax/getListMapNationData"

jobs = []
for m in METALS:
    for y in YEARS:
        jobs.append((KL, kbase(m, **yr(y)), KREF, f"K_list_{m}_{y}"))
        jobs.append((KTOP5, kbase(m, **yr(y)), KREF, f"K_top5_{m}_{y}"))
        jobs.append((KMAP, kbase(m, **yr(y)), KREF, f"K_map_{m}_{y}"))
        for hs in HS_KR[m]:
            jobs.append((KL, kbase(m, srchHsCd=hs, **yr(y)), KREF, f"K_lisths_{m}_{y}_{hs}"))
        for mf in MF:
            jobs.append((KL, kbase(m, srchMttrFlowCd=mf, **yr(y)), KREF, f"K_listmf_{m}_{y}_{mf}"))
        jobs.append((NL, nbase(m, y, srchIncmNtnCd="KR"), NREF, f"N_list_krimp_{m}_{y}"))
        jobs.append((NL, nbase(m, y, srchExpNtnCd="KR"), NREF, f"N_list_krexp_{m}_{y}"))
        jobs.append((NL, nbase(m, y, listCount=100), NREF, f"N_list_global_{m}_{y}"))
        jobs.append((NMAP, nbase(m, y, srchIncmNtnCd="KR"), NREF, f"N_map_krimp_{m}_{y}"))
        for hs in HS_UN[m]:
            jobs.append((NL, nbase(m, y, srchIncmNtnCd="KR", srchHsCd=hs), NREF, f"N_lisths_krimp_{m}_{y}_{hs}"))
    for y in (2024, 2026):
        jobs.append((KLINE, kbase(m, **yr(y)), KREF, f"K_line_{m}_{y}"))
        jobs.append((NBAR, nbase(m, y, srchIncmNtnCd="KR"), NREF, f"N_bar_krimp_{m}_{y}"))
        jobs.append((NBAR, nbase(m, y, srchTypeIE="I"), NREF, f"N_bar_globalI_{m}_{y}"))
        jobs.append((NBAR, nbase(m, y, srchTypeIE="E"), NREF, f"N_bar_globalE_{m}_{y}"))
    for ym in MONTHS:
        jobs.append((KL, kbase(m, **mo(ym)), KREF, f"K_month_{m}_{ym}"))

print("total jobs", len(jobs), flush=True)
done = 0; fails = []
lock = threading.Lock()
def run(j):
    return j[3], post(*j)
with ThreadPoolExecutor(max_workers=3) as ex:
    futs = [ex.submit(run, j) for j in jobs]
    for f in as_completed(futs):
        key, st = f.result()
        with lock:
            done += 1
            if st.startswith("FAIL"): fails.append((key, st))
            if done % 50 == 0 or st.startswith("FAIL"):
                print(f"[{done}/{len(jobs)}] {key} {st}", flush=True)
print("DONE. fails:", len(fails), flush=True)
for k, s in fails: print("  ", k, s)
