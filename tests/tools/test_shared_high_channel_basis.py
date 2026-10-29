"""Scientific controls for optional receiver covariance experiments."""

from types import SimpleNamespace

import numpy as np
import pytest

from probe_graph_shared_high_channels import receiver_basis
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis


@pytest.mark.parametrize("resolution", ["original", "fine", "fast"])
def test_band_covariance_preserves_variance_and_separates_bands(resolution):
    grid = np.linspace(0, 300, 301)
    original = projected_receiver_basis(grid)
    scan = SimpleNamespace(
        tracks=[dict(channel=ch, times=grid.copy()) for ch in (1, 8)],
        rx_basis=[original.copy(), original.copy()],
    )
    node = {"seed": {"state": {"smooth": np.ones((2, original.shape[1]))}}}
    changed, changed_node = receiver_basis(scan, node, "band_" + resolution)
    low, high = changed.rx_basis
    width = low.shape[1] // 2
    # Same average prior variance: increased basis width must not silently
    # increase permissible frequency drift. Independent bands have zero
    # cross-covariance under the common isotropic coefficient prior.
    np.testing.assert_allclose(np.linalg.norm(low), np.linalg.norm(original))
    np.testing.assert_allclose(np.linalg.norm(high), np.linalg.norm(original))
    np.testing.assert_allclose(low[:, :width], high[:, width:])
    np.testing.assert_array_equal(low @ high.T, np.zeros((301, 301)))
    affine = np.column_stack((np.ones(len(grid)), grid - 150))
    np.testing.assert_allclose(affine.T @ low, 0, atol=1e-9)
    assert changed_node["seed"]["state"]["smooth"].shape == (2, 2 * width)
    np.testing.assert_array_equal(scan.rx_basis[0], original)
    np.testing.assert_array_equal(node["seed"]["state"]["smooth"], 1)


def test_unknown_receiver_covariance_fails_explicitly():
    with pytest.raises(ValueError, match="Unknown receiver basis"):
        receiver_basis(SimpleNamespace(), {}, "unrecognized")
