"""Exact GF(2) rank constraints on the observed cyclic-phase alphabet."""

import hashlib
import json
from pathlib import Path

from firmware_seed_search import SEED
from phase_model import codebook

BASE = Path(__file__).resolve().parent


def binary_rank(rows):
    basis = {}
    for row in rows:
        while row:
            pivot = row.bit_length() - 1
            if pivot not in basis:
                basis[pivot] = row
                break
            row ^= basis[pivot]
    return len(basis)


def polynomial_gcd(a, b):
    while b:
        while a.bit_length() >= b.bit_length():
            a ^= b << (a.bit_length() - b.bit_length())
        a, b = b, a
    return a


def main():
    source = BASE / "local/phase_model.json"
    observed = json.loads(source.read_text())
    words = codebook(list(map(int, SEED)))
    assert words == observed["generated_words"]
    assert observed["observed_states"] == list(range(60))
    values = [int(word, 2) for word in words]
    affine_rank = binary_rank([word ^ values[0] for word in values])
    seed_polynomial = sum(int(bit) << i for i, bit in enumerate(SEED))
    gcd = polynomial_gcd(seed_polynomial, (1 << 60) | 1)
    rotations = [int(SEED[i:] + SEED[:i], 2) for i in range(60)]
    rank = binary_rank(rotations)
    assert affine_rank == 59 and rank == 60 and gcd == 1
    assert all(word.bit_count() % 2 == 0 for word in values)
    result = dict(
        input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        distinct_observed_states=len(values),
        affine_rank=affine_rank,
        seed_rotation_rank=rank,
        seed_polynomial_gcd_with_x60_plus_1=gcd,
        linear_parity_constraint_dimension=60 - affine_rank,
        implication="The 60-state alphabet cannot be a fixed affine mapping of six "
        "binary inputs, nor a fixed projection of one 32-input-bit linear codeword. "
        "This does not rule out nonlinear phase selection, varying masks/positions, "
        "multiple codewords, or additional variable encoder state.",
        scope="Exact algebra of the previously recovered alphabet. Not a new RF "
        "decode or claim of 59 independent information bits; only 60 words occur.",
    )
    (BASE / "local/phase_rank.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
