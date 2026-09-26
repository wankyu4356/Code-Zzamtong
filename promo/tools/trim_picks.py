"""
선별·검증된 클립을 실제 쓰는 구간만 남겨 작게 만든다.
  입력: assets/footage/picks/<id>.json (+ <id>.verify.json), assets/footage/shots.json
  출력: assets/footage/final/<id>.mp4 (인점 0.4초 앞부터 need_sec+1.0초 뒤까지), final/manifest.json
사용: python3 tools/trim_picks.py
"""
import json
import os
import subprocess

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOOT = os.path.join(HERE, "assets", "footage")
FINAL = os.path.join(FOOT, "final")
os.makedirs(FINAL, exist_ok=True)
PRE, POST = 0.4, 1.0

shots = {s["id"]: s for s in json.load(open(os.path.join(FOOT, "shots.json"), encoding="utf-8"))}
manifest = {}
for sid, shot in shots.items():
    pick_p = os.path.join(FOOT, "picks", f"{sid}.json")
    ver_p = os.path.join(FOOT, "picks", f"{sid}.verify.json")
    if not os.path.exists(pick_p):
        continue
    pick = json.load(open(pick_p, encoding="utf-8"))
    if pick.get("no_good_match") or not pick.get("chosen"):
        continue
    src, inp, mid = pick["chosen"]["file"], float(pick["chosen"]["in_point"]), str(pick["chosen"]["mixkit_id"])
    if os.path.exists(ver_p):
        v = json.load(open(ver_p, encoding="utf-8"))
        if v.get("use") == "none":
            continue
        if str(v.get("use", "")).startswith("alt:"):
            aid = v["use"].split(":", 1)[1]
            alt = next((a for a in pick.get("alternates", []) if str(a["mixkit_id"]) == aid), None)
            if alt:
                src, mid = alt["file"], aid
        inp = float(v.get("in_point", inp))
    if not os.path.exists(src):
        print(sid, "missing source", src)
        continue
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src]).decode())
    start = max(0.0, inp - PRE)
    end = min(dur, inp + float(shot["need_sec"]) + POST)
    out = os.path.join(FINAL, f"{sid}.mp4")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", src,
                    "-an", "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p", out], check=True)
    manifest[sid] = {"file": out, "in_point": round(inp - start, 3), "mixkit_id": mid, "source": os.path.basename(src), "source_in_point": inp}
    print(sid, mid, f"{start:.2f}~{end:.2f}s", "->", os.path.basename(out), "in", round(inp - start, 3))

json.dump(manifest, open(os.path.join(FINAL, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("manifest:", len(manifest), "clips")
