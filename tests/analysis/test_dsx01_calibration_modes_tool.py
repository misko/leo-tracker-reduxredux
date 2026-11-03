"""Calibration diversity, drift boxes and c-paired selection stay GPS-free."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest
from test_dsx01_rf_clock_tool import problem_inputs


@pytest.fixture
def tool():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        yield importlib.import_module("prototype_dsx01_calibration_modes")
    finally:
        sys.path.remove(path)


def candidate(beta, labels=(100, 100, 200), score=0, hypothesis=0):
    return dict(
        center_score=score,
        hypothesis=hypothesis,
        seed=dict(
            state=dict(beta=beta),
            rows=[dict(component=str(k), candidate_norad=n) for k, n in enumerate(labels)],
        ),
    )


def test_radio_projection_preserves_input_and_final_mean_contrast_box(tool):
    _, seed = problem_inputs()
    seed["state"]["beta"] = np.array([0.0, 1, 2, 3, 150 * 50, 150 * 10, 150 * -100, 150 * 0])
    saved = seed["state"]["beta"].copy()
    s = tool.project_radio_state(seed["state"])
    np.testing.assert_allclose(seed["state"]["beta"], saved)
    np.testing.assert_allclose(s["beta"][4:8] / 150, [31.5, 28.5, -31.5, -28.5])


def test_periodic_radio_equivalence_deduplicates_and_label_changes_preserve_diversity(tool):
    a = candidate(np.zeros(8))
    b = candidate(np.r_[np.ones(4) * tool.PERIOD, np.zeros(4)], score=1, hypothesis=1)
    assert not tool.distinct(a, b)
    c = candidate(np.zeros(8), (100, 300, 400), score=2, hypothesis=2)
    assert tool.distinct(a, c)
    chosen = tool.select_modes([c, b, a], 4)
    assert [r["hypothesis"] for r in chosen] == [0, 2]


def test_c0_selector_keeps_same_hypothesis_for_fitted_c(tool):
    choices = {
        "a": dict(c0=dict(score=10), fitted_c=dict(score=30)),
        "b": dict(c0=dict(score=11), fitted_c=dict(score=1)),
    }
    name, pair = tool.choose_pair(choices)
    assert name == "a" and pair["fitted_c"]["score"] == 30


def test_center_profile_holds_position_and_preserves_all_curved_members(tool):
    scan, seed = problem_inputs()
    fitted, detail = tool.center_profile(scan, seed, iterations=2)
    assert detail["fixed_position_km"] == [0, 0]
    assert {r["component"] for r in fitted["rows"]} == {r["component"] for r in seed["rows"]}
    assert len(fitted["state"]["beta"]) == 8
