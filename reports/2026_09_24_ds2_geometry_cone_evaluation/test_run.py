from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np


def load():
    path = Path(__file__).with_name("run.py")
    spec = importlib.util.spec_from_file_location("ds2_geometry_run", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_fixture_axes_keep_nominal_separation_and_upward_limit():
    module = load()
    values = module.axes(module.orientations())
    separation = np.degrees(np.arccos(np.sum(values[:, 0] * values[:, 1], axis=1)))
    assert np.allclose(separation, 20.0)
    assert np.all(values[:, :, 2] >= np.cos(np.radians(55.0)) - 1e-12)


def test_cone_cannot_improve_unconstrained_training_loss():
    module = load()
    episode = module.Episode(
        "scan",
        "track",
        0,
        np.asarray([0.0, 10.0, 20.0, 30.0]),
        np.asarray([True, True, False, False]),
        np.arange(4.0),
        np.asarray(["1", "2"]),
        np.asarray([[[7000.0, 0.0, 0.0]] * 4, [[7000.0, 20.0, 0.0]] * 4]),
        np.zeros((2, 4, 3)),
    )
    region = module.Region(0.0, 0.0, 10.0, 10.0)
    rows = module.prepared([episode], region, np.asarray([0.0, 0.0]))
    mounts = module.axes(module.orientations()[:24])
    orient, _ = module.fit_orientation(rows, mounts, (0, 1), 90.0)
    cone = module.score_cone(rows, mounts, orient, (0, 1), 90.0)
    assert cone["training_capped_loss"] + 1e-12 >= module.baseline_loss(rows)
