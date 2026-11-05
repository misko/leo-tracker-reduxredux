from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.linalg import block_diag
from scipy.special import logsumexp
from scipy.stats import multivariate_normal

from leo.analysis.localization_v3 import joint_recovery
from leo.analysis.localization_v3.joint_density import two_family_phase_evidence
from leo.analysis.localization_v3.joint_recovery import joint_numerical_only, scoped_membership


@pytest.mark.parametrize("optimized", [True, False])
def test_shared_receiver_covariance_matches_direct_gaussian_integration(optimized):
    rng = np.random.default_rng(93)
    y = [rng.normal(size=3), rng.normal(size=2)]
    means = [rng.normal(size=(3, 3)), rng.normal(size=(4, 2))]
    modes = [rng.normal(size=(3, 3, 2)) * 0.4, rng.normal(size=(4, 2, 1)) * 0.3]
    receiver = rng.normal(size=(5, 2))
    base = np.eye(5) + receiver @ receiver.T
    priors = [np.log([0.2, 0.3, 0.5]), np.log([0.1, 0.2, 0.3, 0.4])]
    visible = [np.array([True, False, True]), np.ones(4, bool)]
    table = np.full((3, 4), -np.inf)
    for i in (0, 2):
        for j in range(4):
            u = block_diag(modes[0][i], modes[1][j])
            table[i, j] = (
                multivariate_normal.logpdf(
                    np.concatenate(y), mean=np.r_[means[0][i], means[1][j]], cov=base + u @ u.T
                )
                + priors[0][i]
                + priors[1][j]
            )
    for chunk in (4, 32768):
        r = two_family_phase_evidence(
            y, means, base, modes, priors, visible, max_pairs=chunk, optimize_contractions=optimized
        )
        assert r["negative_twice_log_density"] == pytest.approx(-2 * logsumexp(table), abs=1e-11)
        np.testing.assert_allclose(
            r["phase_marginals"][0], np.exp(table - logsumexp(table)).sum(axis=1), atol=1e-12
        )
        assert r["receiver_covariance_integrated_once"]


def test_joint_contraction_order_follows_the_stage_policy(monkeypatch):
    from leo.analysis.localization_v3.numerical_policy import NumericalPolicy

    calls = []
    monkeypatch.setattr(
        joint_recovery, "two_family_phase_evidence", lambda *a, **kw: calls.append((a, kw))
    )
    joint_recovery.joint_density({}, "inputs")
    joint_recovery.joint_density({"numerical_policy": NumericalPolicy()}, "inputs")
    assert calls == [(("inputs",), {}), (("inputs",), {"optimize_contractions": False})]


def test_scoped_joint_audit_rejects_unscored_points_entering_fit():
    r = scoped_membership(
        ["old"],
        ["old", "new", "extra"],
        ["new"],
        ["old", "new"],
        {"old": 1},
        {"old": 1, "new": 2, "extra": 3},
    )
    assert r["reviewed_associated_ids"] == ["new", "old"]
    assert r["incidental_unvalidated_ids"] == ["extra"]
    with pytest.raises(ValueError, match="entered the fitted"):
        scoped_membership(
            ["old"],
            ["old", "new", "extra"],
            ["new"],
            ["old", "new", "extra"],
            {"old": 1},
            {"old": 1, "new": 2, "extra": 3},
        )


def test_joint_retry_requires_factorized_physical_audit_too():
    record = dict(
        trial=dict(result=dict(history=[dict(success=False)])),
        audit=dict(
            incumbent_owner_changes=[],
            phase_check=dict(phase_change_s=0.001),
            exact_incumbent_orbits=[dict(all_pass=True)],
            checks=dict(incumbent_and_numerical=False, target_gates=True),
        ),
    )
    experiment = {
        m: {a: deepcopy(record) for a in ("c0", "fitted_c")}
        for m in ("control", "factorized", "joint")
    }
    assert joint_numerical_only(experiment)
    experiment["factorized"]["fitted_c"]["audit"]["checks"]["target_gates"] = False
    assert not joint_numerical_only(experiment)


def test_joint_retry_requires_all_six_completed_records():
    with pytest.raises(KeyError):
        joint_numerical_only({"control": {}})


@pytest.mark.parametrize("optimizer", ["lbfgsb", "powell"])
@pytest.mark.parametrize(
    "method,expected", [("control", 100.0), ("factorized", 120.0), ("joint", 110.0)]
)
def test_endpoint_comparison_does_not_overwrite_fitted_method(
    monkeypatch, optimizer, method, expected
):
    """Reporting both evidence scores must preserve the actual fitted objective."""
    p = SimpleNamespace(
        keep=np.array([True]),
        labels=np.array([0]),
        calculate=lambda _: dict(negative_twice_elbo=100.0, elevation=np.array([10.0])),
        state=lambda _: dict(phases=np.zeros(1)),
    )
    monkeypatch.setattr(
        joint_recovery, "NewFamily", lambda *a, **kw: SimpleNamespace(phases=np.zeros(1))
    )
    monkeypatch.setattr(joint_recovery, "make_event_problem", lambda *a, **kw: p)
    monkeypatch.setattr(joint_recovery, "attach_event_predictive", lambda *a: None)
    monkeypatch.setattr(joint_recovery, "cached", lambda p: p)
    monkeypatch.setattr(joint_recovery, "summary", lambda *a: dict(negative_twice_elbo=100.0))
    monkeypatch.setattr(
        joint_recovery, "evidence", lambda f, p, x, d, m: {"joint": 10.0, "factorized": 20.0}[m]
    )
    monkeypatch.setattr(joint_recovery, "joint_inputs", lambda *a: ())
    monkeypatch.setattr(joint_recovery, "two_family_phase_evidence", lambda *a: {})
    monkeypatch.setattr(
        joint_recovery,
        "minimize",
        lambda objective, x, **kw: SimpleNamespace(
            x=x, fun=objective(x), success=True, message="done", nfev=1
        ),
    )
    d = dict(scan=object(), model={}, means=[0], node={}, keep=[True], powers=[1], entries=[])
    probe = dict(
        protocol=dict(targets=[[], []], phase_step_s=0.0625),
        result=dict(all_individual_replays_verified=True, receiver_calibration_unchanged=True),
    )
    result = joint_recovery.fit_joint(d, probe, "c0", method, optimizer=optimizer)["result"]
    assert result["method"] == method
    assert result["negative_twice_elbo"] == expected
    assert all(r["objective"] == expected for r in result["history"])
