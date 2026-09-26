# 수집 도구

| 파일 | 역할 |
|---|---|
| `naver_reviews.mjs` | 네이버 플레이스 방문자 리뷰, 키워드 통계, 사진 URL, 기본 정보를 수집해 `assets/reviews/`에 저장 |
| `pexels_fetch.py` | 구성안의 샷별 검색어로 Pexels 무료 영상 후보를 내려받아 `assets/footage/candidates/`에 저장 (무료 API 키 필요) |

실행 조건: 세션 네트워크 정책에서 `naver.com`과 `pstatic.net`(사진 CDN)이 허용돼 있어야 한다.

```bash
cd promo/tools
node naver_reviews.mjs 13154835 ../assets/reviews
```

## Pexels 영상 내려받기

```bash
export PEXELS_API_KEY=발급받은키   # https://www.pexels.com/api/
python3 pexels_fetch.py ../assets/footage/shots.json ../assets/footage
```

네트워크 정책에서 `api.pexels.com`, `videos.pexels.com`이 허용돼 있어야 한다. 허용이 어려우면 `candidates.md`의 검색어로 직접 내려받아 `assets/footage/`에 넣어도 된다.
