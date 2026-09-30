"""Test a constant complex gain at the exceptional tail carrier on later symbols."""

import hashlib
import json
from pathlib import Path

import numpy as np
from boundary_tail_prediction import predicted_signs
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def estimate_gain(values, prediction, count=30):
    return np.mean(values[:count] * prediction[:count])


def main():
    source = BASE / "local/full-soft-reference-0-12.npz"
    boundary_path = BASE / "local/soft_tail_boundary.json"
    template_path = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    physical = [
        k
        for k in np.argsort(np.fft.fftfreq(1024))
        if 2 <= k < 1022 and k not in range(488, 496) and k not in range(528, 536)
    ]
    compact = {int(k): i for i, k in enumerate(physical)}
    symbols = np.load(source)["symbols"]
    template = loadmat(template_path)["referenceTemplateRotations"]
    rows = []
    for row in json.loads(boundary_path.read_text())["rows"]:
        if row["flank"] != 502:
            continue
        frame, boundary = row["frame"], row["boundary"]
        for carrier in (510, 511, 512):
            ofdm = np.arange(2, 302)
            positions = (ofdm - 2) * 1004 + compact[carrier]
            keep = positions >= boundary
            ofdm, positions = ofdm[keep], positions[keep]
            values = symbols[frame, ofdm - 1, carrier] * np.exp(
                -0.5j * np.pi * template[carrier, ofdm - 1]
            )
            predicted = predicted_signs(boundary, positions)
            gain = estimate_gain(values, predicted)
            evaluation = values[30:]
            expected = predicted[30:] >= 0
            corrected = evaluation / gain
            rows.append(
                dict(
                    frame=frame,
                    bin=carrier,
                    discovery_symbols=30,
                    gain_real=float(gain.real),
                    gain_imag=float(gain.imag),
                    gain_angle_deg=float(np.angle(gain) * 180 / np.pi),
                    evaluation_symbols=len(evaluation),
                    original_errors=int(((evaluation.real >= 0) != expected).sum()),
                    corrected_errors=int(((corrected.real >= 0) != expected).sum()),
                )
            )
    result = dict(
        rows=rows,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, boundary_path, template_path)
        },
        limitation="Gain fitted separately per frame/carrier from first30 known "
        "tail predictions, then frozen for later symbols. Same acquisition and "
        "posthoc exceptional-carrier choice. A gain model does not establish "
        "whether the phase originates in transmitter, propagation, or processing. "
        "Raw-IQ tail windows are too short for this30-symbol split.",
    )
    (BASE / "local/tail_carrier_phase.json").write_text(json.dumps(result, indent=2) + "\n")
    for carrier in (510, 511, 512):
        selected = [r for r in rows if r["bin"] == carrier]
        print(
            carrier,
            "support",
            sum(r["evaluation_symbols"] for r in selected),
            "before",
            sum(r["original_errors"] for r in selected),
            "after",
            sum(r["corrected_errors"] for r in selected),
            "angles",
            [round(r["gain_angle_deg"], 1) for r in selected],
        )


if __name__ == "__main__":
    main()
