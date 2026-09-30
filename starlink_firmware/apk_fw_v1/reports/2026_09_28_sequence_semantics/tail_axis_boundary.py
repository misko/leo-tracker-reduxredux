"""Locate tail transitions using axis membership, without cyclic word matching."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def first_axis_window(values, width=240, allowed_errors=2):
    qualified = (abs(values.imag) < 0.05) & (abs(abs(values.real) - 1) < 0.05)
    counts = np.convolve(qualified.astype(int), np.ones(width, dtype=int), "valid")
    starts = np.flatnonzero(counts >= width - allowed_errors)
    return int(starts[0]) if starts.size else None


def main():
    source = BASE / "local/full-reference-0-12.npz"
    map_path = BASE / "local/frame_binary_map.json"
    phase_path = BASE / "local/region_phase_audit.json"
    template_path = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    physical = np.array(
        [
            k
            for k in np.argsort(np.fft.fftfreq(1024))
            if 2 <= k < 1022 and k not in range(488, 496) and k not in range(528, 536)
        ]
    )
    archive = np.load(source)
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = archive["symbols"][:, 1:][:, :, physical] * np.exp(-0.5j * np.pi * template[physical, 1:].T)
    rows = []
    for frame in json.loads(map_path.read_text())["frames"]:
        index = frame["frame_index"]
        coarse = frame["binary_like_intervals"][-1][0]
        lo = coarse - 3
        values = z[index, lo - 2 : coarse].ravel()
        for allowed in (0, 1, 2):
            start = first_axis_window(values, allowed_errors=allowed)
            rows.append(
                dict(
                    frame=index,
                    coarse_tail_symbol=coarse,
                    allowed_errors=allowed,
                    boundary=None if start is None else (lo - 2) * 1004 + start,
                )
            )
    # Phase information is accessed only after every boundary has been estimated.
    phases = {
        r["frame"]: r["phase"]
        for r in json.loads(phase_path.read_text())["rows"]
        if r["region"] == "tail_later"
    }
    for row in rows:
        row["phase"] = phases[row["frame"]]
        row["residue"] = None if row["boundary"] is None else (row["boundary"] + row["phase"]) % 60
    result = dict(
        rows=rows,
        width=240,
        axis_tolerance=0.05,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, map_path, phase_path, template_path)
        },
        limitation="Boundary does not use phase or sign, but shares recording and "
        "template with phase fit. Axis membership need not identify the true tail "
        "start. Coarse region selection and prior hypothesis are exploratory.",
    )
    (BASE / "local/tail_axis_boundary.json").write_text(json.dumps(result, indent=2) + "\n")
    for allowed in (0, 1, 2):
        print(allowed, [r["residue"] for r in rows if r["allowed_errors"] == allowed])


if __name__ == "__main__":
    main()
