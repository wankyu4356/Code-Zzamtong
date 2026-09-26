#!/usr/bin/env python3
"""Build footage.mp4 (video only, exact frame count) from a timeline.

One ffmpeg call per shot -> build/segments/<id>.mp4, each verified with
ffprobe -count_frames, then joined with the concat demuxer (stream copy).
"""
import argparse
import os
import shlex
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from timeline import GRADE_DEFAULTS, TimelineError, color_to_ffmpeg, load  # noqa: E402

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")
X264 = ["-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p"]


class FootageError(Exception):
    pass


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise FootageError("ffmpeg failed (exit %d)\n  command: %s\n%s"
                           % (p.returncode, " ".join(shlex.quote(c) for c in cmd), p.stderr[-3000:]))
    return p


def probe(path):
    """Return {"width", "height", "duration" (None for stills)} of a media file."""
    p = run([FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height:format=duration",
             "-of", "default=noprint_wrappers=1", path])
    info = {"duration": None}
    for line in p.stdout.splitlines():
        k, _, v = line.partition("=")
        if k in ("width", "height"):
            info[k] = int(v)
        elif k == "duration" and v not in ("N/A", ""):
            info["duration"] = float(v)
    if "width" not in info:
        raise FootageError(f"no video stream in {path}")
    return info


def count_frames(path):
    p = run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-count_frames",
             "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", path])
    return int(p.stdout.strip())


def cover_zoom_filters(src_w, src_h, W, H, zoom, amount, n, punch=1.0, anchor=(0.5, 0.5)):
    """Scale to cover WxH (times a static punch-in), with an optional linear zoom
    driven by frame number n, then crop around an anchor point (fractions of the
    scaled frame; 0.5,0.5 is center). Sizes are computed in Python so the crop
    offsets can be written as explicit expressions (crop does not refresh in_w per frame)."""
    a = src_w / src_h
    cw, ch = max(W, H * a) * punch, max(H, W / a) * punch
    den = max(n - 1, 1)
    if zoom == "in" and amount > 0:
        z = f"(1+{amount}*n/{den})"
    elif zoom == "out" and amount > 0:
        z = f"(1+{amount}*(1-n/{den}))"
    else:
        z = "1"
    sw = f"ceil({cw:.4f}*{z}/2)*2"
    sh = f"ceil({ch:.4f}*{z}/2)*2"
    ax, ay = anchor
    return [f"scale=w='{sw}':h='{sh}':eval=frame:flags=lanczos",
            f"crop={W}:{H}:x='({sw}-{W})*{ax:.4f}':y='({sh}-{H})*{ay:.4f}'",
            "setsar=1"]


def fade_filters(bg, n):
    """bg.fade_in / bg.fade_out: 프레임 수. bg.fade_color: black(기본) 또는 white."""
    out = []
    color = bg.get("fade_color", "black")
    fi, fo = int(bg.get("fade_in", 0) or 0), int(bg.get("fade_out", 0) or 0)
    if fi > 0:
        out.append(f"fade=t=in:st=0:n={fi}:color={color}")
    if fo > 0:
        out.append(f"fade=t=out:s={max(0, n - fo)}:n={fo}:color={color}")
    return out


def look_filters(bg):
    out = []
    g = bg["grade"]
    if any(abs(g[k] - GRADE_DEFAULTS[k]) > 1e-9 for k in GRADE_DEFAULTS):
        out.append("eq=contrast=%g:saturation=%g:brightness=%g:gamma=%g"
                   % (g["contrast"], g["saturation"], g["brightness"], g["gamma"]))
    if bg.get("vignette"):
        out.append("vignette")
    if bg.get("grain", 0) > 0:
        out.append(f"noise=alls={int(round(bg['grain'] * 100))}:allf=t+u")
    return out


def segment_command(shot, tl, out_path):
    fps, W, H, n = tl["fps"], tl["width"], tl["height"], shot["frames"]
    bg = shot["bg"]
    t = bg["type"]
    head = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
    tail = ["-r", str(fps), "-fps_mode", "cfr", "-frames:v", str(n), "-an", *X264, out_path]

    if t in ("black", "white", "color"):
        color = {"black": "black", "white": "white"}.get(t) or color_to_ffmpeg(bg["color"])
        return head + ["-f", "lavfi", "-i", f"color=c={color}:s={W}x{H}:r={fps}",
                       "-vf", "format=yuv420p"] + tail

    info = probe(bg["src"])
    vf = cover_zoom_filters(info["width"], info["height"], W, H,
                            bg["zoom"], float(bg["zoom_amount"]), n,
                            float(bg.get("punch", 1.0)), tuple(bg.get("anchor", [0.5, 0.5]))) + look_filters(bg) + fade_filters(bg, n)
    if t == "image":
        return head + ["-loop", "1", "-framerate", str(fps), "-i", bg["src"],
                       "-vf", ",".join(vf + ["format=yuv420p"])] + tail

    # clip
    speed = float(bg["speed"])
    need = n / fps * speed  # seconds of source consumed
    if info["duration"] is not None and bg["in"] + need > info["duration"] + 1e-3:
        raise FootageError(
            f"shot {shot['id']}: clip too short. needs {need:.3f}s of source from in={bg['in']}s "
            f"(speed {speed}) but {bg['src']} is {info['duration']:.3f}s long")
    vf = [f"setpts=(PTS-STARTPTS)/{speed}", f"fps={fps}"] + vf + ["format=yuv420p"]
    return head + ["-ss", f"{bg['in']:.6f}", "-t", f"{need + 1.0:.6f}", "-i", bg["src"],
                   "-vf", ",".join(vf)] + tail


def build_footage(tl, build_dir, out_path=None):
    out_path = out_path or os.path.join(build_dir, "footage.mp4")
    seg_dir = os.path.join(build_dir, "segments")
    os.makedirs(seg_dir, exist_ok=True)
    seg_paths = []
    for shot in tl["shots"]:
        t0 = time.time()
        seg = os.path.join(seg_dir, f"{shot['id']}.mp4")
        cmd = segment_command(shot, tl, seg)
        run(cmd)
        got = count_frames(seg)
        if got != shot["frames"]:
            raise FootageError(
                f"shot {shot['id']}: expected {shot['frames']} frames but ffmpeg produced {got} "
                f"(source too short or unreadable)\n  command: {' '.join(shlex.quote(c) for c in cmd)}")
        seg_paths.append(seg)
        print(f"  [{shot['id']}] {shot['bg']['type']:5s} {shot['frames']:4d} frames  {time.time() - t0:5.2f}s",
              flush=True)

    list_path = os.path.join(seg_dir, "concat.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for p in seg_paths:
            f.write("file '%s'\n" % p.replace("'", r"'\''"))
    run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", list_path, "-c", "copy", "-movflags", "+faststart", out_path])
    got = count_frames(out_path)
    if got != tl["total_frames"]:
        raise FootageError(f"footage has {got} frames, expected {tl['total_frames']}")
    print(f"  footage.mp4: {got} frames ({got / tl['fps']:.3f}s)", flush=True)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Build footage.mp4 from a timeline")
    ap.add_argument("timeline")
    ap.add_argument("--build", default=None, help="build dir (default: <timeline dir>/build)")
    a = ap.parse_args()
    build = a.build or os.path.join(os.path.dirname(os.path.abspath(a.timeline)), "build")
    try:
        tl = load(a.timeline)
        t0 = time.time()
        build_footage(tl, build)
        print(f"done in {time.time() - t0:.1f}s")
    except (TimelineError, FootageError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
