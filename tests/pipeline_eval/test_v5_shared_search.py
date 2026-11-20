import sys
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification.shared_search_eval import no_endpoint, verify_search
from tools.pipeline_eval.scoring import ARMS, validate_result
from tools.pipeline_eval.variants import v5_shared_search as shared


@pytest.mark.parametrize("visible", [[False, False, False, False], [False, False, True, True]])
def test_visibility_preserves_fallback_and_first_visible_tie(visible):
    seen = []

    def profile(index, y, rows, method):
        assert rows.flags.f_contiguous and index == 9 and method == "receiver_smooth"
        seen.extend(rows[:, 0].tolist())
        return dict(
            cost=np.zeros(len(rows)),
            passing=np.ones(len(rows), dtype=bool),
            residual=np.copy(rows),
            diagnostics={},
        )

    predicted = np.asfortranarray(np.arange(12, dtype=float).reshape(4, 3))
    values = shared.visible_curve(
        profile, 9, np.zeros(3), predicted, "receiver_smooth", visible=np.array(visible)
    )
    eligible = np.asarray(visible) & values["passing"]
    chosen = np.argmin(np.where(eligible, values["cost"], np.inf))
    assert chosen == (2 if any(visible) else 0)
    assert seen == ([0, 6, 9] if any(visible) else [0])
    np.testing.assert_array_equal(values["residual"][chosen], predicted[chosen])
    with pytest.raises(ValueError, match="excluded candidate"):
        values["residual"][1]


def test_center_and_exact_duplicate_work_is_shared_only_inside_explore(monkeypatch):
    physical = dict(project=0, associate=0, curves=[])
    geometry = object()

    class Scan:
        index = [np.array([0, 1])]
        search_region = SimpleNamespace(center=(0.0, 1.0))

        def predictions(self, state, base, point, method):
            return base

        def curve(self, index, y, predicted, method):
            physical["curves"].append(len(predicted))
            return dict(cost=np.zeros(len(predicted)), passing=np.ones(len(predicted), dtype=bool))

        def association(self, state, base, point, method, *, all_tracks=False):
            physical["associate"] += 1
            f, e, h = self.predictions(state, base, point, method)
            return self.curve(0, np.zeros(2), f, method)

    def project(bank, latitude, longitude):
        physical["project"] += 1
        return np.ones((4, 2)), np.array([[1, 1], [-1, 1], [1, 1], [-1, -1]]), np.zeros((4, 2))

    def explore(scan):
        a = discovery.phase_linear_frequency(geometry, 0.0, 1.0)
        b = discovery.phase_linear_frequency(geometry, 0.0, 1.0)
        assert a is b
        state = {"extra": {}}
        first = scan.association(state, a, (0, 0), "receiver_smooth")
        second = scan.association(state, b, (0, 0), "receiver_smooth")
        assert first is second

    parent = SimpleNamespace()
    discovery = SimpleNamespace(phase_linear_frequency=project, explore=explore)
    parent.discovery = discovery
    monkeypatch.setitem(sys.modules, "leo.analysis.localization_v3", parent)
    scan = Scan()
    scan.geometry = geometry
    with shared.shared_associations(scan) as counts:
        discovery.explore(scan)
        base = discovery.phase_linear_frequency(geometry, 2.0, 3.0)
        result = scan.association({"extra": {}}, base, (0, 0), "receiver_smooth", all_tracks=True)
    assert counts == {"association_reused": 1, "center_projections_reused": 1}
    assert physical == {"project": 2, "associate": 2, "curves": [2, 4]}
    assert result["passing"].all()
    assert discovery.explore is explore and discovery.phase_linear_frequency is project


def test_search_equivalence_rejects_a_changed_intermediate_decision():
    stock = dict(
        association_calls=4,
        association_outcomes=["a", "a", "b", "b"],
        initial_signature={"branches": 3},
    )
    candidate = dict(
        association_calls=2,
        association_reused=2,
        association_outcomes=["a", "b"],
        initial_signature={"branches": 3},
    )
    verify_search(stock, candidate)
    candidate["association_outcomes"][-1] = "c"
    with pytest.raises(ValueError, match="discovery associations"):
        verify_search(stock, candidate)


def test_timeout_retains_both_attempted_arms_and_the_stock_input_binding():
    stock = dict(id="DS26-0122", cpu=20, input_sha256="bound", result={"boundary": "numerical"})
    candidate = no_endpoint(
        stock, "timed_out", "deadline", "original_schedule", position_attempted=True
    )
    validate_result(candidate["result"])
    assert candidate["input_sha256"] == stock["input_sha256"]
    assert candidate["result"]["arms"] == {arm: {"latlon": None} for arm in ARMS}
