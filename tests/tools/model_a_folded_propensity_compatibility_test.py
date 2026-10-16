"""A's final folded density can use the existing B observation port, not native C."""

import importlib.util
from copy import copy
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.channel_group_calibration import GroupCalibrationObjective
from leo.analysis.hard60_joint_clock import JointClockObjective
from leo.analysis.research import model_b_observation_cv as port

_spec = importlib.util.spec_from_file_location(
    "model_a_propensity_fixture", Path(__file__).with_name("model_a_replacement_path_audit_test.py")
)
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)
actual_case = _fixture.actual_case


@pytest.fixture
def family(actual_case, monkeypatch):
    _, model, shift = _fixture.models(actual_case, monkeypatch)
    vector = np.zeros(model.size)
    vector[2:8] = [-80000, 2, -54000, 1.5, -600, 0.051234]
    nuisance = np.zeros_like(model.initial_nuisance)
    assert type(model.base) is JointClockObjective and model.group_count == 0
    assert model.score.sigma_hz == 125
    return model, vector, nuisance, shift


def test_full_folded_legacy_reproduces_final_a_without_changing_locked_contrast(family):
    original, v, n, shift = family
    oracle = original.evaluate_joint(v, n)
    wrapper = port.ObservationModel(
        original, np.ones(len(original.observations.times_s), bool), "legacy"
    )
    result, _ = wrapper.evaluate_details(v, n)
    for i in range(3):
        np.testing.assert_allclose(result[i], oracle[i], atol=1e-9, rtol=0)
    np.testing.assert_allclose(
        result[3].responsibilities, oracle[3].responsibilities, atol=1e-14, rtol=0
    )
    assert result[3].nll == pytest.approx(oracle[3].nll, abs=1e-9)
    np.testing.assert_array_equal(wrapper.original.baseline, original.baseline)
    assert wrapper.original.group_count == 0 and wrapper.observation_parameter_count == 0
    assert len(shift.offsets_hz) == 2  # Fixed in baseline; no free group column invented.


def test_uniform_q_nests_conditional_folded_model_and_counts_budget(family):
    original, v, n, _ = family
    mask = np.ones(len(original.observations.times_s), bool)
    conditional = port.ObservationModel(original, mask, "conditional")
    learned = port.ObservationModel(original, mask, "detectability")
    a, details = conditional.evaluate_details(v, n)
    b, expanded = learned.evaluate_details(
        v, np.r_[n, np.zeros(learned.observation_parameter_count)]
    )
    for i in range(2):
        np.testing.assert_allclose(a[i], b[i], atol=1e-10, rtol=0)
    np.testing.assert_allclose(a[2], b[2][: len(n)], atol=1e-10, rtol=0)
    np.testing.assert_array_equal(a[3].responsibilities, b[3].responsibilities)
    assert expanded["detection_probability"].sum() == pytest.approx(original.score.detection_budget)
    assert learned.observation_parameter_count == len(original.bank.numbers) - 1
    legacy = port.ObservationModel(original, mask, "legacy").evaluate_joint(v, n)
    assert a[0] - legacy[0] == pytest.approx(details["log_integrated_event_mass"].sum(), abs=1e-9)


def test_excluded_measured_values_cannot_affect_folded_q_fit(family):
    original, v, n, _ = family
    mask = np.arange(len(original.observations.times_s)) % 2 == 0
    altered_base = copy(original.base)
    values = original.observations.measured_hz.copy()
    values[~mask] += 54321
    altered_base.observations = replace(original.observations, measured_hz=values)
    altered = GroupCalibrationObjective(
        altered_base, original.observations.channel >= 5, enabled=False
    )
    first, second = [port.ObservationModel(m, mask, "detectability") for m in (original, altered)]
    tail = np.r_[n, 0.1 * np.cos(np.arange(first.observation_parameter_count))]
    a, b = first.evaluate_joint(v, tail), second.evaluate_joint(v, tail)
    for i in range(3):
        np.testing.assert_array_equal(a[i], b[i])


def test_original_fitter_separates_q_tail_from_absent_a_group_and_common_clock(family):
    original, v, n, _ = family
    model = port.ObservationModel(
        original, np.ones(len(original.observations.times_s), bool), "detectability"
    )
    fit = port.fit(
        model,
        v,
        np.r_[n, np.zeros(model.observation_parameter_count)],
        arm="fitted-c",
        seconds=2,
        iterations=5,
        fixed_position=True,
        local_center=v[:2],
        local_radius_km=50,
    )
    np.testing.assert_array_equal(fit["vector"][:2], v[:2])
    assert len(fit["clock_coefficients"]) == original.clock_count
    assert len(fit["group_offsets_hz"]) == 0 and len(fit["group_clock_coefficients"]) == 0
    assert fit["group_prior_penalty"] == 0
    assert len(fit["observation_parameters"]) == len(original.bank.numbers) - 1
