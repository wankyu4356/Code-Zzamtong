"""
구성안(script.json)의 화면 길이와 sound 표기에서 compose_film3.py용 스코어를 만든다.
  python3 tools/score_from_script.py film4/script.json music/score_film4.json
규칙: silence 화면은 음악을 끊는다(앞에 tick), hit 화면 시작에 임팩트, 나머지 컷에는 스냅,
swell 화면은 lift 패턴과 다음 컷을 향한 라이저, role=logo 화면 시작에 코드, 그 뒤는 tail.
"""
import json
import sys

script = json.load(open(sys.argv[1], encoding="utf-8"))
bpm = int(script.get("bpm", 120))
screens = script["screens"]
t = 0.0
marks = []
for sc in screens:
    marks.append((round(t, 3), round(t + float(sc["seconds"]), 3), sc))
    t += float(sc["seconds"])
dur = round(t, 3)

sections, events = [], []
logo_at = next((a for a, b, sc in marks if sc.get("role") == "logo"), None)
cur_pat, cur_start = None, 0.0


def push(pat, a):
    global cur_pat, cur_start
    if pat != cur_pat:
        if cur_pat is not None and a > cur_start:
            sections.append({"start": cur_start, "end": a, "pattern": cur_pat})
        cur_pat, cur_start = pat, a


total_music = logo_at if logo_at is not None else dur
for i, (a, b, sc) in enumerate(marks):
    snd = sc.get("sound", "beat")
    if logo_at is not None and a >= logo_at:
        push("tail", a)
        continue
    if snd == "silence":
        push("silence", a)
        events.append({"t": a, "type": "cut", "len": round(b - a, 3)})
        events.append({"t": a, "type": "tick", "gain": 0.5})
        continue
    pat = "lift" if (snd == "swell" or a >= total_music * 0.6) else ("intro" if a < 2.0 and i == 0 else "groove")
    push(pat, a)
    if snd == "hit":
        events.append({"t": a, "type": "hit"})
    elif a > 0:
        events.append({"t": a, "type": "snap"})
    if snd == "swell":
        events.append({"t": b, "type": "riser", "len": min(2.0, b - a)})
push("end", dur)
if logo_at is not None:
    events.append({"t": logo_at, "type": "chord"})
score = {"bpm": bpm, "duration": dur, "key_root": script.get("key_root", "C"), "target_lufs": -14.0, "fade_out": 1.0,
         "sections": sections, "events": sorted(events, key=lambda e: e["t"])}
json.dump(score, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"wrote {sys.argv[2]}: {dur}s, {len(sections)} sections, {len(events)} events")
for s in sections:
    print(f"  {s['start']:6.2f}~{s['end']:6.2f} {s['pattern']}")
