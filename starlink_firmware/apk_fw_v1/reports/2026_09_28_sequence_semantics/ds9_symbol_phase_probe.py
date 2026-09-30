"""Bounded symbol-phase probe using disjoint pilot-carrier halves."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str((BASE.parents[3] / "reports") / "2026_09_28_ds7_ds8_correspondence"))
from native_rate_decode import (  # noqa: E402
    calibrate,
    demodulate,
    geometry,
    references,
    supported_bins,
)


def correction(pilots, width=9):
    phase = pilots.mean(axis=1)
    kernel = np.ones(width)
    smoothed = np.convolve(phase, kernel, mode="same") / np.convolve(
        np.ones(len(phase)), kernel, mode="same"
    )
    return np.exp(-1j * np.angle(smoothed))


def coherence(x):
    return float(abs(x.mean()) / np.sqrt(np.mean(abs(x) ** 2)))


def main():
    folder = BASE / "local/ds9-last-10m"
    inventory_path = folder / "inventory.json"
    cache_path = BASE / "local/DS9-last-soft.npz"
    inventory = json.loads(inventory_path.read_text())
    cache = np.load(cache_path)
    rows = []
    frames = [1, 14, 28, 43, 51, 64, 76, 88]
    for rx, row in enumerate(inventory["exports"]):
        raw = np.load(folder / (row["name"] + ".npy"))
        assert hashlib.sha256(raw.tobytes()).hexdigest() == row["excerpt_sha256"]
        meta = json.loads(str(cache[f"metadata{rx}"]))
        rate = row["sample_rate_hz"]
        c = row["candidate"]
        _, allpb, center = geometry(row["probe"]["edge"])
        _, _, pilot = references(row["probe"]["edge"])
        pb = supported_bins(allpb, center, rate, c["fractional_tracking_cfo_hz"])
        pilot = pilot[:, np.isin(allpb, pb)]
        for frame in frames:
            ep = c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"]
            ep += frame * rate / 750 * (1 + meta["sample_clock_ppm"] * 1e-6)
            start = max(0, int(ep) - round(rate * 10e-6))
            values = raw[start : start + round(rate * 0.00137)]
            x = values[:, 0].astype(float) + 1j * values[:, 1]
            sy = demodulate(x, rate, ep - start, c["fractional_tracking_cfo_hz"], center)
            y, _ = calibrate(sy, pilot, pb, meta["diagnostics"][frame]["phase_slope"])
            normalized = y[1:, pb] / pilot
            for half in (0, 1):
                fit_values = normalized[:, half::2]
                held = normalized[:, 1 - half :: 2]
                rotated = held * correction(fit_values)[:, None]
                rows.append(
                    dict(
                        receiver=rx,
                        frame=frame,
                        fit_half=half,
                        held_bins=pb[1 - half :: 2].tolist(),
                        before=coherence(held),
                        after=coherence(rotated),
                        header_before=coherence(held[:6]),
                        header_after=coherence(rotated[:6]),
                    )
                )
    summary = dict(
        frame_receiver_half_tests=len(rows),
        mean_before=float(np.mean([r["before"] for r in rows])),
        mean_after=float(np.mean([r["after"] for r in rows])),
        mean_header_before=float(np.mean([r["header_before"] for r in rows])),
        mean_header_after=float(np.mean([r["header_after"] for r in rows])),
        improved=sum(r["after"] > r["before"] for r in rows),
    )
    output = dict(
        summary=summary,
        rows=rows,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (inventory_path, cache_path)
        },
        limitation="Eight frames from one DS9 visit. Nine-symbol boxcar fixed "
        "before evaluation. Incremental phase correction uses alternate pilot "
        "carriers; baseline drift/SSS timing already used all pilots. Pilot "
        "coherence is not header BER. No native decoder/cache changes.",
    )
    (BASE / "local/ds9_symbol_phase_probe.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
