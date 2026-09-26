"""naver_reviews_raw.txt(네이버 플레이스 방문자 리뷰 화면 복사본)를 구조화해 naver_reviews.json으로 저장."""
import json
import re

raw = open("naver_reviews_raw.txt", encoding="utf-8").read()
blocks = raw.split("\n프로필\n")[1:]
skip_exact = {"팔로우", "더보기", "반응 남기기", "진료예약", "방문자리뷰사진", "표정을 눌러 반응을 남겨 보세요!"}
reviews = []
for b in blocks:
    lines = b.split("\n")
    author = lines[0].strip()
    body, wait, visit, reply = [], "", None, []
    i = 1
    in_reply = False
    for ln in lines[1:]:
        s = ln.strip()
        if s == "김철신정형외과의원":
            in_reply = True
            continue
        if in_reply:
            if s and not re.fullmatch(r"\d{1,2}\.\d{1,2}\.[월화수목금토일]|\d{2}\.\d{1,2}\.\d{1,2}\.[월화수목금토일]", s) and s not in skip_exact:
                reply.append(s)
            continue
        if not s or s in skip_exact:
            continue
        if re.match(r"^리뷰 [\d,]+", s):
            continue
        if s.startswith("예약 없이 이용") or s.startswith("예약 후 이용"):
            wait = s
            continue
        m = re.match(r"^방문일.*?(\d{4})년 (\d{1,2})월 (\d{1,2})일 ([월화수목금토일])요일(\d+)번째 방문인증 수단(.+)$", s)
        if m:
            visit = {"date": f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}", "weekday": m[4], "nth_visit": int(m[5]), "verified_by": m[6]}
            continue
        body.append(s)
    text = "\n".join(body).strip()
    reviews.append({"author": author, "text": text, "wait": wait, "visit": visit, "hospital_reply": " ".join(reply).strip() or None})

json.dump({"source": "네이버 플레이스 방문자 리뷰 (의뢰인이 2026-09-26 화면 복사)", "total_reviews_on_naver": 697, "count_parsed": len(reviews), "reviews": reviews},
          open("naver_reviews.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(reviews), "reviews parsed")
for r in reviews[:3]:
    print(r["author"], r["visit"], "|", r["text"][:40])
