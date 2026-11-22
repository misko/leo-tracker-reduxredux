import numpy as np
import pytest

from leo.analysis.research.retained_track_likelihood import PERIOD, profile, whitening
from tools.pipeline_eval.variants.algo08_streamed_nomination import white_nomination


@pytest.mark.parametrize("order", ["C", "F"])
@pytest.mark.parametrize("length", [6, 129, 311])
def test_stream_preserves_every_cost_alias_and_nominee_diagnostic(order, length):
    rng = np.random.default_rng(244)
    times = np.arange(length, dtype=float)
    observed = rng.normal(300, 14, size=length)
    proposed = observed + rng.normal(0, 1300, size=(521, length))
    proposed[0] = proposed[1] = observed + np.linspace(-10.5, 10.5, length)
    proposed[2] = observed - PERIOD / 2.0
    proposed[3] = np.nextafter(proposed[2], -np.inf)
    proposed[4] = np.nextafter(proposed[2], np.inf)
    proposed = np.array(proposed, order=order)
    noise = whitening(times)
    expected = profile(observed, proposed, *noise)
    for visible, winner in (
        (np.ones(len(proposed), dtype=bool), 0),
        (np.arange(len(proposed)) != 0, 1),
        (np.zeros(len(proposed), dtype=bool), 0),
    ):
        nominee, cost, alias, bias, rms, innovation = white_nomination(
            observed, proposed, visible, noise
        )
        assert nominee == winner
        np.testing.assert_array_equal(cost, expected["cost"])
        np.testing.assert_array_equal(alias, expected["alias"])
        assert bias == expected["bias"][winner]
        assert rms == expected["rms"][winner]
        np.testing.assert_array_equal(innovation, expected["innovations"][winner])


def test_correlated_whitening_uses_complete_stock_profile():
    time = np.arange(5., 33., 2.)
    observed = np.cos(time) * 100
    predicted = np.stack((observed / 3, observed / 2))
    visible = np.array([False, True])
    noise = whitening(time, correlated_sigma_hz=150.)
    expected = profile(observed, predicted, *noise)
    nominee, scores, aliases, bias, rms, innovation = white_nomination(
        observed, predicted, visible, noise
    )
    assert nominee == 1
    np.testing.assert_array_equal(scores, expected["cost"])
    np.testing.assert_array_equal(aliases, expected["alias"])
    assert bias == expected["bias"][1]
    assert rms == expected["rms"][1]
    np.testing.assert_array_equal(innovation, expected["innovations"][1])
