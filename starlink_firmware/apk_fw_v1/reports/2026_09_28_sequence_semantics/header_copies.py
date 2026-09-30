"""Discovery/evaluation test for repeated variable header bits at different positions."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]


def select_pairs(bits, valid):
    counts = bits.sum(axis=0)
    eligible = valid.all(axis=0) & (counts >= 2) & (counts <= len(bits) - 2)
    normalized = bits ^ bits[0]
    keys = normalized.T @ (1 << np.arange(len(bits)))
    pairs = []
    for key in np.unique(keys[eligible]):
        ids = np.flatnonzero(eligible & (keys == key))
        for other in ids[1:]:
            pairs.append((int(ids[0]), int(other), int(bits[0, ids[0]] ^ bits[0, other])))
    return pairs


def main():
    oldpath = BASE / "local/pilot_referenced_header_bits.npz"
    newpath = BASE / "local/full-reference-0-12.npz"
    templatepath = (
        ROOT
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
        / "reference-template/referenceTemplate.mat"
    )
    old, new = np.load(oldpath), np.load(newpath)
    template = np.exp(0.5j * np.pi * loadmat(templatepath)["referenceTemplateRotations"])
    bins = old["bins"]
    z = new["symbols"][:, 1:7][:, :, bins] * template[bins, 1:7].T.conj()
    bits = (z.real >= 0).reshape(13, -1)
    valid = ((abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)).reshape(13, -1)
    pairs = select_pairs(old["bits"].reshape(7, -1), old["valid"].reshape(7, -1))
    # Fixed representative per discovery class; no evaluation-based anchor selection.
    pairs = np.array([(a, b, c) for a, b, c in pairs if valid[:, a].all() and valid[:, b].all()])
    left, right, flip = pairs.T
    exact = ((bits[:, left] ^ bits[:, right]) == flip).all(axis=0)
    rng = np.random.default_rng(2013)
    counts = []
    for _ in range(1999):
        shuffled_right = bits[rng.permutation(13)][:, right]
        counts.append(int(((bits[:, left] ^ shuffled_right) == flip).all(axis=0).sum()))
    rows = [
        dict(
            symbol_a=int(a // 1004 + 2),
            carrier_a=int(bins[a % 1004]),
            symbol_b=int(b // 1004 + 2),
            carrier_b=int(bins[b % 1004]),
            inversion=int(c),
            evaluation_ones_a=int(bits[:, a].sum()),
        )
        for a, b, c in pairs[exact]
    ]
    result = dict(
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [oldpath, newpath, templatepath]
        },
        discovery_pairs=len(pairs),
        exact_evaluation_pairs=int(exact.sum()),
        matches=rows,
        shuffle_expected_exact=float(np.mean(counts)),
        shuffle_p_at_least_observed=(1 + sum(n >= exact.sum() for n in counts)) / 2000,
        scope="Seven old frames select matching or inverted column sequences, "
        "requiring each bit value at least twice. One fixed representative per "
        "discovery group. Thirteen new full-band frames evaluate equality. "
        "All pair positions must be qualified throughout evaluation.",
        limitations="Only direct bit copies/complements, not general interleaving or "
        "coding. Permuting evaluation frame order on the right preserves marginal "
        "bit counts and within-side dependence, but exchangeability is an assumption.",
    )
    (BASE / "local/header_copies.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
