"""Physically changed ephemerides, scheduled fades and burst data interference."""

from unittest.mock import patch

import numpy as np

from . import waveform_site_model as stock

SITE_BOX = (7.5, -68.5)
RATE, SAMPLES = stock.RATE, stock.SAMPLES
pulse_bank = stock.pulse_bank
ELEMENTS = (
    "jdsatepoch",
    "jdsatepochF",
    "no_kozai",
    "ecco",
    "inclo",
    "nodeo",
    "argpo",
    "mo",
    "bstar",
)
FFT, CP, OCCUPIED = 256, 16, 160


def changed_bank(bank, causal):
    earlier = {s.satnum: tuple(getattr(s, field) for field in ELEMENTS) for s in causal}
    return [
        s
        for s in bank
        if s.satnum in earlier
        and tuple(getattr(s, field) for field in ELEMENTS) != earlier[s.satnum]
    ]


def stress(visits, rng):
    active = {}
    for v in visits:
        if (p := v["planted"][0]) is not None:
            active.setdefault(p["norad"], []).append(v)
        v["burst"] = None
        if rng.random() < 0.48:
            start = int(rng.integers(0, int(0.20 * SAMPLES)))
            stop = int(rng.integers(int(0.45 * SAMPLES), SAMPLES))
            v["burst"] = dict(
                seed=int(rng.integers(0, 2**63)),
                start=start,
                stop=stop,
                frequency_hz=float(rng.uniform(-750_000, 750_000)),
                level=float(rng.uniform(600, 1150)),
                lane_gains=rng.uniform(0.8, 1.2, 2).tolist(),
            )
        v["activity_gap"] = False
        v["fade_amplitude"] = 1.0
    for probes in active.values():
        start = int(rng.integers(3, len(probes) - 4))
        for v in probes[start : start + 2]:
            v["activity_gap"] = True
            v["planned_norad"] = v["planted"][0]["norad"]
            v["planted"] = [None, None]
        for v in probes:
            if not v["activity_gap"] and rng.random() < 0.25:
                v["fade_amplitude"] = float(10 ** (rng.uniform(-24, -12) / 20))
                for p in v["planted"]:
                    p["amplitude"] *= v["fade_amplitude"]


def make_scene(bank, causal, anchor, rng):
    faster_revised = changed_bank(bank, causal)
    with patch.object(stock, "SITE_BOX", SITE_BOX):
        visits, scene = stock.make_scene(faster_revised, causal, anchor, rng)
    stress(visits, rng)
    axis, sign = int(rng.integers(0, 2)), int(rng.choice([-1, 1]))
    scene["offers"]["far-omitted"] = stock.regional_offer(scene["coordinate"], axis, sign, 55.0)
    return visits, scene


def interference(burst):
    rng = np.random.default_rng(burst["seed"])
    length = burst["stop"] - burst["start"]
    count = (length + FFT + CP - 1) // (FFT + CP)
    quadrant = rng.integers(0, 4, (count, OCCUPIED))
    qpsk = np.array([1, -1, 1j, -1j], dtype=np.complex64)[quadrant]
    bins = np.zeros((count, FFT), dtype=np.complex64)
    half = OCCUPIED // 2
    bins[:, 1 : half + 1] = qpsk[:, :half]
    bins[:, -half:] = qpsk[:, half:]
    symbols = np.fft.ifft(bins, axis=1).astype(np.complex64)
    serial = np.concatenate((symbols[:, -CP:], symbols), axis=1).ravel()[:length]
    carrier = burst["frequency_hz"] * stock.INDEX[:length] / RATE
    return (
        burst["level"] * FFT / np.sqrt(OCCUPIED) * serial * np.exp(2j * np.pi * carrier)
    ).astype(np.complex64)


def iq(record, profile, frame):
    """Emit the Qin pilot and asynchronous QPSK data burst before ADC quantization."""
    rng = np.random.default_rng(record["sample_seed"])
    time = (stock.INDEX - (SAMPLES - 1) / 2) / profile["sample_rate_truth_hz"]
    out = np.empty((SAMPLES, 2, 2), dtype="<i2")
    burst = record["burst"]
    data = interference(burst) if burst is not None else None
    for lane, plant in enumerate(record["planted"]):
        tone = time * record["tone_hz"] + rng.uniform(-0.5, 0.5)
        wave = (record["tone_amplitude"] * np.exp(2j * np.pi * tone)).astype(np.complex64)
        if plant is not None:
            epoch, period = plant["epoch"], plant["period"]
            pilot = stock.pulse(frame, epoch, period)
            pilot += (0.11 + 0.065j) * stock.pulse(frame, epoch + 1.2 + 0.3 * lane, period)
            orbit = (
                time * plant["actual_cfo_hz"]
                + 0.5 * plant["slope_hz_s"] * time**2
                + rng.uniform(-0.5, 0.5)
            )
            wave += (plant["amplitude"] * pilot * np.exp(2j * np.pi * orbit)).astype(np.complex64)
        if data is not None:
            wave[burst["start"] : burst["stop"]] += burst["lane_gains"][lane] * data * (1j**lane)
        analog = np.column_stack((wave.real, wave.imag)) + rng.normal(0, 530, size=(SAMPLES, 2))
        out[:, lane, :] = np.clip(np.rint(analog), -32768, 32767).astype("<i2")
    return out
