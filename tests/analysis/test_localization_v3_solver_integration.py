"""Integrated solver/geometry changes against independently frozen calculations."""

import hashlib
from pathlib import Path

import algo07v3_presolver_discovery_likelihood_oracle as discovery_oracle
import algo07v3_presolver_hierarchical_oracle as kernel_oracle
import algo07v3_presolver_position_oracle as position_oracle
import numpy as np
import pytest
from probe_algo07v3_assembly import exact_result

from leo.analysis.localization_v3 import hierarchical
from leo.analysis.localization_v3.discovery_likelihood import DiscoveryPosition
from leo.analysis.localization_v3.position import NormalPosition
from tests.analysis.test_localization_v3_position import prepared


@pytest.fixture()
def originals(monkeypatch):
    bindings = {
        kernel_oracle: "faaf95e43cea964ffd9d70673e954e627c0a8a5439ca2ccc1a271335afa4b63a",
        position_oracle: "450fb338de783dbee8103208be748982c61d1ca2e2afcece4166f156b57dd0f5",
        discovery_oracle: "e34069c905652a62187d797e277f9cd8bfb3b0033278981fc66f21fc3eb4c3d0",
    }
    for module, digest in bindings.items():
        assert hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() == digest
    # Frozen old calculations use the frozen old kernel, not the new runtime.
    for module in (position_oracle, discovery_oracle):
        monkeypatch.setattr(module, "hierarchical_bound", kernel_oracle.hierarchical_bound)
    return {
        NormalPosition: position_oracle.NormalPosition.calculate,
        DiscoveryPosition: discovery_oracle.DiscoveryPosition.calculate,
    }


@pytest.mark.parametrize("fitted_c", [False, True])
@pytest.mark.parametrize("cls", [NormalPosition, DiscoveryPosition])
@pytest.mark.parametrize("point", [(0.0, 0.0), (1.0, -2.0), (-12.5, 12.5)])
def test_full_position_result_matches_frozen_baseline(originals, fitted_c, cls, point):
    scan, node = prepared()
    if cls is NormalPosition:
        problem = cls(scan, node, 150.0, fitted_c)
    else:
        problem = cls(scan, node["seed"], fitted_c, aliases=node["aliases"])
    x = np.array(point)
    exact_result(originals[cls](problem, x), problem.calculate(x))


@pytest.mark.parametrize("fitted_c", [False, True])
def test_masked_position_preserves_all_residuals_and_ownership(originals, fitted_c):
    scan, node = prepared()
    prototype = NormalPosition(scan, node, 150.0, fitted_c)
    keep = np.arange(len(prototype.values)) % 3 != 0
    problem = NormalPosition(scan, node, 150.0, fitted_c, keep=keep)
    exact_result(originals[NormalPosition](problem, np.zeros(2)), problem.calculate(np.zeros(2)))
    assert np.array_equal(problem.keep, keep)


def test_lapack_factorization_failure_remains_numerical_failure(monkeypatch):
    monkeypatch.setattr(hierarchical, "dgetrf", lambda root: (root, None, 1))
    with pytest.raises(np.linalg.LinAlgError, match="DGETRF"):
        hierarchical.hierarchical_bound(np.ones(3), np.ones((3, 1)), 1.0, np.zeros(3, int))


def test_lapack_solve_failure_remains_numerical_failure(monkeypatch):
    monkeypatch.setattr(hierarchical, "dgetrs", lambda *args: (None, -1))
    with pytest.raises(np.linalg.LinAlgError, match="DGETRS"):
        hierarchical.hierarchical_bound(np.ones(3), np.ones((3, 1)), 1.0, np.zeros(3, int))
