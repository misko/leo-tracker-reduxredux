"""Full-support multi-peak frequency profile with optional causal selection."""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.signal import find_peaks

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
sys.path.insert(0, str(ROOT / "reports/2026_09_29_sequence_long_support"))
sys.path.insert(0, str(ROOT / "reports/2026_09_29_sequence_estimator"))
from estimator import TS, initial_frequency  # noqa: E402
from study import PILOT_TRAIN, error, fit, gain  # noqa: E402


def peaks(y):
    values = y[PILOT_TRAIN]
    power = np.sum(abs(np.fft.fft(values, n=8192, axis=0)) ** 2, axis=1)
    spacing = 1 / (8192 * TS)
    indices, _ = find_peaks(
        np.r_[power[-1], power, power[0]], distance=int(np.ceil(2000 / spacing))
    )
    indices = indices - 1
    indices = indices[(indices >= 0) & (indices < len(power))]
    indices = np.unique(np.r_[indices, int(np.argmax(power))])
    chosen = indices[np.argsort(power[indices])[-6:]]
    energy = max(float(np.mean(np.sum(abs(values) ** 2, axis=1))), 1e-30)
    grid = np.fft.fftfreq(8192, TS)
    candidates = []
    for index in chosen:

        def objective(f):
            return -float(np.sum(abs(gain(y, PILOT_TRAIN, f)) ** 2)) / energy

        result = minimize_scalar(
            objective, bounds=(grid[index] - spacing, grid[index] + spacing), method="bounded"
        )
        if not result.success:
            raise RuntimeError("Peak refinement failed")
        candidates.append(dict(frequency_hz=float(result.x), score=float(-result.fun)))
    return sorted(candidates, key=lambda c: c["score"], reverse=True)


def select(candidates, previous):
    best = candidates[0]
    if best["score"] < 0.2:
        return best, None
    if previous is None:
        return best, best["frequency_hz"]
    period = 1 / TS

    def merit(c):
        delta = (c["frequency_hz"] - previous + period / 2) % period - period / 2
        return c["score"] - 0.03 * min((delta / 500) ** 2, 4)

    selected = max(candidates, key=merit)
    return selected, selected["frequency_hz"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started = time.monotonic()
    parent = ROOT / "reports/2026_09_29_rx_frequency_transfer"
    source = parent / "results.json"
    original = json.loads(source.read_text())
    for path, expected in original["input_sha256"].items():
        assert digest(Path(path)) == expected, path
    bindings = {str(source): digest(source)}
    rows = []
    series = []
    for visit in original["visits"]:
        name = visit["signal"]
        path = parent / "local" / f"{name}-pilots.npz"
        bindings[str(path)] = digest(path)
        archive = np.load(path)
        for rx in [0, 1]:
            values = archive[f"rx{rx}"]
            assert values.shape[0] == 80
            previous = None
            for frame, y in enumerate(values):
                coarse, _ = initial_frequency(y)
                legacy = fit([(y, PILOT_TRAIN)], coarse)
                candidates = peaks(y)
                chosen, previous = select(candidates, previous)
                frequencies = dict(
                    legacy=legacy,
                    global_peak=candidates[0]["frequency_hz"],
                    causal=chosen["frequency_hz"],
                )
                series.append(
                    dict(
                        signal=name,
                        receiver=rx,
                        frame=frame,
                        frequencies=frequencies,
                        candidates=candidates,
                    )
                )
                if frame < 30:
                    continue
                old = next(
                    r
                    for r in original["rows"]
                    if (r["signal"], r["receiver"], r["frame"]) == (name, rx, frame)
                )
                errors = {arm: error(y, PILOT_TRAIN, f) for arm, f in frequencies.items()}
                assert abs(errors["legacy"] - old["nmse"]["own"]) < 1e-10
                rows.append(
                    dict(
                        dataset=visit["dataset"],
                        signal=name,
                        receiver=rx,
                        frame=frame,
                        frequencies=frequencies,
                        nmse=errors,
                        causal_changed=abs(frequencies["causal"] - frequencies["global_peak"]) > 1,
                    )
                )
            print(name, rx, "complete", flush=True)
    for path in [
        BASE / "tracking.py",
        BASE / "PROTOCOL.md",
        ROOT / "reports/2026_09_29_sequence_estimator/estimator.py",
        ROOT / "reports/2026_09_29_sequence_long_support/study.py",
    ]:
        bindings[str(path)] = digest(path)
    (BASE / "results.json").write_text(
        json.dumps(
            dict(
                rows=rows, series=series, input_sha256=bindings, seconds=time.monotonic() - started
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
