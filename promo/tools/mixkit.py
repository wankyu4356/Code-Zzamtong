"""
Mixkit 무료 영상 검색과 내려받기 (Mixkit License: 상업적 사용 가능, 출처 표기 불필요).
  python3 mixkit.py search "walking feet" [--limit 20]          -> JSON 목록 (id, slug, title, thumb, preview720, pages)
  python3 mixkit.py get <id> <out.mp4>                           -> 1080p가 있으면 1080p, 없으면 720p
  python3 mixkit.py thumbs <video.mp4> <out_prefix> [n]           -> 균등 간격 스틸 n장 (기본 4)
  python3 mixkit.py sheet "<query>" <out.jpg> [--limit 24]        -> 검색 결과 썸네일을 id 라벨과 함께 한 장에 모은 콘택트 시트
  python3 mixkit.py strip <video.mp4> <out.jpg> <from_s> <to_s> [step] -> 구간을 step초 간격으로 잘라 시간 라벨과 함께 한 장에
"""
import io
import os
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/local/share/fonts/pretendard/Pretendard-SemiBold.otf"
import json
import re
import subprocess
import sys
import urllib.parse

import requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}
ITEM = re.compile(r'href="/free-stock-video/([a-z0-9-]+?)-(\d+)/"')


def search(query, limit=20):
    seen, items = set(), []
    for page in (1, 2):
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
        url = f"https://mixkit.co/free-stock-video/discover/{slug}/" + (f"?page={page}" if page > 1 else "")
        r = requests.get(url, headers=UA, timeout=40)
        if r.status_code != 200:
            break
        for slug, vid in ITEM.findall(r.text):
            if vid in seen:
                continue
            seen.add(vid)
            items.append({
                "id": vid, "slug": slug, "title": slug.replace("-", " "),
                "page": f"https://mixkit.co/free-stock-video/{slug}-{vid}/",
                "thumb": f"https://assets.mixkit.co/videos/{vid}/{vid}-thumb-720-0.jpg",
                "preview720": f"https://assets.mixkit.co/videos/{vid}/{vid}-720.mp4",
            })
            if len(items) >= limit:
                return items
        if "?page=2" not in r.text and page == 1:
            break
    return items


def get(vid, out):
    for q in ("1080", "720"):
        url = f"https://assets.mixkit.co/videos/{vid}/{vid}-{q}.mp4"
        with requests.get(url, headers=UA, stream=True, timeout=120) as r:
            if r.status_code != 200:
                continue
            with open(out, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
            return {"id": vid, "quality": q, "url": url, "file": out}
    raise SystemExit(f"no file for mixkit id {vid}")


def thumbs(video, prefix, n=4):
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video]).decode().strip())
    outs = []
    for i in range(n):
        t = dur * (i + 0.5) / n
        o = f"{prefix}_{i}.jpg"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4", o], check=True)
        outs.append({"t": round(t, 2), "file": o})
    return {"duration": dur, "stills": outs}


def _label(im, text):
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, 22)
    w = d.textlength(text, font=f)
    d.rectangle([0, 0, w + 14, 32], fill=(0, 0, 0))
    d.text((7, 4), text, fill=(255, 255, 255), font=f)
    return im


def sheet(query, out, limit=24, cols=4, tw=400):
    items = search(query, limit)
    th = int(tw * 9 / 16)

    def fetch(it):
        try:
            r = requests.get(it["thumb"], headers=UA, timeout=30)
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception:
            im = Image.new("RGB", (tw, th), (40, 40, 40))
        im = im.resize((tw, th))
        return _label(im, f"{it['id']}  {it['title'][:34]}")

    with ThreadPoolExecutor(8) as ex:
        ims = list(ex.map(fetch, items))
    rows = (len(ims) + cols - 1) // cols
    grid = Image.new("RGB", (cols * tw, max(1, rows) * th), (0, 0, 0))
    for i, im in enumerate(ims):
        grid.paste(im, ((i % cols) * tw, (i // cols) * th))
    grid.save(out, quality=82)
    return {"query": query, "count": len(items), "sheet": out, "items": items}


def strip(video, out, t0, t1, step=0.25, tw=384):
    th = int(tw * 9 / 16)
    ts = []
    t = t0
    while t <= t1 + 1e-6:
        ts.append(round(t, 3))
        t += step
    frames = []
    for t in ts:
        buf = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-vf", f"scale={tw}:-2", "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "4", "-"], capture_output=True).stdout
        im = Image.open(io.BytesIO(buf)).convert("RGB").resize((tw, th)) if buf else Image.new("RGB", (tw, th), (40, 40, 40))
        frames.append(_label(im, f"{t:.2f}s"))
    cols = min(5, len(frames))
    rows = (len(frames) + cols - 1) // cols
    grid = Image.new("RGB", (cols * tw, rows * th), (0, 0, 0))
    for i, im in enumerate(frames):
        grid.paste(im, ((i % cols) * tw, (i // cols) * th))
    grid.save(out, quality=82)
    return {"video": video, "times": ts, "strip": out}


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "search":
        limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 20
        print(json.dumps(search(sys.argv[2], limit), ensure_ascii=False, indent=1))
    elif cmd == "get":
        print(json.dumps(get(sys.argv[2], sys.argv[3])))
    elif cmd == "thumbs":
        n = int(sys.argv[4]) if len(sys.argv) > 4 else 4
        print(json.dumps(thumbs(sys.argv[2], sys.argv[3], n)))
    elif cmd == "sheet":
        limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 24
        r = sheet(sys.argv[2], sys.argv[3], limit)
        print(json.dumps({"query": r["query"], "count": r["count"], "sheet": r["sheet"], "ids": [(i["id"], i["title"]) for i in r["items"]]}, ensure_ascii=False))
    elif cmd == "strip":
        step = float(sys.argv[6]) if len(sys.argv) > 6 else 0.25
        print(json.dumps(strip(sys.argv[2], sys.argv[3], float(sys.argv[4]), float(sys.argv[5]), step)))
