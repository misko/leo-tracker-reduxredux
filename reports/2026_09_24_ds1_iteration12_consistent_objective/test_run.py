from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


def module():
    path = Path(__file__).parent / "run.py"
    spec = importlib.util.spec_from_file_location("i12test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_profile_uses_cap800_loss_without_prior_in_selection():
    m = module()
    support = SimpleNamespace(
        measured=np.asarray([0.0, 100.0, 0.0, 100.0]),
        nominal=np.zeros(4),
        sensitivity_hz_s=np.zeros(4),
        age_h=np.ones(4),
        source=np.asarray(["1"] * 4, dtype=object),
        track=np.asarray(["track"] * 4, dtype=object),
        weights={"track": 1},
    )
    fit = m.profile_consistent(support)
    expected = (50.0 / 800.0) ** 2
    assert fit["selection_objective"] == pytest.approx(expected)
    assert fit["full_observation_capped_loss"] == pytest.approx(expected)
    assert fit["full_observation_capped_rms_hz"] == pytest.approx(50.0)


def test_multiseed_lattice_is_deduplicated_and_symmetric():
    m = module()
    origin = {"latitude_deg": 37.0, "longitude_deg": -122.0}
    rows = m.lattice([origin, origin], 0.1, origin)
    assert len(rows) == 9
    assert sorted({round(row["east_km_from_iteration10"], 6) for row in rows}) == pytest.approx(
        [-0.1, 0.0, 0.1], abs=1e-5
    )
    assert sorted({round(row["north_km_from_iteration10"], 6) for row in rows}) == pytest.approx(
        [-0.1, 0.0, 0.1], abs=1e-5
    )


def test_exact_selection_uses_equal_weight_cap800_loss():
    m = module()
    point = {
        "latitude_deg": 1.0,
        "longitude_deg": 2.0,
        "east_km_from_iteration10": 0.0,
        "north_km_from_iteration10": 0.0,
        "balanced_proposal_objective": 0.2,
    }

    def row(group: str, tau: float, loss: float):
        return {
            **point,
            "group_id": group,
            "tau_s": tau,
            "exact_comparison": {
                "exact_full_observation_capped_loss": loss,
                "exact_sgp4_gate": {"passed": True},
            },
        }

    audits = [
        row(m.GROUPS[0], -1.0, 0.04),
        row(m.GROUPS[0], -0.5, 0.05),
        row(m.GROUPS[1], -1.0, 0.12),
        row(m.GROUPS[1], -0.5, 0.10),
    ]
    selected = m.select(audits, [point])[0]
    assert selected["balanced_exact_capped_loss"] == pytest.approx(0.07)
    assert selected["best_exact_by_group"][m.GROUPS[0]]["tau_s"] == -1.0
    assert selected["best_exact_by_group"][m.GROUPS[1]]["tau_s"] == -0.5


def test_combine_rejects_nonconverged_rows_and_limit_is_established_value():
    m = module()
    assert m.MAX_ITERATIONS == 300
    point = {
        "latitude_deg": 1.0,
        "longitude_deg": 2.0,
        "east_km_from_iteration10": 0.0,
        "north_km_from_iteration10": 0.0,
    }

    def proposal(tau: float, converged: bool):
        return {
            "tau_s": tau,
            "fit": {"converged": converged, "selection_objective": 0.1},
        }

    scans = [
        {**point, "group_id": m.GROUPS[0], "rows": [proposal(-1.0, True), proposal(-0.5, False)]},
        {**point, "group_id": m.GROUPS[1], "rows": [proposal(-1.0, True), proposal(-0.5, True)]},
    ]
    with pytest.raises(ValueError, match="insufficient converged"):
        m.combine([point], scans)
