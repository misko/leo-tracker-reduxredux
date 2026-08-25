from __future__ import annotations

import math

import pytest

from leo.analysis.research.satellite_activity_scores import (
    BinaryPilotScoreCalibration,
    ConservativeRankMarkCalibration,
    ConservativeRankMarkedPilotScoreCalibration,
    NullRankBucketCalibration,
    PilotScoreEvidence,
    RankAwarePilotScoreCalibration,
    group_pilot_score_evidence,
    poisson_count_upper_mean,
    wilson_probability_lower,
)


def _calibration() -> BinaryPilotScoreCalibration:
    return BinaryPilotScoreCalibration(
        score_threshold=0.1,
        null_positive_count=81,
        null_total_count=96_000,
        signal_positive_count=1_626,
        signal_total_count=1_627,
        detection_probability=0.75,
        pseudocount=1.0,
    )


def test_smoothed_costs_match_the_declared_bernoulli_model() -> None:
    calibration = _calibration()

    null_positive = 82.0 / 96_002.0
    signal_positive = 1_627.0 / 1_629.0
    assert calibration.null_positive_probability == pytest.approx(null_positive)
    assert calibration.signal_positive_probability == pytest.approx(signal_positive)
    assert calibration.clutter_cost(0.1) == pytest.approx(-math.log(null_positive))
    assert calibration.clutter_cost(0.099) == pytest.approx(-math.log1p(-null_positive))
    assert calibration.matched_base_cost(0.1) == pytest.approx(
        -math.log(0.75) - math.log(signal_positive)
    )
    assert calibration.missed_detection_cost == pytest.approx(-math.log(0.25))


def test_calibrated_weak_candidates_are_provably_dominated_by_a_miss() -> None:
    calibration = _calibration()

    assert calibration.match_delta_before_residual(0.0) > calibration.missed_detection_cost
    assert calibration.weak_match_is_dominated_by_miss()
    assert calibration.match_delta_before_residual(0.2) < 0.0


def test_resolution_grouping_is_probe_local_transitive_and_deterministic() -> None:
    evidence = (
        PilotScoreEvidence("a", "p0", 0, 10, 100.0, 0.2),
        PilotScoreEvidence("b", "p0", 1, 11, 500.0, 0.3),
        PilotScoreEvidence("c", "p0", 2, 12, 900.0, 0.1),
        PilotScoreEvidence("d", "p0", 3, 20, 100.0, 0.9),
        PilotScoreEvidence("e", "p1", 0, 10, 100.0, 0.8),
        PilotScoreEvidence("f", "p2", 0, 10, 0.0, 0.4, 123.0),
        PilotScoreEvidence("g", "p2", 1, 10, 2_000.0, 0.5, 123.0),
    )

    grouped = group_pilot_score_evidence(
        tuple(reversed(evidence)),
        epoch_tolerance_samples=1,
        tracking_cfo_tolerance_hz=500.0,
        acquired_cfo_tolerance_hz=0.0,
    )

    assert grouped == group_pilot_score_evidence(
        evidence,
        epoch_tolerance_samples=1,
        tracking_cfo_tolerance_hz=500.0,
        acquired_cfo_tolerance_hz=0.0,
    )
    observed = [
        (item.member_evidence_ids, item.minimum_rank, item.maximum_score) for item in grouped
    ]
    assert observed == [
        (("a", "b", "c"), 0, 0.3),
        (("d",), 3, 0.9),
        (("e",), 0, 0.8),
        (("f", "g"), 0, 0.5),
    ]


def test_rank_aware_null_costs_match_resolution_group_buckets() -> None:
    calibration = RankAwarePilotScoreCalibration(
        score_threshold=0.1,
        null_rank_buckets=(
            NullRankBucketCalibration("rank0", 0, 0, 8, 1000),
            NullRankBucketCalibration("rank1", 1, 1, 1, 900),
            NullRankBucketCalibration("rank2plus", 2, None, 0, 7000),
        ),
        signal_positive_count=99,
        signal_total_count=100,
        detection_probability=0.75,
        pseudocount=1.0,
    )

    assert calibration.clutter_cost(0.2, 0) == pytest.approx(-math.log(9 / 1002))
    assert calibration.clutter_cost(0.2, 1) == pytest.approx(-math.log(2 / 902))
    assert calibration.clutter_cost(0.2, 5) == pytest.approx(-math.log(1 / 7002))
    assert calibration.matched_base_cost(0.2, 5) == pytest.approx(
        -math.log(0.75) - math.log(100 / 102)
    )
    assert calibration.weak_match_is_dominated_by_miss()


def test_exact_poisson_upper_mean_and_wilson_lower_bound() -> None:
    tail_probability = 0.01
    assert poisson_count_upper_mean(0, tail_probability) == pytest.approx(
        -math.log(tail_probability)
    )
    upper_mean = poisson_count_upper_mean(3, tail_probability)
    poisson_cdf = math.exp(-upper_mean) * sum(
        upper_mean**index / math.factorial(index) for index in range(4)
    )
    assert poisson_cdf == pytest.approx(tail_probability)

    lower = wilson_probability_lower(60, 100, tail_probability)
    assert 0.0 < lower < 0.6
    assert wilson_probability_lower(0, 100, tail_probability) == 0.0


def test_conservative_marked_point_process_costs_match_declared_bounds() -> None:
    calibration = ConservativeRankMarkedPilotScoreCalibration(
        score_threshold=0.1,
        rank_marks=(
            ConservativeRankMarkCalibration("rank0", 0, 0, 0.01, 0.5),
            ConservativeRankMarkCalibration("rank1plus", 1, None, 0.02, 0.25),
        ),
        detection_probability=0.75,
    )

    assert calibration.clutter_cost(0.2, 0) == pytest.approx(-math.log(0.01))
    assert calibration.matched_base_cost(0.2, 0) == pytest.approx(-math.log(0.75 * 0.5))
    assert calibration.match_delta_before_residual(0.2, 2) == pytest.approx(
        -math.log(0.75 * 0.25) + math.log(0.02)
    )
    assert calibration.clutter_cost(0.0, 2) == 0.0
    assert calibration.matched_base_cost(0.0, 2) == pytest.approx(calibration.missed_detection_cost)
    assert calibration.weak_match_is_dominated_by_miss()


def test_conservative_signal_mark_lower_masses_cannot_exceed_one() -> None:
    with pytest.raises(ValueError, match="masses must not exceed one"):
        ConservativeRankMarkedPilotScoreCalibration(
            score_threshold=0.1,
            rank_marks=(
                ConservativeRankMarkCalibration("rank0", 0, 0, 0.01, 0.6),
                ConservativeRankMarkCalibration("rank1plus", 1, None, 0.02, 0.5),
            ),
            detection_probability=0.75,
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"null_total_count": 0}, "positive integer"),
        ({"signal_positive_count": 2_000}, r"in \[0, total\]"),
        ({"detection_probability": 1.0}, r"lie in \(0, 1\)"),
        ({"pseudocount": 0.0}, "must be positive"),
    ],
)
def test_invalid_calibration_is_rejected(changes: dict[str, object], message: str) -> None:
    values: dict[str, object] = {
        "score_threshold": 0.1,
        "null_positive_count": 1,
        "null_total_count": 10,
        "signal_positive_count": 9,
        "signal_total_count": 10,
        "detection_probability": 0.75,
        "pseudocount": 1.0,
    }
    values.update(changes)

    with pytest.raises(ValueError, match=message):
        BinaryPilotScoreCalibration(**values)  # type: ignore[arg-type]
