"""Matched-frame cross-receiver tail power with mismatched-frame controls."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent


def cross_powers(x, y):
    x, y = x.reshape(len(x), -1), y.reshape(len(y), -1)
    return x.real @ y.real.T / x.shape[1], x.imag @ y.imag.T / x.shape[1]


def summarize_power(real, imag):
    mask = ~np.eye(len(real), dtype=bool)
    r, q = np.diag(real), np.diag(imag)
    return dict(
        matched_real_mean=float(r.mean()),
        matched_imag_mean=float(q.mean()),
        mismatched_real_mean=float(real[mask].mean()),
        mismatched_imag_mean=float(imag[mask].mean()),
        mismatched_imag_sd=float(imag[mask].std()),
        matched_q_fraction=float(q.sum() / (r + q).sum()),
        positive_matched_total=bool(np.all(r + q > 0)),
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
    x, y = [archive[f"z{i}"][frames] for i in range(2)]
    # Axis estimate uses symbols242..271; all power evaluation uses272..301.
    angles = [0.5 * np.angle(np.mean(z[:, -60:-30] ** 2, axis=(1, 2))) for z in (x, y)]
    corrected = [
        z * np.exp(-1j * angle)[:, None, None] for z, angle in zip((x, y), angles, strict=True)
    ]
    raw = cross_powers(x[:, -30:], y[:, -30:])
    adjusted = cross_powers(corrected[0][:, -30:], corrected[1][:, -30:])
    result = dict(
        frames=frames,
        evaluation_symbols=[272, 301],
        calibration_symbols=[242, 271],
        raw=summarize_power(*raw),
        axis_corrected=summarize_power(*adjusted),
        axis_degrees=[np.rad2deg(a).tolist() for a in angles],
        real_cross_matrix=raw[0].tolist(),
        imaginary_cross_matrix=raw[1].tolist(),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        limitation="Cross-power assumes comparable receiver gauges; can contain "
        "shared interference, leakage, and calibration errors. Different-frame "
        "controls are dependent and not a formal significance test. No transmitted "
        "quadrature bits or semantic fields inferred.",
    )
    (BASE / "local/ds9_cross_power.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("raw", "axis_corrected")}, indent=2))


if __name__ == "__main__":
    main()
