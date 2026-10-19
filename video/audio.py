"""Synthesized soundtrack: lo-fi music bed + foley/UI cues placed from film events.

    python audio.py events.json out.wav

Everything is generated here (no samples), so the film has no third-party audio.
"""
from __future__ import annotations

import json
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

SR = 48000
rng = np.random.default_rng(11)


def t_(d: float) -> np.ndarray:
    return np.arange(int(d * SR)) / SR


def env(n: int, a: float, d: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / d)


def band(x: np.ndarray, lo: float | None, hi: float | None, order: int = 2) -> np.ndarray:
    if lo and hi:
        sos = butter(order, [lo, hi], "bandpass", fs=SR, output="sos")
    elif lo:
        sos = butter(order, lo, "highpass", fs=SR, output="sos")
    else:
        sos = butter(order, hi, "lowpass", fs=SR, output="sos")
    return sosfilt(sos, x)


def note(midi: float) -> float:
    return 440 * 2 ** ((midi - 69) / 12)


# ---- instruments --------------------------------------------------------------------------------

def ep(freq: float, dur: float, vel: float = 1.0) -> np.ndarray:
    """Soft electric-piano pluck."""
    t = t_(dur)
    x = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t * 6) + 0.12 * np.sin(2 * np.pi * 3 * freq * t) * np.exp(-t * 9)
    x *= env(len(t), 0.004, 0.9) * (1 + 0.08 * np.sin(2 * np.pi * 5 * t))
    return x * vel


def pad(freqs: list[float], dur: float) -> np.ndarray:
    t = t_(dur)
    x = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) + 0.3 * np.sin(2 * np.pi * f * 1.003 * t) for f in freqs)
    a = np.minimum(1, t / 0.6) * np.minimum(1, (dur - t) / 0.6).clip(0, 1)
    return band(x, None, 1800) * a / len(freqs)


def kick() -> np.ndarray:
    t = t_(0.35)
    f = 45 + 80 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)


def snare() -> np.ndarray:
    t = t_(0.22)
    n = band(rng.normal(0, 1, len(t)), 1200, 6000) * np.exp(-t * 22)
    return 0.6 * n + 0.3 * np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30)


def hat() -> np.ndarray:
    t = t_(0.06)
    return band(rng.normal(0, 1, len(t)), 7000, None) * np.exp(-t * 70)


def bass(freq: float, dur: float) -> np.ndarray:
    t = t_(dur)
    x = np.sin(2 * np.pi * freq * t) + 0.2 * np.sin(2 * np.pi * 2 * freq * t)
    return x * np.minimum(1, t / 0.01) * np.exp(-t * 2.2)


# ---- foley & UI ---------------------------------------------------------------------------------

def ding(k: int) -> np.ndarray:
    f = [1318.5, 1567.98, 1174.66, 1760.0, 1396.9][k % 5]
    t = t_(0.7)
    x = np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.5 * t) * np.exp(-t * 8)
    return 0.32 * x * env(len(t), 0.002, 0.22)


def step() -> np.ndarray:
    t = t_(0.03)
    x = band(rng.normal(0, 1, len(t)), 2500, 9000) * np.exp(-t * 260)
    return x * rng.uniform(0.05, 0.08)


def land() -> np.ndarray:
    t = t_(0.18)
    thud = np.sin(2 * np.pi * (120 + 160 * np.exp(-t * 40)) * t) * np.exp(-t * 28)
    click = band(rng.normal(0, 1, len(t)), 2000, 8000) * np.exp(-t * 200)
    return 0.22 * thud + 0.08 * click


def plastic_tap(pitch: float = 1.0) -> np.ndarray:
    t = t_(0.08)
    x = np.sin(2 * np.pi * 2300 * pitch * t) * np.exp(-t * 90) + band(rng.normal(0, 1, len(t)), 1500, 7000) * np.exp(-t * 160) * 0.6
    return 0.12 * x


def grab() -> np.ndarray:
    out = np.zeros(int(0.12 * SR))
    for k, d in enumerate((0.0, 0.05)):
        c = plastic_tap(1.0 + 0.2 * k)
        i = int(d * SR)
        out[i:i + len(c)] += c[: len(out) - i]
    return out * 1.4


def drumroll() -> np.ndarray:
    out = np.zeros(int(3.0 * SR))
    for k in range(16):
        c = plastic_tap(0.55 + 0.08 * (k % 2)) * (0.9 + 0.2 * rng.random())
        i = int(k * 0.185 * SR)
        out[i:i + len(c)] += c[: len(out) - i]
    return out


def blip(f0: float, f1: float, dur: float) -> np.ndarray:
    t = t_(dur)
    f = f0 + (f1 - f0) * (t / dur)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.2 * np.sin(3 * ph)
    a = np.minimum(1, t / 0.01) * np.minimum(1, (dur - t) / 0.03).clip(0, 1)
    return band(x * a, 300, 5000) * 0.12


def chirp(kind: str) -> np.ndarray:
    """Bricki's voice: little wordless blips with a pitch contour per emotion."""
    seqs = {
        "wave": [(700, 900, 0.07), (0, 0, 0.03), (900, 1250, 0.11)],
        "raise": [(650, 640, 0.09), (0, 0, 0.03), (640, 980, 0.16)],
        "celebrate": [(800, 1000, 0.06), (1000, 1200, 0.06), (1200, 1500, 0.14)],
        "point": [(900, 880, 0.06), (0, 0, 0.05), (900, 880, 0.06)],
        "look": [(600, 720, 0.12), (720, 640, 0.14)],
    }
    parts = [np.zeros(int(d * SR)) if f0 == 0 else blip(f0, f1, d) for f0, f1, d in seqs.get(kind, seqs["wave"])]
    return np.concatenate(parts)


def ui(kind: str) -> np.ndarray:
    if kind == "card_urgent":
        return np.concatenate([blip(1180, 1180, 0.09), np.zeros(int(0.04 * SR)), blip(1180, 1180, 0.09), np.zeros(int(0.04 * SR)), blip(1400, 1400, 0.14)]) * 1.6
    if kind == "card_needs_you":
        t = t_(0.9)
        return 0.18 * (np.sin(2 * np.pi * 880 * t) * env(len(t), 0.003, 0.3) + 0.8 * np.concatenate([np.zeros(int(0.12 * SR)), np.sin(2 * np.pi * 1318.5 * t)[: len(t) - int(0.12 * SR)] * env(len(t) - int(0.12 * SR), 0.003, 0.35)]))
    if kind == "card_wellbeing":
        t = t_(0.25)
        f = 500 + 900 * (t / 0.25) ** 0.5
        return 0.25 * np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(t), 0.002, 0.07)
    if kind == "card_fyi":
        t = t_(0.5)
        return 0.14 * np.sin(2 * np.pi * 1046.5 * t) * env(len(t), 0.002, 0.15)
    if kind == "key":
        t = t_(0.12)
        return 0.35 * (band(rng.normal(0, 1, len(t)), 1500, 6000) * np.exp(-t * 120) + 0.6 * np.sin(2 * np.pi * 160 * t) * np.exp(-t * 50))
    if kind in ("chip", "title"):
        d = 0.35 if kind == "chip" else 0.6
        t = t_(d)
        n = rng.normal(0, 1, len(t))
        sweep = band(n, 800, 5000) * np.sin(np.pi * t / d) ** 2
        return sweep * (0.035 if kind == "chip" else 0.05)
    if kind == "scan":
        out = band(rng.normal(0, 1, int(1.6 * SR)), 3000, 12000) * np.sin(np.pi * t_(1.6) / 1.6) ** 2 * 0.03
        for k in range(8):
            c = blip(note(84 + [0, 4, 7, 11, 12, 16, 19, 23][k]), note(84 + [0, 4, 7, 11, 12, 16, 19, 23][k]), 0.09) * 0.5
            i = int(k * 0.14 * SR)
            out[i:i + len(c)] += c
        return out
    return np.zeros(1)


# ---- arrangement --------------------------------------------------------------------------------

def music(duration: float, start: float, tense_end: float, outro: float) -> np.ndarray:
    out = np.zeros((int(duration * SR) + SR, 2))
    bpm = 96
    beat = 60 / bpm
    bar = beat * 4
    # Fmaj9 · Am7 · Dm9 · Cmaj9 — warm, unhurried.
    chords = [[53, 57, 60, 64, 67], [57, 60, 64, 67], [50, 57, 60, 64, 65], [48, 55, 59, 62, 64]]
    roots = [41, 45, 38, 36]

    def add(x, at, gain=1.0, pan=0.0):
        i = int(at * SR)
        if i >= len(out):
            return
        x = x[: len(out) - i] * gain
        out[i:i + len(x), 0] += x * np.sqrt(1 - pan)
        out[i:i + len(x), 1] += x * np.sqrt(1 + pan)

    # cold open: a rising, slightly uneasy drone under the notification pile-up
    t = t_(tense_end)
    drone = sum(np.sin(2 * np.pi * note(m) * t) for m in (50, 57, 63)) * (t / tense_end) ** 2
    riser = band(rng.normal(0, 1, len(t)), 2000, 9000) * (t / tense_end) ** 3
    add(band(drone, None, 1200) * 0.05 + riser * 0.05, 0.0)

    t0 = start
    k = 0
    while t0 < outro:
        ci = k % 4
        bar_pos = t0
        add(pad([note(m) for m in chords[ci]], bar + 0.8), bar_pos, 0.11)
        full = k >= 1
        for b in range(4):
            at = bar_pos + b * beat
            if at >= outro:
                break
            if full and b in (0, 2):
                add(kick(), at, 0.45)
            if full and b in (1, 3):
                add(snare(), at, 0.1, 0.1)
            if full:
                for h in (0, 0.5):
                    add(hat(), at + h * beat + (0.02 if h else 0), 0.05 + 0.02 * h, -0.3)
            add(bass(note(roots[ci]), beat * 0.95), at if b in (0, 2) else at + beat * 0.5, 0.22 if b in (0, 2) else 0.0)
            # arpeggiated EP line
            m = chords[ci][(b * 2 + k) % len(chords[ci])] + 12
            add(ep(note(m), 1.2, 0.9), at, 0.09, 0.25 if b % 2 else -0.25)
            if b in (1, 3):
                add(ep(note(chords[ci][(b + 1) % len(chords[ci])] + 12), 1.0, 0.7), at + beat * 0.5, 0.06, 0.2)
        t0 += bar
        k += 1
    # final ringing chord
    for j, m in enumerate([53, 57, 60, 64, 67, 72]):
        add(ep(note(m + 12), 4.0, 0.8), outro + j * 0.06, 0.09, (j - 2.5) / 5)
    add(pad([note(m) for m in [53, 57, 60, 64, 67]], 5.0), outro, 0.12)
    # vinyl-ish air
    air = band(rng.normal(0, 1, len(out)), 300, 6000) * 0.006
    out[int(start * SR):, 0] += air[int(start * SR):]
    out[int(start * SR):, 1] += air[int(start * SR):][::-1][: len(out) - int(start * SR)]
    return out


def main(events_path: str, out_path: str) -> None:
    data = json.loads(open(events_path).read())
    duration = data["duration"]
    marks = dict((name, t) for t, name in data["marks"])
    start = marks.get("meet", 9.3) - 0.05
    end_mark = marks.get("end", duration - 6) + 2.4
    mix = music(duration, start, marks.get("line1", 4.6), end_mark)

    def add(x, at, gain=1.0, pan=0.0):
        i = int(at * SR)
        if i >= len(mix) or i < 0:
            return
        x = x[: len(mix) - i] * gain
        mix[i:i + len(x), 0] += x * (1 - pan * 0.7)
        mix[i:i + len(x), 1] += x * (1 + pan * 0.7)

    dings = 0
    for at, name in sorted(data["events"]):
        if name == "ding":
            add(ding(dings), at, 0.9, rng.uniform(-0.7, 0.7))
            dings += 1
        elif name == "step":
            add(step(), at, 1.0, rng.uniform(-0.2, 0.2))
        elif name == "land":
            add(land(), at)
        elif name == "grab":
            add(grab(), at)
        elif name == "drumroll":
            add(drumroll(), at, 1.3)
        elif name.startswith("chirp_"):
            add(chirp(name[6:]), at + 0.05, 1.0)
        elif name.startswith("card_") or name in ("key", "chip", "title", "scan"):
            add(ui(name), at)

    # hard silence right after the cold open, for the cut
    cut = marks.get("line1")
    if cut:
        i = int(cut * SR)
        mix[i:i + int(0.05 * SR)] *= np.linspace(1, 0, int(0.05 * SR))[:, None]
        mix[i + int(0.05 * SR):int(marks.get("meet", cut + 4.7) * SR)] *= 0.0
        add(kick() * 0.5, cut + 0.12, 0.25)
        add(band(rng.normal(0, 1, int(0.9 * SR)), 300, 2000) * np.exp(-t_(0.9) * 5) * 0.03, marks.get("line2", cut + 2.3))
    peak = np.abs(mix).max()
    mix = np.tanh(mix / peak * 1.4) / np.tanh(1.4) * 0.89
    wavfile.write(out_path, SR, (mix[: int(duration * SR)] * 32767).astype(np.int16))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
