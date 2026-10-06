"""Component tests for frozen absolute-timing association semantics."""

import pytest

from leo.analysis.t1_at import associate, select_timing_modes, top_candidates
from leo.contracts.t1_at import T1AtCandidateV1, T1AtInputV1, T1AtModeV1

DIGEST = "sha256:" + "a" * 64


def candidates(count):
    return tuple(
        T1AtCandidateV1(
            candidate_id=i,
            window_id=f"w{i}",
            receiver_id=0,
            channel=1,
            receive_time_s=i * 0.3,
            refined_cfo_hz=0,
            refined_margin=0.3,
        )
        for i in range(count)
    )


def mode(number, rows, timing=0.0, error=10.0):
    return T1AtModeV1(
        catalog_number=number,
        absolute_timing_s=timing,
        candidate_ids=tuple(rows),
        residual_hz=(error,) * len(rows),
    )


def source(points, modes):
    return T1AtInputV1(
        session_id="scan-test",
        input_manifest_sha256=DIGEST,
        analysis_manifest_sha256=DIGEST,
        refinement_sha256=DIGEST,
        calibration_sha256=DIGEST,
        orbit_bank_sha256=DIGEST,
        candidates=points,
        fitted_c_modes=modes,
        zero_c_modes=modes,
    )


def test_top_is_refined_margin_not_orbit_distance():
    original = candidates(1)[0]
    alternative = original.model_copy(update=dict(candidate_id=2, refined_margin=0.4))
    tied = alternative.model_copy(update=dict(candidate_id=3))
    assert top_candidates((original, tied, alternative)) == (alternative,)


def test_greedy_many_in_replacement_improves_count_minus_penalty():
    data = source(
        candidates(42),
        (
            mode(100, list(range(30))),
            mode(101, list(range(15)) + list(range(30, 36))),
            mode(102, list(range(15, 30)) + list(range(36, 42))),
        ),
    )
    result = associate(data)
    for arm in result["arms"].values():
        assert arm["initial"]["assigned"] == 30
        assert arm["initial"]["objective"] == 20
        assert arm["final"]["assigned"] == 42
        assert arm["final"]["objective"] == 22
        assert len(arm["final"]["satellites"]) == 2
        assert sum(p["accepted"] for p in arm["passes"]) == 1
        assert arm["termination"] == "no_improving_greedy_repair"


def test_short_fragments_not_counted_and_zero_gain_not_added():
    data = source(candidates(20), (mode(100, list(range(10))),))
    assert associate(data)["arms"]["fitted-c"]["final"]["assigned"] == 0


def test_timing_is_absolute_and_shared_pool_required():
    with pytest.raises(ValueError, match="less than or equal"):
        mode(100, [0], timing=20.01)
    data = source(candidates(1), (mode(100, [0]),))
    with pytest.raises(ValueError, match="identical satellite/timing"):
        T1AtInputV1.model_validate(
            {**data.model_dump(), "zero_c_modes": [mode(100, [0], timing=0.5).model_dump()]}
        )


def test_no_duplicate_candidate_or_cross_receiver_window():
    one = candidates(1)[0]
    with pytest.raises(ValueError, match="duplicate candidate"):
        source((one, one), ())
    with pytest.raises(ValueError, match="crosses receiver"):
        source((one, one.model_copy(update=dict(candidate_id=2, receiver_id=1))), ())


def test_no_modes_and_empty_input_have_truthful_denominators():
    for points in ((), candidates(3)):
        result = associate(source(points, ()))["arms"]["fitted-c"]["final"]
        assert result["assigned"] == 0
        assert result["unassigned"] == len(points)


def test_invalid_budget():
    with pytest.raises(ValueError, match="budget"):
        associate(source((), ()), maximum_seconds=float("nan"))


def test_regional_selection_port_preserves_historical_greedy_semantics():
    points = candidates(42)
    modes = (
        mode(100, list(range(30))),
        mode(101, list(range(15)) + list(range(30, 36))),
        mode(102, list(range(15, 30)) + list(range(36, 42))),
    )
    result = select_timing_modes(points, modes)
    assert result == associate(source(points, modes))["arms"]["fitted-c"]
    with pytest.raises(ValueError, match="one candidate"):
        select_timing_modes(points + points, modes)
