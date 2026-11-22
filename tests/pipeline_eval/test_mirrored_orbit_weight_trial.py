from importlib import import_module
from math import sqrt

import numpy as np
import pytest


trial = import_module("reports.ALGO08.single-core-2x.mirrored_orbit_weight_trial")


def test_one_fixed_variance_floor_adds_to_every_satellite():
    mass = trial.masses({12: 9., 13: 1.}, 1.)
    assert mass == pytest.approx({12: 1/6, 13: 5/6})
    assert sum(mass.values()) == pytest.approx(1.)


def test_whole_satellite_mass_is_independent_of_repeated_receivers_or_points():
    errors = np.array([[4., 0.]] * 20 + [[0., 4.]])
    owners = np.array([12] * 20 + [13])
    assert trial.score_by_satellite(errors, owners, {12: 1., 13: 1.}) == pytest.approx([sqrt(8), sqrt(8)])
    mass = trial.masses({12: 9., 13: 1.}, 1.)
    assert trial.score_by_satellite(errors, owners, mass) == pytest.approx([sqrt(16/6), sqrt(80/6)])
