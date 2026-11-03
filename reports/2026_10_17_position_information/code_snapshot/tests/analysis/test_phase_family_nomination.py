"""Linear marks and previously admitted families cannot calibrate a new phase."""

import numpy as np
import pytest

from leo.analysis.research.phase_family_nomination import nominate_clipped_families


def row(key, *, curved=True, accepted=False, norad=100):
    return dict(
        component=key,
        active_curvature=curved,
        compatible=accepted,
        candidate_norad=norad,
        points=30,
    )


def call(rows, other=(), phases=(-3, 0)):
    return nominate_clipped_families(
        rows, list(other), np.array([100, 200]), np.array(phases), np.array([3, 3])
    )


def test_two_curved_arcs_nominate_but_lines_never_enter_calibration():
    result = call([row("a"), row("b"), row("linear", curved=False)])
    assert result == [
        dict(norad=100, members=["a", "b"], points=60, previous_phase_s=-3.0, bound_s=3.0)
    ]
    assert call([row("a"), row("linear", curved=False)]) == []


def test_old_curved_support_in_either_arm_locks_the_established_phase():
    rows = [row("a"), row("b")]
    assert call(rows, [row("prior", curved=True, accepted=True)]) == []


def test_old_linear_matches_cannot_indirectly_lock_or_exclude_a_curved_calibration():
    result = call([row("a"), row("b")], [row("linear", curved=False, accepted=True)])
    assert len(result) == 1
    assert result[0]["members"] == ["a", "b"]


def test_fragment_admitted_as_another_satellite_in_other_arm_is_not_recruited():
    assert call([row("a"), row("b")], [row("a", accepted=True, norad=200)]) == []


def test_unclipped_phase_is_not_a_bound_failure_nomination():
    assert call([row("a"), row("b")], phases=(-1, 0)) == []


def test_duplicate_fragment_is_not_independent_support():
    with pytest.raises(ValueError, match="duplicate"):
        call([row("a"), row("a")])
