"""
두 번째 영상 사운드. 비트 없는 앰비언트: 룸톤, 발소리, 문, 펜, 종이, 새, 피아노 몇 음, 패드, 벨.
  python3 film2_audio.py score.json out.wav

score:
{ "duration": 57.0,
  "beds":   [{"t0": 0, "t1": 4.0, "kind": "bedroom"}, ...],            # bedroom | stairwell | outdoor | subway | clinic | page
  "steps":  [{"t0": 7.0, "t1": 10.0, "bpm": 96, "surface": "pavement", "gain": 1.0}],  # pavement | stairs
  "pads":   [{"t0": 23.0, "t1": 52.5, "notes": ["F3", "C4", "A4"], "cutoff": 420, "gain": 1.0}],
  "events": [{"t": 1.0, "type": "piano", "note": "F3", "vel": 0.5, "dur": 4.0},
             {"t": 2.6, "type": "bird"}, {"t": 0.6, "type": "curtain"}, {"t": 15.5, "type": "door"},
             {"t": 28.7, "type": "pen", "len": 2.4}, {"t": 31.5, "type": "paper"}, {"t": 18.2, "type": "keys", "n": 2},
             {"t": 49.4, "type": "bell", "note": "F5"}, {"t": 20.6, "type": "cloth"}, {"t": 4.4, "type": "step", "surface": "stairs"}],
  "master": {"target_lufs": -19.0, "fade_out": 1.0} }
"""
import json
import subprocess
import sys

import numpy as np
import soundfile as sf
from pedalboard import Compressor, HighpassFilter, Limiter, Pedalboard, Reverb

import synth as S

SR = S.SR
_rng = np.random.default_rng(2026)


def _noise(n):
    return _rng.standard_normal(n)


def _lp(x, c):
    return S._onepole_lp(x, c)


def _bp(x, c, q=0.8):
    return S._svf(x, c, q)


def _hp(x, c):
    return x - _lp(x, c)


def _rms(x):
    return float(np.sqrt(np.mean(x ** 2)) + 1e-12)


def _to_rms_db(x, db):
    return x * (10 ** (db / 20) / _rms(x))


# ----------------------------------------------------------------- 룸톤 (공간)

def bed(kind, dur):
    """공간별 룸톤. 전부 노이즈 기반, 아주 조용하게. 돌려주는 신호의 RMS는 종류별 dBFS로 맞춘다."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    if kind == "bedroom":
        x = _lp(_lp(_noise(n), 320), 320)
        x += 0.15 * _bp(_noise(n), 5200, 0.4) * 0.05         # 아주 옅은 공기 소리
        return _to_rms_db(x, -44)
    if kind == "stairwell":
        x = _lp(_lp(_noise(n), 420), 420)
        hum = np.sin(2 * np.pi * 100 * t) * 0.15               # 형광등 험 흔적
        return _to_rms_db(x + hum, -43)
    if kind == "outdoor":
        low = _lp(_lp(_noise(n), 180), 180)                    # 먼 차 소리
        mod = 1 + 0.35 * np.sin(2 * np.pi * 0.11 * t) + 0.2 * np.sin(2 * np.pi * 0.047 * t + 1.3)
        mid = _lp(_noise(n), 1400) * 0.25
        air = _bp(_noise(n), 6000, 0.4) * 0.06
        return _to_rms_db(low * mod + mid + air, -38)
    if kind == "subway":
        x = _lp(_lp(_noise(n), 520), 520)
        rumble = np.sin(2 * np.pi * 52 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.3 * t))
        x = x + rumble * 0.35
        x = Pedalboard([Reverb(room_size=0.92, damping=0.3, wet_level=0.55, dry_level=0.45)])(x.astype(np.float32)[None, :], SR)[0]
        return _to_rms_db(x, -37)
    if kind == "clinic":
        x = _lp(_lp(_noise(n), 260), 260)
        hvac = np.sin(2 * np.pi * 120 * t) * 0.08 + _lp(_noise(n), 900) * 0.06
        return _to_rms_db(x + hvac, -45)
    if kind == "page":
        x = _lp(_lp(_noise(n), 240), 240)
        return _to_rms_db(x, -50)
    raise ValueError(kind)


# ----------------------------------------------------------------- 소리들

def footstep(surface="pavement", rng=_rng):
    n = int(SR * 0.22)
    t = np.arange(n) / SR
    f = 70 + 60 * np.exp(-t * 40)
    thump = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 26)
    scuff = _bp(_noise(n), 1800 if surface == "pavement" else 2600, 0.7) * np.exp(-t * 60) * (0.5 if surface == "pavement" else 0.8)
    x = _lp(thump, 300) * 1.4 + scuff * 0.35
    return x * rng.uniform(0.75, 1.0)


def bird(rng=_rng):
    """짧은 새소리 두 번: 사인 스윕."""
    out = np.zeros(int(SR * 0.5))
    for k, at in enumerate((0.0, rng.uniform(0.12, 0.2))):
        n = int(SR * 0.075)
        t = np.arange(n) / SR
        f0 = rng.uniform(2900, 3400) * (1.0 if k == 0 else 1.12)
        f = f0 * (1 + 0.25 * np.sin(2 * np.pi * 45 * t)) * (1 + 0.6 * t / 0.075)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / 0.075) ** 1.5
        s = int(at * SR)
        out[s:s + n] += x * (1.0 if k == 0 else 0.7)
    return out * 0.4


def curtain():
    n = int(SR * 0.9)
    t = np.arange(n) / SR
    x = _bp(_noise(n), 1100 + 700 * np.sin(np.pi * t / 0.9), 0.5)
    env = np.sin(np.pi * np.minimum(1, t / 0.9)) ** 1.3
    return x * env * 0.5


def door():
    """손잡이 틱, 문 밀리는 노이즈, 닫히는 둔탁한 소리."""
    out = np.zeros(int(SR * 1.2))
    n = int(SR * 0.05); t = np.arange(n) / SR
    latch = (_hp(_noise(n), 2200) * 0.6 + np.sin(2 * np.pi * 1850 * t) * 0.5) * np.exp(-t * 180)
    out[: n] += latch * 0.9
    n = int(SR * 0.45); t = np.arange(n) / SR
    swing = _lp(_noise(n), 700) * np.sin(np.pi * t / 0.45) ** 1.2
    s = int(0.06 * SR); out[s:s + n] += swing * 0.35
    n = int(SR * 0.22); t = np.arange(n) / SR
    thud = np.sin(2 * np.pi * (95 * np.exp(-t * 12)) * t) * np.exp(-t * 22) + _lp(_noise(n), 400) * np.exp(-t * 60) * 0.5
    s = int(0.62 * SR); out[s:s + n] += thud * 0.7
    return out


def pen(length, rng=_rng):
    """펜이 종이를 긁는 소리: 불규칙한 짧은 밴드패스 노이즈."""
    out = np.zeros(int(SR * (length + 0.3)))
    t = 0.0
    while t < length:
        d = rng.uniform(0.07, 0.28)
        n = int(SR * d); tt = np.arange(n) / SR
        c = rng.uniform(2200, 3400)
        x = _bp(_noise(n), c, 0.9) * np.sin(np.pi * tt / d) ** 0.8 * rng.uniform(0.5, 1.0)
        s = int(t * SR); out[s:s + n] += x
        t += d + rng.uniform(0.04, 0.32)
    return out * 0.35


def paper():
    n = int(SR * 0.16); t = np.arange(n) / SR
    x = _lp(_noise(n), 1600) * np.exp(-t * 28) * np.minimum(1, t / 0.006)
    thud = np.sin(2 * np.pi * 110 * t) * np.exp(-t * 45) * 0.4
    return (x + thud) * 0.5


def cloth():
    n = int(SR * 0.35); t = np.arange(n) / SR
    return _bp(_noise(n), 650, 0.5) * np.sin(np.pi * t / 0.35) ** 1.5 * 0.35


def key_click(rng=_rng):
    n = int(SR * 0.045); t = np.arange(n) / SR
    x = _hp(_noise(n), 1800) * np.exp(-t * 320) + np.sin(2 * np.pi * rng.uniform(180, 260) * t) * np.exp(-t * 180) * 0.25
    return x * rng.uniform(0.6, 1.0)


# ----------------------------------------------------------------- 렌더

def render(score):
    dur = float(score["duration"])
    beds = S.Track(dur); fx = S.Track(dur); tone = S.Track(dur); pads = S.Track(dur)
    XF = 0.45   # 룸톤 사이 크로스페이드

    for b in score.get("beds", []):
        t0, t1 = float(b["t0"]), float(b["t1"])
        x = bed(b["kind"], (t1 - t0) + XF) * float(b.get("gain", 1.0))
        x = S.fade(x, XF, XF)
        beds.add(x, max(0.0, t0 - XF / 2))

    for st in score.get("steps", []):
        t0, t1 = float(st["t0"]), float(st["t1"])
        step = 60.0 / float(st.get("bpm", 96))
        g = 0.2 * float(st.get("gain", 1.0))
        tk = t0 + float(st.get("offset", 0.15)); k = 0
        while tk < t1 - 0.05:
            fx.add(footstep(st.get("surface", "pavement")), tk + _rng.uniform(-0.012, 0.012), gain=g, pan=-0.3 if k % 2 == 0 else 0.3)
            tk += step; k += 1

    for p in score.get("pads", []):
        t0, t1 = float(p["t0"]), float(p["t1"])
        freqs = [S.hz(nm) for nm in p["notes"]]
        x = S.warm_pad(freqs, (t1 - t0), cutoff=float(p.get("cutoff", 420)), a=float(p.get("attack", 3.0)), r=float(p.get("release", 4.0)))
        pads.add(x, t0, gain=0.14 * float(p.get("gain", 1.0)))

    for ev in score.get("events", []):
        t, ty, g = float(ev["t"]), ev["type"], float(ev.get("gain", 1.0))
        if ty == "piano":
            tone.add(S.piano(S.hz(ev["note"]), float(ev.get("dur", 3.0)) + 1.0, vel=float(ev.get("vel", 0.5)), soft=True), t, gain=0.55 * g, pan=float(ev.get("pan", 0.0)))
        elif ty == "bell":
            tone.add(S.sine_bell(S.hz(ev.get("note", "F5")), 3.5), t, gain=0.4 * g)
        elif ty == "bird":
            fx.add(bird(), t, gain=0.3 * g, pan=float(ev.get("pan", 0.55)))
        elif ty == "curtain":
            fx.add(curtain(), t, gain=0.3 * g, pan=-0.2)
        elif ty == "door":
            fx.add(door(), t, gain=0.38 * g, pan=float(ev.get("pan", 0.1)))
        elif ty == "pen":
            fx.add(pen(float(ev.get("len", 2.0))), t, gain=0.3 * g, pan=0.15)
        elif ty == "paper":
            fx.add(paper(), t, gain=0.32 * g)
        elif ty == "cloth":
            fx.add(cloth(), t, gain=0.5 * g, pan=-0.1)
        elif ty == "keys":
            tk = t
            for _ in range(int(ev.get("n", 2))):
                fx.add(key_click(), tk, gain=0.35 * g, pan=0.25)
                tk += _rng.uniform(0.09, 0.16)
        elif ty == "step":
            fx.add(footstep(ev.get("surface", "stairs")), t, gain=0.22 * g, pan=float(ev.get("pan", -0.2)))
        else:
            raise ValueError(ty)

    room = Pedalboard([Reverb(room_size=0.55, damping=0.55, wet_level=0.18, dry_level=0.82)])
    hall = Pedalboard([Reverb(room_size=0.88, damping=0.4, wet_level=0.42, dry_level=0.58, width=1.0)])
    mix = beds.stereo(dur) * 1.0 + room(fx.stereo(dur), SR) * 0.9 + hall(tone.stereo(dur), SR) * 0.7 + hall(pads.stereo(dur), SR) * 0.8
    master = Pedalboard([HighpassFilter(cutoff_frequency_hz=30), Compressor(threshold_db=-26, ratio=1.4, attack_ms=30, release_ms=300), Limiter(threshold_db=-3.0, release_ms=200)])
    out = master(mix.astype(np.float32), SR)
    m = score.get("master", {})
    return S.fade(out, 0.0, float(m.get("fade_out", 1.0)))


def lufs(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=framelog=quiet", "-f", "null", "-"], capture_output=True, text=True)
    for line in r.stderr.splitlines():
        if line.strip().startswith("I:") and "LUFS" in line:
            return float(line.split(":")[1].split("LUFS")[0])
    return None


if __name__ == "__main__":
    score = json.load(open(sys.argv[1], encoding="utf-8"))
    out = render(score)
    sf.write(sys.argv[2], out, SR, subtype="PCM_24")
    target = float(score.get("master", {}).get("target_lufs", -19.0))
    cur = lufs(sys.argv[2])
    if cur is not None:
        gain = 10 ** ((target - cur) / 20)
        out = out * gain
        peak = float(np.abs(out).max())
        if peak > 0.94:
            out *= 0.94 / peak
        sf.write(sys.argv[2], out, SR, subtype="PCM_24")
        print(f"wrote {sys.argv[2]} {len(out)/SR:.2f}s  loudness {cur:.1f} -> {lufs(sys.argv[2]):.1f} LUFS  peak {np.abs(out).max():.3f}")
    else:
        print(f"wrote {sys.argv[2]} (loudness not measured)")
