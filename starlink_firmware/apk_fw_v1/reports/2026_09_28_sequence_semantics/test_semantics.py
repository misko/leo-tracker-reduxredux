import numpy as np
import pytest
from compare_sequences import aligned
from phase_model import codebook, derive_seed
from state_and_header import chronological_pairs, evaluate_header, phase_header_fields


def test_generator_reconstructs_seed_and_is_complement_invariant():
    seed = np.random.default_rng(18).integers(0, 2, 60)
    words = codebook(seed)
    learned = derive_seed(words[1])
    assert codebook(learned) == words
    assert codebook(1 - seed) == words
    assert words[0] == "1" * 60
    for k in range(1, 60):
        assert words[60 - k] == words[k][-k:] + words[k][:-k]
    with pytest.raises(ValueError):
        derive_seed("0" + "1" * 59)


def test_alignment_preserves_gaps_and_split_boundaries():
    a, b = {0: 5, 2: 7, 44: 8}, {1: 5, 3: 7, 45: 8}
    assert aligned(a, b, 1, 0, 44) == [(5, 5), (7, 7)]
    assert aligned(a, b, 1, 44, 90) == [(8, 8)]
    rows = [dict(signal="a", frame=f, phase_index=k) for f, k in a.items()]
    assert chronological_pairs(rows, 0, 90) == []


def test_header_stability_requires_support_and_predicts_withheld_frames():
    bits = np.ones((20, 2, 3), dtype=int)
    valid = np.ones_like(bits, bool)
    train = np.arange(20) < 10
    result = evaluate_header(bits, valid, train, ~train)
    assert result["stable_positions"] == 6
    assert result["evaluation_agreement"] == 1
    bits[~train] = -1
    assert evaluate_header(bits, valid, train, ~train)["evaluation_agreement"] == 0
    valid[:10] = False
    assert evaluate_header(bits, valid, train, ~train)["eligible_positions"] == 0


def test_phase_field_test_recovers_actual_binary_field():
    phases = np.tile(np.arange(60), 2)
    bits = np.array(
        [[[2 * (int(k) & 1) - 1, 2 * ((int(k) & 6).bit_count() % 2) - 1]] for k in phases]
    )
    train = np.arange(120) < 60
    rows = phase_header_fields(bits, np.ones_like(bits, bool), phases, train, ~train)
    assert [r["phase_bit_mask"] for r in rows] == [1, 6]
    assert all(r["evaluation_agreement"] == 1 for r in rows)
