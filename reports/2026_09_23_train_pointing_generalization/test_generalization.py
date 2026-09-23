"""Independent checks of the geometry cross-validation boundaries."""

import importlib.util
from pathlib import Path

import numpy as np


def module(filename, name):
    spec = importlib.util.spec_from_file_location(name, filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


HERE = Path(__file__).parent
RUN = module(HERE / "run.py", "pointing_generalization_test_subject")
CONE = RUN.load(RUN.CONE, "pointing_generalization_test_cone")


def test_norad_fold_is_shared_and_input_order_independent():
    identities = list(range(20)) + [3, 3, 12]
    mapping = RUN.fold_map(identities)
    assert mapping == RUN.fold_map(identities[::-1])
    assert mapping == RUN.fold_map(list(range(20)))
    assert set(mapping.values()) == set(range(5))
    assert all(list(mapping.values()).count(fold) == 4 for fold in range(5))


def test_shuffle_preserves_scan_lane_counts_and_fixed_strata():
    labels = np.array([0, 0, 1, 1, 0, 1, 0, 0, 1])
    strata = np.array(["a"] * 4 + ["b"] * 2 + ["c"] * 2 + ["d"])
    for permutation in range(20):
        shuffled, unchanged, moved = RUN.shuffled_labels(labels, strata, permutation)
        assert unchanged == 2
        assert moved == np.count_nonzero(shuffled != labels)
        for key in np.unique(strata):
            np.testing.assert_array_equal(
                np.sort(shuffled[strata == key]), np.sort(labels[strata == key])
            )
        np.testing.assert_array_equal(shuffled[-3:], labels[-3:])
        np.testing.assert_array_equal(
            shuffled, RUN.shuffled_labels(labels, strata, permutation)[0]
        )


def test_held_angles_cannot_select_orientation():
    orientations = np.array([[0, 0, 0], [1, 5, 10], [2, 10, 20]])
    angles = np.array([[8, 9, 10, 2, 3], [1, 2, 3, 30, 40], [4, 5, 6, 1, 2]])
    weights = np.array([1, 2, 1, 2, 1], dtype=float)
    train = np.array([True, True, True, False, False])
    original = RUN.evaluate(CONE, orientations, angles, weights, train, ~train)
    altered = angles.copy()
    altered[:, ~train] += 100
    perturbed = RUN.evaluate(CONE, orientations, altered, weights, train, ~train)
    for fraction in RUN.FRACTIONS:
        a, b = original[str(fraction)], perturbed[str(fraction)]
        assert a["orientation"] == b["orientation"] == [1, 5, 10]
        assert a["fit_deg"] == b["fit_deg"]
        assert b["held_deg"] == a["held_deg"] + 100
