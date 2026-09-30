"""Estimate a real-axis transition from soft power, independently of signs."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def power_boundary(values, flank=502):
    q = values.imag**2 / np.maximum(abs(values) ** 2, 1e-20)
    before, after = float(q[:flank].mean()), float(q[-flank:].mean())
    # Compare two fixed flank means; their estimation does not use cyclic phase.
    contrast = (q - after) ** 2 - (q - before) ** 2
    scores = np.r_[0, np.cumsum(contrast)]
    split = int(np.argmax(scores[flank:-flank]) + flank)
    return dict(offset=split, before_mean=before, after_mean=after)


def main():
    source = BASE / "local/full-soft-reference-0-12.npz"
    boundary_path = BASE / "local/tail_axis_boundary.json"
    template_path = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    bins = np.array(
        [
            k
            for k in np.argsort(np.fft.fftfreq(1024))
            if 2 <= k < 1022 and k not in range(488, 496) and k not in range(528, 536)
        ]
    )
    archive = np.load(source)
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = archive["symbols"][:, 1:][:, :, bins] * np.exp(-0.5j * np.pi * template[bins, 1:].T)
    rows = []
    boundaries = [
        r for r in json.loads(boundary_path.read_text())["rows"] if r["allowed_errors"] == 0
    ]
    for row in boundaries:
        coarse = row["coarse_tail_symbol"]
        first = coarse - 4
        values = z[row["frame"], first - 2 : coarse].ravel()
        for flank in (251, 502, 1004):
            estimate = power_boundary(values, flank)
            absolute = (first - 2) * 1004 + estimate.pop("offset")
            rows.append(
                dict(
                    frame=row["frame"],
                    flank=flank,
                    boundary=absolute,
                    hard_boundary=row["boundary"],
                    **estimate,
                )
            )
    # Join phase only after locating every transition.
    phases = {r["frame"]: r["phase"] for r in boundaries}
    for row in rows:
        row["residue"] = (row["boundary"] + phases[row["frame"]]) % 60
    result = dict(
        rows=rows,
        primary_flank=502,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, boundary_path, template_path)
        },
        limitation="Sign-independent two-level power change estimate, not an exact "
        "protocol boundary. Shared template/acquisition, exploratory search region "
        "and model. Flank sensitivity does not measure total uncertainty.",
    )
    (BASE / "local/soft_tail_boundary.json").write_text(json.dumps(result, indent=2) + "\n")
    for row in rows:
        if row["flank"] == 502:
            print(row)


if __name__ == "__main__":
    main()
