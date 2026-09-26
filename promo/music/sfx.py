"""
타이핑 효과음. timeline의 typing 요소(keys, post_at)에서 키 클릭과 등록 소리를 만들어 배경음악과 섞는다.
  python3 sfx.py <timeline.json> <music.wav> <out.wav>
"""
import json
import sys

import numpy as np
import soundfile as sf

SR = 48000


def _lp(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.zeros_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


def click(rng, space=False):
    """키보드 클릭: 짧은 노이즈 + 아주 낮은 몸통. 스페이스는 조금 둔탁하게."""
    n = int(SR * 0.05)
    t = np.arange(n) / SR
    nz = rng.standard_normal(n)
    hp = nz - _lp(nz, 1800 if not space else 900)
    body = np.sin(2 * np.pi * (rng.uniform(170, 260)) * t) * np.exp(-t * 180)
    x = hp * np.exp(-t * (330 + rng.uniform(-60, 60))) * 0.9 + body * (0.5 if space else 0.25)
    return x * rng.uniform(0.55, 1.0)


def pop():
    """등록: 부드러운 팝."""
    n = int(SR * 0.18)
    t = np.arange(n) / SR
    f = 880 * (0.62 ** (t / 0.18))
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 22)
    return x * 0.8


def render(tl, music_path, out_path, click_db=-21.0, pop_db=-16.0):
    music, sr = sf.read(music_path)
    assert sr == SR, sr
    if music.ndim == 1:
        music = np.stack([music, music], axis=1)
    fx = np.zeros_like(music)
    rng = np.random.default_rng(11)
    g_click = 10 ** (click_db / 20)
    g_pop = 10 ** (pop_db / 20)

    def add(sig, at, gain, pan=0.0):
        s = int(at * SR)
        e = min(len(fx), s + len(sig))
        if s >= len(fx):
            return
        seg = sig[: e - s] * gain
        fx[s:e, 0] += seg * (1 - pan) * 0.5 + seg * 0.5
        fx[s:e, 1] += seg * (1 + pan) * 0.5 + seg * 0.5

    for shot in tl["shots"]:
        for ty in shot.get("typing", []):
            keys, states = ty["keys"], ty["states"]
            for i, t in enumerate(keys):
                prev = states[i - 1] if i else ""
                space = states[i].endswith(" ") and len(states[i]) > len(prev)
                add(click(rng, space), t, g_click, pan=rng.uniform(-0.15, 0.15))
            add(pop(), float(ty["post_at"]), g_pop)
    mix = music + fx
    peak = float(np.abs(mix).max())
    if peak > 0.95:
        mix *= 0.95 / peak
    sf.write(out_path, mix.astype(np.float32), SR, subtype="PCM_24")
    return out_path


if __name__ == "__main__":
    tl = json.load(open(sys.argv[1], encoding="utf-8"))
    print(render(tl, sys.argv[2], sys.argv[3]))
