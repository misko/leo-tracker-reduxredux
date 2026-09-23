import numpy as np
import pytest

from tools.research.replay_longarc_timing import (
    frozen_mask_row,
    require_same_pairs,
    shifted_slice,
)


@pytest.mark.parametrize("shift", [-1.0, 0.0, 1.0])
def test_integer_shift_uses_exact_source_samples(shift):
    iq = np.arange(500) * (1 + 2j)
    result = shifted_slice(iq, 100, 40, shift, (50, 200))
    np.testing.assert_array_equal(result, iq[99 + int(shift) : 141 + int(shift)])


def test_fractional_shift_has_correct_sign_and_preserves_carrier_phase():
    iq = np.exp(2j * np.pi * 0.03 * np.arange(500))
    result = shifted_slice(iq, 100, 40, 0.37, (50, 200))
    expected = np.exp(2j * np.pi * 0.03 * (np.arange(99, 141) + 0.37))
    np.testing.assert_allclose(result, expected, atol=0.002)


def test_interpolation_support_must_remain_in_group():
    with pytest.raises(ValueError, match="assigned group"):
        shifted_slice(np.ones(500, complex), 100, 40, 0.37, (99, 141))


def test_variant_eligibility_cannot_change_paired_population():
    baseline = {
        "selected_seed_index": 0,
        "branches": [
            {"frames": [{"frame": {"frame_start_sample": 100, "training_supported": True}}]}
        ],
    }
    variant = {
        "branches": [
            {"frames": [{"frame": {"frame_start_sample": 100, "training_supported": False}}]}
        ]
    }
    paired = frozen_mask_row(baseline, variant)
    assert paired["branches"][0]["frames"][0]["frame"]["training_supported"]
    assert not variant["branches"][0]["frames"][0]["frame"]["training_supported"]


def test_missing_fold_cannot_silently_change_phase_pair_population():
    pairs = [
        {"group": 0, "endpoint_ids": ["visit:1", "visit:2"]},
        {"group": 0, "endpoint_ids": ["visit:3", "visit:4"]},
    ]
    with pytest.raises(ValueError, match="frozen phase pair"):
        require_same_pairs(pairs, pairs[:1])
    require_same_pairs(pairs, pairs)
