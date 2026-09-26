"""
프로시저럴 신스 엔진. 외부 샘플 없이 numpy로 소리를 만든다.
모든 시간 단위는 초, 샘플레이트 48kHz, 출력은 float32 스테레오.
"""
import numpy as np

SR = 48000
_rng = np.random.default_rng(7)


def _env_ad(n, a, d, curve=6.0):
    """어택 a초, 지수 감쇠 d초(시간상수)."""
    t = np.arange(n) / SR
    att = np.clip(t / max(a, 1e-4), 0, 1)
    dec = np.exp(-t / max(d, 1e-4))
    return att * dec


def _adsr(n, a, d, s, r, hold):
    """hold초 동안 누르고 있다가 r초 릴리즈."""
    t = np.arange(n) / SR
    env = np.zeros(n)
    m = t < a
    env[m] = t[m] / max(a, 1e-4)
    m = (t >= a) & (t < a + d)
    env[m] = 1 + (s - 1) * (t[m] - a) / max(d, 1e-4)
    m = (t >= a + d) & (t < hold)
    env[m] = s
    m = t >= hold
    env[m] = s * np.exp(-(t[m] - hold) / max(r, 1e-4))
    return env


def _onepole_lp(x, cutoff):
    """1차 저역통과. cutoff는 Hz 스칼라 또는 샘플별 배열."""
    y = np.zeros_like(x)
    if np.isscalar(cutoff):
        a = np.exp(-2 * np.pi * cutoff / SR)
        b = 1 - a
        acc = 0.0
        for i in range(len(x)):
            acc = b * x[i] + a * acc
            y[i] = acc
        return y
    a = np.exp(-2 * np.pi * np.asarray(cutoff) / SR)
    b = 1 - a
    acc = 0.0
    for i in range(len(x)):
        acc = b[i] * x[i] + a[i] * acc
        y[i] = acc
    return y


def _svf(x, cutoff, q=0.7):
    """2차 상태변수 저역통과(공진 있음). cutoff는 스칼라 또는 배열. 벡터화 대신 짧은 루프."""
    n = len(x)
    if np.isscalar(cutoff):
        cutoff = np.full(n, float(cutoff))
    g = np.tan(np.pi * np.clip(cutoff, 20, 20000) / SR)
    k = 1.0 / q
    ic1 = ic2 = 0.0
    out = np.zeros(n)
    for i in range(n):
        gi = g[i]
        a1 = 1.0 / (1.0 + gi * (gi + k))
        a2 = gi * a1
        a3 = gi * a2
        v3 = x[i] - ic2
        v1 = a1 * ic1 + a2 * v3
        v2 = ic2 + a2 * ic1 + a3 * v3
        ic1 = 2 * v1 - ic1
        ic2 = 2 * v2 - ic2
        out[i] = v2
    return out


def _saw(freq, n, phase=0.0):
    t = np.arange(n) / SR
    if np.isscalar(freq):
        ph = freq * t + phase
    else:
        ph = np.cumsum(np.asarray(freq)) / SR + phase
    return 2 * (ph - np.floor(ph + 0.5))


def _sine(freq, n, phase=0.0):
    t = np.arange(n) / SR
    if np.isscalar(freq):
        return np.sin(2 * np.pi * (freq * t + phase))
    return np.sin(2 * np.pi * (np.cumsum(np.asarray(freq)) / SR + phase))


def _noise(n):
    return _rng.standard_normal(n)


# ----------------------------------------------------------------- 악기

def kick(dur=0.45, f0=48.0, f1=190.0, sweep=32.0, click=0.35):
    """서브 킥. 피치 스윕 사인 + 짧은 클릭."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = f0 + (f1 - f0) * np.exp(-t * sweep)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7.5)
    body = np.tanh(body * 1.6)
    cl = _noise(n) * np.exp(-t * 420) * click
    cl = cl - _onepole_lp(cl, 900)
    return body + cl


def sub_note(freq, dur, glide_from=None, glide_time=0.06):
    """808풍 서브베이스. 살짝 새추레이션."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    if glide_from:
        f = glide_from + (freq - glide_from) * np.clip(t / glide_time, 0, 1)
    else:
        f = np.full(n, freq)
    x = _sine(f, n)
    x = np.tanh(x * 1.8) * 0.8
    return x * _adsr(n, 0.004, 0.05, 0.85, 0.12, dur - 0.12)


def clap(dur=0.35):
    n = int(SR * dur)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for k, off in enumerate([0.0, 0.011, 0.022, 0.031]):
        m = t >= off
        x[m] += _noise(m.sum()) * np.exp(-(t[m] - off) * (140 if k < 3 else 22))
    x = x - _onepole_lp(x, 700)
    x = _onepole_lp(x, 7500)
    return x * 0.9


def snare_body(dur=0.3):
    n = int(SR * dur)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * (185 + 60 * np.exp(-t * 60)) * t) * np.exp(-t * 28)
    nz = _noise(n) * np.exp(-t * 18)
    nz = nz - _onepole_lp(nz, 1200)
    return tone * 0.6 + nz * 0.5


def hat(dur=0.06, open_=False, tone=9000.0):
    n = int(SR * (0.32 if open_ else dur))
    t = np.arange(n) / SR
    x = _noise(n)
    x = x - _onepole_lp(x, tone * 0.7)
    x = x - _onepole_lp(x, 2500)
    env = np.exp(-t * (11 if open_ else 95))
    return x * env * 0.5


def impact(dur=2.2, low=42.0):
    """쾅. 저역 붐 + 노이즈 폭발 + 긴 꼬리."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    boom = np.sin(2 * np.pi * (low + 70 * np.exp(-t * 9)) * t) * np.exp(-t * 3.2)
    boom = np.tanh(boom * 2.2)
    burst = _noise(n) * np.exp(-t * 14)
    burst = _onepole_lp(_onepole_lp(burst, 2600), 2600)
    tail = _noise(n) * np.exp(-t * 1.6) * 0.12
    tail = _onepole_lp(_onepole_lp(tail, 700), 700)
    return boom * 0.9 + burst * 0.5 + tail


def riser(dur=2.0, f_start=200.0, f_end=6000.0):
    """노이즈 라이저. 필터가 열리며 상승."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    p = (t / dur) ** 1.6
    cutoff = f_start * (f_end / f_start) ** p
    x = _svf(_noise(n), cutoff, q=1.2)
    tone = _sine(60 * (16 ** p), n) * 0.15
    env = p ** 1.2
    return (x * 0.7 + tone) * env


def downlifter(dur=1.6):
    n = int(SR * dur)
    t = np.arange(n) / SR
    p = t / dur
    cutoff = 6000 * (0.03 ** p)
    x = _svf(_noise(n), cutoff, q=0.9)
    return x * (1 - p) ** 1.5 * 0.5


def pad_chord(freqs, dur, cutoff_start=350.0, cutoff_end=1800.0, detune=0.006, a=0.6, r=1.2):
    """디튠 톱니파 패드. 필터가 서서히 열린다."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for f in freqs:
        for d, ph in ((1 - detune, 0.0), (1.0, 0.31), (1 + detune, 0.67)):
            x += _saw(f * d, n, ph)
    x /= (3 * len(freqs))
    p = np.clip(t / dur, 0, 1)
    cutoff = cutoff_start + (cutoff_end - cutoff_start) * (p ** 0.7)
    x = _svf(x, cutoff, q=0.8)
    return x * _adsr(n, a, 0.3, 0.9, r, dur - r)


def pluck(freq, dur=0.35, bright=2600.0):
    """짧은 필터 플럭."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    x = _saw(freq, n) * 0.6 + _saw(freq * 2.003, n) * 0.25
    cutoff = 300 + bright * np.exp(-t * 22)
    x = _svf(x, cutoff, q=1.1)
    return x * _env_ad(n, 0.002, 0.11)


def sine_bell(freq, dur=1.2):
    n = int(SR * dur)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2 * t) * np.exp(-t * 6)
    return x * np.exp(-t * 3.2) * 0.5


def tick(dur=0.03):
    """아주 작은 클릭. 검은 화면 글자 등장용."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    x = _noise(n) * np.exp(-t * 600)
    return (x - _onepole_lp(x, 3000)) * 0.6


# ----------------------------------------------------------------- 믹싱 도구

class Track:
    def __init__(self, dur):
        self.n = int(SR * dur) + SR  # 여유 1초
        self.L = np.zeros(self.n)
        self.R = np.zeros(self.n)

    def add(self, sig, at, gain=1.0, pan=0.0):
        s = int(at * SR)
        if s >= self.n:
            return
        sig = np.asarray(sig)
        e = min(self.n, s + len(sig))
        seg = sig[: e - s] * gain
        gl = np.cos((pan + 1) * np.pi / 4)
        gr = np.sin((pan + 1) * np.pi / 4)
        self.L[s:e] += seg * gl
        self.R[s:e] += seg * gr

    def stereo(self, dur):
        n = int(SR * dur)
        return np.stack([self.L[:n], self.R[:n]], axis=1).astype(np.float32)


def sidechain_env(dur, times, depth=0.85, attack=0.004, release=0.22):
    """킥 타이밍마다 눌렀다 풀리는 게인 곡선(1이 원음)."""
    n = int(SR * dur) + SR
    g = np.ones(n)
    for tk in times:
        s = int(tk * SR)
        if s >= n:
            continue
        m = min(n - s, int(SR * (attack + release * 5)))
        t = np.arange(m) / SR
        dip = np.where(t < attack, 1 - depth * t / attack, 1 - depth * np.exp(-(t - attack) / release))
        g[s:s + m] = np.minimum(g[s:s + m], dip)
    return g


def fade(sig, in_s=0.0, out_s=0.0):
    n = len(sig)
    env = np.ones(n)
    if in_s > 0:
        k = int(SR * in_s)
        env[:k] = np.linspace(0, 1, k)
    if out_s > 0:
        k = int(SR * out_s)
        env[-k:] = np.linspace(1, 0, k)
    if sig.ndim == 2:
        return sig * env[:, None]
    return sig * env


NOTE = {"C": 0, "C#": 1, "Db": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11}


def hz(name):
    """예: 'D2', 'F#3'."""
    p = name[:-1]
    o = int(name[-1])
    return 440.0 * 2 ** ((NOTE[p] + 12 * (o + 1) - 69) / 12)
