#!/usr/bin/env python3
"""Composite footage.mp4 + overlay/%05d.png (+ optional audio) into out.mp4."""
import argparse
import os
import shlex
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from timeline import TimelineError, load  # noqa: E402

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")


class ComposeError(Exception):
    pass


def count_frames(path):
    p = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-count_frames",
                        "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return int(p.stdout.strip() or 0)


def compose(tl, footage, overlay_dir, out_path, preview=False):
    n, fps = tl["total_frames"], tl["fps"]
    if not os.path.isfile(footage):
        raise ComposeError(f"footage not found: {footage}")
    missing = [i for i in range(n) if not os.path.isfile(os.path.join(overlay_dir, f"{i:05d}.png"))]
    if missing:
        raise ComposeError(f"overlay is missing {len(missing)} of {n} frames (first: {missing[0]:05d}.png) in {overlay_dir}")
    got = count_frames(footage)
    if got != n:
        raise ComposeError(f"footage has {got} frames, timeline needs {n}")

    audio = tl.get("audio")
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
           "-i", footage,
           "-framerate", str(fps), "-start_number", "0", "-i", os.path.join(overlay_dir, "%05d.png")]
    if audio:
        cmd += ["-i", audio]
    graph = "[0:v][1:v]overlay=0:0:format=yuv444"
    if preview:
        graph += ",scale=960:540:flags=lanczos"
    graph += ",format=yuv420p[v]"
    cmd += ["-filter_complex", graph, "-map", "[v]"]
    if audio:
        cmd += ["-map", "2:a:0", "-af", "apad", "-c:a", "aac", "-b:a", "128k" if preview else "256k"]
    if preview:
        cmd += ["-c:v", "libx264", "-crf", "24", "-preset", "veryfast"]
    else:
        cmd += ["-c:v", "libx264", "-crf", "17", "-preset", "slow"]
    cmd += ["-pix_fmt", "yuv420p", "-r", str(fps), "-fps_mode", "cfr",
            "-frames:v", str(n), "-t", f"{n / fps:.6f}", "-shortest",
            "-movflags", "+faststart", out_path]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise ComposeError("ffmpeg failed (exit %d)\n  command: %s\n%s"
                           % (p.returncode, " ".join(shlex.quote(c) for c in cmd), p.stderr[-3000:]))
    got = count_frames(out_path)
    if got != n:
        raise ComposeError(f"{out_path} has {got} frames, expected {n}")
    print(f"  {os.path.basename(out_path)}: {got} frames ({got / fps:.3f}s)"
          + (f", audio {os.path.basename(audio)}" if audio else ", no audio"), flush=True)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Composite footage + overlay (+ audio) into out.mp4")
    ap.add_argument("timeline")
    ap.add_argument("--build", default=None, help="build dir holding footage.mp4 and overlay/ (default: <timeline dir>/build)")
    ap.add_argument("--preview", action="store_true", help="960x540 crf 24 fast encode -> preview.mp4")
    ap.add_argument("--out", default=None, help="output path (default: <build>/out.mp4 or preview.mp4)")
    a = ap.parse_args()
    build = a.build or os.path.join(os.path.dirname(os.path.abspath(a.timeline)), "build")
    out = a.out or os.path.join(build, "preview.mp4" if a.preview else "out.mp4")
    try:
        tl = load(a.timeline)
        t0 = time.time()
        compose(tl, os.path.join(build, "footage.mp4"), os.path.join(build, "overlay"), out, a.preview)
        print(f"done in {time.time() - t0:.1f}s")
    except (TimelineError, ComposeError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
