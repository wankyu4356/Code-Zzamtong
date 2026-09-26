"""
두 번째 영상용 작곡기. 따뜻하고 느린 피아노풍.
사용: python3 compose_film2.py score.json out.wav

score:
{ "bpm": 84, "duration": 55.0, "key_root": "D",
  "sections": [ {"start":0,"end":8,"pattern":"intro"}, ... ],   # intro | theme | movement | swell | resolve | silence
  "events":   [ {"t": 3.0, "type": "melody", "note": "F#5", "vel": 0.8, "dur": 1.6}, {"t":40,"type":"bell"}, {"t":30,"type":"swell","len":2.0}, {"t":45,"type":"hit_soft"} ] }
진행은 I, V, vi, IV (장조). 마디마다 코드가 바뀐다.
"""
import json
import math
import sys

import numpy as np
import soundfile as sf
from pedalboard import Pedalboard, Compressor, HighpassFilter, Limiter, Reverb, LowShelfFilter

import synth as S

SR = S.SR


def chords(root):
    r = S.NOTE[root]
    def n(semi, octv):
        return 440.0 * 2 ** ((r + semi + 12 * (octv + 1) - 69) / 12)
    # I, V, vi, IV : 아르페지오(저음부터), 패드 보이싱, 베이스
    return [
        {"arp": [n(0, 3), n(7, 3), n(4, 4), n(7, 4), n(12, 4)], "pad": [n(0, 3), n(7, 3), n(4, 4)], "bass": n(0, 2), "top": [n(4, 5), n(2, 5), n(0, 5), n(7, 4)]},
        {"arp": [n(7, 2), n(2, 3), n(11, 3), n(2, 4), n(7, 4)], "pad": [n(7, 2), n(2, 3), n(11, 3)], "bass": n(7, 1), "top": [n(2, 5), n(11, 4), n(9, 4), n(7, 4)]},
        {"arp": [n(9, 2), n(4, 3), n(0, 4), n(4, 4), n(9, 4)], "pad": [n(9, 2), n(4, 3), n(0, 4)], "bass": n(9, 1), "top": [n(0, 5), n(11, 4), n(9, 4), n(4, 4)]},
        {"arp": [n(5, 2), n(0, 3), n(9, 3), n(0, 4), n(5, 4)], "pad": [n(5, 2), n(0, 3), n(9, 3)], "bass": n(5, 1), "top": [n(9, 4), n(0, 5), n(2, 5), n(4, 5)]},
    ]


def render(score):
    bpm = score["bpm"]; beat = 60.0 / bpm; bar = beat * 4
    dur = float(score["duration"])
    prog = chords(score.get("key_root", "D"))
    piano = S.Track(dur); pad = S.Track(dur); perc = S.Track(dur); bass = S.Track(dur); fx = S.Track(dur)
    SH = S.shaker(); KK = S.soft_kick()

    for sec in score["sections"]:
        s0, s1, pat = float(sec["start"]), float(sec["end"]), sec["pattern"]
        sg = float(sec.get("gain", 1.0))
        nbars = int(math.ceil((s1 - s0) / bar - 1e-6))
        for b in range(nbars):
            t_bar = s0 + b * bar
            ch = prog[b % 4] if pat != "resolve" else prog[0]
            def _in(t): return t < s1 - 1e-6
            if pat == "silence":
                continue
            if pat == "intro":
                pad.add(S.warm_pad(ch["pad"], bar + 1.5, cutoff=600, a=1.6, r=2.5), t_bar, gain=0.28 * sg)
                if b % 2 == 0:
                    piano.add(S.piano(ch["arp"][0], 3.0, vel=0.55), t_bar, gain=0.9 * sg)
                    if _in(t_bar + 2 * beat):
                        piano.add(S.piano(ch["arp"][2], 2.4, vel=0.45), t_bar + 2 * beat, gain=0.8 * sg)
            if pat in ("theme", "movement", "swell"):
                cutoff = {"theme": 800, "movement": 1100, "swell": 1600}[pat]
                pad.add(S.warm_pad(ch["pad"], bar + 1.2, cutoff=cutoff, a=0.8, r=2.0), t_bar, gain={"theme": 0.32, "movement": 0.36, "swell": 0.42}[pat] * sg)
                # 아르페지오: 8분음표, 위로 갔다가 내려온다 (swell은 16분)
                order = [0, 1, 2, 3, 4, 3, 2, 1]
                div = 8 if pat != "swell" else 16
                for k in range(div):
                    tk = t_bar + k * bar / div
                    if not _in(tk):
                        continue
                    note = ch["arp"][order[k % 8]]
                    vel = 0.62 if k % (div // 4) == 0 else 0.45
                    piano.add(S.piano(note, 1.6, vel=vel), tk, gain=0.75 * sg, pan=-0.15 + 0.3 * (order[k % 8] / 4))
                bass.add(S.sub_note(ch["bass"], bar * 0.95), t_bar, gain={"theme": 0.18, "movement": 0.26, "swell": 0.3}[pat] * sg)
                if pat in ("movement", "swell"):
                    for k in range(8):
                        tk = t_bar + k * beat / 2
                        if _in(tk):
                            perc.add(SH, tk, gain=(0.5 if k % 2 == 0 else 0.3) * sg, pan=0.25)
                    for k in (0, 2):
                        if _in(t_bar + k * beat):
                            perc.add(KK, t_bar + k * beat, gain=0.55 * sg)
                if pat == "swell":
                    # 정점에서 선율 한 줄
                    for k, note in enumerate(ch["top"]):
                        tk = t_bar + k * beat
                        if _in(tk):
                            piano.add(S.piano(note, 2.0, vel=0.8, soft=False), tk, gain=0.7 * sg, pan=0.1)
            if pat == "resolve":
                if b == 0:
                    for i, note in enumerate(ch["arp"]):
                        piano.add(S.piano(note, 6.0, vel=0.6), t_bar + i * 0.06, gain=0.85 * sg)
                    pad.add(S.warm_pad(ch["pad"], (s1 - t_bar) + 2.0, cutoff=700, a=0.6, r=3.5), t_bar, gain=0.34 * sg)
                    bass.add(S.sub_note(ch["bass"], min(6.0, s1 - t_bar)), t_bar, gain=0.2 * sg)

    for ev in score.get("events", []):
        t, ty, g = float(ev["t"]), ev["type"], float(ev.get("gain", 1.0))
        if ty == "melody":
            piano.add(S.piano(S.hz(ev["note"]), float(ev.get("dur", 1.6)) + 0.8, vel=float(ev.get("vel", 0.8)), soft=ev.get("soft", True)), t, gain=0.9 * g, pan=0.08)
        elif ty == "bell":
            fx.add(S.sine_bell(S.hz(ev.get("note", "D6")), 2.5), t, gain=0.35 * g)
        elif ty == "swell":
            fx.add(S.riser(dur=float(ev.get("len", 2.0)), f_start=150, f_end=2500), t, gain=0.22 * g)
        elif ty == "hit_soft":
            fx.add(S.impact(dur=1.6, low=48), t, gain=0.35 * g)
        elif ty == "roomtone":
            fx.add(S.fade(S.roomtone(float(ev.get("len", 1.0))), 0.05, 0.02), t, gain=g)

    verb = Pedalboard([Reverb(room_size=0.78, damping=0.45, wet_level=0.3, dry_level=0.7, width=1.0)])
    pia = verb(piano.stereo(dur), SR)
    pd = Pedalboard([Reverb(room_size=0.85, damping=0.5, wet_level=0.35, dry_level=0.65)])(pad.stereo(dur), SR)
    pc = Pedalboard([Reverb(room_size=0.3, damping=0.7, wet_level=0.1, dry_level=0.9)])(perc.stereo(dur), SR)
    bs = bass.stereo(dur)
    ef = verb(fx.stereo(dur), SR)
    mix = pia * 0.6 + pd * 0.55 + pc * 0.5 + bs * 0.5 + ef * 0.6
    for ev in score.get("events", []):
        if ev["type"] == "cut":
            s = int(float(ev["t"]) * SR); e = int((float(ev["t"]) + float(ev["len"])) * SR)
            k = int(0.004 * SR); mix[s:s + k] *= np.linspace(1, 0, k)[:, None]; mix[s + k:e] = 0
    master = Pedalboard([HighpassFilter(cutoff_frequency_hz=28), LowShelfFilter(cutoff_frequency_hz=120, gain_db=1.0),
                         Compressor(threshold_db=-18, ratio=1.8, attack_ms=20, release_ms=220), Limiter(threshold_db=-1.5, release_ms=120)])
    out = master(mix.astype(np.float32), SR)
    peak = float(np.abs(out).max())
    if peak > 0.89:
        out *= 0.89 / peak
    return S.fade(out, 0.0, 1.2)


if __name__ == "__main__":
    score = json.load(open(sys.argv[1], encoding="utf-8"))
    out = render(score)
    sf.write(sys.argv[2], out, SR, subtype="PCM_24")
    print(f"wrote {sys.argv[2]} {len(out)/SR:.2f}s peak {np.abs(out).max():.3f}")
