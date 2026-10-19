"""Scientific guards for carrying repaired raw observations into localization."""

from types import SimpleNamespace

import numpy as np
import propagate_ds23_arc_positions as module


def test_secondary_noise_is_fixed_by_radio_margin_not_satellite_residual():
    metadata = dict(
        extra_parameter_BIC_gain=10.0,
        floor_sigma_hz=40.0,
        strength_hz2=1200.0,
        constant_radio_sigma_hz=70.0,
    )
    assert module.secondary_noise(metadata, 0.5) == np.sqrt(1600 + 2400)
    assert module.secondary_noise({**metadata, "extra_parameter_BIC_gain": -1}, 0.01) == 70.0


def test_receiver_gauge_resolves_half_period_alias_ambiguity():
    predicted = np.array([90000.0, 100000.0, 110000.0])
    receiver = 114000.0
    measured = predicted + receiver - module.PERIOD
    assert module.alias_from_receiver_gauge(measured, predicted, 0.0) == 0
    assert module.alias_from_receiver_gauge(measured, predicted, receiver) == 1
    assert module.alias_from_receiver_gauge(measured + 3 * module.PERIOD, predicted, receiver) == -2


def test_only_curves_inside_the_requested_interval_are_replaced():
    base = dict(receiver=1, channel=2)
    assert module.removed_target(dict(base, times=np.linspace(74, 134, 48)), "DS23-0342")
    assert not module.removed_target(dict(base, times=np.linspace(31, 63, 35)), "DS23-0342")
    assert not module.removed_target(dict(base, times=np.linspace(180, 230, 35)), "DS23-0342")


def test_raw_track_preserves_measurements_modulo_integer_aliases(monkeypatch):
    observed = np.array([-600000.0, -620000.0, -640000.0])
    source = dict(indices=np.arange(3), candidate_index=0, orbit=dict(parameters=[0.0, 0.0, 0.0]))
    doc = dict(
        times=[70.0, 80.0, 90.0],
        radio_hz=[100000.0, 100000.0, 100000.0],
        site=[37.0, -122.0],
        rf_hz=11e9,
        winners=[0, 2],
        candidates=[dict(cfo_hz=float(v), probe=i, rank=0) for i, v in enumerate(observed)],
    )
    monkeypatch.setattr(module, "frequency", lambda *args: np.array([100000.0, 80000.0, 60000.0]))
    track = module.raw_track(
        "DS23-0342", "test", 0, source, doc, SimpleNamespace(sky={}), {0: "A", 2: "C"}
    )
    lift = (track["values"] - observed) / module.PERIOD
    np.testing.assert_allclose(lift, np.rint(lift), atol=1e-10)
    assert track["observation_ids"][0] == "A" and track["observation_ids"][2] == "C"
    assert track["observation_ids"][1] not in ["A", "C"]


def test_shared_scale_linearization_keeps_absolute_phase_prior(monkeypatch):
    p = module.PositionNormal.__new__(module.PositionNormal)
    n = 5
    p.scale_labels = [0]
    p.labels = [0]
    p.scale_reference = np.array([0.002])
    p.reference = np.array([2.0])
    p.hardware = np.zeros((n, 1))
    p.smooth = np.zeros((n, 0))
    p.flat_labels = np.zeros(n, int)
    p.values = np.zeros(n)
    p.q = np.full(n, 0.95)
    p.members = [0]
    p.keep = np.ones(n, bool)
    p.point_noise = np.full(n, 40.0)
    p.noise_groups = np.zeros(n, int)
    p.noise_volume = 0.0
    derivative = np.linspace(-500, 500, n)
    f = np.linspace(-100000, 100000, n)
    phase_sigma = 3.0
    original = np.column_stack([np.zeros(n), p.q * derivative * phase_sigma, np.ones(n) * 1000])
    monkeypatch.setattr(
        module.JointMarginal,
        "calculate",
        lambda self, x: dict(
            features=original,
            frequency=f,
            derivative=derivative,
            intercept=f - derivative * 2.0,
            elevation=np.ones(n) * 40,
        ),
    )

    def bound(raw, features, sigma, groups):
        return dict(
            coefficient=np.zeros(features.shape[1]),
            noise_precision=np.ones(1),
            residual=np.zeros(n),
        )

    monkeypatch.setattr(module, "hierarchical_bound", bound)
    result = p.calculate(np.zeros(2))
    np.testing.assert_allclose(result["intercept"], f - 1.002 * derivative * 2.0)
    # At the expansion reference the linearized model exactly recovers f*(1+s).
    coeff = np.array([0.0, 2.0 / phase_sigma, 0.002 / 0.005, 0.0])
    reconstructed = p.q * result["intercept"] + result["features"] @ coeff
    np.testing.assert_allclose(reconstructed, p.q * f * 1.002, atol=1e-9)


def test_scale_coefficients_do_not_overlap_fragment_constants(monkeypatch):
    p = module.PositionNormal.__new__(module.PositionNormal)
    p.scale_labels = [4, 8]
    p.members = [1, 2]
    monkeypatch.setattr(
        module.PositionNormal, "calculate", lambda self, x: dict(coefficient=np.arange(10.0))
    )
    np.testing.assert_allclose(p.scale_state(np.zeros(2)), np.array([6.0, 7.0]) * 0.005)
