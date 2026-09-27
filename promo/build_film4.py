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
ACCENT_ON_BLACK = "#9cc3ff"

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
PAPER_SOFT = "rgba(245,245,247,0.85)"
GRAY_READ = "#515154"          # 작은 글자용 진회색 (흰 배경 대비 7.3:1)
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
    return "rgba(245,245,247,0.12)" if bg in ("black", "navy") else "rgba(29,29,31,0.12)"


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


SKY = "#9cc3ff"           # 사진·남색 위 강조색


def line_words(text, times):
    """줄 단위 등장: times[i]는 i번째 줄의 모든 단어가 뜨는 시각."""
    out = []
    for li, line in enumerate(text.split("\n")):
        for _ in [w for w in line.split(" ") if w]:
            out.append(round(times[min(li, len(times) - 1)], 4))
    return out


def split_accents(text):
    """'*둘 다*'처럼 여러 단어에 걸친 강조를 '*둘* *다*'로 나눈다 (엔진은 단어 단위로 칠한다)."""
    import re
    return re.sub(r"\*([^*]+)\*", lambda m: " ".join(f"*{w}*" for w in m.group(1).split(" ") if w), text)


def thin_dot(text):
    return text.replace("·", "\u2009·\u2009")


def build(script):
    END = round(sum(float(sc["seconds"]) for sc in script["screens"]), 3)
    src_label = script.get("quote_source", "네이버 방문자 리뷰 · 영수증 인증")
    shots = []
    t = 0.0
    marks = []
    for sc in script["screens"]:
        marks.append(t)
        t += float(sc["seconds"])
    logo_at = next((round(marks[i], 3) for i, sc in enumerate(script["screens"]) if sc.get("role") == "logo"), END)
    t = 0.0
    for sc in script["screens"]:
        sid = f"s{sc['no']:02d}"
        secs = float(sc["seconds"])
        a, b = t, t + secs
        a_f, b_f = round(round(a * FPS) / FPS, 6), round(round(b * FPS) / FPS, 6)
        kind = sc["bg"]
        bg = bg_of(kind)
        if kind == "photo_reception":
            bg.pop("fade_out", None); bg.pop("fade_color", None)          # 다음 강타에 하드 컷
        texts, images, fx = [], [], []
        text = split_accents(sc["text"].replace("\\n", "\n"))
        motion = sc.get("motion", "cut")
        items = [str(x) for x in (sc.get("items") or [])]
        role = sc.get("role")
        snd = sc.get("sound", "beat")
        col, soft = tcolor(kind), tcolor(kind, soft=True)
        acc = SKY if kind in ("navy", "photo_reception") else accent(kind)
        title_anim = dict(anim_in="hit", in_frames=4, hit_scale=1.03)      # 답 화면(사양표) 제목은 강타로 묶는다. 질문은 track

        if role == "brand":
            # 브랜드: 앞 화면 슬롯 줄이 같은 자리에 남고 둘째 줄이 강타에 붙는다. 로고 화면에서 절반 크기로 줄며 위로 올라간다
            words = line_words(text, [a_f - 1.0, a_f])
            texts.append(dict(HEAD, text=text, start=a_f, end=END, size=168, color=INK, accent_color=ACCENT, y=350, y_to=51, scale_to=0.5,
                              move_at=round(logo_at - 0.4, 4), move_frames=24, move_ease="inOut", ls_to=-0.02,
                              drift_scale=0.015, drift_until=round(logo_at - 0.4, 4), anim_in="none", words=words, word_frames=6))
        elif role == "logo":
            # 로고와 이름 한 줄: 처음엔 가운데 쪽에 있다가 정보가 들어올 때 120px 올라간다
            lift = dict(move_at=b_f, move_frames=18, move_ease="inOut")
            images.append(dict({"src": os.path.join(HOSP, "logo_color.png"), "start": round(a_f + 0.4, 4), "end": END, "width": 440, "y": 512, "y_to": 392,
                                "anim_in": "fade", "in_frames": 12, "anim_out": "none"}, **lift))
            texts.append(dict(SUB, text=text.replace("\n", " "), start=round(a_f + 0.6, 4), end=END, size=56, weight=600, color=INK, accent_color=GRAY_READ,
                              y=659, y_to=539, anim_in="fade", in_frames=10, anim_out="fade", out_frames=12, out_to=0.35, **lift))
        elif role == "info":
            lines = text.split("\n")
            ys = [686, 763, 850]
            for i, ln in enumerate(lines[:3]):
                phone = any(ch.isdigit() for ch in ln) and "-" in ln and i == len(lines[:3]) - 1
                d = dict(SUB, text=ln, start=round(a_f + 0.4 + 0.2 * i, 4), end=END, size=80 if phone else 60, weight=600 if phone else 500,
                         letter_spacing=0.01 if phone else -0.01, color=INK if phone else GRAY_READ, y=ys[i], anim_in="fade", in_frames=10)
                if not phone:
                    d.update(anim_out="fade", out_frames=12, out_to=0.35)     # 마지막 호흡: 정보 두 줄만 옅어지고 전화는 남는다
                texts.append(d)
        elif motion == "quote":
            body = text.strip().strip('"“”')
            lines = body.split("\n")
            longest = max(len(x) for x in lines)
            size = 108 if longest <= 14 else (96 if longest <= 17 else 84)
            qtext = f"“{body}”"
            texts.append(dict(QUOTE, text=qtext, start=a_f, end=b_f, size=size, color=col, accent_color=acc, anim_in="none", hang_quotes=True,
                              words=line_words(qtext, [a_f + 0.75 * i for i in range(len(lines))]), word_frames=10))
            texts.append(dict(SRC, text=sc.get("source") or src_label, start=round(a_f + 0.75 * len(lines) - 0.25, 4), end=b_f, size=56,
                              color=GRAY_READ if kind == "white" else soft, y=int(540 + size * 1.28 * len(lines) / 2 + 56)))
        elif motion == "slot":
            n = max(1, text.count("|") + 1)
            fx.append({"type": "slot", "text": text, "start": a_f, "end": b_f, "size": 168, "weight": 700, "color": col, "slot_color": acc,
                       "letter_spacing": -0.035, "y": 350, "slot_times": [round(a_f + i * 0.5, 4) for i in range(n)], "roll_frames": 6,
                       "roll_frames_last": 12, "roll_overshoot": 1.2, "slot_color_to": INK, "color_at": round(b_f - 0.2, 4), "color_frames": 6,
                       "anim_in": "fade", "in_frames": 6})
        elif motion == "grid":
            cells = items[:12]
            lt = []
            for i in range(len(cells)):
                lt.append(round(a_f + (0.25 + 0.5 * i if i < 3 else 1.5 + 0.25 * (i - 3)), 4))
            fx.append({"type": "grid", "start": a_f, "end": b_f, "size": 80, "weight": 600, "cols": 3, "items": cells, "color": col, "align": "left",
                       "dim_color": dim_color(kind), "light_times": lt, "light_frames": 6, "col_gap": 110, "row_gap": 36, "drift_scale": 0.02,
                       "anim_in": "fade", "in_frames": 6})
        elif motion == "spec":
            texts.append(dict(HEAD, text=thin_dot(text), start=a_f, end=b_f, size=150, color=col, accent_color=acc, y=330, **title_anim))
            for i, it_ in enumerate(items[:4]):
                texts.append(dict(SUB, text=it_, start=round(a_f + 0.5 * (i + 1), 4), end=b_f, size=84, weight=500, color=soft, y=540 + i * 104,
                                  anim_in="rise", in_frames=8))
        elif motion == "list":
            x0 = 160                                   # 앞 화면 이름(x=160)과 같은 기준선
            texts.append(dict(HEAD, text=text, start=a_f, end=b_f, size=110, color=col, accent_color=acc, x=x0, align="left", max_width=1400, y=262,
                              anim_in="fade", in_frames=8))
            for i, it_ in enumerate(items[:6]):
                first = i == 0
                texts.append(dict(SUB, text=it_, start=round(a_f + 0.5 * (i + 1), 4), end=b_f, size=72 if first else 70, weight=600,
                                  color=col if first else GRAY_READ, x=x0, align="left", max_width=1400, y=428 if first else 536 + (i - 1) * 98,
                                  anim_in="rise", in_frames=8))
        else:
            h = dict(HEAD, text=text, start=a_f, end=b_f, size=head_size(text), color=col, accent_color=acc, **anim_for(snd))
            if kind == "photo_doctor":
                h.update(x=160, align="left", max_width=1000, color=INK, shadow=False, size=120, y=472, anim_in="hit", in_frames=4, hit_scale=1.03)
            if kind == "photo_reception":
                h.update(x=300, align="left", max_width=1000, size=124, y=780, shadow=False)
                for op in (1.0, 0.8):                  # 스크림 두 겹: 글자 뒤 검정 알파 약 0.4~0.5
                    images.append({"src": os.path.join(HOSP, "scrim_bottom.png"), "start": a_f, "end": b_f, "width": 1920, "x": 0, "y": 0,
                                   "anim_in": "none", "anim_out": "cut", "opacity": op})
            if motion == "track":
                h.update(anim_in="track", in_frames=20, track_from=0.1, size=124)
            elif motion == "wipe":
                h.update(anim_in="wipe", in_frames=18)
            elif motion == "stack":
                nl = text.count("\n") + 1
                ws = line_words(text, [a_f + 0.75 * i for i in range(nl)])
                if ", " in text.split("\n")[-1]:
                    ws[-1] = round(ws[-1] + 0.5, 4)          # '허리일까,' 다음 한 박 뒤에 '혈관일까?'
                h.update(anim_in="none", words=ws, word_frames=10)
            elif motion == "words":
                h.update(anim_in="none", words=word_times(text, a_f), word_frames=8)
            texts.append(h)

        shot = {"id": sid, "start": a_f, "end": b_f, "bg": bg, "texts": texts, "_sound": snd, "_motion": motion, "_note": sc.get("note", "")}
        if images:
            shot["images"] = images
        if fx:
            shot["fx"] = fx
        shots.append(shot)
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
