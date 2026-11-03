"""Matched block-frequency fits and complete held-frame accounting."""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
sys.path.insert(0, str(ROOT / "reports/2026_09_29_sequence_long_support"))
from study import PILOT_TRAIN, TS, error  # noqa: E402


def block_fit(frames):
    if len(frames) == 0:
        return None
    y = np.asarray(frames)[:, PILOT_TRAIN]
    spectrum = np.sum(abs(np.fft.fft(y, n=8192, axis=1)) ** 2, axis=(0, 2))
    coarse = np.fft.fftfreq(8192, TS)[np.argmax(spectrum)]
    spacing = 1 / (8192 * TS)

    def objective(f):
        gain = np.mean(y * np.exp(-2j * np.pi * f * (PILOT_TRAIN * TS))[None, :, None], axis=1)
        return -float(np.sum(abs(gain) ** 2))

    r = minimize_scalar(objective, bounds=(coarse - spacing, coarse + spacing), method="bounded")
    if not r.success:
        raise RuntimeError("Block frequency optimization failed")
    return float(r.x)


def compare(frames, support):
    frames = np.asarray(frames)
    support = np.asarray(support, dtype=bool)
    assert frames.shape[0] == len(support)
    all_frequency = block_fit(frames)
    supported_frequency = block_fit(frames[support])
    rows = []
    for y, accepted in zip(frames, support, strict=True):
        all_error = error(y, PILOT_TRAIN, all_frequency)
        support_error = (
            1.0 if supported_frequency is None else error(y, PILOT_TRAIN, supported_frequency)
        )
        rows.append(
            dict(
                accepted=bool(accepted),
                all_nmse=all_error,
                support_fit_nmse=support_error,
                abstention_nmse=support_error if accepted else 1.0,
            )
        )
    return dict(
        all_frequency_hz=all_frequency,
        support_frequency_hz=supported_frequency,
        retained=int(support.sum()),
        rows=rows,
    )


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started = time.monotonic()
    source = ROOT / "reports/2026_09_29_frame_support/results.json"
    parent = json.loads(source.read_text())
    for path, expected in parent["input_sha256"].items():
        assert sha(Path(path)) == expected, path
    bindings = {str(source): sha(source)}
    blocks = []
    for name in dict.fromkeys(r["signal"] for r in parent["rows"]):
        path = ROOT / f"reports/2026_09_29_rx_frequency_transfer/local/{name}-pilots.npz"
        assert sha(path) == parent["input_sha256"][str(path)]
        bindings[str(path)] = sha(path)
        archive = np.load(path)
        for rx in [0, 1]:
            for first in range(30, 80, 10):
                indices = range(first, first + 10)
                inherited = [
                    next(
                        r
                        for r in parent["rows"]
                        if (r["signal"], r["receiver"], r["frame"]) == (name, rx, n)
                    )
                    for n in indices
                ]
                support = [r["support"]["accepted"] for r in inherited]
                result = compare(archive[f"rx{rx}"][first : first + 10], support)
                result.update(
                    signal=name, receiver=rx, first_frame=first, dataset=inherited[0]["dataset"]
                )
                blocks.append(result)
    for p in [
        BASE / "block.py",
        BASE / "PROTOCOL.md",
        ROOT / "reports/2026_09_29_sequence_long_support/study.py",
        ROOT / "reports/2026_09_29_sequence_estimator/estimator.py",
    ]:
        bindings[str(p)] = sha(p)
    (BASE / "results.json").write_text(
        json.dumps(
            dict(blocks=blocks, input_sha256=bindings, seconds=time.monotonic() - started), indent=2
        )
        + "\n"
    )
    print("Complete:", len(blocks), "blocks")


if __name__ == "__main__":
    main()
