import numpy as np

from tools.pipeline_eval.qualification.external_clock_trial import other_sites
from tools.pipeline_eval.variants import external_clock_information as model


def test_finite_clock_prior_matches_schur_complement():
    rng = np.random.default_rng(71)
    arcs = np.repeat(np.arange(3), 10)
    clock = rng.normal(0, 600, len(arcs))
    x = np.column_stack((clock / 15 + rng.normal(0, 4, len(arcs)), rng.normal(0, 12, len(arcs))))
    c = model.carrier_design(arcs, np.arange(len(arcs), dtype=float))
    p = model.project_off(x, c)
    t = model.project_off(clock, c)
    scale, seconds = 73.0, 0.5
    mixed = p.T @ t
    expected = p.T @ p - np.outer(mixed, mixed) / (t @ t + (scale / seconds) ** 2)
    singular = model.singular_for(x, c, clock, scale, seconds)
    np.testing.assert_allclose(singular**2, np.linalg.eigvalsh(expected)[::-1], rtol=1e-10)


def test_absolute_clock_is_gauge_with_independent_orbit_phase():
    rng = np.random.default_rng(72)
    arcs = np.repeat(np.arange(3), 8)
    clock = rng.normal(0, 400, len(arcs))
    x = rng.normal(0, 10, (len(arcs), 2)) + clock[:, None] * np.array([0.02, 0.03])
    c = model.carrier_design(arcs, np.arange(len(arcs), dtype=float))
    result = model.information(x, clock, c, arcs, 80)
    ordered = [
        result[k]["worst_sd_km"]
        for k in ("fixed-utc", "50ms-utc", "500ms-utc", "free-common-utc", "free-orbit-epochs")
    ]
    assert ordered == sorted(ordered)
    assert result["free-orbit-epochs"]["absolute_utc_gauge_relative_residual"] < 1e-13


def test_known_clock_and_carrier_calibration_generalize_across_held_epochs():
    times = np.r_[np.arange(8) * 10.0, np.arange(8) * 15.0 + 400]
    arc = np.repeat(np.arange(2), 8)
    early = np.tile([True, True, True, True, False, False, False, False], 2)
    design = model.carrier_design(arc, times)
    baseline = 2500 * np.sin(times / 180)
    clock = 600 * np.sin(times / 30)
    values = baseline + clock * -0.65 + design @ np.array([16000, -13500, 180])
    estimated = model.identified_shift(values[early] - baseline[early], design[early], clock[early])
    np.testing.assert_allclose(estimated, -0.65, atol=1e-12)
    late = model.held_residual(values, baseline + estimated * clock, design, early)
    np.testing.assert_allclose(late, 0, atol=1e-8)
    altered = values.copy()
    altered[~early] += 600
    remained = model.held_residual(altered, baseline + estimated * clock, design, early)
    np.testing.assert_allclose(remained, 600, atol=1e-8)


def test_single_rf_level_and_offset_drift_are_fully_profiled():
    times = np.r_[np.arange(8) * 10.0, np.arange(8) * 15.0 + 400]
    arc = np.repeat(np.arange(2), 8)
    early = np.tile([True, True, True, True, False, False, False, False], 2)
    design = model.carrier_design(arc, times)
    values = np.sin(times / 50) * 1700
    forecast = np.cos(times / 25) * 1300
    residual = model.held_residual(values, forecast, design, early)
    adjusted = values + 1500.0 + design @ np.array([10000, -3000, 80])
    other = model.held_residual(adjusted, forecast, design, early)
    np.testing.assert_allclose(residual, other, atol=1e-8)


def test_donor_selection_excludes_every_recording_at_the_held_site():
    roster = [
        dict(capture="first-a", site="a", cohort="primary"),
        dict(capture="second-a", site="a", cohort="repeat"),
        dict(capture="first-b", site="b", cohort="primary"),
        dict(capture="second-b", site="b", cohort="repeat"),
        dict(capture="first-c", site="c", cohort="primary"),
    ]
    estimates = {row["capture"]: i for i, row in enumerate(roster)}
    assert other_sites(roster[1], estimates, roster) == [2, 4]
