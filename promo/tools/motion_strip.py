"""
글자 모션 검수용 필름 스트립. 화면마다 시작 직후 촘촘히(등장), 중간, 끝 직전(퇴장·전환) 프레임을 한 줄에.
  python3 tools/motion_strip.py <video.mp4> <timeline.json> <out.jpg> [--ids s01,s02] [--n 8]
"""
import io
import json
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/local/share/fonts/pretendard/Pretendard-SemiBold.otf"


def grab(video, t, w=320):
    buf = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1",
                          "-vf", f"scale={w}:-2", "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3", "-"], capture_output=True).stdout
    return Image.open(io.BytesIO(buf)).convert("RGB") if buf else Image.new("RGB", (w, w * 9 // 16), (60, 0, 0))


def main():
    video, tl_path, out = sys.argv[1:4]
    ids = sys.argv[sys.argv.index("--ids") + 1].split(",") if "--ids" in sys.argv else None
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 8
    tl = json.load(open(tl_path, encoding="utf-8"))
    f = ImageFont.truetype(FONT, 16)
    rows = []
    for s in tl["shots"]:
        if ids and s["id"] not in ids:
            continue
        a, b = s["start"], s["end"]
        # 등장 구간 0~1.2초를 촘촘히, 나머지는 중간 하나와 끝 직전 둘
        head = [a + 0.03 + i * min(1.2, (b - a) * 0.5) / (n - 4) for i in range(n - 3)]
        ts = head + [(a + b) / 2, b - 0.25, b - 2 / 30]
        ims = [grab(video, t) for t in ts]
        w, h = ims[0].size
        row = Image.new("RGB", (len(ims) * (w + 2), h + 20), (20, 20, 20))
        d = ImageDraw.Draw(row)
        d.text((4, 2), f"{s['id']}  {a:.2f}~{b:.2f}s", fill=(255, 255, 255), font=f)
        for i, im in enumerate(ims):
            row.paste(im, (i * (w + 2), 20))
            d.text((i * (w + 2) + 4, 22), f"{ts[i]:.2f}", fill=(255, 255, 0), font=f)
        rows.append(row)
    W = max(r.size[0] for r in rows)
    H = sum(r.size[1] for r in rows)
    sheet = Image.new("RGB", (W, H))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.size[1]
    sheet.save(out, quality=82)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
