"""
렌더 결과 검수용 콘택트 시트. 샷마다 시작 직후, 중간, 끝 직전 프레임을 한 줄로 놓는다.
  python3 tools/qc_sheet.py <video.mp4> <timeline.json> <out.jpg> [--ids f02,f03] [--extra 0.3,1.0]
"""
import io
import json
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/local/share/fonts/pretendard/Pretendard-SemiBold.otf"


def grab(video, t, w=480):
    buf = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1",
                          "-vf", f"scale={w}:-2", "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3", "-"], capture_output=True).stdout
    return Image.open(io.BytesIO(buf)).convert("RGB") if buf else Image.new("RGB", (w, w * 9 // 16), (60, 0, 0))


def main():
    video, tl_path, out = sys.argv[1:4]
    ids = sys.argv[sys.argv.index("--ids") + 1].split(",") if "--ids" in sys.argv else None
    tl = json.load(open(tl_path, encoding="utf-8"))
    fps = tl["fps"]
    rows = []
    f = ImageFont.truetype(FONT, 20)
    for s in tl["shots"]:
        if ids and s["id"] not in ids:
            continue
        a, b = s["start"], s["end"]
        ts = [a + 0.2, (a + b) / 2, b - 1.5 / fps]
        ims = [grab(video, t) for t in ts]
        w, h = ims[0].size
        row = Image.new("RGB", (w * 3 + 8, h + 28), (20, 20, 20))
        d = ImageDraw.Draw(row)
        d.text((6, 4), f"{s['id']}  {a:.2f}~{b:.2f}s  {s['bg']['type']}", fill=(255, 255, 255), font=f)
        for i, im in enumerate(ims):
            row.paste(im, (i * (w + 4), 28))
            d.text((i * (w + 4) + 6, 32), f"{ts[i]:.2f}s", fill=(255, 255, 0), font=f)
        rows.append(row)
    W = max(r.size[0] for r in rows)
    H = sum(r.size[1] for r in rows)
    sheet = Image.new("RGB", (W, H), (0, 0, 0))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.size[1]
    sheet.save(out, quality=80)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
