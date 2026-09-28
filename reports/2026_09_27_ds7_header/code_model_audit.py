"""Bound the dimension of a fixed affine seed-only model for recovered T-codes."""

import hashlib
import json
from pathlib import Path

import numpy as np


def binary_rank(matrix):
    """Exact row rank over GF(2), not floating-point/SVD rank."""
    a = np.asarray(matrix, dtype=np.uint8).copy()
    if a.ndim != 2 or np.any(a > 1):
        raise ValueError("Expected a matrix of binary values")
    pivot = 0
    for column in range(a.shape[1]):
        candidates = np.flatnonzero(a[pivot:, column])
        if not len(candidates):
            continue
        selected = pivot + candidates[0]
        a[[pivot, selected]] = a[[selected, pivot]]
        for row in range(pivot + 1, len(a)):
            if a[row, column]:
                a[row] ^= a[pivot]
        pivot += 1
        if pivot == len(a):
            break
    return pivot


def main():
    out = Path(__file__).parent / "local"
    sources = [out / group / "tcodes.json" for group in ("best-upper", "holdout-upper")]
    rows = [r for p in sources for r in json.loads(p.read_text())["results"]]
    assert all(r["repeated_code_candidate"] and r["receiver_bit_agreement"] == 1 for r in rows)
    a = np.array([[int(b) for b in r["rx0_word"]] for r in rows], dtype=np.uint8)
    b = np.array([[int(v) for v in r["rx1_word"]] for r in rows], dtype=np.uint8)
    assert np.array_equal(a, b)
    affine_rank = binary_rank(a ^ a[0])
    result = dict(
        input_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        observations=len(rows),
        distinct_words=len(np.unique(a, axis=0)),
        linear_rank=binary_rank(a),
        affine_rank=affine_rank,
        fixed_affine_15_bit_seed_only_model_rejected=affine_rank > 15,
        model="Each aligned 60-bit word is A*s XOR c, with fixed binary A and c, "
        "and s containing at most 15 varying bits. Such words have affine rank at most 15.",
        interpretation="The observed affine dimension exceeds this model's limit. "
        "A fixed linear encoder applied solely to a 15-bit seed and constant data "
        "cannot generate all observed aligned words under these assumptions.",
        limitations=[
            "Conditional on recovered signs and common code-position convention.",
            "Does not rule out frame-dependent mapping, variable data, nonlinear processing, "
            "multiple seeds, or an LFSR elsewhere in the transmitter.",
            "Affine dimension is not payload entropy and is not a decoded field width.",
            "Receiver agreement is not an independent transmitted-bit ground truth.",
        ],
    )
    (out / "code-model-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
