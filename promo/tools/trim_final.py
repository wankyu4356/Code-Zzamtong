"""
편집자가 확정한 선별(final_picks.json)대로 실제 쓰는 구간만 잘라 final/에 넣고 manifest.json을 쓴다.
  python3 tools/trim_final.py assets/footage2 [f14,f16]   (샷 id를 주면 그것만 다시 자르고 manifest는 갱신)
final_picks.json: {"f02": {"file": "candidates/f02_21669.mp4", "mixkit_id": "21669", "in": 1.0, "need": 4.0, "speed": 1.0, "note": "..."}, ...}
  need: 타임라인에서 쓰는 길이(초). speed<1이면 소스는 need*speed 초만 필요하다. 앞 0.4초, 뒤 1.0초 여유.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOOT = os.path.join(HERE, sys.argv[1] if len(sys.argv) > 1 else "assets/footage2")
FINAL = os.path.join(FOOT, "final")
os.makedirs(FINAL, exist_ok=True)
PRE, POST = 0.4, 1.0

picks = json.load(open(os.path.join(FOOT, "final_picks.json"), encoding="utf-8"))
ONLY = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None
man_p = os.path.join(FINAL, "manifest.json")
manifest = json.load(open(man_p, encoding="utf-8")) if (ONLY and os.path.exists(man_p)) else {}
for sid, p in picks.items():
    if ONLY and sid not in ONLY:
        continue
    src = p["file"] if os.path.isabs(p["file"]) else os.path.join(FOOT, p["file"])
    if not os.path.exists(src):
        print(sid, "missing", src)
        continue
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src]).decode())
    inp = float(p["in"])
    need_src = float(p["need"]) * float(p.get("speed", 1.0))
    start = max(0.0, inp - PRE)
    end = min(dur, inp + need_src + POST)
    if end < inp + need_src - 1e-3:
        print(sid, f"WARNING: source too short ({dur:.2f}s) for in {inp} + {need_src:.2f}s")
    out = os.path.join(FINAL, f"{sid}.mp4")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", src,
                    "-an", "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p", out], check=True)
    manifest[sid] = {"file": out, "in_point": round(inp - start, 3), "mixkit_id": str(p["mixkit_id"]), "source": os.path.basename(src),
                     "source_in_point": inp, "speed": float(p.get("speed", 1.0)), "note": p.get("note", "")}
    print(sid, p["mixkit_id"], f"{start:.2f}~{end:.2f}s", "->", os.path.basename(out), "in", round(inp - start, 3), "speed", p.get("speed", 1.0))

json.dump(manifest, open(os.path.join(FINAL, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("manifest:", len(manifest), "clips")
