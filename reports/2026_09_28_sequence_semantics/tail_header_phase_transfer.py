"""Test tail-trained bin511 phase corrections on later tail and earlier header."""

import hashlib
import json
from pathlib import Path

import numpy as np
from boundary_tail_prediction import predicted_signs
from scipy.io import loadmat

BASE = Path(__file__).parent


def fit_phase(indices, values, signs):
    return np.polyfit(indices, np.unwrap(np.angle(values * signs)), 1)


def axis_fraction(values):
    return float(np.mean(values.imag**2 / np.maximum(abs(values) ** 2, 1e-20)))


def main():
    source = BASE / "local/full-soft-reference-0-12.npz"
    boundary_path = BASE / "local/soft_tail_boundary.json"
    template_path = (
        BASE.parents[1]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = np.load(source)["symbols"][:, 1:, 511] * np.exp(-0.5j * np.pi * template[511, 1:])
    rows = []
    for row in json.loads(boundary_path.read_text())["rows"]:
        if row["flank"] != 502:
            continue
        frame, boundary = row["frame"], row["boundary"]
        indices = np.arange(300)
        positions = indices * 1004 + 1003
        tail = indices[positions >= boundary]
        split = len(tail) // 2
        train, evaluation = tail[:split], tail[split:]
        signs = predicted_signs(boundary, positions)
        coefficients = fit_phase(train, z[frame, train], signs[train])
        corrected = z[frame] * np.exp(-1j * np.polyval(coefficients, indices))
        rows.append(
            dict(
                frame=frame,
                slope_rad_per_symbol=float(coefficients[0]),
                intercept_rad=float(coefficients[1]),
                discovery_symbols=len(train),
                evaluation_symbols=len(evaluation),
                header_q_before=axis_fraction(z[frame, :6]),
                header_q_after=axis_fraction(corrected[:6]),
                evaluation_tail_q_before=axis_fraction(z[frame, evaluation]),
                evaluation_tail_q_after=axis_fraction(corrected[evaluation]),
                evaluation_sign_errors=int(
                    np.sum((corrected[evaluation].real >= 0) != (signs[evaluation] >= 0))
                ),
            )
        )
    result = dict(
        rows=rows,
        carrier=511,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, boundary_path, template_path)
        },
        limitation="Linear phase fitted on first half of tail only. Header axis "
        "improvement is not verified header bits or proof of transmitter coding. "
        "One selected carrier, six header decisions/frame; same acquisition. "
        "Extrapolation may fail and original data remain unchanged.",
    )
    (BASE / "local/tail_header_phase_transfer.json").write_text(json.dumps(result, indent=2) + "\n")
    print("header improved", sum(r["header_q_after"] < r["header_q_before"] for r in rows))
    print(
        "header mean before/after",
        np.mean([r["header_q_before"] for r in rows]),
        np.mean([r["header_q_after"] for r in rows]),
    )
    print(
        "evaluation sign errors/support",
        sum(r["evaluation_sign_errors"] for r in rows),
        sum(r["evaluation_symbols"] for r in rows),
    )


if __name__ == "__main__":
    main()
