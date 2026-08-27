from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.research.cross_family_injection_experiment import (
    CrossFamilyInjectionInputError,
    generate_cross_family_injected_evidence,
)
from leo.analysis.research.cross_family_injection_protocol import (
    CrossFamilyInjectionProtocol,
    CrossFamilyTruthPair,
    load_cross_family_injection_protocol,
)
from leo.analysis.research.cross_family_orbit_truth import VerifiedCrossFamilyTruthPair
from leo.analysis.research.doppler_dataset_policy import load_doppler_dataset_policy
from leo.analysis.research.trajectory_qin_injection import PiecewiseLinearCfoTrajectory

PROJECT_ROOT = Path(__file__).parents[2]


def _protocol() -> CrossFamilyInjectionProtocol:
    policy = load_doppler_dataset_policy(
        PROJECT_ROOT / "config/analysis/doppler-experiment-dataset-policy-v1.json"
    )
    protocol = load_cross_family_injection_protocol(
        PROJECT_ROOT / "config/analysis/satellite-pnt-cross-family-injection-protocol-v1.json",
        dataset_policy=policy,
        repository_root=PROJECT_ROOT,
    )
    background = replace(protocol.base_protocol.backgrounds[0], sample_count=30_000)
    base = replace(protocol.base_protocol, backgrounds=(background,), frame_count=9)
    pair = replace(
        protocol.pairs[0],
        background_session_id=background.session_id,
        sample_zero_utc_ns=1_000_000_000,
        span_start_utc_ns=9_000_000_000,
        span_centre_utc_ns=10_000_000_000,
    )
    return replace(
        protocol, base_protocol=base, pairs=(pair,), training_fraction=2 / 3, future_fraction=1 / 3
    )


def _truth(pair: CrossFamilyTruthPair) -> VerifiedCrossFamilyTruthPair:
    times = (-0.01, 0.0, 0.01, 0.02, 0.03)
    orbit = PiecewiseLinearCfoTrajectory(
        pair.orbit_scenario_id,
        times,
        (99_900.0, 100_000.0, 100_150.0, 100_350.0, 100_600.0),
    )
    radio = PiecewiseLinearCfoTrajectory(
        pair.radio_scenario_id,
        times,
        (99_900.0, 100_000.0, 100_100.0, 100_200.0, 100_300.0),
    )
    return VerifiedCrossFamilyTruthPair(
        pair_id=pair.pair_id,
        true_catalog_number=pair.true_catalog_number,
        true_object_name=pair.true_object_name,
        starlink_object_count=10,
        visible_starlink_count=3,
        selected_centre_elevation_deg=pair.centre_elevation_deg,
        orbit_trajectory=orbit,
        radio_trajectory=radio,
        orbit_interpolation_maximum_error_hz=1e-6,
        truth_digest="sha256:" + "1" * 64,
    )


def test_paired_arms_use_identical_occupancy_and_parity_isolated_rows() -> None:
    protocol = _protocol()
    pair = protocol.pairs[0]
    generator = np.random.default_rng(41)
    background = np.asarray(
        1e-3 * (generator.normal(size=30_000) + 1j * generator.normal(size=30_000)),
        dtype=np.complex64,
    )
    before = background.copy()

    result = generate_cross_family_injected_evidence(background, pair, _truth(pair), protocol)

    np.testing.assert_array_equal(background, before)
    assert result.occupancy_identical is True
    assert result.independent_unit_count == 1
    assert result.orbit.training_opportunity_count == 6
    assert result.orbit.future_opportunity_count == 3
    assert all(item.split == "training-even-qin" for item in result.orbit.observation_rows[:6])
    assert all(item.split == "future-odd-qin" for item in result.orbit.observation_rows[6:])
    assert result.orbit.future_response_used_for_training is False
    assert result.radio.future_response_used_for_training is False
    assert result.pair_evidence_digest.startswith("sha256:")


def test_no_result_opportunities_are_retained() -> None:
    protocol = _protocol()
    pair = protocol.pairs[0]
    background = np.full(30_000, 1e-3 + 1e-3j, dtype=np.complex64)

    result = generate_cross_family_injected_evidence(background, pair, _truth(pair), protocol)

    assert len(result.orbit.observation_rows) == 9
    assert result.orbit.observation_rows[0].usable is False
    assert result.orbit.observation_rows[0].status == "incomplete_guard"


def test_truth_pair_mismatch_and_wrong_span_fail_closed() -> None:
    protocol = _protocol()
    pair = protocol.pairs[0]

    with pytest.raises(CrossFamilyInjectionInputError, match="bind"):
        generate_cross_family_injected_evidence(
            np.ones(30_000, dtype=np.complex64),
            pair,
            replace(_truth(pair), pair_id="other"),
            protocol,
        )
    with pytest.raises(CrossFamilyInjectionInputError, match="frozen span"):
        generate_cross_family_injected_evidence(
            np.ones(29_999, dtype=np.complex64), pair, _truth(pair), protocol
        )


def test_nonfinite_background_is_rejected_before_injection() -> None:
    protocol = _protocol()
    pair = protocol.pairs[0]
    background = np.ones(30_000, dtype=np.complex64)
    background[10] = np.nan

    with pytest.raises(CrossFamilyInjectionInputError, match="non-finite"):
        generate_cross_family_injected_evidence(background, pair, _truth(pair), protocol)
