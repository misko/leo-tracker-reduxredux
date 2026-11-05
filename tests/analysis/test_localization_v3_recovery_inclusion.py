from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import recovery_gates, recovery_inclusion
from leo.analysis.localization_v3.new_family import integration_grid
from leo.analysis.localization_v3.recovery_acceptance import (
    numerical_only,
    scoped_pair,
    shared_family_route,
    single_candidate,
)


def test_expanded_phase_grid_requires_existing_causal_bank_support():
    grid = integration_grid([0, 40], [-30, 70], 0.025, 30)
    assert len(grid) == 2401 and grid[0] == -30 and grid[-1] == 30
    with pytest.raises(ValueError, match="causal orbit bank"):
        integration_grid([0, 40], [-29, 70], 0.025, 30)
    for step, limit in [(0, 15), (np.nan, 15), (0.1, 31), (0.1, 14)]:
        with pytest.raises(ValueError):
            integration_grid([0, 40], [-30, 70], step, limit)


def inclusion_case():
    inventory = dict(
        policy={a: dict(proposed_associated_ids=["old", "postfit"]) for a in ("c0", "fitted_c")},
        publication_support={a: dict(owners={"old": 10}) for a in ("c0", "fitted_c")},
    )
    targets = [dict(observation_ids=["new"], norad=20)]
    row = dict(
        endpoint_east_north_km=[1, 2],
        endpoint_latlon=[37, -122],
        negative_twice_elbo=123,
        proposed_owners={"old": 10, "postfit": 30, "new": 20},
        history=[dict(fit=dict(stopped="small_step_and_improvement"))],
    )
    arms = {a: deepcopy(row) for a in ("c0", "fitted_c")}
    trial = dict(
        protocol=dict(targets=targets),
        control=dict(arms=deepcopy(arms), paired_valid=True),
        target_0=dict(arms=arms, paired_valid=True),
    )
    audit = dict(all_verified=True, rows=[])
    return inventory, targets, trial, audit


def test_scoped_publication_does_not_credit_unscored_postfit_points():
    inv, targets, trial, _ = inclusion_case()
    arms = trial["target_0"]["arms"]
    owners = {a: r["proposed_owners"] for a, r in arms.items()}
    result = scoped_pair(inv, arms, owners, targets)
    assert result["c0"]["associated_ids"] == ["new", "old"]
    assert result["fitted_c"]["added_points"] == 1
    owners["fitted_c"]["new"] = 999
    with pytest.raises(ValueError, match="Target ownership"):
        scoped_pair(inv, arms, owners, targets)


def test_scoped_publication_requires_retained_ids_and_matched_owners():
    inv, targets, trial, _ = inclusion_case()
    arms = trial["target_0"]["arms"]
    owners = {a: r["proposed_owners"] for a, r in arms.items()}
    owners["c0"].pop("old")
    with pytest.raises(ValueError, match="Lost incumbent"):
        scoped_pair(inv, arms, owners, targets)
    owners["c0"]["old"] = 999
    with pytest.raises(ValueError, match="Paired observation"):
        scoped_pair(inv, arms, owners, targets)


def test_shared_fit_requires_optimizer_completion_for_both_control_arms():
    inv, _, trial, audit = inclusion_case()
    assert single_candidate(inv, trial, audit, True)["kind"] == "shared_family"
    trial["control"]["arms"]["fitted_c"]["history"][-1]["fit"] = dict(success=False)
    assert single_candidate(inv, trial, audit, True) is None
    trial["control"]["arms"]["fitted_c"]["history"] = []
    assert single_candidate(inv, trial, audit, True) is None


def test_numerical_retry_cannot_relax_physical_or_owner_or_quadrature_gates():
    row = dict(
        gates=dict(tracks=[dict(compatible=True)]),
        linear_gates=[],
        final_phase_change_s=0.001,
        endpoint_east_north_km=[0, 0],
        lost_points=0,
        history=[dict(success=False)],
        phase_resolution_audit=dict(local_agreement=True),
        family=dict(phase_boundary_mass=0),
    )
    control = dict(arms={a: deepcopy(row) for a in ("c0", "fitted_c")}, paired_valid=False)
    addition = deepcopy(control)
    assert numerical_only(control, addition, dict(all_verified=True))
    assert not numerical_only(control, addition, dict(all_verified=False))
    for field, value in [
        ("lost_points", 1),
        ("phase_resolution_audit", dict(local_agreement=False)),
        ("family", dict(phase_boundary_mass=0.02)),
        ("gates", dict(tracks=[dict(compatible=False)])),
    ]:
        changed = deepcopy(addition)
        changed["arms"]["fitted_c"][field] = value
        assert not numerical_only(control, changed, dict(all_verified=True))


def test_unknown_predictive_prior_cannot_choose_an_inclusion_route():
    folds = [
        dict(
            proposals=[
                dict(
                    norad=20, arms={a: dict(prior=dict(kind="unknown")) for a in ("c0", "fitted_c")}
                )
            ]
        )
    ]
    with pytest.raises(ValueError, match="unknown or missing"):
        shared_family_route(folds, 20)


def test_exact_orbit_replay_restores_likelihood_even_when_gate_raises(monkeypatch):
    def calculate(_):
        return dict(conditional_residual_hz=np.zeros(0))

    def frequency(_):
        return np.zeros(0), np.zeros(0)
    p = SimpleNamespace(
        calculate=calculate,
        conditional_frequency=frequency,
        explicit_phase_family=0,
        rows=[],
        members=[],
        slices=[],
    )

    def failing_gate(p, x, entries):
        assert p.calculate is not calculate
        raise ValueError("test gate failure")

    monkeypatch.setattr(recovery_gates, "gate_slacks", failing_gate)
    with pytest.raises(ValueError, match="test gate failure"):
        recovery_gates.exact_gate_replay(p, np.zeros(2), [])
    assert p.calculate is calculate and p.conditional_frequency is frequency


def test_identity_failure_never_runs_a_position_fit(monkeypatch):
    monkeypatch.setattr(
        recovery_inclusion, "identity_consensus", lambda *a, **kw: dict(status="unstable_identity")
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Unstable identity must not be fit")

    monkeypatch.setattr(recovery_inclusion, "fit_shared", forbidden)
    monkeypatch.setattr(recovery_inclusion, "fit_new", forbidden)
    result = recovery_inclusion.include_annotation({}, {}, dict(result=dict(folds=[])))
    assert result == dict(
        status="unstable_identity", annotation=dict(status="unstable_identity"), selected=None
    )
