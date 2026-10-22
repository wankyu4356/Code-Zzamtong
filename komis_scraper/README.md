# KOMIS 희소금속 수출입 데이터 수집기

KOMIS 핵심광물지도(대한민국: 관세청 / 글로벌: UN Comtrade)의 내부 AJAX API를 호출해
탄탈륨(Ta)·니오븀(Nb)·인듐(In)·갈륨(Ga)·하프늄(Hf)·레늄(Re)의 2020~2026년 수출입 데이터를 수집하고
`KOMIS_희소금속_수입현황_2020-2026.xlsx`를 생성한다.

- 출처: https://www.komis.or.kr/Komis/MnrlMap/Korea , https://www.komis.or.kr/Komis/MnrlMap/Nation
- `scrape.py` : API 호출 → `data/*.json` (1,234건, 이미 받은 파일은 건너뜀, 재시도 내장)
- `build_xlsx.py` : `data/` + `raw/`(광종·HS·국가 코드표) → 엑셀 생성 (openpyxl, 비중·합계는 수식)
- `raw/` : 광종코드, 관세청 HS 10자리, UN HS 6자리, 국가코드 목록

```bash
pip install requests openpyxl
python3 scrape.py          # 약 5분
python3 build_xlsx.py      # ../KOMIS_희소금속_수입현황_2020-2026.xlsx 생성
# 생성 직후에는 수식 캐시값이 없으므로 Excel/LibreOffice에서 한 번 열어 저장(재계산)할 것
```

주의: UN Comtrade(HS 6자리)는 인듐·갈륨·니오븀 코드(811292/811299)가 Ga·Ge·In·Nb·V 공용이라 금속별 구분이 안 된다.
금속별 수치는 관세청(HS 10자리) 시트를 사용한다. 하프늄·레늄은 2020~2021년 데이터가 없다(HS 2022 개정 전 '기타' 코드에 포함).
