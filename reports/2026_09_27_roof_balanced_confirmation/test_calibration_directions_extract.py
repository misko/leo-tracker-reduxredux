import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest


PATH = Path(__file__).with_name("calibration_directions_extract.py")
SPEC = importlib.util.spec_from_file_location("calibration_directions_extract", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_exact_observation_alignment_preserves_requested_order():
    actual = MODULE.align_indices(["a", "b", "c"], ["c", "a"])
    assert actual.tolist() == [2, 0]


def test_alignment_rejects_missing_or_duplicate_ids():
    with pytest.raises(ValueError, match="missing observation"):
        MODULE.align_indices(["a", "b"], ["z"])
    with pytest.raises(ValueError, match="duplicate requested"):
        MODULE.align_indices(["a", "b"], ["a", "a"])
    with pytest.raises(ValueError, match="duplicate track"):
        MODULE.align_indices(["a", "a"], ["a"])


def test_candidate_directions_and_weighted_means():
    # Receiver at origin, east=x, up=z. Candidate rows are candidate,time,xyz.
    positions = np.array([
        [[1., 0., 0.], [0., 0., 2.]],
        [[0., 0., 3.], [-4., 0., 0.]],
    ])
    east, up = MODULE.candidate_directions(
        positions, np.zeros(3), [1., 0., 0.], [0., 0., 1.])
    assert np.allclose(east, [[1., 0.], [0., -1.]])
    assert np.allclose(up, [[0., 1.], [1., 0.]])
    mean_east, mean_up = MODULE.weighted_means(east, up, [1., 3.])
    assert mean_east == pytest.approx([.25, -.75])
    assert mean_up == pytest.approx([.75, .25])


def test_weighted_means_reject_invalid_weights_and_shapes():
    with pytest.raises(ValueError, match="nonnegative"):
        MODULE.weighted_means([[1.]], [[1.]], [-1.])
    with pytest.raises(ValueError, match="shape"):
        MODULE.weighted_means([[1., 2.]], [[1.]], [1.])
