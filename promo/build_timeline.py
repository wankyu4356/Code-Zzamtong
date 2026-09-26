"""
storyboard_v1.md의 샷 리스트를 engine/timeline.json으로 만든다.
실사 샷은 assets/footage/picks/<id>.json(리서처)과 <id>.verify.json(검수)에서 파일과 인점을 읽는다.
아직 없는 실사는 검은 화면으로 두어 언제든 렌더가 돌게 한다.
사용: python3 build_timeline.py [out.json]
"""
import json
import os
import sys

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
}


def clip_bg(shot_id, zoom="in", amount=0.05, brightness=0.0, vignette=True):
    f = footage(shot_id)
    if not f:
        return {"type": "black"}
    file, inp = f
    o = OVERRIDES.get(shot_id, {})
    g = dict(GRADE)
    g["brightness"] = o.get("brightness", brightness)
    return {"type": "clip", "src": file, "in": inp, "fit": "cover", "zoom": zoom, "zoom_amount": amount, "grade": g, "vignette": vignette, "grain": 0.08,
            "punch": o.get("punch", 1.0), "anchor": o.get("anchor", [0.5, 0.5])}


def photo_bg(name, brightness=-0.3, zoom="in", amount=0.03):
    p = os.path.join(HOSP, name)
    if not os.path.exists(p):
        return {"type": "black"}
    g = dict(GRADE)
    g["brightness"] = brightness
    return {"type": "image", "src": p, "fit": "cover", "zoom": zoom, "zoom_amount": amount, "grade": g, "vignette": True, "grain": 0.06}


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


def quote(text, start, end, caption, y=None, first_slam=True):
    """리뷰 인용: 본문 60px(세로 중앙) + 캡션 30px. 두 줄이면 캡션을 조금 더 내린다."""
    q = dict(QUOTE)
    q.update(dict(text=text, start=start, end=end, anim_in="slam" if first_slam else "fade", hit_scale=1.12, in_frames=3, anim_out="cut", align="center", y="center"))
    lines = text.count("\n") + 1
    c = dict(CAP)
    c.update(dict(text=caption, start=start, end=end, size=30, y=640 + 42 * lines, anim_in="fade", in_frames=6))
    return [q, c]


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
shots.append(shot("s12", 11.0, 12.0, photo_bg("doctor_portrait_16x9.jpg", brightness=-0.3), [T("10년, 일대일로.", 11.0, 12.0, 170, in_frames=3, shadow=True, x="left", align="left")]))
shots.append(shot("s13", 12.0, 13.0, photo_bg("reception_16x9.jpg", brightness=-0.3), [T("짧은 시간이라도,", 12.0, 13.0, 170, in_frames=3, shadow=True)]))
shots.append(shot("s14", 13.0, 14.0, {"type": "black"}, [T("누구보다, 귀 기울여.", 13.0, 14.0, 170, in_frames=3)]))
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
shots.append(shot("s30", 22.0, 24.0, {"type": "black"},
                  [T("진작 올걸 그랬어요!", 22.0, 24.0, 120, weight=700, anim_in="slam", hit_scale=1.12, in_frames=3),
                   dict(CAP, text="네이버 방문자 리뷰 · vqfc**** · 2026.07.16 방문 · 영수증 인증", start=22.0, end=24.0, size=30, y=700)]))
# 리뷰 그루브 (검은 화면, 인용 교체는 앞 인용 cut 뒤 새 인용 slam)
shots.append(shot("s31", 24.0, 26.5, {"type": "black"},
                  quote("딱 필요한 치료만 권유해 주시더라구요.", 24.0, 26.5, "네이버 방문자 리뷰 · ngyz**** · 2026.07.29 방문 · 영수증 인증")))
shots.append(shot("s32", 26.5, 29.5, {"type": "black"},
                  quote("선생님이 원인 파악을 명확하게 해주셔서\n속이 다 시원했어요.", 26.5, 29.5, "네이버 방문자 리뷰 · mtzu**** · 2026.09.06 방문 · 영수증 인증")))
shots.append(shot("s33", 29.5, 32.0, {"type": "black"},
                  quote("의사선생님이 완전 친절하세요!", 29.5, 32.0, "네이버 방문자 리뷰 · 눅눅해져**** · 2026.02.08 방문 · 영수증 인증")))
# 본질 세 줄
shots.append(shot("s34", 32.0, 33.0, {"type": "black"}, [T("먼저 듣고,", 32.0, 33.0, 170, in_frames=3)]))
shots.append(shot("s35", 33.0, 34.0, {"type": "black"}, [T("왜 아픈지 말하고,", 33.0, 34.0, 170, in_frames=3)]))
shots.append(shot("s36", 34.0, 1072 * F, {"type": "black"}, [T("필요한 치료만.", 34.0, 1072 * F, 170, in_frames=3)]))
shots.append(shot("s37", 1072 * F, 36.0, {"type": "black"}))
# 요일 드롭
t = 36.0
for sid, w, flash in [("s38", "월", True), ("s39", "화", False), ("s40", "수", False), ("s41", "목", False), ("s42", "금", True), ("s43", "토", False)]:
    fl = [{"at": t, "frames": 2, "color": "#fff", "opacity": 0.9}] if flash else None
    shots.append(shot(sid, t, t + 0.5, clip_bg(sid, amount=0.06), [T(w, t, t + 0.5, 320, anim_in="slam", hit_scale=1.15, in_frames=3, shadow=True)], flashes=fl))
    t += 0.5
shots.append(shot("s44", 39.0, 40.0, photo_bg("building_16x9.jpg", brightness=-0.5, amount=0.04),
                  [T("일", 39.0, 40.0, 320, anim_in="slam", hit_scale=1.15, in_frames=3, shadow=True)],
                  flashes=[{"at": 39.0, "frames": 2, "color": "#fff", "opacity": 0.9}]))
# 일요일 리뷰 (건물 사진 유지, 밝기 30%)
q = quote("담에는 어디 아프면 꼭 여기 가려구요.", 40.0, 43.0, "네이버 방문자 리뷰 · Sept**** · 2025.02.09 일요일 방문 · 예약 인증 · 발췌")
q[0]["anim_out"] = "fade"; q[0]["out_frames"] = 8; q[1]["anim_out"] = "fade"; q[1]["out_frames"] = 8
shots.append(shot("s45", 40.0, 43.0, photo_bg("building_16x9.jpg", brightness=-0.7, amount=0.04), q))
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

tl = {"fps": 30, "width": 1920, "height": 1080, "duration": 50.0,
      "audio": os.path.join(HERE, "music", "render", "music_v1.wav"),
      "shots": shots}
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "engine", "timeline_v1.json")
json.dump(tl, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
missing = [s["id"] for s in shots if s["bg"]["type"] == "black" and s["id"] in
           ("s01", "s09", "s10", "s11", "s18", "s19", "s20", "s21", "s22", "s23", "s24", "s25", "s26", "s27", "s28", "s29", "s38", "s39", "s40", "s41", "s42", "s43")]
print(f"wrote {out}: {len(shots)} shots, footage still missing: {missing}")
