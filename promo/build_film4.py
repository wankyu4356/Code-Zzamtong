"""
네 번째 영상: 진료 범위와 원장 이력을 중심에 둔 애플풍 타이포그래피 필름.
구성은 film4/script.json에서 읽는다. motion: cut words stack track wipe slot ticker grid spec count list quote. bg: white black navy photo_doctor photo_reception.
사용: python3 build_film4.py [film4/script.json] [out.json]
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
    if bg in ("black", "navy", "photo_reception"):
        return PAPER_SOFT if soft else PAPER
    return INK_SOFT if soft else INK


def accent(bg):
    if bg == "black":
        return ACCENT_ON_BLACK
    if bg == "navy":
        return "#9cc3ff"
    return ACCENT


def dim_color(bg):
    return "rgba(245,245,247,0.22)" if bg in ("black", "navy") else "rgba(29,29,31,0.18)"


def bg_of(kind):
    if kind == "white":
        return {"type": "color", "color": WHITE}
    if kind == "black":
        return {"type": "color", "color": BLACK}
    if kind == "navy":
        return {"type": "color", "color": ACCENT}
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
    src_label = script.get("quote_source", "네이버 방문자 리뷰 · 영수증 인증 · 발췌")
    shots = []
    t = 0.0
    prev = None
    for sc in script["screens"]:
        sid = f"s{sc['no']:02d}"
        secs = float(sc["seconds"])
        a, b = t, t + secs
        a_f, b_f = round(round(a * FPS) / FPS, 6), round(round(b * FPS) / FPS, 6)
        kind = sc["bg"]
        bg = bg_of(kind)
        texts, images, fx = [], [], []
        text = sc["text"].replace("\\n", "\n")
        motion = sc.get("motion", "cut")
        items = [str(x) for x in (sc.get("items") or [])]
        role = sc.get("role")
        col, soft, acc = tcolor(kind), tcolor(kind, soft=True), accent(kind)
        same_photo = prev is not None and kind == "photo_reception" and prev["bg"] == "photo_reception"
        on_doctor = kind == "photo_doctor"

        if role == "brand":
            texts.append(dict(HEAD, text=text, start=a_f + 0.17, end=END, size=220, color=INK, accent_color=ACCENT, y=414, y_to=170,
                              move_at=b_f, move_frames=18, anim_in="track", in_frames=16))
        elif role == "logo":
            images.append({"src": os.path.join(HOSP, "logo_color.png"), "start": a_f + 0.2, "end": END, "width": 600, "y": 470,
                           "anim_in": "fade", "in_frames": 12, "anim_out": "none"})
            texts.append(dict(SUB, text=text, start=a_f + 0.55, end=END, size=52, weight=500, color=NAME_GRAY, y=660, anim_in="fade", in_frames=10))
        elif role == "info":
            l1, _, l2 = text.partition("\n")
            texts.append(dict(SUB, text=l1, start=a_f, end=END, size=60, weight=500, color=INK, y=796, anim_in="fade", in_frames=8))
            if l2:
                texts.append(dict(SUB, text=l2, start=a_f + 0.15, end=END, size=96, weight=600, letter_spacing=0.02, color=INK, y=872, anim_in="fade", in_frames=8))
        elif motion == "quote":
            body = text.strip().strip('"“”')
            lines = body.split("\n")
            longest = max(len(x) for x in lines)
            size = 108 if longest <= 14 else (96 if longest <= 17 else 84)
            texts.append(dict(QUOTE, text=f"“{body}”", start=a_f, end=b_f, size=size, color=col, accent_color=acc, **anim_for(sc.get("sound"))))
            label = sc.get("source") or src_label
            texts.append(dict(SRC, text=label, start=a_f + 0.35, end=b_f, color=soft, y=int(540 + size * 1.28 * len(lines) / 2 + 56)))
        elif motion == "slot":
            n = max(1, text.count("|") + 1)
            hold = 1.1
            step = max(0.3, (secs - hold - 0.1) / max(1, n - 1))
            fx.append({"type": "slot", "text": text, "start": a_f, "end": b_f, "size": 168 if len(text) <= 22 else 136, "weight": 700, "color": col,
                       "slot_color": acc, "slot_times": [round(a_f + 0.1 + i * step, 4) for i in range(n)], "roll_frames": 7, "anim_in": "fade", "in_frames": 6})
        elif motion == "ticker":
            rows = [x for x in items if x.strip()][:6]
            n = len(rows)
            ys = [int(540 - (n - 1) * 90 + i * 180) - 60 for i in range(n)] if n else []
            speeds = [260, 180, 320, 210, 290, 240]
            fx.append({"type": "ticker", "start": a_f, "end": b_f, "size": 96, "weight": 600, "color": dim_color(kind).replace("0.18", "0.38").replace("0.22", "0.38"),
                       "settle": sc.get("settle") or "", "settle_at": round(b_f - max(1.2, secs * 0.4), 3), "settle_size": 176, "settle_color": col,
                       "rows": [{"words": r.split(), "y": ys[i], "speed": speeds[i % 6], "dir": -1 if i % 2 == 0 else 1, "phase": (i * 370) % 1000} for i, r in enumerate(rows)],
                       "anim_in": "fade", "in_frames": 6})
        elif motion == "grid":
            cells = items[:12]
            cols = 3 if len(cells) in (5, 6, 9) else (4 if len(cells) >= 7 else 3)
            step = max(0.12, (secs - 1.2) / max(1, len(cells)))
            fx.append({"type": "grid", "start": a_f, "end": b_f, "size": 84 if len(cells) <= 9 else 72, "weight": 600, "cols": cols, "items": cells,
                       "color": col, "dim_color": dim_color(kind), "light_times": [round(a_f + 0.25 + i * step, 4) for i in range(len(cells))],
                       "light_frames": 6, "col_gap": 84, "row_gap": 22, "anim_in": "fade", "in_frames": 6})
            if text.strip():
                texts.append(dict(SUB, text=text, start=a_f, end=b_f, size=44, weight=500, color=soft, y=120, anim_in="fade", in_frames=6))
        elif motion == "count":
            try:
                to = int("".join(ch for ch in text if ch.isdigit()))
            except ValueError:
                to = 0
            fx.append({"type": "count", "start": a_f, "end": b_f, "from": 0, "to": to, "count_start": a_f + 0.1, "count_frames": 30,
                       "size": 300, "weight": 700, "color": acc, "letter_spacing": -0.04, "y": 300, "anim_in": "fade", "in_frames": 6})
            if items:
                texts.append(dict(SUB, text=items[0], start=a_f + 1.1, end=b_f, size=72, weight=600, color=col, y=660, anim_in="rise", in_frames=8))
        elif motion == "spec":
            h = dict(HEAD, text=text, start=a_f, end=b_f, size=136, color=col, accent_color=acc, y=248, anim_in="track", in_frames=14)
            texts.append(h)
            rows = items[:6]
            for i, it_ in enumerate(rows):
                texts.append(dict(SUB, text=it_, start=round(a_f + 0.35 + i * 0.16, 4), end=b_f, size=64, weight=500, color=soft, y=460 + i * 88,
                                  anim_in="rise", in_frames=8))
        elif motion == "list":
            x0 = 160
            h = dict(HEAD, text=text, start=a_f, end=b_f, size=84, color=INK if on_doctor else col, accent_color=acc, x=x0, align="left", max_width=1000,
                     y=180, anim_in="fade", in_frames=8)
            texts.append(h)
            rows = items[:8]
            for i, it_ in enumerate(rows):
                texts.append(dict(SUB, text=it_, start=round(a_f + 0.4 + i * 0.22, 4), end=b_f, size=50, weight=500, color=(INK if on_doctor else col),
                                  x=x0, align="left", max_width=1000, y=330 + i * 74, anim_in="rise", in_frames=8))
        else:
            h = dict(HEAD, text=text, start=a_f, end=b_f, size=head_size(text), color=col, accent_color=acc, **anim_for(sc.get("sound")))
            if on_doctor:
                h.update(x=160, align="left", max_width=1000, color=INK, shadow=False, size=min(head_size(text), 140), y=int(540 - 140 * 1.14))
            if kind == "photo_reception":
                h.update(x=300, align="left", max_width=900, size=104, y=660, shadow=False, anim_in="fade", in_frames=8)
                if not same_photo:
                    images.append({"src": os.path.join(HOSP, "scrim_bottom.png"), "start": a_f, "end": b_f, "width": 1920, "x": 0, "y": 0,
                                   "anim_in": "none", "anim_out": "fade", "out_frames": 4})
            if motion == "track":
                h.update(anim_in="track", in_frames=16)
            elif motion == "wipe":
                h.update(anim_in="wipe", in_frames=18)
            elif sc.get("words_rel"):
                h.update(anim_in="none", words=[round(a_f + w, 4) for w in sc["words_rel"]], word_frames=8)
            elif motion in ("words", "stack"):
                h.update(anim_in="none", words=word_times(text, a_f), word_frames=8)
            texts.append(h)

        if same_photo:
            shots[-1]["end"] = b_f
            shots[-1]["texts"] += texts
            if shots[-1].get("images"):
                shots[-1]["images"][0]["end"] = b_f
        else:
            shot = {"id": sid, "start": a_f, "end": b_f, "bg": bg, "texts": texts, "_sound": sc.get("sound", "beat"), "_motion": motion, "_note": sc.get("note", "")}
            if images:
                shot["images"] = images
            if fx:
                shot["fx"] = fx
            shots.append(shot)
        prev = sc
        t = b_f
    return shots, t


if __name__ == "__main__":
    args = [x for x in sys.argv[1:]]
    script_p = args[0] if args else os.path.join(HERE, "film4", "script.json")
    script = json.load(open(script_p, encoding="utf-8"))
    shots, total = build(script)
    audio = os.path.join(HERE, "music", "render", "film4_music.wav")
    tl = {"fps": FPS, "width": 1920, "height": 1080, "duration": total, "audio": audio if os.path.exists(audio) else None, "shots": shots}
    out = args[1] if len(args) > 1 else os.path.join(HERE, "engine", "timeline_film4.json")
    json.dump(tl, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {out}: {len(shots)} shots, {total:.2f}s")
    for s in shots:
        first = (s["texts"][0]["text"] if s["texts"] else (s["fx"][0]["type"] if s.get("fx") else ""))
        print(f"  {s['id']} {s['start']:6.2f}~{s['end']:6.2f} {s['bg']['type']:5s} {s['_motion']:6s} {s['_sound']:7s} {first[:30]!r}")
