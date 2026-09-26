"""
Pexels API로 무료 영상을 검색해 내려받는다 (상업적 사용 가능, 출처 표기 불필요).
사용:
  export PEXELS_API_KEY=...      # https://www.pexels.com/api/ 에서 무료 발급
  python3 pexels_fetch.py shots.json ../assets/footage
shots.json 형식: [ {"id": "s07", "query": "woman running morning park slow motion", "min_duration": 3}, ... ]
각 샷마다 후보 5개를 assets/footage/candidates/<id>_<n>.mp4 로 받고, 목록을 assets/footage/candidates.md 에 적는다.
세션 네트워크 정책에서 api.pexels.com 과 videos.pexels.com 이 허용돼 있어야 한다.
"""
import json
import os
import sys

import requests

API = "https://api.pexels.com/videos/search"


def best_file(video, max_h=1080):
    files = [f for f in video["video_files"] if f.get("height") and f["height"] <= max_h and f.get("file_type") == "video/mp4"]
    files.sort(key=lambda f: (f["height"], f.get("width", 0)), reverse=True)
    return files[0] if files else None


def main():
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        sys.exit("PEXELS_API_KEY 환경변수가 필요하다")
    shots = json.load(open(sys.argv[1], encoding="utf-8"))
    out_dir = sys.argv[2]
    cand_dir = os.path.join(out_dir, "candidates")
    os.makedirs(cand_dir, exist_ok=True)
    lines = ["# 영상 후보 (Pexels)", "", "| 샷 | 파일 | 길이 | 해상도 | 촬영자 | 페이지 |", "|---|---|---|---|---|---|"]
    s = requests.Session()
    s.headers["Authorization"] = key
    for shot in shots:
        r = s.get(API, params={"query": shot["query"], "orientation": "landscape", "size": "medium", "per_page": 8}, timeout=30)
        r.raise_for_status()
        n = 0
        for v in r.json().get("videos", []):
            if v["duration"] < shot.get("min_duration", 2):
                continue
            f = best_file(v)
            if not f:
                continue
            n += 1
            name = f"{shot['id']}_{n}.mp4"
            path = os.path.join(cand_dir, name)
            if not os.path.exists(path):
                with s.get(f["link"], stream=True, timeout=120) as dl:
                    dl.raise_for_status()
                    with open(path, "wb") as fh:
                        for chunk in dl.iter_content(1 << 20):
                            fh.write(chunk)
            lines.append(f"| {shot['id']} | candidates/{name} | {v['duration']}s | {f['width']}x{f['height']} | {v['user']['name']} | {v['url']} |")
            print(shot["id"], name, v["duration"], "s", f["width"], "x", f["height"])
            if n >= 5:
                break
        if n == 0:
            lines.append(f"| {shot['id']} | (없음) | | | | 검색어: {shot['query']} |")
    open(os.path.join(out_dir, "candidates.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
