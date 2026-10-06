from dataclasses import fields, replace

import numpy as np
import pytest

from leo.contracts.regional_position import (
    POSITION_SCORES,
    PositionObservations,
    PositionOrbitBank,
    RegionalPrior,
)


def test_profiles_are_exact_and_reference_is_not_an_inference_field():
    c0, v16 = POSITION_SCORES["T1AT"], POSITION_SCORES["V16"]
    assert (
        c0.sigma_hz,
        c0.detection_budget,
        c0.clutter_rate,
        c0.common_sigma_s,
        c0.relative_sigma_s,
    ) == (200, 0.8, 2, 10, 1)
    assert (
        v16.sigma_hz,
        v16.detection_budget,
        v16.clutter_rate,
        v16.common_sigma_s,
        v16.relative_sigma_s,
    ) == (125, 1.6, 0.5, 3, 0.15)
    for model in (PositionObservations, PositionOrbitBank, RegionalPrior):
        assert not any("reference" in f.name or "truth" in f.name for f in fields(model))


def test_window_identity_and_numeric_validation():
    source = np.array([1.0, 2.0])
    obs = PositionObservations(("a", "b"), source, [2, 3], [11e9, 12e9], [0, 1], [1, 2], [0.1, 0.2])
    source[0] = 100
    assert obs.times_s[0] == 1
    with pytest.raises(ValueError):
        obs.times_s[0] = 2
    for change in (
        {"window_ids": ("a", "a")},
        {"rf_hz": [0, 1]},
        {"receiver": [0, 0.5]},
        {"measured_hz": [np.nan, 2]},
    ):
        with pytest.raises(ValueError):
            replace(obs, **change)


def test_orbit_geometry_must_be_finite_and_regular():
    bank = PositionOrbitBank([1, 2], [0, 1, 2], np.ones((2, 3, 3)), np.ones((2, 3, 3)))
    for change in (
        {"numbers": [1, 1]},
        {"numbers": [1, 2.5]},
        {"nodes_s": [0, 1, 3]},
        {"velocity_km_s": np.zeros((2, 2, 3))},
    ):
        with pytest.raises(ValueError):
            replace(bank, **change)
    assert bank.select([1]).numbers.tolist() == [2]
    with pytest.raises(ValueError):
        RegionalPrior(radius_km=-1)
