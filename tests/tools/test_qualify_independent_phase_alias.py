import numpy as np

from leo.analysis.qam.pilot import _frequency_likelihood
from tools.research.qualify_independent_phase_alias import (
    FULL_PERIOD_HZ,
    HALF_PERIOD_HZ,
    branch_seeds,
)


def test_branch_family_is_predeclared_from_metadata_only():
    observation = {"acquired_cfo_hz": 1000.0, "fractional_tracking_cfo_hz": 2000.0}
    rows = branch_seeds(observation)
    assert [row["label"] for row in rows] == [
        "acquired_minus_full",
        "acquired_minus_half",
        "acquired",
        "acquired_plus_half",
        "acquired_plus_full",
        "archived_refined",
    ]
    assert rows[1]["seed_cfo_hz"] == 1000.0 - HALF_PERIOD_HZ
    assert rows[4]["seed_cfo_hz"] == 1000.0 + FULL_PERIOD_HZ


def test_stride_two_likelihood_has_half_period_alias_but_full_symbols_do_not():
    rng = np.random.default_rng(20260924)
    matched = rng.normal(size=(300, 8)) + 1j * rng.normal(size=(300, 8))
    times = np.arange(300) * 4.4e-6
    frequencies = np.asarray([1379.0, 1379.0 + HALF_PERIOD_HZ])
    even = _frequency_likelihood(matched[::2], times[::2], frequencies)
    full = _frequency_likelihood(matched, times, frequencies)
    assert np.allclose(even[0], even[1], rtol=1e-12, atol=1e-8)
    assert not np.isclose(full[0], full[1], rtol=1e-4, atol=1e-4)
