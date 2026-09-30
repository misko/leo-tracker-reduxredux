"""Test the patent's 1+D^14+D^15 recurrence on the BPSK-invariant phase plane."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]


def extend(seed, length):
    seed = np.asarray(seed, dtype=np.uint8)
    if seed.shape[-1] != 15 or length < 15:
        raise ValueError("Need 15 starting bits and length >=15")
    result = np.zeros((*seed.shape[:-1], length), dtype=np.uint8)
    result[..., :15] = seed
    for i in range(15, length):
        result[..., i] = result[..., i - 14] ^ result[..., i - 15]
    return result


def main():
    path = BASE / "local/pilot_polarity.npz"
    templatepath = (
        ROOT
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
        / "reference-template/referenceTemplate.mat"
    )
    r = loadmat(templatepath)["referenceTemplateRotations"].astype(int)
    p = np.load(path)
    order = np.argsort(np.fft.fftfreq(1024)[p["bins"]])
    bins = p["bins"][order]
    # Restore the removed reference rotation. These are pilot-referenced received
    # quadrants, not the template's bit plane alone. BPSK data flips add two.
    z = p["deviations"][:, 0, :6][:, :, order] * np.exp(0.5j * np.pi * r[bins, 1:7].T)
    quadrant = np.rint(np.angle(z) / (np.pi / 2)).astype(int) % 4
    low = quadrant % 2
    predicted = extend(low[:, :, 32:47], 956)
    errors = predicted[:, :, 15:] != low[:, :, 47:988]
    all_syndrome = low[:, :, 15:] ^ low[:, :, 1:-14] ^ low[:, :, :-15]
    result = dict(
        input_sha256={
            str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in [path, templatepath]
        },
        recurrence="p[n] = p[n-14] XOR p[n-15]",
        seed_compact_indices=[32, 46],
        evaluation_compact_indices=[47, 987],
        predicted_bits=int(errors.size),
        mismatches=int(errors.sum()),
        per_frame_mismatches=errors.sum(axis=(1, 2)).tolist(),
        seeds=low[:, :, 32:47].tolist(),
        syndrome_error_compact_indices=(
            np.flatnonzero(all_syndrome.any(axis=(0, 1))) + 15
        ).tolist(),
        source="https://patents.google.com/patent/US12074683B1/en",
        limitations="Exploratory interval selected after observing edge failures. "
        "Seven frames share a scrambler sequence; not 39522 independent trials. "
        "This identifies one observable phase plane, not both scrambler outputs "
        "or decoded header payload. Edge insertion/order and initialization remain open.",
    )
    (BASE / "local/phase_lfsr.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ["seeds", "input_sha256"]}, indent=2
        )
    )


if __name__ == "__main__":
    main()
