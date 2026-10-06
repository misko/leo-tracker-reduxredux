import numpy as np
import pytest

from leo.analysis.regional_position_bank import could_be_visible
from leo.analysis.regional_position_score import observer
from leo.contracts.regional_position import RegionalPrior


def test_horizon_screen_retains_every_satellite_visible_anywhere_in_prior():
    rng = np.random.default_rng(3821)
    directions = rng.normal(size=(500, 3, 3))
    directions /= np.linalg.norm(directions, axis=2)[..., None]
    position = directions * rng.uniform(6600, 8000, size=(500, 3, 1))
    prior = RegionalPrior()
    keep = could_be_visible(position, prior)
    visible = np.zeros(500, bool)
    for radius in (0, 125, 250):
        for angle in np.linspace(0, 2 * np.pi, 32):
            site, up = observer(prior, radius * np.array([np.cos(angle), np.sin(angle)]))
            visible |= np.any(np.einsum("knj,j->kn", position - site, up) >= 0, axis=1)
    assert visible.any() and (~keep).any()
    assert np.all(keep[visible])


def test_screen_keeps_a_satellite_over_prior_edge():
    prior = RegionalPrior()
    site, up = observer(prior, [250, 0])
    assert could_be_visible((site + 550 * up)[None, None, :], prior).tolist() == [True]
    assert could_be_visible((-site - 550 * up)[None, None, :], prior).tolist() == [False]
    with pytest.raises(ValueError):
        could_be_visible(np.zeros((1, 1, 3)), prior)
