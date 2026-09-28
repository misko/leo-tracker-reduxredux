"""Apply the existing low-phase model to newly extracted reference frames, no refit."""

import hashlib
import json
from pathlib import Path

import numpy as np
from rotational_descramble import pn_planes

BASE = Path(__file__).parent


def main():
    source = BASE / "local/full-reference-0-12.npz"
    modelpath = BASE / "local/rotational_descramble.json"
    archive = np.load(source)
    model = json.loads(modelpath.read_text())
    physical = np.array([k for k in np.argsort(np.fft.fftfreq(1024)) if 2 <= k < 1022])
    keep = ~np.isin(physical, np.r_[488:496, 528:536])
    bins, indices = physical[keep], np.flatnonzero(keep)
    low, _ = pn_planes(model["seed"], np.arange(2, 8), indices)
    z = archive["symbols"][:, 1:7][:, :, bins]
    quadrant = np.rint(np.angle(z) / (np.pi / 2)).astype(int) % 4
    # This qualification depends only on constellation membership, not on the
    # predicted phase bit, so failures remain visible.
    qualified = abs(z - np.exp(0.5j * np.pi * quadrant)) < 0.05
    errors = (quadrant % 2 != low) & qualified
    result = dict(
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [source, modelpath]
        },
        array_indices=archive["frame_indices"].tolist(),
        symbols=list(range(2, 8)),
        qualified=int(qualified.sum()),
        mismatches=int(errors.sum()),
        per_frame_mismatches=errors.sum(axis=(1, 2)).tolist(),
        mismatch_fft_bins=np.unique(bins[np.where(errors)[2]]).tolist(),
        frozen_central_interval=[47, 987],
        central_qualified=int(qualified[:, :, 47:988].sum()),
        central_mismatches=int(errors[:, :, 47:988].sum()),
        limitations="First full-band examination of these array frames; eight carrier "
        "slices were previously inspected. Same public recording and template family, "
        "not independent satellites or RF acquisition. Model and frequency interval "
        "carried over without refitting. No inference of header fields or second plane.",
    )
    (BASE / "local/full_reference_validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
