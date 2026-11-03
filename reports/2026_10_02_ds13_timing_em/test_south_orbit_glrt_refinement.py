from types import SimpleNamespace

import numpy as np
import pytest
from south_orbit_glrt_refinement import peak_frequency, refine_correlations


def test_peak_uses_signal_vertex_not_window_center_and_flags_boundary():
    frequencies = np.arange(-200., 201., 10.)
    peak, edge, _ = peak_frequency(frequencies, -(frequencies - 37.) ** 2)
    assert peak == pytest.approx(37.)
    assert not edge
    assert peak_frequency(frequencies, frequencies)[:2] == (200., True)


def test_guidance_clips_excluded_peak_and_control_retains_independent_peak():
    lags = np.arange(64) * 4.4e-6
    correlations = SimpleNamespace(values=np.exp(2j * np.pi * 75 * lags)[None, :],
                                   times_s=lags[None, :])
    result, grids = refine_correlations(correlations, correlations, 0., 0., 0., 400.)
    assert result["control_refined_frequency_hz"] == pytest.approx(75., abs=.01)
    assert result["truth_refined_frequency_hz"] == pytest.approx(75., abs=.01)
    assert result["south_refined_frequency_hz"] == pytest.approx(200.)
    assert result["south_boundary_hit"]
    assert result["south_refined_exact_score"] < result["control_refined_exact_score"]
    assert grids["truth_exact"].shape == (41,)
    assert grids["control_exact"].shape == (201,)


def test_peak_rejects_nonfinite_scores():
    with pytest.raises(ValueError):
        peak_frequency([0., 1., 2.], [0., np.nan, 1.])
