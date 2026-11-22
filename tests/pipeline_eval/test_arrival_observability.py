from importlib import import_module

import numpy as np


study = import_module("reports.ALGO08.single-core-2x.arrival_observability_trial")


def test_phase_closure_uses_short_disjoint_held_intervals():
    times = np.r_[np.arange(0, 12), 14, np.arange(20, 26)]
    train, held = study.partition(times)
    assert train.any() and held.any()
    assert not train[11] and not held[11]
    assert not train[12] and not held[12]
    assert times[1:][train].max() < times[:-1][held].min()


def test_positive_counter_phase_closure_with_wrap_and_unknown_linear_rate():
    t = np.arange(15.)
    rate, rf = 10e6, 11.5e9
    f = 3000 * t**2
    expected = study.carrier_samples(f, np.diff(t), rf, rate)
    epoch = (9e3 + np.r_[0, np.cumsum(expected + 4.5)]) % (rate / study.phase.FRAME_HZ)
    controls, _, _ = study.controls(epoch, f, t, rate, rf)
    assert np.max(abs(controls["positive"])) < 1e-10
    assert np.min(abs(controls["reflected"])) > 1
    assert np.min(abs(controls["clock_only"])) > 1


def test_mirror_face_geometry_uses_the_same_face_after_translation():
    first = {"center": [-41., -32.], "width_km": 25}
    second = {"center": [-41., -32.003], "width_km": 25}
    a = study.face(first, [-41., -31.997])
    b = study.face(second, first["center"])
    np.testing.assert_allclose(a - b, np.array([0, .003]))
