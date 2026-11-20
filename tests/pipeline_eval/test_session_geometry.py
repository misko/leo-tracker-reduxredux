from dataclasses import replace

import numpy as np
import pytest

from leo.sky.frames import geodetic_to_ecef_km
from tools.pipeline_eval.qualification import session_geometry_cross_orbit as mismatch
from tools.pipeline_eval.qualification import session_geometry_nominal_check as nominal
from tools.pipeline_eval.qualification import session_geometry_results as results
from tools.pipeline_eval.qualification import session_geometry_simulation as simulation
from tools.pipeline_eval.qualification import session_geometry_trial as trial
from tools.pipeline_eval.scoring import distance_km
from tools.pipeline_eval.variants import session_geometry as model


def test_all_offers_are_disjoint_and_all_near_bearings_omit_receiver():
    offers = {name: model.offer(simulation.ORIGIN, name) for name in model.REGIONS_KM}
    signed = results.signed_margins(simulation.truth(), offers)
    assert signed["containing"] > 0
    assert all(-10 < v < 0 for name, v in signed.items() if name.startswith("near-"))
    assert all(v < -30 for name, v in signed.items() if name.startswith("far-"))
    with pytest.raises(ValueError, match="touch or overlap"):
        results.signed_margins(simulation.truth(), dict(offers, duplicate=offers["near-east"]))


def test_affine_invariant_held_metric_and_single_rf_training_gauge():
    arc = simulation.generate()[0].arcs[0]
    site = geodetic_to_ecef_km(*simulation.ORIGIN, model.HEIGHT_M)[None, :]
    predicted = model.doppler(site, model.orbit(arc))
    original = model.costs(predicted, arc.frequency_hz, arc.times_s)
    adjusted = model.costs(predicted, arc.frequency_hz + 98913.5, arc.times_s)
    for method in model.MODES:
        np.testing.assert_allclose(original[method], adjusted[method], rtol=1e-12)
    residual = arc.frequency_hz - predicted[model.PHASES_S.index(0), 0]
    np.testing.assert_allclose(
        model.curvature(residual, arc.times_s),
        model.curvature(residual + 57000 - 129.3 * arc.times_s, arc.times_s),
        atol=1e-10,
    )


def test_nominal_whole_visit_position_recovers_and_held_rows_cannot_move_it():
    truth = [*model.geographic(simulation.ORIGIN, (3.83, -4.67)), model.HEIGHT_M]
    genuine = nominal.nominal_observations(truth)
    captures = [genuine[i] for i in (0, 1, 2, 5, 6, 7)]
    origin = simulation.ORIGIN
    offers = dict(containing=model.offer(origin, "containing"))

    def predict(items):
        hashes = {capture.id: trial.observation_hash(capture) for capture in items}
        rows, _, _ = trial.evaluate("simulation", items, offers, origin, hashes)
        return {row["recording"]: row for row in rows if row["method"] == "phase-clock"}

    good = predict(captures)
    for row in good.values():
        assert distance_km(row["result"]["arms"]["c0"]["forced_latlon"], truth[:2]) < 1
        assert row["result"]["arms"]["fitted_c"]["status"] == "unavailable"
    damaged = replace(
        captures[0],
        arcs=tuple(
            replace(a, frequency_hz=a.frequency_hz + 10000 * np.sin(a.times_s / 7.5))
            for a in captures[0].arcs
        ),
    )
    changed = predict([damaged, *captures[1:]])["1"]
    baseline = good["1"]
    assert changed["train_captures"] == baseline["train_captures"]
    assert changed["train_objective_rms_hz"] == baseline["train_objective_rms_hz"]
    assert changed["result"] == baseline["result"]
    assert changed["held_frequency"][0]["whole_curvature_rms_hz"] > 2e3
    assert changed["held_frequency"][0]["capture"] not in changed["train_captures"]


def test_profiled_clock_uses_prefix_before_forecasting_tail():
    times = np.linspace(0.0, 40.0, 101)
    prefix = 40
    dark = np.zeros_like(times)
    dark[prefix:] = 1735
    residual = 7700 - 17 * times + dark
    np.testing.assert_allclose(model.clock(residual, times, True, prefix), dark, atol=1e-10)


def test_wrong_pass_changes_orbit_and_preserves_time_and_frequency():
    capture, donor = simulation.generate()[:2]
    correct, wrong = mismatch.paired_tracks(capture, donor)
    for matched, mismatched in zip(correct.arcs, wrong.arcs, strict=True):
        np.testing.assert_array_equal(matched.times_s, mismatched.times_s)
        np.testing.assert_array_equal(matched.frequency_hz, mismatched.frequency_hz)
        assert np.ptp(matched.times_s) <= 2 * mismatch.HALF_WINDOW_S
        assert np.linalg.norm(matched.position_km[0] - mismatched.position_km[0]) > 1
