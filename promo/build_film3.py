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

# 글자 규격: 한 줄 10자 이하 168, 14자 이하 136, 그 외 118. 두 줄은 150
def head_size(text):
    longest = max(len(line) for line in text.replace("*", "").split("\n"))
    lines = text.count("\n") + 1
    s = 168 if longest <= 10 else (136 if longest <= 14 else 118)
    if lines >= 2:
        s = min(s, 150)
    return s


HEAD = dict(weight=700, letter_spacing=-0.035, line_height=1.14, max_width=1700, shadow=False, align="center", x="center", y="center",
            anim_in="fade", in_frames=6, anim_out="cut")
SUB = dict(size=56, weight=500, letter_spacing=-0.015, line_height=1.3, max_width=1500, shadow=False, align="center", x="center",
           anim_in="fade", in_frames=8, anim_out="cut")
QUOTE = dict(size=108, weight=600, letter_spacing=-0.03, line_height=1.28, max_width=1560, shadow=False, align="center", x="center", y="center",
             anim_in="fade", in_frames=6, anim_out="cut")
SRC = dict(size=54, weight=500, letter_spacing=0.0, line_height=1.2, max_width=1400, shadow=False, align="center", x="center",
           anim_in="fade", in_frames=8, anim_out="cut")
PAPER_SOFT = "rgba(245,245,247,0.75)"
NAME_GRAY = "#6e6e73"


def tcolor(bg, soft=False):
    if bg in ("black", "photo_reception"):
        return PAPER_SOFT if soft else PAPER
    return INK_SOFT if soft else INK


def accent(bg):
    return ACCENT_ON_BLACK if bg == "black" else ACCENT


def bg_of(kind):
    if kind == "white":
        return {"type": "color", "color": WHITE}
    if kind == "black":
        return {"type": "color", "color": BLACK}
    if kind == "photo_doctor":
        return {"type": "image", "src": os.path.join(HOSP, "doctor_portrait_16x9.jpg"), "zoom": "in", "zoom_amount": 0.05, "anchor": [0.62, 0.0],
                "grade": {"contrast": 1.0, "saturation": 0.95}, "vignette": False, "grain": 0.03}
    if kind == "photo_reception":
        return {"type": "image", "src": os.path.join(HOSP, "reception_16x9.jpg"), "zoom": "in", "zoom_amount": 0.06,
                "grade": {"contrast": 1.02, "saturation": 0.88, "brightness": -0.10, "gamma": 0.92}, "vignette": False, "grain": 0.03,
                "fade_out": 4, "fade_color": "white"}
    raise ValueError(kind)


def word_times(text, start, step=0.25, two_word_step=0.35, line_gap=0.35):
    """단어별 등장 시각. 두 단어짜리 줄은 간격을 조금 넓히고, 다음 줄 첫 단어는 앞 줄 마지막 단어 + line_gap."""
    out = []
    t = start + 0.05
    for li, line in enumerate(text.split("\n")):
        words = [w for w in line.split(" ") if w]
        st = two_word_step if len(words) == 2 else step
        if li > 0:
            t = out[-1] + line_gap
        for i, _ in enumerate(words):
            out.append(round(t + i * st, 4))
    return out


def anim_for(sound):
    if sound == "hit":
        return dict(anim_in="hit", in_frames=4, hit_scale=1.03)     # 강타는 소리가 맡고 글자는 거의 가만히
    if sound == "silence":
        return dict(anim_in="fade", in_frames=12)
    return dict(anim_in="fade", in_frames=6)


def build(script):
    END = round(sum(float(sc["seconds"]) for sc in script["screens"]), 3)
    src_label = script.get("quote_source", "네이버 방문자 리뷰")
    shots = []
    t = 0.0
    prev = None
    for sc in script["screens"]:
        sid = f"s{sc['no']:02d}"
        secs = float(sc["seconds"])
        a, b = t, t + secs
        a_f, b_f = round(round(a * FPS) / FPS, 6), round(round(b * FPS) / FPS, 6)
        bg = bg_of(sc["bg"])
        texts, images = [], []
        text = sc["text"].replace("\\n", "\n")
        motion = sc.get("motion", "cut")
        role = sc.get("role")
        same_photo = prev is not None and sc["bg"] == "photo_reception" and prev["bg"] == "photo_reception"
        if role == "brand":
            # 브랜드 한 줄: 컷 뒤 5프레임 빈 흰 화면, 중앙에서 떠올라 다음 화면에서 위로 물러나며 끝까지 남는다
            size = 220
            texts.append(dict(HEAD, text=text, start=a_f + 0.17, end=END, size=size, color=INK, accent_color=ACCENT, y=414, y_to=170,
                              move_at=b_f, move_frames=18, anim_in="fade", in_frames=12))
        elif role == "logo":
            images.append({"src": os.path.join(HOSP, "logo_color.png"), "start": a_f + 0.2, "end": END, "width": 600, "y": 470,
                           "anim_in": "fade", "in_frames": 12, "anim_out": "none"})
            texts.append(dict(SUB, text=text, start=a_f + 0.55, end=END, size=52, weight=500, color=NAME_GRAY, y=660, anim_in="fade", in_frames=10))
        elif role == "info":
            l1, _, l2 = text.partition("\n")
            texts.append(dict(SUB, text=l1, start=a_f, end=END, size=60, weight=500, color=INK, y=796, anim_in="fade", in_frames=8))
            texts.append(dict(SUB, text=l2, start=a_f + 0.15, end=END, size=96, weight=600, letter_spacing=0.02, color=INK, y=872, anim_in="fade", in_frames=8))
        elif motion == "quote":
            body = text.strip().strip('"“”')
            lines = body.split("\n")
            longest = max(len(x) for x in lines)
            size = 108 if longest <= 14 else (96 if longest <= 17 else 84)
            q = dict(QUOTE, text=f"“{body}”", start=a_f, end=b_f, size=size, color=tcolor(sc["bg"]), accent_color=accent(sc["bg"]), **anim_for(sc.get("sound")))
            texts.append(q)
            cap = dict(SRC, text=src_label, start=a_f + 0.35, end=b_f, color=tcolor(sc["bg"], soft=True),
                       y=int(540 + size * 1.28 * len(lines) / 2 + 56))
            if prev is not None and prev.get("motion") == "quote" and prev["bg"] == sc["bg"]:
                cap.update(start=a_f, anim_in="none")            # 같은 캡션이 사라졌다 다시 뜨지 않게
            texts.append(cap)
        else:
            h = dict(HEAD, text=text, start=a_f, end=b_f, size=head_size(text), color=tcolor(sc["bg"]), accent_color=accent(sc["bg"]), **anim_for(sc.get("sound")))
            if sc["bg"] == "photo_doctor":
                h.update(x=160, align="left", max_width=1000, color=INK, shadow=False, size=140, y=int(540 - 140 * 1.14))
            if sc["bg"] == "photo_reception":
                h.update(x=300, align="left", max_width=900, size=104, y=660, shadow=False, anim_in="fade", in_frames=8)
                if not same_photo:
                    images.append({"src": os.path.join(HOSP, "scrim_bottom.png"), "start": a_f, "end": b_f, "width": 1920, "x": 0, "y": 0,
                                   "anim_in": "none", "anim_out": "fade", "out_frames": 4})
            if sc["no"] in (3, 4):
                h.update(x=540, align="left")                       # '다'가 같은 자리에 멈추고 뒷말만 바뀌는 매치 컷
            if sc.get("words_rel"):
                h.update(anim_in="none", words=[round(a_f + w, 4) for w in sc["words_rel"]], word_frames=8)
            elif motion in ("words", "stack"):
                h.update(anim_in="none", words=word_times(text, a_f), word_frames=8)
            texts.append(h)
        if same_photo:
            # 같은 사진이 이어지면 샷을 합쳐 줌이 한 번만 걸리게 한다 (글자만 바뀐다)
            shots[-1]["end"] = b_f
            shots[-1]["texts"] += texts
            if shots[-1].get("images"):
                shots[-1]["images"][0]["end"] = b_f
        else:
            shot = {"id": sid, "start": a_f, "end": b_f, "bg": bg, "texts": texts, "_sound": sc.get("sound", "beat"), "_motion": motion, "_note": sc.get("note", "")}
            if images:
                shot["images"] = images
            shots.append(shot)
        prev = sc
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
