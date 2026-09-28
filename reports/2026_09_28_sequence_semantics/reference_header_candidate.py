"""Evaluate the frozen local 498/503 candidate on existing reference frames."""

import hashlib
import json
from pathlib import Path

import numpy as np
from header_common_phase import describe
from scipy.io import loadmat

BASE = Path(__file__).parent


def main():
    source = BASE / "local/header-reference-0-77.npz"
    template_path = (
        BASE.parents[1]
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
        / "reference-template/referenceTemplate.mat"
    )
    template = loadmat(template_path)["referenceTemplateRotations"]
    bins = np.array([498, 503])
    # Cache OFDM2 is index0, template OFDM2 is index1.
    z = np.load(source)["symbols"][:, 0, bins] * np.exp(-0.5j * np.pi * template[bins, 1])
    valid = ((abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)).all(axis=1)
    result = dict(
        symbol=2,
        bins=bins.tolist(),
        frames=78,
        qualified_frames=int(valid.sum()),
        qualified=describe(z[valid]),
        signs=["".join("1" if b else "0" for b in z[:, i].real >= 0) for i in range(2)],
        validity=valid.tolist(),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        limitation="Same existing public acquisition, fixed coordinates from local "
        "candidate. Tests universal equality only; conditional layouts remain possible.",
    )
    (BASE / "local/reference_header_candidate.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
