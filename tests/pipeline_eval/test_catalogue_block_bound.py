from importlib import import_module
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def block(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("catalogue_block_bound")


def test_box_lower_is_valid_for_every_member_and_signed_native_alias(block):
    from leo.analysis.research.retained_track_likelihood import profile, whitening

    rng = np.random.default_rng(962)
    n = 61
    x = np.linspace(-1., 1., n)
    observed = 11_943. + 691. * x + 175. * x**2
    frequency = rng.uniform(-.9, .9, (57, 1)) * block.PERIOD + rng.uniform(-40_000., 40_000., (57, 1)) * x
    elevation = np.full_like(frequency, 20.)
    sample = block.sample_indices(n)
    index = block.nominal_blocks(frequency[:, sample], elevation[:, sample], sample)
    assert len(sample) == len(set(sample)) == 16
    assert set(index.rows) == set(range(57))
    lower = index.lower(observed)
    exact = profile(observed, frequency, *whitening(np.arange(n)))
    for label, chunk in enumerate(np.split(index.rows, index.starts[1:])):
        assert np.all(lower[label] / block.NOISE**2 <= exact["cost"][chunk])
        assert np.all(lower[label] <= n * exact["rms"][chunk]**2)
        for native_alias in (-3, -1, 0, 1, 3):
            residual = observed - frequency[chunk] + native_alias * block.PERIOD - 845.
            assert np.all(lower[label] <= (residual**2).sum(axis=1))


def test_block_gate_needs_both_score_and_rms_failure_and_keeps_ties(block):
    points = 8
    selection = block.sample_indices(points)
    frequency = np.zeros((32, points))
    frequency[:16] = [-800., -800., -800., -800., 800., 800., 800., 800.]
    frequency[16:] = 2 * frequency[:16]
    index = block.nominal_blocks(frequency, np.zeros_like(frequency), selection)
    loss = np.array([points*500.**2, points*400.**2])
    assert block.reject_blocks(index, loss, 4., points).tolist() == [True, False]
    assert not block.reject_blocks(index, loss, loss[0]/block.NOISE**2, points).any()
    maximum = np.inf
    assert not block.reject_blocks(index, loss, maximum, points).any()
    visibility = np.array([False, True, True, True, False])
    terms = dict(cost=np.array([0., 1., 1., 2., 3.]), passing=np.array([False, False, True, True, True]))
    protected, cutoff = block.exact_protected(visibility, terms)
    assert cutoff == 1.
    assert protected.tolist() == [True, True, True, True, False]
    visibility[:] = False
    protected, cutoff = block.exact_protected(visibility, terms)
    assert np.isinf(cutoff) and protected.tolist() == [True, False, False, False, False]


def test_sampled_horizon_and_feasible_incumbent_keep_unsupported_requests(block):
    points = 65
    n = 32
    sample = block.sample_indices(points)
    observed = np.linspace(-500., 1000., points)
    frequency = np.repeat(observed[None, :], n, axis=0)
    elevation = np.ones_like(frequency)
    elevation[:16, sample[0]] = -1.
    index = block.nominal_blocks(frequency[:, sample], elevation[:, sample], sample)
    assert index.horizon_excluded().tolist() == [True, False]
    upper_inputs = (index, index.lower(observed), observed)
    shifted = np.zeros(n, dtype=bool)
    elided = set(range(points)) - set(sample)
    elevation[16, min(elided)] = -1.
    row, upper = block.independent_incumbent(*upper_inputs, shifted, frequency, elevation, np.arange(points), 1.)
    assert row == 16 and np.isinf(upper)
    shifted[16] = True
    row, upper = block.independent_incumbent(*upper_inputs, shifted, frequency, elevation, np.arange(points), 1.)
    assert row == 17 and np.isfinite(upper)
    frequency[17] += block.PERIOD/2
    row, upper = block.independent_incumbent(*upper_inputs, shifted, frequency, elevation, np.arange(points), 1.)
    assert row == 17 and np.isinf(upper)


def test_full_height_bias_releases_identical_ordered_diagnostics(block):
    from leo.analysis.research.retained_track_likelihood import profile, whitening

    prototype = import_module("catalogue_block_rank")
    rng = np.random.default_rng(14)
    for nrows, points, keep in ((1472, 47, 39), (1472, 90, 41), (1476, 20, 35), (1476, 31, 2)):
        observed = rng.normal(43_000., 1150., size=points)
        orbit = np.asfortranarray(rng.normal(45_000., 67_000., size=(nrows, points)))
        chosen = np.sort(rng.choice(nrows, size=keep, replace=False))
        inverse, volume = whitening(np.arange(points))
        full = profile(observed, orbit, inverse, volume)
        candidate = prototype.reduced_profile(observed, np.asfortranarray(orbit[chosen]), chosen,
                                              np.diag(inverse), np.empty_like(orbit))
        assert all(value[chosen].tobytes() == candidate[name].tobytes() for name, value in full.items())


def test_prototype_falls_back_near_signed_alias_tie(block):
    prototype = import_module("catalogue_block_rank")
    observed = np.zeros(40)
    orbit = np.full((2, len(observed)), block.PERIOD / 2, order="F")
    assert prototype.reduced_profile(observed, orbit, np.array([0, 2]), np.full(40, 1/block.NOISE),
                                     np.empty((4, 40), order="F")) is None
