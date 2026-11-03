"""Position-level integration tests for association arms."""

from __future__ import annotations

import importlib.util
import sys
from math import isclose, log
from pathlib import Path

import numpy as np
import pytest

MODULE_PATH = Path(__file__).with_name("association_runner.py")
SPEC = importlib.util.spec_from_file_location("sacramento_association_runner", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def group(group_id: str, signal, background=(0.0,)):
    return runner.CompetitionGroup(
        group_id,
        tuple(f"obs-{group_id}-{i}" for i in range(len(signal))),
        tuple(f"sat-{i}" for i in range(len(signal[0]))),
        np.asarray(signal, dtype=float),
        np.asarray(background, dtype=float),
        "response-independent-same-rx-overlap-v1",
    )


def position(name: str, east: float, groups):
    return runner.PositionAssociationInput(name, east, 0.0, log(0.5), tuple(groups))


@pytest.mark.parametrize("arm", ["M1", "G2"])
def test_exact_arms_choose_position_using_group_evidence(arm) -> None:
    weak = position("west", -1.0, [group("a", [[0.0]], [0.0])])
    strong = position("east", 1.0, [group("a", [[log(9.0)]], [0.0])])
    result = runner.evaluate_position_hypotheses((weak, strong), arm=arm)
    assert result.point_estimate_east_km == 1.0
    assert result.retained_probability == pytest.approx(1.0)
    assert result.discarded_probability == pytest.approx(0.0)
    # Evidence weights: west=(1+1)/2, east=(9+1)/2.
    assert result.position_hypotheses[0].posterior_probability == pytest.approx(5 / 6)


def test_candidates_can_repeat_across_independent_groups() -> None:
    item = position(
        "center",
        0.0,
        [group("early", [[10.0]]), group("late", [[10.0]])],
    )
    result = runner.evaluate_position_hypotheses((item,), arm="M1")
    assert result.position_hypotheses[0].group_assignments == (("sat-0",), ("sat-0",))
    assert "finite position set" in result.warnings[0]


def test_singleton_groups_make_full_candidate_marginal_feasible() -> None:
    singleton = runner.CompetitionGroup(
        "track-1",
        ("track-1",),
        tuple(f"sat-{i}" for i in range(1000)),
        np.zeros((1, 1000)),
        np.zeros(1),
        "response-independent-singleton-v1",
    )
    result = runner.score_position_associations((singleton,), "M1", max_events_per_group=1001)
    assert result.log_score == pytest.approx(log(1001))
    assert result.exact_probability_semantics


def test_retained_geographic_mass_is_certified_over_finite_set() -> None:
    positions = tuple(
        position(str(index), float(index), [group("a", [[0.0]])]) for index in range(4)
    )
    result = runner.evaluate_position_hypotheses(positions, arm="M1", retained_positions=1)
    assert isclose(result.retained_probability, 0.25)
    assert isclose(result.discarded_probability, 0.75)
    assert "finite position set" in result.warnings[0]


def test_group_requires_response_independent_attestation() -> None:
    with pytest.raises(Exception, match="attestation"):
        runner.CompetitionGroup(
            "bad", ("obs",), ("sat",), np.zeros((1, 1)), np.zeros(1), "score-picked"
        )
