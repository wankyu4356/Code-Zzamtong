#!/usr/bin/env python3
"""One command: validate timeline -> build footage -> render overlay -> compose."""
import argparse
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_footage import FootageError, build_footage  # noqa: E402
from compose import ComposeError, compose  # noqa: E402
from timeline import TimelineError, load  # noqa: E402

NODE = os.environ.get("NODE_BIN") or ("/opt/node22/bin/node" if os.path.exists("/opt/node22/bin/node") else "node")


def main():
    ap = argparse.ArgumentParser(description="Render a timeline to out.mp4")
    ap.add_argument("timeline")
    ap.add_argument("--build", default=None, help="build dir (default: <timeline dir>/build)")
    ap.add_argument("--preview", action="store_true", help="also produce a 960x540 preview.mp4")
    ap.add_argument("--skip-footage", action="store_true", help="reuse build/footage.mp4")
    ap.add_argument("--skip-overlay", action="store_true", help="reuse build/overlay/*.png")
    a = ap.parse_args()
    build = a.build or os.path.join(os.path.dirname(os.path.abspath(a.timeline)), "build")
    os.makedirs(build, exist_ok=True)
    overlay_dir = os.path.join(build, "overlay")
    timings = []

    try:
        t0 = time.time()
        tl = load(a.timeline)
        print(f"timeline ok: {len(tl['shots'])} shots, {tl['total_frames']} frames @ {tl['fps']} fps, "
              f"{tl['width']}x{tl['height']}, audio: {tl['audio'] or 'none'}")
        timings.append(("validate", time.time() - t0))

        if not a.skip_footage:
            t0 = time.time()
            print("building footage...")
            build_footage(tl, build)
            timings.append(("footage", time.time() - t0))

        if not a.skip_overlay:
            t0 = time.time()
            print("rendering overlay...")
            shutil.rmtree(overlay_dir, ignore_errors=True)
            r = subprocess.run([NODE, os.path.join(HERE, "render_overlay.mjs"),
                                "--timeline", a.timeline, "--out", overlay_dir])
            if r.returncode != 0:
                sys.exit(f"error: overlay render failed (exit {r.returncode})")
            timings.append(("overlay", time.time() - t0))

        t0 = time.time()
        print("composing...")
        out = compose(tl, os.path.join(build, "footage.mp4"), overlay_dir, os.path.join(build, "out.mp4"))
        timings.append(("compose", time.time() - t0))
        if a.preview:
            t0 = time.time()
            compose(tl, os.path.join(build, "footage.mp4"), overlay_dir, os.path.join(build, "preview.mp4"), preview=True)
            timings.append(("preview", time.time() - t0))
    except (TimelineError, FootageError, ComposeError) as e:
        sys.exit(f"error: {e}")

    print("timings: " + ", ".join(f"{k} {v:.1f}s" for k, v in timings))
    print(f"output: {out}")


if __name__ == "__main__":
    main()
