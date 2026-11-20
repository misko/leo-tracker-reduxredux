from types import SimpleNamespace

import numpy as np
import pytest
from scipy.optimize import brentq

from tools.pipeline_eval.qualification.fit_work_bundle import revised_source
from tools.pipeline_eval.variants import fit_work_projection as variant


def legacy_bic(residual, times):
    """Original three-column least-squares implementation for the quadratic gate."""
    n = len(times)
    x = times - times.mean()
    tx = x / max(float(np.ptp(times)) / 2, 1.0)
    design = np.stack([np.ones(n), tx, tx * tx], axis=1)
    fitted = (design @ np.linalg.lstsq(design, residual.T, rcond=None)[0]).T
    floor = n * 75.0**2
    rss0 = np.maximum(np.sum(residual * residual, axis=1), floor)
    rss1 = np.maximum(np.sum((residual - fitted) ** 2, axis=1), floor)
    return n * np.log(rss0 / rss1) - 3 * np.log(n)


def unexpected_stock(*_args):
    raise AssertionError("well separated and conditioned result used a fresh least-squares fit")


@pytest.mark.parametrize("count", (4, 17, 105, 509))
@pytest.mark.parametrize("rows", (1, 5))
def test_fixed_projection_agrees_with_fresh_solve(count, rows):
    rng = np.random.default_rng(260237 + rows + count)
    times = np.sort(rng.uniform(0, 300, size=count))
    residual = rng.normal(0.0, 170.0, size=(rows, count))
    screen = variant.FixedNoiseScreen(times, unexpected_stock)
    computed = screen(residual)
    expected = legacy_bic(residual, times)
    np.testing.assert_allclose(computed["quadratic_bic_gain"], expected, atol=1e-11, rtol=0)
    sigma = np.maximum(np.std(residual, axis=1, ddof=1), 75.0)
    centered_time = times - times.mean()
    np.testing.assert_array_equal(
        computed["slope_z"],
        np.abs(residual @ centered_time)
        / np.maximum(sigma * np.sqrt(centered_time @ centered_time), 1e-12),
    )
    np.testing.assert_array_equal(
        computed["mean_z"], np.abs(residual.mean(axis=1)) * np.sqrt(count) / sigma
    )


@pytest.mark.parametrize("boundary", variant._BIC_EDGES)
def test_original_replay_at_every_comparison_boundary(boundary):
    times = np.linspace(0.0, 12, 40)
    rng = np.random.default_rng(6)
    noise = rng.normal(0.0, 300.0, size=(1, len(times)))
    curve = ((times - times.mean()) / 6) ** 2
    amplitude = brentq(lambda a: legacy_bic(noise + a * curve, times)[0] - boundary, 0, 6000)
    result = object()
    calls = []

    def stock(residual, stamps):
        calls.append((residual.copy(), stamps.copy()))
        return result

    screen = variant.FixedNoiseScreen(times, stock)
    residual = noise + amplitude * curve
    assert screen(residual) is result
    assert len(calls) == 1
    np.testing.assert_array_equal(calls[0][0], residual)
    np.testing.assert_array_equal(calls[0][1], times)


def test_rank_uncertainty_and_masked_time_ownership():
    repeated = [0.0, 0.0, 0.0, 0.0, 1.0, 1.0]
    payload = object()
    screen = variant.FixedNoiseScreen(repeated, lambda *_: payload)
    assert screen(np.ones((1, 6))) is payload
    curved_times = np.arange(7.0)
    linear_times = np.arange(41.0, 46.0)
    problem = SimpleNamespace(
        scan=SimpleNamespace(tracks=[{"times": curved_times}, {"times": linear_times}]),
        members=[0],
        slices=[slice(0, 7)],
        keep=np.array([0, 1, 1, 1, 0, 1, 1], dtype=bool),
    )
    curved, linear = variant.prepare(problem, [{"track_index": 1}], unexpected_stock)
    original_times = curved_times[problem.keep]
    curved_times += 10
    np.testing.assert_array_equal(curved[0].times, original_times)
    np.testing.assert_array_equal(linear[1].times, linear_times)
    with pytest.raises(ValueError, match="finite"):
        curved[0](np.ones((1, 7)))
    with pytest.raises(ValueError, match="unrecognized constrained"):
        revised_source("def unrelated(): return None")
