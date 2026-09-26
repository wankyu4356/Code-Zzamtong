"""
세 번째 영상(타이포그래피 필름) 작곡기. 애플 광고풍의 미니멀 전자음: 타이트한 킥, 스냅, 서브 베이스, 플럭 훅, 정적과 임팩트.
  python3 compose_film3.py score.json out.wav

score:
{ "bpm": 100, "duration": 48.0, "key_root": "C",
  "sections": [ {"start":0,"end":4.8,"pattern":"intro"}, ... ],
     pattern: silence | intro (플럭 훅만) | pulse (킥·스냅·서브) | groove (pulse + 하이햇 + 플럭) | lift (groove + 패드, 상승) | tail (패드와 마지막 코드)
  "events": [ {"t":4.8,"type":"hit"}, {"t":30,"type":"riser","len":1.6}, {"t":47,"type":"chord"}, {"t":10,"type":"tick"}, {"t":12,"type":"cut","len":0.5}, {"t":20,"type":"snap"} ] }
훅은 5음 음계(단조 펜타토닉)의 8분음표 플럭. 마디마다 코드는 i, VI, III, VII.
"""
import json
import math
import sys

import numpy as np
import soundfile as sf
from pedalboard import Compressor, HighpassFilter, LowShelfFilter, Pedalboard, Reverb

import synth as S

SR = S.SR


def chords(root):
    r = S.NOTE[root]
    def n(semi, octv):
        return 440.0 * 2 ** ((r + semi + 12 * (octv + 1) - 69) / 12)
    # i, VI, III, VII (단조)
    return [
        {"bass": n(0, 1), "pad": [n(0, 3), n(3, 3), n(7, 3), n(0, 4)], "hook": [n(0, 4), n(3, 4), n(7, 4), n(10, 4), n(12, 4), n(7, 4), n(3, 4), n(10, 3)]},
        {"bass": n(8, 0), "pad": [n(8, 2), n(0, 3), n(3, 3), n(8, 3)], "hook": [n(8, 3), n(0, 4), n(3, 4), n(8, 4), n(7, 4), n(3, 4), n(0, 4), n(8, 3)]},
        {"bass": n(3, 1), "pad": [n(3, 3), n(7, 3), n(10, 3), n(3, 4)], "hook": [n(3, 4), n(7, 4), n(10, 4), n(3, 5), n(10, 4), n(7, 4), n(3, 4), n(10, 3)]},
        {"bass": n(10, 0), "pad": [n(10, 2), n(2, 3), n(5, 3), n(10, 3)], "hook": [n(10, 3), n(2, 4), n(5, 4), n(10, 4), n(7, 4), n(5, 4), n(2, 4), n(10, 3)]},
    ]


def snap(dur=0.16):
    """손가락 스냅: 짧은 밴드패스 노이즈 + 나무 몸통."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    nz = S._noise(n)
    x = S._svf(nz, 2600, q=1.2) * np.exp(-t * 90)
    body = np.sin(2 * np.pi * 900 * t) * np.exp(-t * 160) * 0.4
    return (x + body) * 0.8


def tight_kick(dur=0.32):
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = 50 + 170 * np.exp(-t * 45)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 14)
    click = S._noise(n) * np.exp(-t * 700) * 0.25
    return body * 0.95 + click


def pluck_hook(freq, dur=0.5):
    """마림바 느낌의 플럭: 사인 + 4배음 짧게, 어택 클릭."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * freq * t) * np.exp(-t * 7) + 0.35 * np.sin(2 * np.pi * freq * 4.0 * t) * np.exp(-t * 28)
    x += 0.15 * np.sin(2 * np.pi * freq * 10.0 * t) * np.exp(-t * 60)
    x *= np.minimum(1, t / 0.002)
    return x * 0.5


def render(score):
    bpm = score["bpm"]; beat = 60.0 / bpm; bar = beat * 4
    dur = float(score["duration"])
    prog = chords(score.get("key_root", "C"))
    drums = S.Track(dur); bass = S.Track(dur); hook = S.Track(dur); pad = S.Track(dur); fx = S.Track(dur)
    KK, SN, HH = tight_kick(), snap(), S.hat(0.05)
    kick_times = []

    for sec in score["sections"]:
        s0, s1, pat = float(sec["start"]), float(sec["end"]), sec["pattern"]
        sg = float(sec.get("gain", 1.0))
        nbars = int(math.ceil((s1 - s0) / bar - 1e-6))
        for b in range(nbars):
            t_bar = s0 + b * bar
            ch = prog[b % 4]
            def _in(t): return t < s1 - 1e-6
            if pat == "silence":
                continue
            if pat in ("intro", "groove", "lift"):
                # 플럭 훅: 8분음표, 마디 패턴 [x . x x . x . x]
                grid = [1, 0, 1, 1, 0, 1, 0, 1]
                for k in range(8):
                    tk = t_bar + k * beat / 2
                    if grid[k] and _in(tk):
                        vel = 1.0 if k in (0, 3) else 0.7
                        hook.add(pluck_hook(ch["hook"][k]), tk, gain=0.55 * vel * sg, pan=-0.2 + 0.4 * (k % 3) / 2)
            if pat in ("pulse", "groove", "lift"):
                for k in (0, 2):                       # 킥 1·3박
                    tk = t_bar + k * beat
                    if _in(tk):
                        drums.add(KK, tk, gain=0.9 * sg); kick_times.append(tk)
                if pat != "pulse" or b % 2 == 1:
                    for k in (1, 3):                   # 스냅 2·4박
                        tk = t_bar + k * beat
                        if _in(tk):
                            drums.add(SN, tk, gain=0.55 * sg, pan=0.1)
                bass.add(S.sub_note(ch["bass"], bar * 0.98), t_bar, gain=0.5 * sg)
            if pat in ("groove", "lift"):
                for k in range(8):                     # 하이햇 8분, 뒷박 약하게
                    tk = t_bar + k * beat / 2
                    if _in(tk):
                        drums.add(HH, tk, gain=(0.35 if k % 2 == 0 else 0.2) * sg, pan=0.3)
            if pat == "lift":
                pad.add(S.warm_pad(ch["pad"], bar + 0.6, cutoff=900 + 300 * b, a=0.4, r=1.2), t_bar, gain=0.16 * sg)
            if pat == "tail":
                if b == 0:
                    pad.add(S.warm_pad(prog[0]["pad"], (s1 - t_bar) + 1.5, cutoff=1100, a=0.3, r=3.0), t_bar, gain=0.26 * sg)
                    bass.add(S.sub_note(prog[0]["bass"], min(5.0, s1 - t_bar)), t_bar, gain=0.45 * sg)
                    for i, f0 in enumerate(prog[0]["pad"]):
                        hook.add(pluck_hook(f0 * 2, 2.4), t_bar + i * 0.05, gain=0.5 * sg)

    for ev in score.get("events", []):
        t, ty, g = float(ev["t"]), ev["type"], float(ev.get("gain", 1.0))
        if ty == "hit":
            fx.add(S.impact(dur=1.4, low=46), t, gain=0.7 * g); kick_times.append(t)
        elif ty == "riser":
            fx.add(S.riser(dur=float(ev.get("len", 1.6)), f_start=200, f_end=5000), t - float(ev.get("len", 1.6)), gain=0.3 * g)
        elif ty == "snap":
            drums.add(SN, t, gain=0.7 * g)
        elif ty == "tick":
            fx.add(S.tick(), t, gain=0.5 * g)
        elif ty == "chord":
            ch = prog[0]
            pad.add(S.warm_pad([f * 2 for f in ch["pad"]], 4.0, cutoff=1600, a=0.05, r=3.0), t, gain=0.3 * g)
            fx.add(S.impact(dur=2.0, low=44), t, gain=0.5 * g)
        elif ty == "pluck":
            hook.add(pluck_hook(S.hz(ev.get("note", "C5")), 1.2), t, gain=0.6 * g)

    d = drums.stereo(dur); b = bass.stereo(dur); h = hook.stereo(dur); p = pad.stereo(dur); e = fx.stereo(dur)
    h = Pedalboard([Reverb(room_size=0.35, damping=0.6, wet_level=0.14, dry_level=0.86)])(h, SR)
    p = Pedalboard([Reverb(room_size=0.7, damping=0.5, wet_level=0.3, dry_level=0.7)])(p, SR)
    e = Pedalboard([Reverb(room_size=0.5, damping=0.5, wet_level=0.2, dry_level=0.8)])(e, SR)
    # 사이드체인: 킥마다 베이스·패드가 살짝 눌린다
    env = S.sidechain_env(dur, sorted(set(round(x, 4) for x in kick_times)), depth=0.5, release=0.16)[: len(b)]
    mix = d * 0.8 + b * env[:, None] * 0.7 + h * 0.6 + p * env[:, None] * 0.6 + e * 0.7
    for ev in score.get("events", []):
        if ev["type"] == "cut":
            s = int(float(ev["t"]) * SR); e_ = int((float(ev["t"]) + float(ev["len"])) * SR)
            k = int(0.004 * SR); mix[s:s + k] *= np.linspace(1, 0, k)[:, None]; mix[s + k:e_] = 0
    master = Pedalboard([HighpassFilter(cutoff_frequency_hz=28), LowShelfFilter(cutoff_frequency_hz=100, gain_db=1.5),
                         Compressor(threshold_db=-16, ratio=2.0, attack_ms=12, release_ms=180)])
    out = master(mix.astype(np.float32), SR)
    return out


def peak_limit(x, ceiling=0.95, lookahead_ms=2.0, release_ms=100.0):
    n = len(x)
    la = max(1, int(SR * lookahead_ms / 1000))
    peak = np.abs(x).max(axis=1)
    pad = np.concatenate([peak, np.zeros(la)])
    env = np.max(np.lib.stride_tricks.sliding_window_view(pad, la + 1), axis=1)[:n]
    need = np.minimum(1.0, ceiling / np.maximum(env, 1e-9))
    rel = np.exp(-1.0 / (SR * release_ms / 1000))
    g = np.ones(n); cur = 1.0
    for i in range(n):
        cur = need[i] if need[i] < cur else (cur * rel + need[i] * (1 - rel))
        g[i] = cur
    return x * g[:, None]


def lufs(path):
    import subprocess
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=framelog=quiet", "-f", "null", "-"], capture_output=True, text=True)
    for line in r.stderr.splitlines():
        if line.strip().startswith("I:") and "LUFS" in line:
            return float(line.split(":")[1].split("LUFS")[0])
    return None


if __name__ == "__main__":
    score = json.load(open(sys.argv[1], encoding="utf-8"))
    out = render(score)
    out = peak_limit(out, 0.95).astype(np.float32)
    sf.write(sys.argv[2], out, SR, subtype="PCM_24")
    target = float(score.get("target_lufs", -14.0))
    cur = lufs(sys.argv[2])
    if cur is not None:
        out = peak_limit(out * 10 ** ((target - cur) / 20), 0.95).astype(np.float32)
        out = S.fade(out, 0.0, float(score.get("fade_out", 0.8)))
        sf.write(sys.argv[2], out, SR, subtype="PCM_24")
        print(f"wrote {sys.argv[2]} {len(out)/SR:.2f}s loudness {cur:.1f} -> {lufs(sys.argv[2]):.1f} LUFS peak {np.abs(out).max():.3f}")
