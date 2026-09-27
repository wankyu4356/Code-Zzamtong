"""
storyboard_v1.md의 샷 리스트를 engine/timeline.json으로 만든다.
실사 샷은 assets/footage/picks/<id>.json(리서처)과 <id>.verify.json(검수)에서 파일과 인점을 읽는다.
아직 없는 실사는 검은 화면으로 두어 언제든 렌더가 돌게 한다.
사용: python3 build_timeline.py [out.json]
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "music"))
import hangul  # noqa: E402
import sfx  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "assets")
FOOT = os.path.join(A, "footage")
HOSP = os.path.join(A, "hospital")
GRADE = {"contrast": 1.05, "saturation": 0.9, "brightness": 0.0, "gamma": 1.0}

# 글자 규격 (9장 크기 규칙)
BIG = dict(weight=900, letter_spacing=-0.03, color="#fff", shadow=False)
CAP = dict(size=28, weight=400, letter_spacing=0, color="rgba(255,255,255,0.6)", shadow=False, anim_in="none", anim_out="cut")
QUOTE = dict(size=60, weight=500, letter_spacing=-0.01, line_height=1.35, max_width=1440, color="#fff", shadow=False)


MANIFEST = os.path.join(FOOT, "final", "manifest.json")
_manifest = json.load(open(MANIFEST, encoding="utf-8")) if os.path.exists(MANIFEST) else {}


def footage(shot_id):
    """final/manifest.json(트림본)이 있으면 그것을, 없으면 picks의 원본과 검수 인점을 돌려준다. 없으면 None."""
    m = _manifest.get(shot_id)
    if m and os.path.exists(m["file"]):
        return m["file"], float(m["in_point"])
    pick_p = os.path.join(FOOT, "picks", f"{shot_id}.json")
    ver_p = os.path.join(FOOT, "picks", f"{shot_id}.verify.json")
    if not os.path.exists(pick_p):
        return None
    pick = json.load(open(pick_p, encoding="utf-8"))
    if pick.get("no_good_match") or not pick.get("chosen"):
        return None
    file, inp = pick["chosen"]["file"], float(pick["chosen"]["in_point"])
    if os.path.exists(ver_p):
        v = json.load(open(ver_p, encoding="utf-8"))
        use = v.get("use", "chosen")
        if use == "none":
            return None
        if use.startswith("alt:"):
            aid = use.split(":", 1)[1]
            alt = next((a for a in pick.get("alternates", []) if str(a["mixkit_id"]) == aid), None)
            if alt:
                file = alt["file"]
        inp = float(v.get("in_point", inp))
    if not os.path.exists(file):
        return None
    return file, inp


# 샷별 미세 조정: 펀치인(정적 확대), 크롭 기준점, 밝기
OVERRIDES = {
    "s25": {"punch": 1.35, "anchor": [0.32, 0.6]},   # 도서관 와이드샷, 인물이 왼쪽
    "s26": {"brightness": -0.15},                     # 피부와 흰 티가 밝아 흰 글자 대비 확보
    "s27": {"punch": 1.25, "anchor": [0.5, 0.3]},     # 실루엣이 상단 중앙에 작게 있음
    # 증상 드롭: 밝은 배경은 감마로 낮춘다(밝기만 내리면 어두운 쪽 색이 붉게 뜬다)
    "c39": {"brightness": -0.2, "gamma": 0.65, "saturation": 0.65},   # 흰 스튜디오 배경, 흰 글자 대비
    "c40": {"punch": 1.3, "anchor": [0.6, 0.0]},      # 앞쪽 연고 튜브를 화면 밖으로
    "c41": {"punch": 1.15, "anchor": [0.3, 0.5], "brightness": -0.1, "gamma": 0.8},   # 발이 글자 오른쪽으로
    "c42": {"brightness": -0.1, "gamma": 0.75},       # 밝은 흰 배경
    "c43": {"punch": 1.15, "anchor": [0.2, 0.5], "brightness": -0.1},   # 아이가 글자 오른쪽으로
}


def clip_bg(shot_id, zoom="in", amount=0.05, brightness=0.0, vignette=True):
    f = footage(shot_id)
    if not f:
        return {"type": "black"}
    file, inp = f
    o = OVERRIDES.get(shot_id, {})
    g = dict(GRADE)
    g["brightness"] = o.get("brightness", brightness)
    g.update({k: o[k] for k in ("gamma", "saturation", "contrast") if k in o})
    return {"type": "clip", "src": file, "in": inp, "fit": "cover", "zoom": zoom, "zoom_amount": amount, "grade": g, "vignette": vignette, "grain": 0.08,
            "punch": o.get("punch", 1.0), "anchor": o.get("anchor", [0.5, 0.5])}


def photo_bg(name, brightness=-0.3, zoom="in", amount=0.03, grade=None, punch=1.0):
    p = os.path.join(HOSP, name)
    if not os.path.exists(p):
        return {"type": "black"}
    g = dict(GRADE)
    g["brightness"] = brightness
    g.update(grade or {})
    return {"type": "image", "src": p, "fit": "cover", "zoom": zoom, "zoom_amount": amount, "grade": g, "vignette": True, "grain": 0.06, "punch": punch}


def T(text, start, end, size, **kw):
    d = dict(BIG)
    d.update(dict(text=text, start=start, end=end, size=size, anim_in="hit", anim_out="cut", max_width=1600))
    d.update(kw)
    return d


def shot(sid, start, end, bg, texts=None, images=None, flashes=None):
    s = {"id": sid, "start": start, "end": end, "bg": bg}
    if texts:
        s["texts"] = texts
    if images:
        s["images"] = images
    if flashes:
        s["flashes"] = flashes
    return s


def typing_card(text, start, end, nick, chip, date, type_end=None, hold_min=0.35, seed=1, anim_out="cut", out_frames=8):
    """리뷰를 실제로 입력하는 카드. 키 입력 시각과 화면 상태를 미리 계산한다."""
    keys = hangul.keystrokes(text)
    states = hangul.states(text)
    n = len(keys)
    type_start = start + 0.12                       # 카드가 뜬 직후 시작
    type_end = type_end or (end - hold_min - 0.3)   # 마지막 키 뒤 등록까지 0.3, 등록 뒤 hold_min
    # 띄어쓰기·문장부호 뒤에 잠깐 쉬고, 나머지는 균등 + 작은 흔들림
    rng = random.Random(seed)
    pauses = [0.0] * n
    for i, k in enumerate(keys[:-1]):
        if k == " ":
            pauses[i] = 0.07
        elif k in ",.!?":
            pauses[i] = 0.11
    span = type_end - type_start - sum(pauses)
    base = span / max(n - 1, 1)
    times = [type_start]
    for i in range(1, n):
        times.append(times[-1] + base + pauses[i - 1] + rng.uniform(-0.25, 0.25) * base)
    # 단조 증가 보정과 범위 고정
    for i in range(1, n):
        times[i] = max(times[i], times[i - 1] + 0.012)
    scale = (type_end - type_start) / max(times[-1] - type_start, 1e-6)
    times = [type_start + (t - type_start) * scale for t in times]
    times = [round(t, 4) for t in times]
    return {"text": text, "start": start, "end": end, "keys": times, "states": states, "post_at": round(type_end + 0.3, 3),
            "nick": nick, "chip": chip, "date": date, "anim_in": "rise", "in_frames": 6, "anim_out": anim_out, "out_frames": out_frames}


REVIEWS = sys.argv[sys.argv.index("--reviews") + 1] if "--reviews" in sys.argv else "typing"
assert REVIEWS in ("typing", "chat", "receipt"), REVIEWS


def receipt(text, start, end, nick, date, chip="영수증 인증", print_from=None, print_secs=None, seed=7, anim_out="cut", out_frames=8):
    """영수증 프린터. 줄 수를 어림해 한 줄씩 나오는 시각을 만든다."""
    body_lines = max(1, -(-len(text) // 16))          # 58px 굵은 글자, 폭 888px 기준 한 줄 약 16자
    n_lines = 9 + body_lines                           # 머리 5줄, 본문, 꼬리(바코드·상호) 4줄
    print_from = start + 0.1 if print_from is None else print_from
    print_secs = (end - start) * 0.62 if print_secs is None else print_secs
    rng = random.Random(seed)
    step = print_secs / n_lines
    times = [round(print_from + i * step + rng.uniform(-0.15, 0.15) * step, 4) for i in range(n_lines)]
    times = [times[0]] + [max(times[i], times[i - 1] + 0.02) for i in range(1, n_lines)]
    tear_at = round(times[-1] + 0.42, 3)
    return {"text": text, "start": start, "end": end, "nick": nick, "date": date, "chip": chip,
            "line_times": times, "tear_at": tear_at, "anim_out": anim_out, "out_frames": out_frames}


def chat_scene(start, end, messages, anim_out="cut", out_frames=8, height=720):
    """메신저 장면. messages: (text, nick, chip, date, typing_from, arrive_at)"""
    return {"start": start, "end": end, "height": height, "anim_out": anim_out, "out_frames": out_frames,
            "messages": [{"text": t, "nick": n, "chip": c, "date": d, "typing_from": tf, "arrive_at": aa} for t, n, c, d, tf, aa in messages]}


F = 1 / 30
shots = []
# 후킹
shots.append(shot("s01", 0.0, 1.0, clip_bg("s01", zoom="in", amount=0.12)))
# 오프닝 블랙
shots.append(shot("s02", 1.0, 2.0, {"type": "black"}, [T("아, 허리.", 1.0, 2.0, 170, in_frames=3)]))
shots.append(shot("s03", 2.0, 3.0, {"type": "black"}, [T("괜찮겠지.", 2.0, 3.0, 170, in_frames=3)]))
shots.append(shot("s04", 3.0, 3.5, {"type": "black"}, [T("하루.", 3.0, 3.5, 170, in_frames=3)]))
shots.append(shot("s05", 3.5, 4.0, {"type": "black"}, [T("이틀.", 3.5, 4.0, 170, in_frames=3)]))
shots.append(shot("s06", 4.0, 5.0, {"type": "black"}, [T("일주일.", 4.0, 5.0, 220, hit_scale=1.15, in_frames=4)]))
shots.append(shot("s07", 5.0, 6.0, {"type": "black"}, [T("병원은 나중에.", 5.0, 6.0, 170, in_frames=3)]))
shots.append(shot("s08", 6.0, 8.0, {"type": "black"}, [T("어디로 가야 하나.", 6.0, 8.0, 170, in_frames=3, drift_scale=0.03)]))
# 빌드
shots.append(shot("s09", 8.0, 9.0, clip_bg("s09", amount=0.04), [T("수능 앞, 목.", 8.0, 9.0, 170, in_frames=3, shadow=True)]))
shots.append(shot("s10", 9.0, 10.0, clip_bg("s10", amount=0.04), [T("모니터 앞, 거북목.", 9.0, 10.0, 170, in_frames=3, shadow=True)]))
shots.append(shot("s11", 10.0, 11.0, clip_bg("s11", amount=0.04), [T("계단 앞, 무릎.", 10.0, 11.0, 170, in_frames=3, shadow=True)]))
# 원장 소개: '일대일'은 병원이면 당연한 말이라 이름과 직함으로 바꿨다. 다음 두 화면과 이어져 한 문장이 된다
shots.append(shot("s12", 11.0, 12.0, photo_bg("doctor_portrait_16x9.jpg", brightness=-0.3), [T("유병찬 대표원장,", 11.0, 12.0, 150, in_frames=3, shadow=True, x="left", align="left")]))
shots.append(shot("s13", 12.0, 13.0, photo_bg("reception_16x9.jpg", brightness=-0.3), [T("짧은 시간이라도,", 12.0, 13.0, 170, in_frames=3, shadow=True)]))
# 앞 화면이 원장 이름이라 '누구보다'는 특정 의사의 비교 주장이 된다. '끝까지'로 바꿨다
shots.append(shot("s14", 13.0, 14.0, {"type": "black"}, [T("끝까지, 귀 기울여.", 13.0, 14.0, 170, in_frames=3)]))
shots.append(shot("s15", 14.0, 15.0, {"type": "black"}, [T("몸은 원래,", 14.0, 15.0, 170, in_frames=3)]))
shots.append(shot("s16", 15.0, 472 * F, {"type": "black"}, [T("이렇게.", 15.0, 472 * F, 170, in_frames=3)]))
shots.append(shot("s17", 472 * F, 16.0, {"type": "black"}))
# 드롭: 동작 8 (220px), 부위 4 (320px)
drop = [("s18", "걷고", True), ("s19", "뛰고", False), ("s20", "들고", False), ("s21", "안고", False),
        ("s22", "오르고", True), ("s23", "굽히고", False), ("s24", "타고", False), ("s25", "앉고", False)]
t = 16.0
for sid, w, flash in drop:
    fl = [{"at": t, "frames": 2, "color": "#fff", "opacity": 0.9}] if flash else None
    shots.append(shot(sid, t, t + 0.5, clip_bg(sid, amount=0.06), [T(w, t, t + 0.5, 220, anim_in="slam", hit_scale=1.15, in_frames=3, shadow=True)], flashes=fl))
    t += 0.5
for sid, w in [("s26", "목"), ("s27", "어깨"), ("s28", "무릎"), ("s29", "허리")]:
    shots.append(shot(sid, t, t + 0.5, clip_bg(sid, amount=0.06), [T(w, t, t + 0.5, 320, anim_in="slam", hit_scale=1.15, in_frames=3, shadow=True)],
                      flashes=[{"at": t, "frames": 2, "color": "#fff", "opacity": 0.9}]))
    t += 0.5
# 브레이크: 리뷰 한 줄 120px
s30 = shot("s30", 22.0, 24.0, {"type": "black"})
if REVIEWS == "receipt":
    s30["receipts"] = [receipt("진작 올걸 그랬어요!", 22.0, 24.0, "vqfc****", "2026.07.16", print_from=22.0, print_secs=1.1, seed=30)]
elif REVIEWS == "chat":
    s30["chat"] = [chat_scene(22.0, 24.0, [("진작 올걸 그랬어요!", "vqfc****", "영수증 인증", "2026.07.16", 22.0, 22.0)], height=420)]
else:
    s30["typing"] = [typing_card("진작 올걸 그랬어요!", 22.0, 24.0, "vqfc****", "네이버 방문자 리뷰 · 영수증 인증", "2026.07.16 방문", seed=30)]
shots.append(s30)
# 리뷰 그루브 (검은 화면, 인용 교체는 앞 인용 cut 뒤 새 인용 slam)
if REVIEWS == "receipt":
    for sid, a, e, text, nick, date, seed in [
        ("s31", 24.0, 791 * F, "딱 필요한 치료만 권유해 주시더라구요.", "ngyz****", "2026.07.29", 31),
        ("s32", 791 * F, 896 * F, "선생님이 원인 파악을 명확하게 해주셔서 속이 다 시원했어요.", "mtzu****", "2026.09.06", 32),
        ("s33", 896 * F, 32.0, "의사선생님이 완전 친절하세요!", "눅눅해져****", "2026.02.08", 33),
    ]:
        sh = shot(sid, a, e, {"type": "black"})
        sh["receipts"] = [receipt(text, a, e, nick, date, seed=seed)]
        shots.append(sh)
elif REVIEWS == "chat":
    # 24~32초를 한 장면으로: 세 사람이 차례로 말풍선을 보낸다. 도착은 박자(24.5, 27.5, 30.5)에
    sh = shot("s31", 24.0, 32.0, {"type": "black"})
    sh["chat"] = [chat_scene(24.0, 32.0, [
        ("딱 필요한 치료만 권유해 주시더라구요.", "ngyz****", "영수증 인증", "2026.07.29", 24.0, 24.5),
        ("선생님이 원인 파악을 명확하게 해주셔서 속이 다 시원했어요.", "mtzu****", "영수증 인증", "2026.09.06", 26.5, 27.5),
        ("의사선생님이 완전 친절하세요!", "눅눅해져****", "영수증 인증", "2026.02.08", 29.5, 30.5),
    ], height=760)]
    shots.append(sh)
else:
    for sid, a, b, text, nick, date, seed in [
        ("s31", 24.0, 791 * F, "딱 필요한 치료만 권유해 주시더라구요.", "ngyz****", "2026.07.29 방문", 31),
        ("s32", 791 * F, 896 * F, "선생님이 원인 파악을 명확하게 해주셔서 속이 다 시원했어요.", "mtzu****", "2026.09.06 방문", 32),
        ("s33", 896 * F, 32.0, "의사선생님이 완전 친절하세요!", "눅눅해져****", "2026.02.08 방문", 33),
    ]:
        sh = shot(sid, a, b, {"type": "black"})
        sh["typing"] = [typing_card(text, a, b, nick, "네이버 방문자 리뷰 · 영수증 인증", date, seed=seed)]
        shots.append(sh)
# 본질 세 줄
shots.append(shot("s34", 32.0, 33.0, {"type": "black"}, [T("먼저 듣고,", 32.0, 33.0, 170, in_frames=3)]))
shots.append(shot("s35", 33.0, 34.0, {"type": "black"}, [T("왜 아픈지 말하고,", 33.0, 34.0, 170, in_frames=3)]))
shots.append(shot("s36", 34.0, 1072 * F, {"type": "black"}, [T("필요한 치료만.", 34.0, 1072 * F, 170, in_frames=3)]))
shots.append(shot("s37", 1072 * F, 36.0, {"type": "black"}))
# 증상 드롭: 부위와 느낌을 환자의 입말로, 진료 범위의 다른 묶음을 한 박씩 (관절, 혈관, 족부, 교통사고, 소아)
# 16~20초 드롭에서 나온 목·어깨·무릎·허리는 글자로 다시 쓰지 않는다. 영상은 final/c38~c43 (자기 손이 아픈 곳을 짚는 장면 위주)
t = 36.0
for sid, clip, w, flash in [("s38", "c38", "손목 시큰", True), ("s39", "c39", "다리 묵직", False), ("s40", "c40", "발목 삐끗", False),
                            ("s41", "c41", "발바닥 찌릿", False), ("s42", "c42", "사고 후 뻐근", True), ("s43", "c43", "아이 꽈당", False)]:
    fl = [{"at": t, "frames": 2, "color": "#fff", "opacity": 0.9}] if flash else None
    shots.append(shot(sid, t, t + 0.5, clip_bg(clip, amount=0.06), [T(w, t, t + 0.5, 220, anim_in="slam", hit_scale=1.15, in_frames=3, shadow=True)], flashes=fl))
    t += 0.5
# 병원이 먼저 묻고, 바로 뒤 리뷰가 '어디 아프면'으로 받는다 (6초 '어디로 가야 하나.'에서 시작한 질문을 닫는다)
# 건물 두 화면(39~43초)은 같은 사진이라 색 보정을 같게 하고 줌을 컷 너머로 이어 간다 (감마로 어둡게 해 외벽 색 유지)
BLD_GRADE = {"contrast": 1.05, "saturation": 0.55, "brightness": -0.1, "gamma": 0.45}
shots.append(shot("s44", 39.0, 40.0, photo_bg("building_16x9.jpg", amount=0.015, grade=BLD_GRADE),
                  [T("어디 아프세요?", 39.0, 40.0, 240, anim_in="slam", hit_scale=1.15, in_frames=3, shadow=True)],
                  flashes=[{"at": 39.0, "frames": 2, "color": "#fff", "opacity": 0.9}]))
# 리뷰 (건물 사진 유지, 밝기 30%)
s45 = shot("s45", 40.0, 43.0, photo_bg("building_16x9.jpg", amount=0.045, grade=BLD_GRADE, punch=round(1.015 * (1 + 0.015 / 29), 5)))
if REVIEWS == "receipt":
    s45["receipts"] = [receipt("담에는 어디 아프면 꼭 여기 가려구요.", 40.0, 43.0, "Sept****", "2025.02.09", chip="예약 인증", print_secs=1.7, seed=45, anim_out="fade", out_frames=8)]
elif REVIEWS == "chat":
    s45["chat"] = [chat_scene(40.0, 43.0, [("담에는 어디 아프면 꼭 여기 가려구요.", "Sept****", "예약 인증", "2025.02.09", 40.0, 40.5)], anim_out="fade", out_frames=8, height=420)]
    s45["chat"][0]["y"] = 200                      # 말풍선이 건물 간판('김철신 정형외과')을 가리지 않게 위로
else:
    s45["typing"] = [typing_card("담에는 어디 아프면 꼭 여기 가려구요.", 40.0, 43.0, "Sept****", "네이버 방문자 리뷰 · 예약 인증", "2025.02.09 방문", seed=45, anim_out="fade", out_frames=8)]
shots.append(s45)
# 엔딩
shots.append(shot("s46", 43.0, 45.5, {"type": "black"},
                  [T("먼저 듣고,\n필요한 치료만.", 43.0, 45.5, 170, in_frames=4, anim_out="fade", out_frames=15, line_height=1.15)]))
shots.append(shot("s47", 45.5, 47.0, {"type": "black"}, images=[
    {"src": os.path.join(HOSP, "logo_white.png"), "start": 45.5, "end": 48.0, "width": 900, "anim_in": "fade", "in_frames": 12, "anim_out": "fade", "out_frames": 15}]))
shots.append(shot("s48", 47.0, 50.0, {"type": "black"},
                  texts=[dict(CAP, text="낙성대역 4번 출구 1분 · 주차 무료 · 02-872-3301", start=47.0, end=50.0, size=30, color="rgba(255,255,255,0.7)", y=880, anim_in="fade", in_frames=8, anim_out="fade", out_frames=18),
                         dict(CAP, text="평일 9~19시 · 토 9~14시 · 일요일 진료는 네이버 예약", start=47.0, end=50.0, size=30, color="rgba(255,255,255,0.7)", y=930, anim_in="fade", in_frames=8, anim_out="fade", out_frames=18)],
                  images=[{"src": os.path.join(HOSP, "logo_color.png"), "start": 48.0 - 15 * F, "end": 50.0, "width": 900, "anim_in": "fade", "in_frames": 15, "anim_out": "fade", "out_frames": 18}]))

# 로고 두 장을 s47 이미지 span(45.5~48.0)과 s48 컬러(47.5~50)로 겹쳐 크로스페이드. 검증기는 span이 샷 밖으로 걸쳐도 허용한다.
shots[-2]["images"][0]["end"] = 48.0
# 프레임 경계 보정
for s in shots:
    s["start"] = round(round(s["start"] * 30) / 30, 6)
    s["end"] = round(round(s["end"] * 30) / 30, 6)

music_wav = os.path.join(HERE, "music", "render", "music_v1.wav")
audio_wav = os.path.join(HERE, "music", "render", f"audio_v2_{REVIEWS}.wav")
tl = {"fps": 30, "width": 1920, "height": 1080, "duration": 50.0, "audio": audio_wav, "shots": shots}
if os.path.exists(music_wav):
    sfx.render(tl, music_wav, audio_wav)
    print("audio with sfx:", audio_wav)
args = [a for a in sys.argv[1:] if not a.startswith("--") and a != REVIEWS]
out = args[0] if args else os.path.join(HERE, "engine", f"timeline_v1{'' if REVIEWS == 'typing' else '_' + REVIEWS}.json")
json.dump(tl, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
missing = [s["id"] for s in shots if s["bg"]["type"] == "black" and s["id"] in
           ("s01", "s09", "s10", "s11", "s18", "s19", "s20", "s21", "s22", "s23", "s24", "s25", "s26", "s27", "s28", "s29", "s38", "s39", "s40", "s41", "s42", "s43")]
print(f"wrote {out}: {len(shots)} shots, footage still missing: {missing}")
