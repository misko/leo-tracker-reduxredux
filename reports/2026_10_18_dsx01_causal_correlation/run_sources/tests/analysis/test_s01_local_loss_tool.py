"""Numerical controls for location axes and finite-difference loss diagnostics."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def tool():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        yield (
            importlib.import_module("probe_s01_local_loss"),
            importlib.import_module("report_s01_local_loss"),
        )
    finally:
        sys.path.remove(path)


def test_zero_diagnostic_displacement_is_exact_reference_with_different_regional_center(tool):
    probe, _ = tool
    scan = SimpleNamespace(center=(37.5, -122.0), scale=88.3)
    east, north = probe.position(scan, (0, 0))
    np.testing.assert_allclose(
        (scan.center[0] + north / 111, scan.center[1] + east / scan.scale),
        probe.REFERENCE,
        atol=1e-13,
        rtol=0,
    )
    shifted = probe.position(scan, (1, 1))
    assert shifted[0] > east and shifted[1] > north


def test_multiscale_gradient_matches_analytic_quadratic_and_descent_direction(tool):
    _, report = tool
    for h in (0.125, 0.5, 1.0):
        points = [(0, 0), (h, 0), (-h, 0), (0, h), (0, -h)]
        # Minimum is east and south; central gradient is exactly (-12, 8).
        data = {
            p: dict(metrics={"x": dict(score=3 * (p[0] - 2) ** 2 + 2 * (p[1] + 2) ** 2)})
            for p in points
        }
        result = report.gradient(data, "x", h)
        np.testing.assert_allclose(result["central_east_north"], [-12, 8], atol=1e-12)
        positive = np.array(result["positive_east_north"])
        negative = np.array(result["negative_east_north"])
        np.testing.assert_allclose(positive - negative, [6 * h, 4 * h], atol=1e-12)


def test_common_grid_is_unique_bounded_and_contains_all_gradient_probes(tool):
    probe, _ = tool
    points = probe.grid_points()
    assert len(points) == len(set(points))
    assert points[0] == (0, 0)
    assert all(np.linalg.norm(p) <= probe.RADIUS for p in points)
    for h in (0.125, 0.5, 1.0):
        assert {(h, 0), (-h, 0), (0, h), (0, -h)} <= set(points)
