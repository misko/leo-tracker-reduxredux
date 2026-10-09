"""Synthetic metadata only: no reference locations, orbit states or recordings."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "segments108", Path(__file__).with_name("segments.py")
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def observations(times, receiver=None, channel=None, rf=None):
    n = len(times)
    return SimpleNamespace(
        times_s=np.asarray(times),
        receiver=np.zeros(n) if receiver is None else np.asarray(receiver),
        channel=np.ones(n) if channel is None else np.asarray(channel),
        rf_hz=np.full(n, 1e10) if rf is None else np.asarray(rf),
    )


def test_interleaved_tracks_permutation_and_scatter():
    obs = observations([0, 0.1, 1, 1.1, 2, 2.1])
    actual = module.prepare_segments(((0, 2, 4), (1, 3, 5)), obs)
    np.testing.assert_array_equal(actual["permutation"], [0, 2, 4, 1, 3, 5])
    np.testing.assert_array_equal(actual["reset"], [True, False, False, True, False, False])
    x = np.arange(6) * 3
    np.testing.assert_array_equal(x[actual["permutation"]][actual["inverse_permutation"]], x)
    swapped = module.prepare_segments(((5, 3, 1), (4, 2, 0)), obs)
    np.testing.assert_array_equal(swapped["permutation"], actual["permutation"])
    assert actual["counts"]["eligible_links"] == 4


def test_overlap_removal_never_bridges_and_uncovered_independent():
    actual = module.prepare_segments(((0, 1, 2), (1, 3)), observations([0, 0.5, 1, 1.5, 2]))
    assert actual["counts"]["overlapping_rows"] == 1
    assert actual["counts"]["uncovered_rows"] == 1
    assert actual["counts"]["eligible_links"] == 0
    assert actual["counts"]["independent_rows"] == 5
    assert actual["reset"].all()


@pytest.mark.parametrize(
    "field,values,reason",
    [
        ("receiver", [0, 1, 1], "receiver"),
        ("channel", [1, 2, 2], "channel"),
        ("rf", [1e10, np.nextafter(1e10, np.inf), np.nextafter(1e10, np.inf)], "rf"),
    ],
)
def test_lane_boundaries_exact(field, values, reason):
    actual = module.prepare_segments(((0, 1, 2),), observations([0, 1, 2], **{field: values}))
    assert actual["segments"] == ((0,), (1, 2))
    assert actual["counts"]["boundaries"][reason] == 1


def test_gap_boundary_and_equal_times():
    actual = module.prepare_segments(((0, 1, 2, 3, 4),), observations([0, 0, 2, 4.000001, 5]))
    assert actual["segments"] == ((0,), (1, 2), (3, 4))
    assert actual["counts"]["boundaries"]["nonpositive_gap"] == 1
    assert actual["counts"]["boundaries"]["gap_over_2s"] == 1


def test_all_uncovered_is_exact_independent_policy():
    actual = module.prepare_segments((), observations([1, 0, 2]))
    assert actual["reset"].all() and actual["counts"]["eligible_rows"] == 0
    assert actual["counts"]["observations"] == 3


@pytest.mark.parametrize("tracks", [((0, 0),), ((0, 3),), ((0, -1),), ((True,),), ((0.0,),)])
def test_invalid_memberships_rejected(tracks):
    with pytest.raises(ValueError):
        module.prepare_segments(tracks, observations([0, 1, 2]))


def test_nonfinite_metadata_rejected():
    with pytest.raises(ValueError):
        module.prepare_segments(((0, 1),), observations([0, np.nan]))


def test_adapter_kernel_segments_equal_separate_calls():
    from leo.application.hard60_runner import HARD60_SCORE

    spec = importlib.util.spec_from_file_location(
        "kernel108", Path(__file__).with_name("persistence.py")
    )
    kernel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kernel)
    obs = observations([0, 0.1, 1, 1.1, 2, 2.1], receiver=[0, 1, 0, 1, 0, 1])
    layout = module.prepare_segments(((0, 2, 4), (1, 3, 5)), obs)
    measured = np.arange(6) * 20.0
    prediction = measured[:, None] + np.array([10.0, 90.0, 200.0])[None, :]
    visible = np.ones_like(prediction, bool)
    p = layout["permutation"]
    combined = kernel.evaluate(
        measured[p], prediction[p], visible[p], HARD60_SCORE, rho=0.6, reset=layout["reset"]
    )
    score, gradient = 0.0, np.empty_like(prediction)
    for segment in layout["segments"]:
        rows = list(segment)
        out = kernel.evaluate(
            measured[rows],
            prediction[rows],
            visible[rows],
            HARD60_SCORE,
            rho=0.6,
            reset=np.r_[True, np.zeros(len(rows) - 1, bool)],
        )
        score += out["nll"]
        gradient[rows] = out["prediction_gradient"]
    assert combined["nll"] == pytest.approx(score, abs=1e-12)
    np.testing.assert_allclose(
        combined["prediction_gradient"][layout["inverse_permutation"]], gradient
    )
