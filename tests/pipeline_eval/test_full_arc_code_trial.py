from dataclasses import replace
from importlib import import_module

import numpy as np
import pytest

study = import_module("reports.ALGO08.single-core-2x.full_arc_code_trial")
RATE = 10_000_000


def sample_arcs(drift):
    times = np.arange(19) * 2.
    observed = [21_000. + 143. * times + .51 * times**2,
                35_000. - 110. * times + .28 * times**2]
    phases = [6200., -6550.]
    arcs = [
        study.code.Arc(owner, 11e9, "test", times,
                       study.code.wrap(ranges + phase + drift * times, RATE / 750.),
                       np.zeros_like(times), times < 24.)
        for owner, (ranges, phase) in enumerate(zip(observed, phases, strict=True), 1)
    ]
    return arcs, observed


def test_circular_profile_fits_two_transmitter_phases_and_one_clock():
    arcs, delays = sample_arcs(1.75)
    residual, drift = study.bounded_residual(arcs, delays, RATE)
    assert drift == pytest.approx(1.75, abs=1e-3)
    assert study.held(arcs, residual)["held_rms_samples"] < .03
    reflected, _ = study.bounded_residual(arcs, [-d for d in delays], RATE)
    assert study.held(arcs, reflected)["held_rms_samples"] > 10.


def test_held_samples_cannot_change_training_drift_or_prediction():
    arcs, delays = sample_arcs(-1.25)
    expected, before = study.bounded_residual(arcs, delays, RATE)
    changed = [replace(arc, phase=arc.phase + 35. * ~arc.train) for arc in arcs]
    residual, after = study.bounded_residual(changed, delays, RATE)
    assert before == after
    for arc, a, b in zip(arcs, expected, residual, strict=True):
        np.testing.assert_array_equal(a[arc.train], b[arc.train])
        np.testing.assert_allclose(b[~arc.train] - a[~arc.train], 35.)


def test_common_rate_cannot_absorb_an_unphysical_clock():
    arcs, delays = sample_arcs(6.)
    _, drift = study.bounded_residual(arcs, delays, RATE)
    assert drift == pytest.approx(3.5, abs=1e-10)


def test_score_rejects_predictions_changed_before_label_reveal(tmp_path):
    prediction = tmp_path / "changed.json"
    prediction.write_text("{}")
    with pytest.raises(ValueError, match="changed before label reveal"):
        study.reveal(prediction, "0" * 64)
