"""Compare published soft estimates and hard slicing at the suspected transition."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

BASE = Path(__file__).parent


def moments(values):
    return dict(
        median_abs_real=float(np.median(abs(values.real))),
        median_abs_imag=float(np.median(abs(values.imag))),
        rms_imag=float(np.sqrt(np.mean(values.imag**2))),
        quadrature_to_inphase_power=float(np.sum(values.imag**2) / np.sum(values.real**2)),
    )


def main():
    soft_path = BASE / "local/soft-transition-0-12.npz"
    hard_path = BASE / "local/full-reference-0-12.npz"
    boundary_path = BASE / "local/tail_axis_boundary.json"
    template_path = (
        BASE.parents[1]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    archive = np.load(soft_path)
    bins = archive["bins"]
    template = loadmat(template_path)["referenceTemplateRotations"]
    rotation = np.exp(-0.5j * np.pi * template[bins, :].T)
    soft = archive["symbols"] * rotation
    hard = np.load(hard_path)["symbols"][:, :, bins] * rotation
    rows = []
    for boundary in json.loads(boundary_path.read_text())["rows"]:
        if boundary["allowed_errors"] or boundary["residue"] == 0:
            continue
        frame = boundary["frame"]
        previous = boundary["boundary"] // 1004 + 1
        for label, symbol in (
            ("earlier", previous - 2),
            ("transition", previous),
            ("later", previous + 2),
        ):
            rows.append(
                dict(
                    frame=frame,
                    symbol=symbol,
                    region=label,
                    soft=moments(soft[frame, symbol - 1]),
                    hard=moments(hard[frame, symbol - 1]),
                )
            )
    result = dict(
        rows=rows,
        bins=bins.tolist(),
        carriers_per_window=len(bins),
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (soft_path, hard_path, boundary_path, template_path)
        },
        limitation="Published soft and hard decisions from one acquisition, "
        "not independent raw demodulation. Small selected carrier windows. "
        "Strong evidence of constellation slicing artifacts, not a bit decode.",
    )
    (BASE / "local/soft_transition_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    for row in rows:
        if row["region"] == "transition":
            print(row["frame"], row["soft"], row["hard"])


if __name__ == "__main__":
    main()
