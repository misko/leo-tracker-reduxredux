"""Independent finite derivatives on synthetic multi-satellite graph curves."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from dsx01_legacy_jacobian import jacobian, robust_derivative  # noqa: E402
from profile_dsx01_geographic_calibration import geometry_problem  # noqa: E402

from leo.analysis.research.continuous_curve_fit import robust_curve  # noqa: E402
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis  # noqa: E402


def test_robust_derivative_against_directional_finite_differences():
    rng = np.random.default_rng(9)
    z = rng.normal(size=11) * 4
    j = rng.normal(size=(11, 4))
    h = 1e-5
    expected = np.column_stack(
        [(robust_curve(z + h * v, 10) - robust_curve(z - h * v, 10)) / (2 * h) for v in j.T]
    )
    np.testing.assert_allclose(robust_derivative(z, j, 10), expected, atol=1e-9)


def fake_scan():
    grid = np.arange(-20.0, 41.0)
    pos = np.zeros((2, len(grid), 3))
    vel = np.zeros_like(pos)
    for j in range(2):
        pos[j, :, 0] = -3000 + grid * (2 + j)
        pos[j, :, 1] = -5000 + grid * (1 - j)
        pos[j, :, 2] = 4000 + j * 300
        vel[j, :, 0] = 2 + j
        vel[j, :, 1] = 1 - j
    sky = dict(time_s=grid, position_km=pos, velocity_km_s=vel)
    tracks = []
    for i in range(4):
        t = np.arange(12.0) + i
        tracks.append(
            dict(
                key=f"t{i}",
                receiver=1 + i % 2,
                channel=1 if i % 2 == 0 else 6,
                rf_hz=11.5e9 + i % 2 * 1e9,
                times=t,
                values=10000 + 20 * t + t * t,
            )
        )
    white = [(np.eye(12) / 150, 0.0) for _ in tracks]
    scan = SimpleNamespace(
        tracks=tracks,
        curved=list(range(4)),
        sky=sky,
        norads=np.array([100, 101]),
        sigma=np.array([2.0, 3.0]),
        white=white,
        ou=white,
        rx_basis=[projected_receiver_basis(t["times"]) for t in tracks],
    )

    def hardware(t, beta):
        g = 2 * (t["receiver"] - 1) + int(t["channel"] > 4)
        result = beta[g] + beta[4 + g] * (t["times"] - 150) / 150
        return result + (beta[8] * (t["rf_hz"] / 1e9 - 11.5) if len(beta) == 9 else 0)

    scan.hardware = hardware
    scan.element_basis = lambda j: (
        np.tile(np.array([[[1.0, 0.0, 0.0]], [[0.0, 1.0, 0.0]]]), (1, len(grid), 1)) * 1000,
        np.zeros((2, len(grid), 3)),
    )
    rows = [
        dict(
            component=f"t{i}",
            candidate_index=i // 2,
            candidate_norad=100 + i // 2,
            active_curvature=True,
            split_at=6,
        )
        for i in range(4)
    ]
    seed = dict(
        rows=rows,
        state=dict(
            beta=np.zeros(8), phases=np.array([0.2, -0.3]), extra={}, smooth=np.zeros((2, 11))
        ),
    )
    return scan, seed


@pytest.mark.parametrize(
    "method",
    [
        "shared_phase",
        "family_rate",
        "orbit_em",
        "penalized_split",
        "correlated_noise",
        "receiver_smooth",
    ],
)
def test_complete_jacobian_matches_original_residual_on_two_satellites(method):
    scan, seed = fake_scan()
    p = geometry_problem(scan, seed, method, True, [0.0, 0.0], mean_sigma=10, height_sigma=0)
    x = p.initial.copy()
    x[2:] += 0.01
    actual = jacobian(p, x)
    h = 1e-4
    expected = np.column_stack(
        [(p.residual(x + h * v) - p.residual(x - h * v)) / (2 * h) for v in np.eye(len(x))]
    )
    np.testing.assert_allclose(actual, expected, atol=2e-4, rtol=2e-4)
