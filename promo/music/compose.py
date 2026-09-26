"""
score.json을 읽어 배경음악 wav를 만든다.
사용: python3 compose.py score.json out.wav

score 형식
{
  "bpm": 120, "duration": 46.0, "key_root": "D",
  "sections": [ {"start": 0, "end": 8, "pattern": "pulse"}, ... ],
  "events":   [ {"t": 0.0, "type": "impact", "gain": 1.0}, ... ]
}
pattern: silence | pulse | build | drop | groove | outro
event type: impact | impact_short | tick | riser | downlifter | bell | cut(무음 구간: len)
"""
import json
import math
import sys

import numpy as np
import soundfile as sf
from pedalboard import Pedalboard, Compressor, HighpassFilter, Limiter, Reverb, LowShelfFilter

import synth as S

SR = S.SR


def chords_for(root):
    """i, i, VI, VII 진행 (단조). 서브 음과 패드 보이싱을 돌려준다."""
    r = S.NOTE[root]
    def n(semi, octv):
        return 440.0 * 2 ** ((r + semi + 12 * (octv + 1) - 69) / 12)
    prog = [
        {"sub": n(0, 2), "pad": [n(0, 3), n(3, 3), n(7, 3), n(14, 3)], "arp": [n(0, 4), n(3, 4), n(7, 4), n(12, 4)]},
        {"sub": n(0, 2), "pad": [n(0, 3), n(3, 3), n(7, 3), n(14, 3)], "arp": [n(0, 4), n(3, 4), n(7, 4), n(12, 4)]},
        {"sub": n(8, 1), "pad": [n(8, 2), n(12, 3), n(15, 3), n(19, 3)], "arp": [n(8, 3), n(12, 4), n(15, 4), n(20, 4)]},
        {"sub": n(10, 1), "pad": [n(10, 2), n(14, 3), n(17, 3), n(22, 3)], "arp": [n(10, 3), n(14, 4), n(17, 4), n(22, 4)]},
    ]
    return prog


def render(score):
    bpm = score["bpm"]
    beat = 60.0 / bpm
    bar = beat * 4
    dur = float(score["duration"])
    prog = chords_for(score.get("key_root", "D"))

    drums = S.Track(dur)
    bass = S.Track(dur)
    music = S.Track(dur)   # 패드, 아르페지오 (사이드체인 대상)
    fx = S.Track(dur)
    kick_times = []

    # 드럼 원샷 캐시
    KICK = S.kick()
    CLAP = S.clap()
    _sb = S.snare_body() * 0.7
    CLAP[: len(_sb)] += _sb
    HAT = S.hat()
    HAT_O = S.hat(open_=True)
    TICK = S.tick()

    for sec in score["sections"]:
        s0, s1, pat = float(sec["start"]), float(sec["end"]), sec["pattern"]
        sg = float(sec.get("gain", 1.0))
        nbars = int(math.ceil((s1 - s0) / bar - 1e-6))
        # 구간 끝을 넘는 이벤트는 버린다 (1.5마디 같은 구간을 허용)
        def _in(t):
            return t < s1 - 1e-6
        for b in range(nbars):
            t_bar = s0 + b * bar
            ch = prog[b % 4] if pat not in ("outro", "break") else prog[0]
            if pat == "silence":
                continue

            if pat == "break":
                # 킥 없음. 패드가 열린 채 머물고 서브 꼬리만
                music.add(S.pad_chord(ch["pad"], (s1 - t_bar) + 0.6, cutoff_start=1200, cutoff_end=700, a=0.02, r=0.8), t_bar, gain=0.45 * sg)
                if b == 0:
                    bass.add(S.sub_note(ch["sub"], 1.6), t_bar, gain=0.5 * sg)
                continue

            if pat == "pulse":
                # 마디 첫 박에 서브 한 번, 아주 낮게. 긴장감만
                bass.add(S.sub_note(ch["sub"] / 2, beat * 1.5), t_bar, gain=0.35 * sg)
                for k in range(4):
                    tk = t_bar + k * beat + beat * 0.5
                    if _in(tk):
                        drums.add(HAT, tk, gain=0.12 * sg)

            if pat == "build":
                music.add(S.pad_chord(ch["pad"], bar + 0.4, cutoff_start=300, cutoff_end=1400), t_bar, gain=0.55 * sg)
                bass.add(S.sub_note(ch["sub"], bar * 0.98), t_bar, gain=0.6 * sg)
                for k in range(8):
                    g = 0.28 if k % 2 == 0 else 0.16
                    drums.add(HAT, t_bar + k * beat / 2, gain=g * sg, pan=0.15 if k % 2 else -0.15)
                # 킥 예고: 마지막 세 마디에 걸쳐 2박, 4박, 4박으로 늘어난다. 1마디짜리 빌드면 3·4박만
                if nbars == 1:
                    kicks = [t_bar + 2 * beat, t_bar + 3 * beat]
                elif b == nbars - 1:
                    kicks = [t_bar + k * beat for k in range(4)]
                elif b == nbars - 2:
                    kicks = [t_bar + k * beat for k in range(4)]
                elif b == nbars - 3:
                    kicks = [t_bar + 2 * beat, t_bar + 3 * beat]
                else:
                    kicks = []
                for tk in kicks:
                    if _in(tk):
                        drums.add(KICK, tk, gain=0.75 * sg)
                        kick_times.append(tk)

            if pat in ("drop", "groove"):
                # 킥 4박, 클랩 2·4박, 하이햇 16분, 서브베이스, 패드, 플럭
                for k in range(4):
                    tk = t_bar + k * beat
                    if not _in(tk):
                        continue
                    drums.add(KICK, tk, gain=1.0 * sg)
                    kick_times.append(tk)
                    if pat == "drop" and k in (1, 3):
                        drums.add(CLAP, tk, gain=0.55 * sg)
                for k in range(16):
                    tk = t_bar + k * beat / 4
                    if not _in(tk):
                        continue
                    if k % 4 == 2:
                        g = 0.32
                    elif k % 2 == 0:
                        g = 0.12
                    else:
                        g = 0.18
                    drums.add(HAT, tk, gain=g * sg, pan=0.2 if k % 2 else -0.2)
                if b % 2 == 1 and _in(t_bar + 3.5 * beat):
                    drums.add(HAT_O, t_bar + 3.5 * beat, gain=0.22 * sg)
                # 서브: 1박 3박에 두 번, 살짝 글라이드
                bass.add(S.sub_note(ch["sub"], beat * 1.9), t_bar, gain=0.85 * sg)
                if _in(t_bar + 2 * beat):
                    bass.add(S.sub_note(ch["sub"], beat * 1.9, glide_from=ch["sub"] * 1.5), t_bar + 2 * beat, gain=0.8 * sg)
                music.add(S.pad_chord(ch["pad"], min(bar, s1 - t_bar) + 0.3, cutoff_start=900, cutoff_end=2200, a=0.05), t_bar, gain=(0.5 if pat == "drop" else 0.38) * sg)
                if pat == "drop":
                    # 플럭 아르페지오: 16분 중 뒤박 위주로 성글게
                    pattern = [1, 0, 1, 0, 0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 0, 1]
                    arp = ch["arp"]
                    for k, on in enumerate(pattern):
                        if on and _in(t_bar + k * beat / 4):
                            music.add(S.pluck(arp[(k * 3) % 4]), t_bar + k * beat / 4, gain=0.22 * sg, pan=(-1) ** k * 0.35)

            if pat == "outro" and b == 0:
                music.add(S.pad_chord(ch["pad"], (s1 - t_bar) + 1.5, cutoff_start=500, cutoff_end=700, a=0.8, r=2.5), t_bar, gain=0.4 * sg)
                bass.add(S.sub_note(ch["sub"] / 2, (s1 - t_bar)), t_bar, gain=0.35 * sg)

    for ev in score.get("events", []):
        t, ty, g = float(ev["t"]), ev["type"], float(ev.get("gain", 1.0))
        if ty == "impact":
            fx.add(S.impact(), t, gain=g)
        elif ty == "impact_short":
            fx.add(S.impact(dur=0.9), t, gain=g * 0.8)
        elif ty == "tick":
            fx.add(TICK, t, gain=g)
        elif ty == "riser":
            fx.add(S.riser(dur=float(ev.get("len", 2.0))), t, gain=g * 0.6)
        elif ty == "downlifter":
            fx.add(S.downlifter(), t, gain=g)
        elif ty == "bell":
            fx.add(S.sine_bell(prog[0]["arp"][0] * 2), t, gain=g * 0.5)
        elif ty == "sub_hit":
            bass.add(S.sub_note(prog[0]["sub"] / 2, 1.2), t, gain=g * 0.6)
        elif ty == "roomtone":
            fx.add(S.fade(S.roomtone(float(ev.get("len", 1.0))), 0.05, 0.02), t, gain=g)
        elif ty == "hat_roll":
            # len초 동안 32분음표 햇이 점점 커진다
            L = float(ev.get("len", 0.5))
            step = beat / 8
            k = 0
            while k * step < L - 1e-6:
                drums.add(HAT, t + k * step, gain=g * (0.12 + 0.28 * (k * step / L)), pan=(-1) ** k * 0.25)
                k += 1

    # 사이드체인: 킥마다 패드·플럭·서브가 눌린다
    sc = S.sidechain_env(dur, kick_times, depth=0.8, release=0.18)
    sc_bass = S.sidechain_env(dur, kick_times, depth=0.55, release=0.1)
    n = music.n
    music.L *= sc[:n]; music.R *= sc[:n]
    bass.L *= sc_bass[:n]; bass.R *= sc_bass[:n]

    # 버스 처리
    wet = Pedalboard([Reverb(room_size=0.55, damping=0.5, wet_level=0.22, dry_level=0.78, width=0.9)])
    mus = wet(music.stereo(dur), SR)
    drm = drums.stereo(dur)
    drm_room = Pedalboard([Reverb(room_size=0.25, damping=0.7, wet_level=0.07, dry_level=0.93)])(drm, SR)
    bas = bass.stereo(dur)
    efx = Pedalboard([Reverb(room_size=0.7, damping=0.4, wet_level=0.18, dry_level=0.82)])(fx.stereo(dur), SR)

    mix = drm_room * 0.42 + bas * 0.40 + mus * 0.36 + efx * 0.40

    # 무음 컷(cut 이벤트): 완전 정적 구간
    for ev in score.get("events", []):
        if ev["type"] == "cut":
            s = int(float(ev["t"]) * SR); e = int((float(ev["t"]) + float(ev["len"])) * SR)
            k = int(0.004 * SR)
            mix[s:s + k] *= np.linspace(1, 0, k)[:, None]
            mix[s + k:e] = 0

    master = Pedalboard([
        HighpassFilter(cutoff_frequency_hz=24),
        LowShelfFilter(cutoff_frequency_hz=90, gain_db=1.5),
        Compressor(threshold_db=-16, ratio=2.0, attack_ms=15, release_ms=150),
        Limiter(threshold_db=-1.5, release_ms=90),
    ])
    out = master(mix.astype(np.float32), SR)
    peak = float(np.abs(out).max())
    if peak > 0.89:
        out = out * (0.89 / peak)
    # 리미터 지연으로 새어 들어온 꼬리를 정적 구간에서 다시 지운다 (완전한 무음)
    for ev in score.get("events", []):
        if ev["type"] == "cut":
            s = int(float(ev["t"]) * SR) + int(0.004 * SR); e = int((float(ev["t"]) + float(ev["len"])) * SR)
            out[s:e] = 0
    out = S.fade(out, 0.0, 0.8)
    return out


if __name__ == "__main__":
    score = json.load(open(sys.argv[1], encoding="utf-8"))
    out = render(score)
    sf.write(sys.argv[2], out, SR, subtype="PCM_24")
    print(f"wrote {sys.argv[2]} {len(out)/SR:.2f}s peak {np.abs(out).max():.3f}")
