"""Timeline loading, validation and frame math shared by the engine tools.

load(path) returns the parsed JSON with these fields attached:
    shot["start_f"], shot["end_f"]   global frame indices, end exclusive
    shot["frames"]                   end_f - start_f
    tl["total_frames"]
"src" and "audio" paths are resolved to absolute paths relative to the JSON file.
bg defaults are filled in. Text/card/image/flash defaults live in overlay.html.
"""
import json
import math
import os

BG_TYPES = ("black", "white", "color", "clip", "image")
ZOOMS = ("in", "out", "none")
ANIM_IN = ("hit", "slam", "fade", "rise", "none", "track", "wipe")
ANIM_OUT = ("cut", "fade", "none")
CARD_TYPES = ("review",)
GRADE_DEFAULTS = {"contrast": 1.0, "saturation": 1.0, "brightness": 0.0, "gamma": 1.0, "temperature": 6500}


class TimelineError(Exception):
    pass


def to_frame(sec, fps):
    """Seconds -> frame index. floor(x + 0.5) so Python and JS agree exactly."""
    return int(math.floor(sec * fps + 0.5))


def color_to_ffmpeg(c):
    """'#fff' / '#ffffff' / 'black' -> ffmpeg color string."""
    c = str(c).strip()
    if c.startswith("#"):
        h = c[1:]
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        if len(h) != 6:
            raise TimelineError(f"bad color {c!r}")
        return "0x" + h
    return c


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def load(path):
    with open(path, encoding="utf-8") as f:
        tl = json.load(f)
    validate(tl, os.path.dirname(os.path.abspath(path)))
    return tl


def _resolve(path, base_dir):
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(base_dir, path))


def validate(tl, base_dir):
    errs = []
    err = errs.append

    fps = tl.get("fps")
    if not (isinstance(fps, int) and fps > 0):
        err("fps must be a positive integer")
    for k in ("width", "height"):
        v = tl.get(k)
        if not (isinstance(v, int) and v > 0 and v % 2 == 0):
            err(f"{k} must be a positive even integer")
    dur = tl.get("duration")
    if not (_is_num(dur) and dur > 0):
        err("duration must be a number > 0")
    shots = tl.get("shots")
    if not (isinstance(shots, list) and shots):
        err("shots must be a non-empty list")
    if errs:
        raise TimelineError("invalid timeline:\n  - " + "\n  - ".join(errs))

    audio = tl.get("audio")
    if audio:
        tl["audio"] = _resolve(audio, base_dir)
        if not os.path.isfile(tl["audio"]):
            err(f"audio not found: {tl['audio']}")
    else:
        tl["audio"] = None

    tl["total_frames"] = to_frame(dur, fps)
    ids = set()
    prev_end, prev_end_f = 0.0, 0
    for i, s in enumerate(shots):
        s["id"] = str(s.get("id") or f"shot{i}")
        sid = s["id"]
        if sid in ids:
            err(f"shot {sid}: duplicate id")
        ids.add(sid)
        st, en = s.get("start"), s.get("end")
        if not (_is_num(st) and _is_num(en)) or en <= st:
            err(f"shot {sid}: start/end must be numbers with end > start")
            continue
        if i == 0 and abs(st) > 1e-6:
            err(f"shot {sid}: first shot must start at 0 (starts at {st})")
        elif abs(st - prev_end) > 1e-6:
            err(f"shot {sid}: starts at {st} but previous shot ends at {prev_end} "
                "(shots must tile [0, duration] with no gaps or overlaps)")
        if abs(en * fps - round(en * fps)) > 1e-3:
            err(f"shot {sid}: end {en}s is not on a frame boundary at {fps} fps")
        s["start_f"] = prev_end_f
        s["end_f"] = to_frame(en, fps)
        s["frames"] = s["end_f"] - s["start_f"]
        if s["frames"] <= 0:
            err(f"shot {sid}: shorter than one frame")
        prev_end, prev_end_f = en, s["end_f"]

        _validate_bg(s, base_dir, err)
        for j, t in enumerate(s.get("texts") or []):
            _validate_text(t, f"shot {sid} texts[{j}]", err)
        for j, c in enumerate(s.get("cards") or []):
            _validate_card(c, f"shot {sid} cards[{j}]", err)
        for j, im in enumerate(s.get("images") or []):
            _validate_image(im, f"shot {sid} images[{j}]", base_dir, err)
        for j, ty in enumerate(s.get("typing") or []):
            _validate_typing(ty, f"shot {sid} typing[{j}]", err)
        for j, ch in enumerate(s.get("chat") or []):
            _validate_chat(ch, f"shot {sid} chat[{j}]", err)
        for j, rc in enumerate(s.get("receipts") or []):
            _validate_receipt(rc, f"shot {sid} receipts[{j}]", err)
        for j, fl in enumerate(s.get("flashes") or []):
            _validate_flash(fl, f"shot {sid} flashes[{j}]", err)
        for j, fx in enumerate(s.get("fx") or []):
            _validate_fx(fx, f"shot {sid} fx[{j}]", err)

    if abs(prev_end - dur) > 1e-6:
        err(f"last shot ends at {prev_end} but duration is {dur}")
    if errs:
        raise TimelineError("invalid timeline:\n  - " + "\n  - ".join(errs))


def _validate_bg(s, base_dir, err):
    sid = s["id"]
    bg = s.get("bg")
    if not isinstance(bg, dict):
        err(f"shot {sid}: bg must be an object")
        return
    t = bg.get("type")
    if t not in BG_TYPES:
        err(f"shot {sid}: bg.type must be one of {BG_TYPES}")
        return
    if t == "color" and not isinstance(bg.get("color"), str):
        err(f"shot {sid}: bg.color (e.g. '#1a1a1a') is required for type 'color'")
    if t in ("clip", "image"):
        src = bg.get("src")
        if not isinstance(src, str):
            err(f"shot {sid}: bg.src is required for type '{t}'")
        else:
            bg["src"] = _resolve(src, base_dir)
            if not os.path.isfile(bg["src"]):
                err(f"shot {sid}: bg.src not found: {bg['src']}")
    bg.setdefault("in", 0.0)
    bg.setdefault("speed", 1.0)
    bg.setdefault("fit", "cover")
    bg.setdefault("zoom", "none")
    bg.setdefault("zoom_amount", 0.06)
    bg.setdefault("vignette", False)
    bg.setdefault("grain", 0.0)
    bg.setdefault("punch", 1.0)
    bg.setdefault("anchor", [0.5, 0.5])
    for k in ("fade_in", "fade_out"):
        bg.setdefault(k, 0)
        if not (isinstance(bg[k], int) and bg[k] >= 0):
            err(f"shot {sid}: bg.{k} must be a non-negative integer (frames)")
    bg.setdefault("fade_color", "black")
    if bg["fade_color"] not in ("black", "white"):
        err(f"shot {sid}: bg.fade_color must be black or white")
    if not (_is_num(bg["punch"]) and bg["punch"] >= 1.0):
        err(f"shot {sid}: bg.punch must be a number >= 1")
    an = bg["anchor"]
    if not (isinstance(an, list) and len(an) == 2 and all(_is_num(v) and 0 <= v <= 1 for v in an)):
        err(f"shot {sid}: bg.anchor must be [x, y] with values between 0 and 1")
    grade = dict(GRADE_DEFAULTS)
    grade.update(bg.get("grade") or {})
    bg["grade"] = grade
    if not (_is_num(bg["in"]) and bg["in"] >= 0):
        err(f"shot {sid}: bg.in must be >= 0")
    if not (_is_num(bg["speed"]) and bg["speed"] > 0):
        err(f"shot {sid}: bg.speed must be > 0")
    if bg["fit"] != "cover":
        err(f"shot {sid}: bg.fit only supports 'cover'")
    if bg["zoom"] not in ZOOMS:
        err(f"shot {sid}: bg.zoom must be one of {ZOOMS}")
    if not (_is_num(bg["zoom_amount"]) and bg["zoom_amount"] >= 0):
        err(f"shot {sid}: bg.zoom_amount must be >= 0")
    if not (_is_num(bg["grain"]) and 0 <= bg["grain"] <= 1):
        err(f"shot {sid}: bg.grain must be between 0 and 1")
    for k, v in grade.items():
        if k not in GRADE_DEFAULTS or not _is_num(v):
            err(f"shot {sid}: bg.grade.{k} must be a number ({', '.join(GRADE_DEFAULTS)})")


def _validate_span(o, where, err):
    st, en = o.get("start"), o.get("end")
    if not (_is_num(st) and _is_num(en)) or en <= st:
        err(f"{where}: start/end must be numbers with end > start")
    if o.get("anim_in", "hit") not in ANIM_IN:
        err(f"{where}: anim_in must be one of {ANIM_IN}")
    if o.get("anim_out", "cut") not in ANIM_OUT:
        err(f"{where}: anim_out must be one of {ANIM_OUT}")


def _validate_text(t, where, err):
    if not isinstance(t.get("text"), str) or not t["text"]:
        err(f"{where}: text must be a non-empty string")
    _validate_span(t, where, err)
    for k in ("size", "weight", "letter_spacing", "line_height", "max_width", "in_frames", "out_frames", "hit_scale", "drift_scale", "word_frames", "y_to", "move_at", "move_frames", "scale_to", "track_from", "ls_to", "out_to", "drift_until"):
        if k in t and not _is_num(t[k]):
            err(f"{where}: {k} must be a number")
    if "words" in t:
        w = t["words"]
        if not (isinstance(w, list) and w and all(_is_num(v) for v in w)):
            err(f"{where}: words must be a non-empty list of seconds (one per word)")
        elif any(w[i] > w[i + 1] for i in range(len(w) - 1)):
            err(f"{where}: words must be non-decreasing")
    if "accent_color" in t and not isinstance(t["accent_color"], str):
        err(f"{where}: accent_color must be a string")


def _validate_card(c, where, err):
    if c.get("type") not in CARD_TYPES:
        err(f"{where}: type must be one of {CARD_TYPES}")
    if not isinstance(c.get("text"), str):
        err(f"{where}: text must be a string")
    stars = c.get("stars", 5)
    if not (isinstance(stars, int) and 0 <= stars <= 5):
        err(f"{where}: stars must be an integer 0..5")
    _validate_span(c, where, err)


def _validate_image(im, where, base_dir, err):
    src = im.get("src")
    if not isinstance(src, str):
        err(f"{where}: src is required")
    else:
        im["src"] = _resolve(src, base_dir)
        if not os.path.isfile(im["src"]):
            err(f"{where}: src not found: {im['src']}")
    _validate_span(im, where, err)
    if "width" in im and not (_is_num(im["width"]) and im["width"] > 0):
        err(f"{where}: width must be a number > 0")
    op = im.get("opacity", 1)
    if not (_is_num(op) and 0 <= op <= 1):
        err(f"{where}: opacity must be between 0 and 1")


def _validate_typing(ty, where, err):
    if not isinstance(ty.get("text"), str) or not ty["text"]:
        err(f"{where}: text must be a non-empty string")
    _validate_span(ty, where, err)
    keys, states = ty.get("keys"), ty.get("states")
    if not (isinstance(keys, list) and keys and all(_is_num(k) for k in keys)):
        err(f"{where}: keys must be a non-empty list of seconds")
    elif not (isinstance(states, list) and len(states) == len(keys)):
        err(f"{where}: states must have one string per key")
    elif any(keys[i] > keys[i + 1] for i in range(len(keys) - 1)):
        err(f"{where}: keys must be non-decreasing")
    elif _is_num(ty.get("start")) and _is_num(ty.get("end")) and not (ty["start"] <= keys[0] and keys[-1] < ty["end"]):
        err(f"{where}: keys must lie inside [start, end)")
    if not _is_num(ty.get("post_at")):
        err(f"{where}: post_at (seconds) is required")


def _validate_chat(ch, where, err):
    _validate_span(ch, where, err)
    msgs = ch.get("messages")
    if not (isinstance(msgs, list) and msgs):
        err(f"{where}: messages must be a non-empty list")
        return
    for i, m in enumerate(msgs):
        if not isinstance(m.get("text"), str) or not m["text"]:
            err(f"{where}: messages[{i}].text must be a non-empty string")
        if not (_is_num(m.get("typing_from")) and _is_num(m.get("arrive_at")) and m["typing_from"] <= m["arrive_at"]):
            err(f"{where}: messages[{i}] needs typing_from <= arrive_at (seconds)")


def _validate_receipt(rc, where, err):
    if not isinstance(rc.get("text"), str) or not rc["text"]:
        err(f"{where}: text must be a non-empty string")
    _validate_span(rc, where, err)
    lt = rc.get("line_times")
    if not (isinstance(lt, list) and lt and all(_is_num(v) for v in lt)):
        err(f"{where}: line_times must be a non-empty list of seconds")
    if not _is_num(rc.get("tear_at")):
        err(f"{where}: tear_at (seconds) is required")


FX_TYPES = ("slot", "ticker", "grid", "count")


def _validate_fx(fx, where, err):
    if fx.get("type") not in FX_TYPES:
        err(f"{where}: type must be one of {FX_TYPES}")
        return
    _validate_span(fx, where, err)
    t = fx["type"]
    if t == "slot":
        if not isinstance(fx.get("text"), str) or "{" not in fx["text"]:
            err(f"{where}: slot text must contain {{a|b|c}}")
        st = fx.get("slot_times")
        if not (isinstance(st, list) and st and all(_is_num(v) for v in st)):
            err(f"{where}: slot_times must be a non-empty list of seconds")
    if t == "ticker":
        rows = fx.get("rows")
        if not (isinstance(rows, list) and rows and all(isinstance(r.get("words"), list) and r["words"] and _is_num(r.get("y")) for r in rows)):
            err(f"{where}: rows must be a list of {{words: [...], y: px, speed?, dir?, size?}}")
    if t == "grid":
        if not (isinstance(fx.get("items"), list) and fx["items"]):
            err(f"{where}: items must be a non-empty list")
    if t == "count":
        for k in ("from", "to"):
            if not _is_num(fx.get(k)):
                err(f"{where}: {k} must be a number")


def _validate_flash(fl, where, err):
    if not _is_num(fl.get("at")):
        err(f"{where}: at must be a number (seconds)")
    frames = fl.get("frames", 2)
    if not (isinstance(frames, int) and frames >= 1):
        err(f"{where}: frames must be an integer >= 1")
    op = fl.get("opacity", 0.9)
    if not (_is_num(op) and 0 <= op <= 1):
        err(f"{where}: opacity must be between 0 and 1")
