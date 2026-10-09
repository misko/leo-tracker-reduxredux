"""Requires a C compiler. Bounded synthetic calls, no RF or corpus access."""

import numpy as np
import pytest
from partial_signal import signal

from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
from tools.native_presence import NativePresence, build_library


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    library = build_library(tmp_path_factory.mktemp("iter120") / "presence.so")
    with NativePresence(library, 2_500_000, "lower") as estimator:
        yield estimator


@pytest.mark.parametrize("cutoff", [0.00015, 0.001, 0.005, 0.020])
def test_partial_coherence_not_occupancy(native, cutoff):
    values, occupancy = signal(cutoff)
    actual = native.glrt(values, 0, 0)
    oracle = conditioned_glrt64_score(values, 2_500_000, epoch_sample=0, acquired_cfo_hz=0)
    np.testing.assert_allclose(
        actual[:2], [oracle.exact_score, oracle.control_score], atol=1e-10, rtol=0
    )
    assert actual[2] == 0
    assert actual[0] == pytest.approx(1, abs=1e-10, rel=0)
    if cutoff < 0.020:
        assert occupancy < 0.3
        assert actual[0] > occupancy + 0.5
    np.testing.assert_allclose(native.glrt(values * 0.01, 0, 0), actual, atol=1e-10, rtol=0)


def test_noise_is_not_removed_with_signal(native):
    values, occupancy = signal(0, noise_rms=1)
    assert occupancy == 0
    assert np.count_nonzero(values) == len(values)
    result = native.glrt(values, 0, 0)
    assert np.all(np.isfinite(result))
    assert 0 < result[0] < 1
