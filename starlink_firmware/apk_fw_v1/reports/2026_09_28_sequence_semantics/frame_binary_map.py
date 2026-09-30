"""Map template-relative real-axis membership across complete reference frames."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def intervals(mask):
    edges = np.diff(np.r_[False, mask, False].astype(int))
    return [
        [int(a + 2), int(b + 1)]
        for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1), strict=True)
    ]


def main():
    source = BASE / "local/full-reference-0-12.npz"
    bins_path = BASE / "local/pilot_referenced_header_bits.npz"
    template_path = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    bins = np.load(bins_path)["bins"]
    archive = np.load(source)
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = archive["symbols"][:, 1:][:, :, bins] * np.exp(-0.5j * np.pi * template[bins, 1:].T)
    qualified = (abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)
    fractions = qualified.mean(axis=-1)
    rows = [
        dict(
            frame_index=int(f),
            binary_like_intervals=intervals(q > 0.95),
            membership_fraction=q.tolist(),
        )
        for f, q in zip(archive["frame_indices"], fractions, strict=True)
    ]
    result = dict(
        frames=rows,
        threshold=0.95,
        symbols=list(range(2, 302)),
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, bins_path, template_path)
        },
        limitation="Membership near +/-1 after the shared published template. "
        "Not independent modulation identification, BER, or semantic classification. "
        "Same previously examined UT recording; no new data acquired.",
    )
    (BASE / "local/frame_binary_map.json").write_text(json.dumps(result, indent=2) + "\n")
    for row in rows:
        print(row["frame_index"], row["binary_like_intervals"])


if __name__ == "__main__":
    main()
