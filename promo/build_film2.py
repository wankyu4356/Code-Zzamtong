"""
두 번째 영상 "토요일, 내 무릎의 하루" (1인칭 POV, 세리프 자막, 크림색 종이 화면, 비트 없는 앰비언트).
film2/concept_pov.json의 구성에 심사 지적(첫 3초 비우지 않기, 자막 읽는 시간, 요일 사실, 세 인물 재등장, 엔딩 구조)을 반영했다.
실사는 assets/footage2/final/manifest.json(트림본)에서 읽고, 없으면 크림색 화면에 자막만 얹어 구조가 항상 렌더되게 한다.
사용: python3 build_film2.py [out.json]
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "assets")
FOOT = os.path.join(A, "footage2")
HOSP = os.path.join(A, "hospital")
MANIFEST = os.path.join(FOOT, "final", "manifest.json")
_manifest = json.load(open(MANIFEST, encoding="utf-8")) if os.path.exists(MANIFEST) else {}

CREAM = "#F4EFE6"
INK = "#3A312B"
INK_SOFT = "rgba(58,49,43,0.66)"
PAPER_WHITE = "rgba(250,246,238,0.96)"
SERIF = "Noto Serif CJK KR"
SANS = "Noto Sans CJK KR"
GRADE_CLIP = {"contrast": 0.96, "saturation": 0.84, "brightness": 0.0, "gamma": 1.02, "temperature": 5900}
GRADE_PHOTO = {"contrast": 0.98, "saturation": 0.92, "brightness": 0.0, "gamma": 1.0, "temperature": 6300}

# 샷별 미세 조정 (실사 클립을 받은 뒤 채운다): punch, anchor, brightness, speed
OVERRIDES = {
    "f02": {"grade": {"temperature": 5600}},                                    # 흐린 날 중립광을 아침빛으로
    "f04": {"grade": {"temperature": 5300}},                                    # 푸른 기운 보정
    "f03": {"speed": 0.3},                                                     # 1.1초쯤부터 자전거가 들어오므로 0.9초만 늘려 쓴다
    "f05": {"punch": 1.45, "anchor": [0.5, 1.0], "grade": {"saturation": 0.6}},  # 에스컬레이터 발판 위주로, 주황 신발 채도 내림
    "f17": {"speed": 0.3},
    "f09": {"punch": 1.1},
    "f12": {"punch": 1.6, "anchor": [0.9, 0.72], "grade": {"saturation": 0.6, "temperature": 5400}},  # 펜 끝과 빗금 위주로 크게 잘라 그림 형태를 덜 보이게, 파란 펜 채도 내림
    "f14": {"grade": {"temperature": 5500}},
    "f16": {"punch": 1.4, "anchor": [0.5, 0.5]},                                # 문 쪽으로 펀치인
    "f18": {"grade": {"saturation": 0.78}},
}

# 자막 규격
VOICE = dict(font=SERIF, size=44, weight=500, letter_spacing=0.0, line_height=1.45, color=PAPER_WHITE, shadow=True,
             x=168, y=884, align="left", max_width=1600, anim_in="fade", in_frames=12, anim_out="cut")
PLACE = dict(font=SERIF, size=34, weight=300, letter_spacing=0.02, line_height=1.4, color=PAPER_WHITE, shadow=True,
             x=168, y=912, align="left", max_width=1200, anim_in="fade", in_frames=9, anim_out="fade", out_frames=9)
QUOTE = dict(font=SERIF, size=46, weight=400, letter_spacing=0.0, line_height=1.7, color=INK, shadow=False,
             x="center", y="center", align="center", max_width=1400, anim_in="rise", in_frames=15, anim_out="fade", out_frames=10)
LABEL = dict(font=SANS, size=24, weight=300, letter_spacing=0.06, line_height=1.2, color=INK_SOFT, shadow=False,
             x="center", align="center", max_width=1400, anim_in="fade", in_frames=12, anim_out="fade", out_frames=10)


def footage(shot_id):
    m = _manifest.get(shot_id)
    if m and os.path.exists(m["file"]):
        return m["file"], float(m["in_point"]), float(m.get("speed", 1.0))
    pick_p = os.path.join(FOOT, "picks", f"{shot_id}.json")
    if not os.path.exists(pick_p):
        return None
    pick = json.load(open(pick_p, encoding="utf-8"))
    if pick.get("no_good_match") or not pick.get("chosen"):
        return None
    f, inp = pick["chosen"]["file"], float(pick["chosen"]["in_point"])
    return (f, inp, 1.0) if os.path.exists(f) else None


def clip_len(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).decode())


def clip_bg(shot_id, need, zoom="in", amount=0.03, **kw):
    f = footage(shot_id)
    if not f:
        return None
    file, inp, speed = f
    o = dict(OVERRIDES.get(shot_id, {}))
    speed = o.pop("speed", speed)
    avail = clip_len(file) - inp
    if avail < need * speed:
        # 부족하면 그만큼 느리게 (최대 25%) 아니면 인점을 앞으로
        speed = max(0.75, avail / need - 0.01)
        if avail < need * speed:
            inp = max(0.0, inp - (need * speed - avail) - 0.02)
    g = dict(GRADE_CLIP)
    g.update(o.pop("grade", {}))
    g["brightness"] = o.pop("brightness", kw.pop("brightness", 0.0))
    bg = {"type": "clip", "src": file, "in": inp, "speed": speed, "fit": "cover", "zoom": zoom, "zoom_amount": amount,
          "grade": g, "vignette": True, "grain": 0.05, "punch": 1.0, "anchor": [0.5, 0.5]}
    bg.update(o)
    bg.update(kw)
    return bg


def photo_bg(name, zoom="in", amount=0.05, punch=1.0, anchor=(0.5, 0.5), **kw):
    p = os.path.join(HOSP, name)
    bg = {"type": "image", "src": p, "fit": "cover", "zoom": zoom, "zoom_amount": amount, "grade": dict(GRADE_PHOTO),
          "vignette": True, "grain": 0.04, "punch": punch, "anchor": list(anchor)}
    bg.update(kw)
    return bg


def page_bg(**kw):
    bg = {"type": "color", "color": CREAM, "grain": 0.025}
    bg.update(kw)
    return bg


def voice(text, start, end, **kw):
    d = dict(VOICE)
    d.update(text=text, start=start, end=end)
    d.update(kw)
    return d


def quote_page(sid, start, end, text, lines, label="네이버 리뷰", show_from=None):
    a = start if show_from is None else show_from
    q = dict(QUOTE, text=text, start=a, end=end)
    # 인용 아래 출처: 인용 블록 높이(줄수 x 42 x 1.7)의 절반 + 여백
    y = int(540 + lines * 46 * 1.7 / 2 + 46)
    lab = dict(LABEL, text=label, start=a + 0.25, end=end, y=y)
    return shot(sid, start, end, page_bg(), [q, lab])


def shot(sid, start, end, bg, texts=None, images=None):
    s = {"id": sid, "start": start, "end": end, "bg": bg}
    if texts:
        s["texts"] = texts
    if images:
        s["images"] = images
    return s


def region_luma(src, t=None):
    """자막이 놓이는 왼쪽 아래 영역의 평균 밝기(0~255). 소스를 1920x1080 cover로 맞춘 근사치."""
    import io
    from PIL import Image
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if t is not None:
        cmd += ["-ss", f"{t:.3f}"]
    cmd += ["-i", src, "-frames:v", "1", "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080", "-f", "image2pipe", "-vcodec", "png", "-"]
    buf = subprocess.run(cmd, capture_output=True).stdout
    if not buf:
        return 0
    from PIL import ImageStat
    im = Image.open(io.BytesIO(buf)).convert("L").crop((150, 860, 1500, 980))
    return ImageStat.Stat(im).mean[0]


def ink_if_bright(bg, texts, threshold=125):
    """배경이 밝으면 자막을 잉크색(그림자 없음)으로 바꾼다. 어두우면 크림색 유지."""
    if not texts or bg["type"] not in ("clip", "image"):
        return
    if bg["type"] == "clip":
        mid = bg["in"] + 1.2 * bg.get("speed", 1.0)
        luma = max(region_luma(bg["src"], bg["in"] + 0.1), region_luma(bg["src"], mid))
    else:
        luma = region_luma(bg["src"])
    if luma > threshold:
        for t in texts:
            if t.get("color") == PAPER_WHITE or str(t.get("color", "")).startswith("rgba(250,246,238"):
                t["color"] = INK if t.get("color") == PAPER_WHITE else INK_SOFT
                t["shadow"] = False
                t["weight"] = 600      # 밝은 배경 위 얇은 세리프는 압축 후 흐려져서 조금 굵게


def clip_shot(sid, start, end, texts=None, fallback_ink=True, **bgkw):
    """실사 샷. 클립이 없으면 크림 화면에 같은 자막(잉크색)으로 대신한다."""
    bg = clip_bg(sid, end - start, **bgkw)
    if bg is None:
        bg = page_bg()
        if texts and fallback_ink:
            for t in texts:
                t["color"] = INK
                t["shadow"] = False
    else:
        ink_if_bright(bg, texts)
    return shot(sid, start, end, bg, texts)


shots = []
# 1. 집을 나서다 ---------------------------------------------------------------
shots.append(clip_shot("f02", 0.0, 4.0, [voice("토요일 아침. 무릎이 또 말을 한다.", 0.9, 4.0)], fade_in=15, amount=0.03))
shots.append(clip_shot("f03", 4.0, 7.0, [voice("계단 앞에서 잠깐 멈추는 게 버릇이 됐다.", 4.3, 7.0, color=INK, shadow=False, weight=600)], zoom="in", amount=0.015))   # 밝은 돌계단 위라 잉크색
shots.append(clip_shot("f04", 7.0, 10.0, [voice("어디로 가야 할지 몰라 검색만 오래 했다.", 7.2, 10.0)], zoom="none"))
shots.append(clip_shot("f05", 10.0, 12.5, [dict(PLACE, text="낙성대역 4번 출구", start=10.3, end=12.5)], zoom="none"))
# 2. 문을 열다 -----------------------------------------------------------------
# 건물 외관 사진은 다른 병원 간판이 화면을 차지해 밝은 3초 컷으로는 쓰지 않는다 (4번 출구 쪽 가로 사진이 오면 f07 앞에 넣는다)
# f07: 유리문 손잡이 POV가 없어 엘리베이터 버튼을 누르는 손으로 '올라간다'를 보여준다
shots.append(clip_shot("f07", 12.5, 15.5, [voice("학생도, 직장인도, 할머님도 온다고 했다.", 12.7, 15.5)], zoom="none"))
_p08_t = [voice("생각보다 조용했다. 오래 기다리지 않았다.", 15.8, 18.5)]
_p08_bg = photo_bg("reception_16x9.jpg", amount=0.05)
ink_if_bright(_p08_bg, _p08_t)
shots.append(shot("p08", 15.5, 18.5, _p08_bg, _p08_t))
shots.append(clip_shot("f09", 18.5, 21.5, [voice("어떻게 말할지 미리 연습했다.", 18.7, 21.5)], amount=0.03))
# 3. 나를 보는 의사 -------------------------------------------------------------
_p10_t = [voice("그런데 먼저 물었다. 언제부터, 어떻게 아팠는지.", 21.8, 24.6, anim_out="fade", out_frames=9),
          voice("내 말이 끝날 때까지 기다렸다.", 24.8, 27.0)]
_p10_bg = photo_bg("doctor_portrait_16x9.jpg", amount=0.08, anchor=(0.6, 0.5))
ink_if_bright(_p10_bg, _p10_t)
shots.append(shot("p10", 21.5, 27.0, _p10_bg, _p10_t))
shots.append(clip_shot("f12", 27.0, 30.0, [voice("종이에 그려가며, 왜 아픈지 설명해줬다.", 27.2, 30.0)], zoom="none"))
shots.append(quote_page("q13", 30.0, 34.5, "왜 아팠는지 확실히 알겠더라고요.\n모형으로까지 설명해주셔서 이해가 쏙쏙 됐어요.", 2))
shots.append(clip_shot("f14", 34.5, 37.3, [voice("필요한 것만 하자고 했다. 그게 다였다.", 34.7, 37.3, color=INK, shadow=False, weight=600, x="right", align="right")], amount=0.03))   # 왼쪽 아래는 손이라 오른쪽 흰 블라인드 위에 잉크색
shots.append(quote_page("q15", 37.3, 39.8, "딱 필요한 치료만 권유해 주시더라구요.", 1))
# 4. 다시 계단 -----------------------------------------------------------------
shots.append(clip_shot("f16", 39.8, 42.3, None, zoom="none", fade_out=14, fade_color="white"))
shots.append(clip_shot("f17", 42.3, 45.3, [voice("같은 계단인데, 이번엔 이유를 알고 내려간다.", 42.6, 45.3, color=INK, shadow=False, weight=600)], zoom="in", amount=0.08, fade_in=8, fade_color="white"))
shots.append(clip_shot("f18", 45.3, 47.8, [voice("진작 올걸 그랬어요!", 45.5, 47.8),
                                          dict(LABEL, text="네이버 리뷰", start=45.8, end=47.8, x=168, y=950, align="left", color="rgba(250,246,238,0.7)", shadow=True)],
                       zoom="none"))
# 엔딩: 크림 종이 한 장 위에 브랜드 문장, 서명처럼 로고, 정보. 마지막은 흰 화면으로
END = 55.5
shots.append(shot("e19", 47.8, END, page_bg(fade_out=24, fade_color="white"),
                  texts=[dict(QUOTE, text="짧은 시간이라도, 끝까지 듣습니다.", start=47.8, end=END, size=60, weight=500, letter_spacing=-0.005,
                              y=418, anim_in="rise", in_frames=18, anim_out="fade", out_frames=24),
                         dict(LABEL, text="낙성대역 4번 출구 100m · 주차 무료 · 02-872-3301", start=50.9, end=END, size=30, y=764, out_frames=24),
                         dict(LABEL, text="평일 9~19시 · 토 9~14시 · 일요일 진료는 네이버 예약", start=50.9, end=END, size=30, y=812, out_frames=24)],
                  images=[{"src": os.path.join(HOSP, "logo_color.png"), "start": 49.5, "end": END, "width": 520, "y": 548,
                           "anim_in": "fade", "in_frames": 18, "anim_out": "fade", "out_frames": 24}]))

for s in shots:
    s["start"] = round(round(s["start"] * 30) / 30, 6)
    s["end"] = round(round(s["end"] * 30) / 30, 6)

audio = os.path.join(HERE, "music", "render", "film2_audio.wav")
tl = {"fps": 30, "width": 1920, "height": 1080, "duration": END, "audio": audio if os.path.exists(audio) else None, "shots": shots}
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "engine", "timeline_film2.json")
json.dump(tl, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
missing = [s["id"] for s in shots if s["id"].startswith("f") and s["bg"]["type"] != "clip"]
print(f"wrote {out}: {len(shots)} shots, {END}s, footage missing: {missing}")
