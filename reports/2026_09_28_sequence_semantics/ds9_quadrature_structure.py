"""Measure reproducibility of quadrature signs without asserting bit semantics."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent


def agreement(a, b, mask=None):
    a, b = np.asarray(a), np.asarray(b)
    if mask is not None:
        a, b = a[mask], b[mask]
    p, q = a >= 0, b >= 0
    return dict(
        count=int(p.size),
        agreement=float(np.mean(p == q)),
        marginal_baseline=float(p.mean() * q.mean() + (1 - p.mean()) * (1 - q.mean())),
    )


def main():
    source = BASE / "local/DS9-middle-soft.npz"
    archive = np.load(source)
    assert np.array_equal(archive["bins0"], archive["bins1"])
    metadata = [json.loads(str(archive[f"metadata{i}"])) for i in range(2)]
    frames = sorted(set(metadata[0]["evaluation_frames"]) & set(metadata[1]["evaluation_frames"]))
    frames = [
        f
        for f in frames
        if min(m["diagnostics"][f]["held_pilot_coherence"] for m in metadata) > 0.5
    ]
    split = len(frames) // 2
    train, evaluation = frames[:split], frames[split:]
    x, y = [archive[f"z{i}"][evaluation, -60:] for i in range(2)]
    # Thresholds use RX0 discovery frames only. RX1 signs never select samples.
    discovery = abs(archive["z0"][train, -60:].imag)
    gates = []
    for quantile in (0, 0.5, 0.75, 0.9):
        threshold = float(np.quantile(discovery, quantile)) if quantile else 0.0
        gates.append(
            dict(
                quantile=quantile,
                threshold=threshold,
                **agreement(x.imag, y.imag, abs(x.imag) >= threshold),
            )
        )
    shifts = []
    for lag in (1, 2, 5, 15, 30):
        shifts.append(
            dict(
                symbol_lag=lag,
                quadrature=agreement(x[:, :-lag].imag, y[:, lag:].imag),
                inphase=agreement(x[:, :-lag].real, y[:, lag:].real),
            )
        )
    # Frame-mismatched control keeps each coordinate and symbol position fixed.
    mismatched = agreement(x.imag, np.roll(y.imag, 1, axis=0))
    frequency_shifts = []
    bins = archive["bins0"].tolist()
    for lag in (1, 2, 4):
        pairs = [(i, bins.index(b + lag)) for i, b in enumerate(bins) if b + lag in bins]
        left, right = np.array(pairs).T
        frequency_shifts.append(
            dict(
                bin_lag=lag,
                carrier_pairs=len(pairs),
                quadrature=agreement(x[:, :, left].imag, y[:, :, right].imag),
            )
        )
    output = dict(
        discovery_frames=train,
        evaluation_frames=evaluation,
        symbols=[242, 301],
        quadrature_gates=gates,
        inphase=agreement(x.real, y.real),
        quadrature_frame_shift=mismatched,
        symbol_shifts=shifts,
        frequency_shifts=frequency_shifts,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        limitation="Receiver agreement, not BER or decoded bit validity. Shared "
        "interference/calibration may reproduce across receivers. One recorded "
        "visit; dependent lag comparisons are descriptive, not significance tests.",
    )
    (BASE / "local/ds9_quadrature_structure.json").write_text(json.dumps(output, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in output.items() if k not in ("discovery_frames", "evaluation_frames")},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
