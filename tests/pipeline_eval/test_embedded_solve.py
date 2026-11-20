"""Compare the compiled arrowhead solver with the receiver's real BVLS reference."""

import json
import subprocess
from dataclasses import replace

import numpy as np
import pytest

from tools.pipeline_eval.qualification.embedded_solve import RUNNER, comparison, packet, synthetic
from tools.pipeline_eval.variants import embedded_solve as small
from tools.pipeline_eval.variants import robust_em as lean
from tools.pipeline_eval.variants.projected_fit import Region


@pytest.fixture(scope="module")
def kernel(tmp_path_factory):
    binary = tmp_path_factory.mktemp("embedded-solve") / "kernel.so"
    small.compile_library(binary)
    return small.Kernel(binary)


@pytest.mark.parametrize("arm", lean.ARMS)
def test_bound_active_shared_and_orbit_coordinates_match_scipy(kernel, arm):
    rows, n, half = synthetic()
    stats = small.statistics(rows, half, arm)
    result = kernel(stats)
    details = comparison(rows, n + 4, half, arm, stats, result)
    assert details["active_lower"] == details["scipy_active_lower"]
    assert details["active_upper"] == details["scipy_active_upper"]
    width = len(stats.rhs)
    assert 1 in details["active_lower"] and 0 in details["active_upper"]
    assert width + 1 in details["active_lower"] and width in details["active_upper"]
    assert result.bound_updates >= 4
    assert result.optimality < 1e-9
    assert details["maximum_coefficient_delta"] < 1e-9
    assert abs(details["rms_delta_hz"]) < 1e-9
    assert abs(details["score_delta"]) < 1e-8
    assert abs(details["radius_delta_km"]) < 1e-9
    assert not small.state(stats, result.coefficients, n + 4).phase[-4:].any()


def test_releases_a_bound_without_requiring_a_dense_orbit_gram(kernel):
    gram = np.eye(10)
    rhs = np.zeros(10)
    gram[:2, :2] = [[1, -2], [-2, 5]]
    rhs[:2] = [-2, 6.5]
    stats = small.Statistics(gram, rhs, np.zeros((0, 12)), np.ones(10), (), 0, 0.0)
    solved = kernel(stats)
    assert np.allclose(solved.coefficients[:2], [0.0, 1.0])
    assert solved.bound_updates == 3
    assert solved.optimality < 1e-9
    assert np.allclose(solved.position_covariance, np.linalg.inv(gram)[:2, :2])


def test_nonfinite_input_cannot_certify_a_solution(kernel):
    rhs = np.zeros(10)
    rhs[0] = np.nan
    stats = small.Statistics(np.eye(10), rhs, np.zeros((0, 12)), np.ones(10), (), 0, 0.0)
    with pytest.raises(ArithmeticError, match="did not certify convergence"):
        kernel(stats)


def test_standalone_runner_replays_step_fractions_and_coordinates(kernel, tmp_path):
    rows, _, half = synthetic()
    stats = small.statistics(rows, half, "fitted_c")
    opposite = stats.orbits.copy()
    opposite[:, -1] *= -1
    reflected = replace(stats, rhs=-stats.rhs, orbits=opposite)
    region = Region("equator", (0, 0), np.array([6378.137, 0, 0]), np.array([[0, 1, 0], [0, 0, 1]]))
    payload = packet(region, [dict(stats=stats, alpha=1), dict(stats=reflected, alpha=0.25)])
    binary = tmp_path / "standalone"
    subprocess.run(
        ["cc", *small.BUILD_FLAGS, str(small.SOURCE), str(RUNNER), "-lm", "-o", str(binary)],
        check=True,
    )
    terminal = subprocess.run([binary, "3"], input=payload, capture_output=True, check=True)
    result = json.loads(terminal.stdout)
    expected = kernel(stats).coefficients * 0.5
    assert result["linearizations"] == 2
    assert np.allclose(result["coefficients"], expected, rtol=0, atol=1e-12)
    assert np.allclose(result["latlon"], region.site(expected[:2])[1], rtol=0, atol=1e-14)
