# 수집 도구

| 파일 | 역할 |
|---|---|
| `naver_reviews.mjs` | 네이버 플레이스 방문자 리뷰, 키워드 통계, 사진 URL, 기본 정보를 수집해 `assets/reviews/`에 저장 |

실행 조건: 세션 네트워크 정책에서 `naver.com`과 `pstatic.net`(사진 CDN)이 허용돼 있어야 한다.

```bash
cd promo/tools
node naver_reviews.mjs 13154835 ../assets/reviews
```
