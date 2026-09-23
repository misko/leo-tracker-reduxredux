import numpy as np
import pytest

from tools.research.position_nuisance_information import project_nuisance, sensitivity


def test_nuisance_projection_removes_only_span_and_is_rank_safe():
    t = np.linspace(-1, 1, 21)
    nuisance = np.column_stack([np.ones_like(t), t, 2 * t])
    j = np.column_stack([3 + 2 * t, t * t])
    projected = project_nuisance(j, nuisance)
    np.testing.assert_allclose(projected[:, 0], 0, atol=1e-12)
    np.testing.assert_allclose(nuisance.T @ projected, 0, atol=1e-12)
    assert np.linalg.norm(projected[:, 1]) > 0


def test_known_isotropic_frequency_sensitivity():
    result = sensitivity([np.eye(2) * 10])
    np.testing.assert_allclose(result["rms_change_for_300m_hz_min_max"], [3 / np.sqrt(2)] * 2)


def test_rejects_nonfinite_rows():
    with pytest.raises(ValueError):
        project_nuisance([[np.nan]], [[1]])
