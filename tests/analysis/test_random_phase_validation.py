import numpy as np
import pytest

from leo.analysis.research.random_phase_validation import (
    _balanced_controls,
    extract_random_phase,
    random_phase_groups,
)
from leo.analysis.starlink.broadband_alignment import _group_phase_fit


def test_random_groups_preserve_whole_windows_and_guard_boundaries():
    for rate in (2_500_000, 10_000_000, 15_000_000):
        split = random_phase_groups(round(0.12 * rate), rate, seed=20260923)
        assert split == random_phase_groups(round(0.12 * rate), rate, seed=20260923)
        assert set(split["training_groups"]).isdisjoint(split["held_groups"])
        assert split["training_groups"] != [0, 1, 2]
        for block in split["blocks"]:
            start = block["index"] * split["block_samples"]
            left = block["group"] * split["group_samples"] + split["boundary_guard_samples"]
            right = (block["group"] + 1) * split["group_samples"] - split["boundary_guard_samples"]
            assert left <= start < start + split["block_samples"] <= right


def test_random_held_iq_cannot_change_carrier_or_normalized_response():
    rate = 200_000
    rng = np.random.default_rng(451)
    source = rng.normal(size=24_000) + 1j * rng.normal(size=24_000)
    phase = 0.8 + 2 * np.pi * 15_000 * np.arange(len(source)) / rate
    iq = np.column_stack((source, source * np.exp(1j * phase)))
    iq += 0.02 * (rng.normal(size=iq.shape) + 1j * rng.normal(size=iq.shape))
    result = extract_random_phase(iq, rate, receiver_cfo_seed_hz=15_000)
    assert result["supported"]
    assert result["tracked_coherence"] > 0.85
    assert result["relative_cfo_hz"] == pytest.approx(15_000, abs=2)
    changed = iq.copy()
    for group in result["split"]["held_groups"]:
        selection = slice(group * 4000, (group + 1) * 4000)
        changed[selection] = rng.normal(size=(4000, 2)) + 1j * rng.normal(size=(4000, 2))
    perturbed = extract_random_phase(changed, rate, receiver_cfo_seed_hz=15_000)
    assert not perturbed["supported"]
    for key in (
        "relative_cfo_hz",
        "relative_cfo_rate_hz_s",
        "normalized_transfer",
        "normalized_frequency_hz",
        "training_block_phase_rad",
    ):
        assert result[key] == perturbed[key]


def test_group_carrier_fit_does_not_need_phase_connection_across_gaps():
    times = np.concatenate([np.arange(8) * 0.001 + offset for offset in (0, 0.04, 0.08)])
    groups = np.repeat(np.arange(3), 8)
    omega, acceleration = 13.2, 192.0
    offsets = np.repeat([2.8, -2.4, 1.3], 8)
    z = np.exp(1j * (offsets + omega * times + 0.5 * acceleration * times**2))
    result = _group_phase_fit(times, z, groups, 2)
    assert result[0][1] == pytest.approx(omega, abs=1e-8)
    assert result[0][2] == pytest.approx(acceleration, abs=1e-8)
    z *= np.exp(1j * np.repeat([-2.5, 1.7, -0.3], 8))
    changed = _group_phase_fit(times, z, groups, 2)
    assert changed[0][1:] == pytest.approx(result[0][1:], abs=1e-8)


def test_group_carrier_fit_abstains_for_sparse_group():
    times = np.arange(6) * 0.01
    with pytest.raises(ValueError, match="at least three blocks"):
        _group_phase_fit(times, np.ones(6, dtype=complex), np.array([0, 0, 0, 0, 1, 2]), 2)


def test_group_carrier_fit_abstains_for_near_pi_increment():
    times = np.arange(9) * 0.001
    with pytest.raises(ValueError, match="ambiguous local phase"):
        _group_phase_fit(times, np.exp(0.95j * np.pi * np.arange(9)), np.repeat([0, 1, 2], 3), 1)


def test_wrong_pair_control_is_balanced_one_to_one_and_cross_group():
    held = [dict(index=i, group=i // 4) for i in range(11)]
    selected, controls = _balanced_controls(held)
    assert len(selected) == 9
    assert sorted(controls) == list(range(9))
    assert len({b["index"] for b in selected}) == 9
    for i, wrong in enumerate(controls):
        assert selected[i]["group"] != selected[wrong]["group"]
