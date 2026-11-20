from types import SimpleNamespace

import numpy as np
import pytest

from leo.sky.frames import geodetic_to_ecef_km
from tools.pipeline_eval.reference import grid
from tools.pipeline_eval.variants import code_carrier as model


def test_integer_counter_phase_keeps_fractional_precision_and_cancels_track_origin():
    rate = 10_000_000
    first = 28_212_345_678_901
    counters = first + np.array([0, 8_234_819, 20_555_254], dtype=np.int64)
    epochs = np.array([12.125, 18.75, 40.375])
    period = rate / model.FRAME_HZ

    def delta(origin, e):
        return model.wrapped(np.diff(model.arrival_samples(counters, origin, e, rate)), period)

    direct = delta(first, epochs)
    np.testing.assert_allclose(delta(first - 2_450_001, epochs + 236.75), direct, atol=1e-10)
    exact = ((np.diff(counters) * model.FRAME_HZ) % rate) / model.FRAME_HZ + np.diff(epochs)
    np.testing.assert_allclose(direct, model.wrapped(exact, period), atol=1e-10)


def test_positive_slant_range_and_negative_doppler_give_the_same_interval():
    site = (0.0, 0.0)
    station = geodetic_to_ecef_km(*site, 0.0)
    sample_rate, rf = 10_000_000, 11.3e9
    t = np.array([0.1, 1.9, 2.7, 4.0])
    rho = 840 + 2.0 * t + 0.25 * t**2
    cfo = -rf / grid.LIGHT_SPEED_KM_S * (2.0 + 0.5 * t)
    p = station + np.column_stack((rho, np.zeros(len(t)), np.zeros(len(t))))
    arc = SimpleNamespace(position=p)
    predicted, _ = model.geometry(
        [arc], [np.ones(len(t) - 1, dtype=bool)], site, sample_rate / grid.LIGHT_SPEED_KM_S
    )
    integrated = model.carrier_samples(cfo, np.diff(t), rf, sample_rate)
    np.testing.assert_allclose(predicted, integrated, atol=1e-10)
    assert (predicted > 0).all()
    np.testing.assert_allclose(model.carrier_samples(-cfo, np.diff(t), rf, sample_rate), -predicted)


def test_train_only_clock_keeps_held_scheduling_step_visible():
    period = 10_000_000 / model.FRAME_HZ
    train = np.array([True, True, True, False, False])
    dt = np.array([0.4, 1.2, 0.6, 1.4, 0.95])
    predicted = np.array([230.0, -210.0, 110.0, 325.0, -180.0])
    measured = model.wrapped(predicted + dt * 19.0, period)
    measured[~train] += 41.0
    residual = model.predict(measured, predicted, dt[:, None], train, 3.0, period)
    np.testing.assert_allclose(residual[train], 0.0, atol=1e-10)
    np.testing.assert_allclose(residual[~train], 41.0, atol=1e-10)


def test_intervals_drop_gap_and_training_boundary_before_fitting():
    t = np.array([0.1, 0.5, 0.9, 1.3, 2.0, 4.7, 5.0, 5.7])
    capture = SimpleNamespace(sample_rate_hz=10_000_000, first_counter=79_000)

    def arc(path, slip):
        return SimpleNamespace(
            time=t,
            stop=4,
            lane=path,
            norad=10,
            counters=capture.first_counter + np.rint(t * capture.sample_rate_hz).astype(np.int64),
            epoch=np.arange(len(t)) + slip,
            cfo=np.linspace(20, -5, len(t)),
        )

    initial = arc((0, 1, 11e9, "upper"), 0)
    second = arc((0, 2, 11.2e9, "upper"), 82)
    packet, use = model.packet([initial, second], capture)
    for membership in use:
        assert list(membership) == [True, True, True, False, False, True, True]
    assert list(packet["train"]) == [True, True, True, False, False] * 2
    assert list(packet["track"]) == [0] * 5 + [1] * 5
    np.testing.assert_allclose(packet["code"][:5], packet["code"][5:])


def test_fixed_rf_term_projects_out_of_independent_carrier_levels():
    packet = dict(
        dt=np.array([1, 2, 1, 2, 1, 2], dtype=float),
        time=np.array([2, 4, 8, 15, 20, 25], dtype=float),
        rf=np.array([11.0, 11.0, 11.0, 12.4, 12.4, 12.4]) * 1e9,
        track=np.repeat([0, 1], 3),
        receiver=np.repeat([0, 1], 3),
        path=np.repeat([0, 2], 3),
    )
    _, carrier = model.design(packet, free=False)
    result = model.calibration_audit(packet, carrier, 10_000_000)
    assert result["norm"] > 0
    assert result["rank"] == result["rank_with_c"]
    assert result["residual_norm"] < 1e-12


def test_fisher_removes_the_direction_equivalent_to_clock_rate():
    t = np.arange(5, dtype=float)
    design = (1 + t)[:, None]
    jacobian = np.column_stack((2 * design[:, 0], t**2))
    info = model.fisher(jacobian, design, np.ones(len(t), dtype=bool), 3.0)
    assert info[0, 0] == pytest.approx(0)
    assert info[1, 1] > 0
    assert np.linalg.matrix_rank(info) == 1
