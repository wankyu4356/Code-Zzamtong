"""
세 번째 영상: 애플 광고 문법의 타이포그래피 필름. 흰/검 화면에 큰 글자, 실제 사진 두 장, 리뷰는 큰 따옴표 인용.
구성은 film3/script.json (카피 워크플로 결과)에서 읽는다. 각 screen: text, bg, seconds, motion, sound, note.
사용: python3 build_film3.py [film3/script.json] [out.json]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOSP = os.path.join(HERE, "assets", "hospital")
FPS = 30
F = 1 / FPS

WHITE = "#f5f5f7"
BLACK = "#000000"
INK = "#1d1d1f"
INK_SOFT = "rgba(29,29,31,0.55)"
PAPER = "#f5f5f7"
PAPER_SOFT = "rgba(245,245,247,0.6)"
ACCENT = "#003070"          # 로고 남색
ACCENT_ON_BLACK = "#5b9cff"

# 글자 규격: 헤드라인은 글자 수에 따라 크기를 정한다 (한 줄 기준 최대 폭 1640px)
def head_size(text):
    longest = max(len(line) for line in text.replace("*", "").split("\n"))
    lines = text.count("\n") + 1
    if longest <= 6:
        s = 200
    elif longest <= 9:
        s = 168
    elif longest <= 12:
        s = 136
    elif longest <= 14:
        s = 118
    else:
        s = 100
    if lines >= 2:
        s = min(s, 150)
    return s


HEAD = dict(weight=700, letter_spacing=-0.035, line_height=1.14, max_width=1700, shadow=False, align="center", x="center", y="center",
            anim_in="fade", in_frames=7, anim_out="cut")
SUB = dict(size=56, weight=500, letter_spacing=-0.015, line_height=1.3, max_width=1500, shadow=False, align="center", x="center",
           anim_in="fade", in_frames=8, anim_out="cut")
QUOTE = dict(size=108, weight=600, letter_spacing=-0.03, line_height=1.28, max_width=1560, shadow=False, align="center", x="center", y="center",
             anim_in="fade", in_frames=8, anim_out="cut")
SRC = dict(size=40, weight=500, letter_spacing=0.0, line_height=1.2, max_width=1400, shadow=False, align="center", x="center",
           anim_in="fade", in_frames=8, anim_out="cut")


def tcolor(bg, soft=False):
    if bg in ("black", "photo_doctor", "photo_reception"):
        return PAPER_SOFT if soft else PAPER
    return INK_SOFT if soft else INK


def accent(bg):
    return ACCENT_ON_BLACK if bg in ("black", "photo_doctor", "photo_reception") else ACCENT


def bg_of(kind):
    if kind == "white":
        return {"type": "color", "color": WHITE}
    if kind == "black":
        return {"type": "color", "color": BLACK}
    if kind == "photo_doctor":
        return {"type": "image", "src": os.path.join(HOSP, "doctor_portrait_16x9.jpg"), "zoom": "in", "zoom_amount": 0.05, "anchor": [0.62, 0.5],
                "grade": {"contrast": 1.02, "saturation": 0.9}, "vignette": True, "grain": 0.03}
    if kind == "photo_reception":
        return {"type": "image", "src": os.path.join(HOSP, "reception_16x9.jpg"), "zoom": "in", "zoom_amount": 0.05,
                "grade": {"contrast": 1.02, "saturation": 0.88, "brightness": -0.28}, "vignette": True, "grain": 0.03}
    raise ValueError(kind)


def word_times(text, start, step=0.11):
    n = len([w for w in text.replace("\n", " ").split(" ") if w])
    return [round(start + i * step, 4) for i in range(n)]


def build(script):
    shots = []
    t = 0.0
    for sc in script["screens"]:
        sid = f"s{sc['no']:02d}"
        secs = float(sc["seconds"])
        a, b = t, t + secs
        a_f, b_f = round(round(a * FPS) / FPS, 6), round(round(b * FPS) / FPS, 6)
        bg = bg_of(sc["bg"])
        texts = []
        text = sc["text"].replace("\\n", "\n")
        motion = sc.get("motion", "cut")
        if motion == "quote":
            body, _, src = text.partition("\n")
            body = body.strip().strip('"“”')
            q = dict(QUOTE, text=f"“{body}”", start=a_f, end=b_f, color=tcolor(sc["bg"]), accent_color=accent(sc["bg"]))
            q["size"] = 108 if len(body) <= 16 else (92 if len(body) <= 22 else (80 if len(body) <= 30 else 68))
            texts.append(q)
            texts.append(dict(SRC, text=(src.strip() or "네이버 방문자 리뷰"), start=a_f + 0.35, end=b_f, color=tcolor(sc["bg"], soft=True),
                              y=int(540 + q["size"] * 1.28 * (1 if len(body) <= 22 else 2) / 2 + 64)))
        else:
            h = dict(HEAD, text=text, start=a_f, end=b_f, size=head_size(text), color=tcolor(sc["bg"]), accent_color=accent(sc["bg"]))
            if sc["bg"] == "photo_doctor":
                h.update(x=140, align="left", max_width=1000)
            if motion == "words":
                h.update(anim_in="none", words=word_times(text, a_f + 0.05), word_frames=8)
            texts.append(h)
        shot = {"id": sid, "start": a_f, "end": b_f, "bg": bg, "texts": texts, "_sound": sc.get("sound", "beat"), "_motion": motion, "_note": sc.get("note", "")}
        shots.append(shot)
        t = b_f
    return shots, t


if __name__ == "__main__":
    args = [x for x in sys.argv[1:]]
    script_p = args[0] if args else os.path.join(HERE, "film3", "script.json")
    script = json.load(open(script_p, encoding="utf-8"))
    shots, total = build(script)
    audio = os.path.join(HERE, "music", "render", "film3_music.wav")
    tl = {"fps": FPS, "width": 1920, "height": 1080, "duration": total, "audio": audio if os.path.exists(audio) else None, "shots": shots}
    out = args[1] if len(args) > 1 else os.path.join(HERE, "engine", "timeline_film3.json")
    json.dump(tl, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {out}: {len(shots)} shots, {total:.2f}s")
    for s in shots:
        print(f"  {s['id']} {s['start']:6.2f}~{s['end']:6.2f} {s['bg']['type']:5s} {s['_motion']:6s} {s['_sound']:7s} {s['texts'][0]['text'][:30]!r}")
