"""Frame-linked bias correlation preserves marginal variance and counts data once."""

import importlib
import sys
from pathlib import Path

import numpy as np
from test_dsx01_rf_clock_tool import problem_inputs


def test_bias_correlation_preserves_diagonal_and_independent_control_matches_marginal_oracle():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        tool = importlib.import_module("prototype_dsx01_frame_bias")
        marg = importlib.import_module("prototype_dsx01_orbit_marginal")
    finally:
        sys.path.remove(path)
    scan, seed = problem_inputs()
    links = [[0, 2], [1, 3]]
    base = tool.FrameBiasFamilies(
        scan, seed, "shared_phase", False, (0, 0), independent_sigma=1000, provided_links=links
    )
    linked = tool.FrameBiasFamilies(
        scan, seed, "shared_phase", False, (0, 0), independent_sigma=100, provided_links=links
    )
    oracle = marg.MarginalFamilies(
        scan, seed, "shared_phase", False, (0, 0), kind="none", likelihood="student"
    )
    r0 = base.residual(base.initial)
    r1 = oracle.residual(oracle.initial)
    np.testing.assert_allclose(r0 @ r0, r1 @ r1, rtol=1e-10)
    a, b = base.blocks[0]["covariance"], linked.blocks[0]["covariance"]
    np.testing.assert_allclose(np.diag(a), np.diag(b))
    # Matching first samples in RX1 and RX2, same CH: shared uncertainty
    # cancels from a receiver difference, while the marginal variance is fixed.
    i, j = 0, 62
    independent_difference = a[i, i] + a[j, j] - 2 * a[i, j]
    linked_difference = b[i, i] + b[j, j] - 2 * b[i, j]
    assert independent_difference == 2 * (150**2 + 1000**2)
    assert linked_difference == 2 * (150**2 + 100**2)
    assert len(base.flat_times) == 4 * 31 and len(base.initial) == len(linked.initial)


def test_association_screen_uses_member_bias_scale_for_linked_and_unlinked_curves(monkeypatch):
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        tool = importlib.import_module("prototype_dsx01_frame_bias")
        reporter = importlib.import_module("report_dsx01_model_iterations")
    finally:
        sys.path.remove(path)
    scan, seed = problem_inputs()
    p = tool.FrameBiasFamilies(
        scan, seed, "shared_phase", False, (0, 0), independent_sigma=100, provided_links=[[0, 2]]
    )
    fit = dict(
        rows=p.rows,
        state=p.decode(p.initial),
        east_north_km=[0, 0],
        aliases=p.alias,
        fits=[dict(parameters=p.initial, score=0)],
    )
    seen = []
    original = reporter.profile

    def record(*args, **kwargs):
        seen.append(kwargs["bias_sigma"])
        return original(*args, **kwargs)

    monkeypatch.setattr(reporter, "profile", record)
    reporter.nominated_metrics(
        scan,
        dict(fit=fit, method="shared_phase", arm="c0"),
        problem_factory=lambda *args: tool.FrameBiasFamilies(
            *args, independent_sigma=100, provided_links=[[0, 2]]
        ),
    )
    assert seen == [100, 1000, 100, 1000]
