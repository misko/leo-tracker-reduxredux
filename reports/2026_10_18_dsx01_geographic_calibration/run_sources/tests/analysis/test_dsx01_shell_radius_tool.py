"""A shell correction must be shared and keep hardware priors separate."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from test_dsx01_rf_clock_tool import problem_inputs


def test_shell_radius_is_shared_between_distinct_satellites_and_prior_composes(monkeypatch):
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        tool = importlib.import_module("prototype_dsx01_shell_radius")
    finally:
        sys.path.remove(path)
    scan, seed = problem_inputs()
    scan.norads = np.array([100, 101])
    scan.sigma = np.ones(2)
    seed["state"]["phases"] = np.zeros(2)
    for name in ("position_km", "velocity_km_s"):
        scan.sky[name] = np.repeat(scan.sky[name], 2, axis=0)
    for row in seed["rows"][2:]:
        row.update(candidate_index=1, candidate_norad=101)
    scan.elements = {str(n): dict(lines=["dummy", "dummy"]) for n in (100, 101)}
    sat = SimpleNamespace(inclo=np.deg2rad(43), no_kozai=15.3 * 2 * np.pi / 1440)
    monkeypatch.setattr(tool, "Satrec", SimpleNamespace(twoline2rv=lambda *args: sat))
    monkeypatch.setattr(
        tool,
        "reference_motion_basis",
        lambda s, j: (
            np.ones_like(s.sky["position_km"][j]),
            np.zeros_like(s.sky["velocity_km_s"][j]),
        ),
    )
    p = tool.shell_problem(scan, seed, "shared_phase", False, (0, 0))
    assert len(p.shell_groups) == 1
    assert len(next(iter(p.shell_groups.values()))) == 2
    x = p.initial.copy()
    x[-1] = 0.8
    x[p.pairs[0][0]] = 0.4
    state = p.decode(x)
    radius = next(iter(state["shell_radial_km"].values()))
    assert abs(radius - 0.24) < 1e-12
    sky = p.problem.orbit_sky(state)
    np.testing.assert_allclose(
        sky["position_km"][0] - scan.sky["position_km"][0],
        sky["position_km"][1] - scan.sky["position_km"][1],
    )
    r = p.residual(x)
    assert r[0] == 0.8
    start = len(r) - len(p.labels) - 4
    np.testing.assert_allclose(r[start : start + 4], [0.4, 0, 0, 0])


def test_single_satellite_group_has_no_new_radius_parameter(monkeypatch):
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        tool = importlib.import_module("prototype_dsx01_shell_radius")
    finally:
        sys.path.remove(path)
    scan, seed = problem_inputs()
    scan.elements = {"100": dict(lines=["dummy", "dummy"])}
    sat = SimpleNamespace(inclo=np.deg2rad(43), no_kozai=15.3 * 2 * np.pi / 1440)
    monkeypatch.setattr(tool, "Satrec", SimpleNamespace(twoline2rv=lambda *args: sat))
    base = tool.AnchoredFamilies(scan, seed, "shared_phase", False, (0, 0))
    p = tool.ShellFamilies(scan, seed, "shared_phase", False, (0, 0))
    assert not p.shell_groups
    np.testing.assert_allclose(p.residual(p.initial), base.residual(base.initial))
