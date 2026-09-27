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


def _abs_t(t, shot):
    """모션 사양의 시각: 화면 시작보다 작으면 화면 기준 상대 시각으로 본다."""
    # 모션 사양의 시각은 모두 절대 시각(영상 처음부터 초)이다. 화면 시작보다 이른 값은 '첫 프레임에 이미 서 있음'을 뜻한다
    return round(float(t), 4)


def _line_times_from_words(text, words):
    out, k = [], 0
    for line in text.split("\n"):
        n = len([w for w in line.split(" ") if w])
        if n and k < len(words):
            out.append(words[k])
        k += n
    return out


UNITS = ("char", "word", "line")
TEXT_KEYS = ("anim_in", "in_frames", "hit_scale", "track_from", "drift_scale", "drift_until")


def _clean_exit(x):
    ex = {k: v for k, v in x.items() if k in ("style", "unit", "stagger", "dur", "ease")}
    if ex.get("unit") not in UNITS:
        ex.pop("unit", None)                      # 설명문이 들어온 경우: 엔진이 reveal 단위를 따른다
    return ex


def _set_reveal(t, rv, shot):
    rv = dict(rv)
    if "line_times" in rv:
        rv["line_times"] = [_abs_t(x, shot) for x in rv["line_times"]]
    elif t.get("words") and "\n" in t.get("text", ""):
        rv["line_times"] = _line_times_from_words(t["text"], t["words"])
    t["reveal"] = rv
    t.pop("words", None)
    t.setdefault("anim_in", "none")
    if t.get("anim_in") not in ("hit", "fade", "track", "none"):
        t["anim_in"] = "none"


def _apply_text_keys(t, src, shot):
    for k in TEXT_KEYS:
        if k in src:
            t[k] = _abs_t(src[k], shot) if k == "drift_until" else src[k]
            if k == "anim_in":
                t.pop("words", None)
    if t.get("anim_in") == "hit":
        t["hit_blur"] = src.get("hit_blur", 60)          # 강타 시작 흐림: 배율 0.1당 6px


def apply_motion(shots, script, motion):
    """film4/motion.json(모션 디자인 워크플로 최종 사양)을 타임라인에 입힌다. 카피는 바꾸지 않는다."""
    by_no = {int(m["no"]): m for m in motion.get("screens", [])}
    bg_color = {"white": WHITE, "black": BLACK, "navy": ACCENT, "photo_doctor": WHITE, "photo_reception": WHITE}
    scr = {sc["no"]: sc for sc in script["screens"]}
    for idx, shot in enumerate(shots):
        no = int(shot["id"][1:])
        m = by_no.get(no)
        if not m:
            continue
        sc = scr[no]
        texts = shot.get("texts", [])
        fxs = shot.setdefault("fx", [])
        role = sc.get("role")
        motion_kind = sc.get("motion")
        source = texts[1] if motion_kind == "quote" and len(texts) > 1 else None
        if role == "info":
            phone = next((t for t in texts if "-" in t["text"] and any(c.isdigit() for c in t["text"])), None)
            main, items = phone, [t for t in texts if t is not phone]
        else:
            main = texts[0] if texts else (fxs[0] if fxs else None)
            items = texts[1:] if motion_kind != "quote" else []
        sp = m.get("special") or {}

        # --- 배치 조정 (크기·위치)
        lay = sp.get("layout") or {}
        if main is not None:
            if "size" in lay:
                main["size"] = lay["size"]
            if isinstance(lay.get("title"), dict):
                for k in ("size", "y"):
                    if k in lay["title"]:
                        main[k] = lay["title"][k]
            if isinstance(lay.get("phone"), dict):
                for k in ("size", "weight", "y"):
                    if k in lay["phone"]:
                        main[k] = lay["phone"][k]
        if isinstance(lay.get("items_y"), list):
            for t, y in zip(items, lay["items_y"]):
                t["y"] = y

        # --- 등장
        e = m.get("entry") or {}
        if main is not None and e:
            if "reveal" in e and "text" in main:
                _set_reveal(main, e["reveal"], shot)
            _apply_text_keys(main, e, shot)
            if "element_start" in e and role != "brand":
                main["start"] = _abs_t(e["element_start"], shot)

        # --- 항목 등장
        ie = m.get("items_entry") or {}
        if ie.get("reveal") and items:
            starts = ie.get("element_starts")
            for i, t in enumerate(items):
                _set_reveal(t, ie["reveal"], shot)
                _apply_text_keys(t, ie, shot)
                if starts and i < len(starts):
                    t["start"] = _abs_t(starts[i], shot)
            for t, L in zip(items, ie.get("layout") or []):
                for k in ("x", "y", "align"):
                    if k in L:
                        t[k] = L[k]
        if isinstance(ie.get("source"), dict) and source is not None:
            so = ie["source"]
            if so.get("reveal"):
                _set_reveal(source, so["reveal"], shot)
            _apply_text_keys(source, so, shot)
            if "start" in so:
                source["start"] = _abs_t(so["start"], shot)
        if isinstance(ie.get("logo_image"), dict) and shot.get("images"):
            lg = ie["logo_image"]
            for k in ("anim_in", "in_frames"):
                if k in lg:
                    shot["images"][0][k] = lg[k]
            if "start" in lg:
                shot["images"][0]["start"] = _abs_t(lg["start"], shot)

        # --- 퇴장
        x = m.get("exit") or {}
        if x.get("anim_out"):                                   # 정한 시각부터 옅어지는 마무리 (엔딩)
            tg = items if role == "info" else ([main] if main is not None else [])
            for t in tg:
                t.update(anim_out=x["anim_out"], out_frames=x.get("out_frames", 12), out_to=x.get("out_to", 0))
                if "out_at" in x:
                    t["out_at"] = _abs_t(x["out_at"], shot)
            if role not in ("info",) and main is not None and main.get("type") in ("grid",):
                main.update(anim_out=x["anim_out"], out_frames=x.get("out_frames", 12))
        elif x.get("style") and x["style"] != "none":
            ex = _clean_exit(x)
            end_all = x.get("element_end")
            if x["style"] == "zoom":
                if main is not None:
                    main["exit"] = ex
                for t in items + ([source] if source else []):
                    if t.get("end", 0) <= shot["end"] + 0.01:
                        t["exit"] = {"style": "blur", "dur": ex.get("dur", 10)}
            else:
                els = ([main] if main is not None and "text" in main else []) + items + ([source] if source else [])
                ends = x.get("element_ends")
                for i, t in enumerate(els):
                    if t.get("end", 0) > shot["end"] + 0.01:
                        continue
                    t["exit"] = dict(ex)
                    if ends and i < len(ends):
                        t["end"] = _abs_t(ends[i], shot)
                    elif end_all is not None:
                        t["end"] = _abs_t(end_all, shot)

        # --- 스윕·밑줄
        a_ = m.get("accent_fx") or {}
        if main is not None and "text" in main:
            for k in ("sheen", "underline"):
                if a_.get(k):
                    v = dict(a_[k])
                    v["at"] = _abs_t(v.get("at", shot["start"]), shot)
                    main[k] = v

        # --- 이동·호흡 (브랜드 줄, 로고·이름)
        if isinstance(sp.get("move"), dict) and main is not None:
            mv = sp["move"]
            if role == "logo":
                for k, key in (("logo_y_to", "img"), ("name_y_to", "name")):
                    pass
                if shot.get("images"):
                    im = shot["images"][0]
                    im.update(move_at=_abs_t(mv.get("move_at", im.get("move_at", shot["end"])), shot), move_frames=mv.get("move_frames", 15),
                              move_ease=mv.get("move_ease", "inOut"))
                    if "logo_y_to" in mv:
                        im["y_to"] = mv["logo_y_to"]
                main.update(move_at=_abs_t(mv.get("move_at", shot["end"]), shot), move_frames=mv.get("move_frames", 15), move_ease=mv.get("move_ease", "inOut"))
                if "name_y_to" in mv:
                    main["y_to"] = mv["name_y_to"]
            else:
                for k in ("move_frames", "move_ease", "y_to", "scale_to", "ls_to"):
                    if k in mv:
                        main[k] = mv[k]
                if "move_at" in mv:
                    main["move_at"] = _abs_t(mv["move_at"], shot)
        for k in ("drift_scale", "drift_until"):
            if k in sp and main is not None:
                main[k] = _abs_t(sp[k], shot) if k == "drift_until" else sp[k]

        # --- 배경: 끝에서 검정으로 가라앉기, 카메라 밀어 넣기
        if isinstance(sp.get("bg"), dict):
            for k in ("fade_out", "fade_color"):
                if k in sp["bg"]:
                    shot["bg"][k] = sp["bg"][k]
        if isinstance(sp.get("bg_push_out"), dict) and shot["bg"]["type"] in ("image", "clip"):
            shot["bg"]["push_out"] = {k: sp["bg_push_out"][k] for k in ("frames", "amount", "blur") if k in sp["bg_push_out"]}

        # --- 전환
        tr = m.get("transition_out") or {}
        if tr.get("type") == "shape_wipe":
            nxt = script["screens"][idx + 1]["bg"] if idx + 1 < len(script["screens"]) else "white"
            f = {"type": "shape_wipe", "shape": tr.get("shape", "circle"), "origin": tr.get("origin", [960, 540]),
                 "color": tr.get("color") or bg_color.get(nxt, WHITE), "start": _abs_t(tr["start"], shot), "end": _abs_t(tr.get("end", shot["end"]), shot)}
            for k in ("ease", "feather", "feather_grow"):
                if k in tr:
                    f[k] = tr[k]
            fxs.append(f)
        elif tr.get("type") == "exit_zoom" and main is not None and not main.get("exit"):
            main["exit"] = {"style": "zoom", "dur": tr.get("dur", 8)}

        # --- 특수 요소
        SKIP = {"remove", "text", "note", "request", "pattern"}
        for fx in fxs:
            spec_fx = sp.get(fx["type"])
            if isinstance(spec_fx, dict):
                for k, v in spec_fx.items():
                    if k in SKIP:
                        continue
                    if k in ("light_times", "slot_times"):
                        v = [_abs_t(t, shot) for t in v]
                    elif k == "color_at":
                        v = _abs_t(v, shot)
                    fx[k] = v
                if fx["type"] == "slot" and "slot_color_to" not in spec_fx:
                    for k in ("slot_color_to", "color_at", "color_frames"):
                        fx.pop(k, None)
        if isinstance(ie.get("light_times"), list):
            for fx in fxs:
                if fx["type"] == "grid":
                    fx["light_times"] = [_abs_t(t, shot) for t in ie["light_times"]]
                    for k in ("cell_style", "light_frames"):
                        if k in ie:
                            fx[k] = ie[k]
        lds = sp.get("line_draw")
        lds = lds if isinstance(lds, list) else ([lds] if isinstance(lds, dict) else [])
        line_end = sp.get("element_end") or x.get("element_end")
        for ld in lds:
            f = {"type": "line_draw", "start": shot["start"], "end": _abs_t(ld.get("end", line_end or shot["end"]), shot),
                 "draw_start": _abs_t(ld.get("start", shot["start"]), shot), "anim_out": ld.get("anim_out", "fade"),
                 "out_frames": ld.get("out_frames", sp.get("line_out_frames", 8))}
            f.update({k: ld[k] for k in ("x1", "y1", "x2", "y2", "color", "thickness", "dur") if k in ld})
            fxs.append(f)
        if not fxs:
            shot.pop("fx", None)


if __name__ == "__main__":
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    script_p = args[0] if args else os.path.join(HERE, "film4", "script.json")
    script = json.load(open(script_p, encoding="utf-8"))
    shots, total = build(script)
    motion_p = os.path.join(HERE, "film4", "motion.json")
    if os.path.exists(motion_p) and "--no-motion" not in sys.argv:
        apply_motion(shots, script, json.load(open(motion_p, encoding="utf-8")))
        print("motion spec applied:", motion_p)
    audio = os.path.join(HERE, "music", "render", "film4_music.wav")
    tl = {"fps": FPS, "width": 1920, "height": 1080, "duration": total, "audio": audio if os.path.exists(audio) else None, "shots": shots}
    out = args[1] if len(args) > 1 else os.path.join(HERE, "engine", "timeline_film4.json")
    json.dump(tl, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {out}: {len(shots)} shots, {total:.2f}s")
    for s in shots:
        first = (s["texts"][0]["text"] if s["texts"] else (s["fx"][0]["type"] if s.get("fx") else ""))
        print(f"  {s['id']} {s['start']:6.2f}~{s['end']:6.2f} {s['bg']['type']:5s} {s['_motion']:6s} {s['_sound']:7s} {first[:30]!r}")
