from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import reassociation_context as context


def test_finite_differences_recover_known_coupled_quadratic():
    hessian = np.array([[4.0, 1.0], [1.0, 3.0]])
    linear = np.array([2.0, -1.0])
    x = np.array([0.3, -0.7])
    gradient, actual = context.derivatives(lambda v: 0.5 * v @ hessian @ v + linear @ v, x)
    np.testing.assert_allclose(gradient, hessian @ x + linear, atol=1e-12)
    np.testing.assert_allclose(actual, hessian, atol=1e-12)


def test_omission_removes_whole_family_and_preserves_other_conditional_attachments(monkeypatch):
    old = SimpleNamespace(
        rows=[dict(candidate_norad=10), dict(candidate_norad=20)], slices=[slice(0, 2), slice(2, 4)]
    )
    entries = [dict(norad=n, component=str(n), candidate_index=i) for i, n in enumerate((10, 20))]
    families = [SimpleNamespace(entries=[dict(norad=n)]) for n in (10, 30)]
    retained = dict(
        keep=np.ones(4, bool),
        problems={"c0": (old, None)},
        entries=entries,
        families=families,
        conditional_components=("10", "20"),
        scan=object(),
        node=object(),
        powers=object(),
        means=object(),
        model=dict(multiplier=2.0),
    )
    calls = []
    problem = object()

    def make(scan, node, keep, arm, reference, powers, means, model, events, **kwargs):
        np.testing.assert_array_equal(keep, [False, False, True, True])
        assert model["multiplier"] == 3.0 and events == []
        return problem

    monkeypatch.setattr(context, "make_event_problem", make)
    monkeypatch.setattr(context, "cached", lambda p: p)
    monkeypatch.setattr(context, "attach_recovery_predictive", lambda p, e, powers: calls.append(e))
    monkeypatch.setattr(
        context,
        "attach_conditional_satellite_refresh",
        lambda p, e, powers, labels: calls.append(labels),
    )
    p, omitted = context.build(retained, "c0", np.zeros(2), omit=10, phase_scale=1.5)
    assert p is problem and omitted["entries"] == [entries[1]]
    assert omitted["families"] == [families[1]] and calls == [[entries[1]], [1]]
    assert retained["keep"].all() and retained["entries"] == entries


def test_final_stage_requests_its_frozen_contraction_order(monkeypatch):
    seen = []
    monkeypatch.setattr(context, "residual_family_score", lambda *a, **kw: seen.append(kw) or 7.0)
    assert context.family_score([], {}, None, None) == 7.0
    assert seen == [dict(optimize_contractions=True)]


def test_rf_trigger_respects_counts_and_ranks_summed_both_arm_influence(monkeypatch):
    # Three families have large influence; one lacks two tracks and is ineligible.
    rows = [dict(candidate_norad=n) for n in (10, 10, 20, 20, 30)]
    base = SimpleNamespace(
        rows=rows,
        slices=[slice(i * 20, (i + 1) * 20) for i in range(5)],
        keep=np.ones(100, bool),
        reference=np.zeros(3),
        omit=None,
    )
    retained = dict(problems={a: (base, np.zeros(2)) for a in ("c0", "fitted_c")})
    monkeypatch.setattr(context, "build", lambda d, a, r, omit: (SimpleNamespace(omit=omit), d))

    def objective(p, d, x):
        shift = {None: 0.0, 10: 1.0, 20: 0.3, 30: 4.0}[p.omit]
        return float(x @ x + 2 * shift * x[0])

    monkeypatch.setattr(context, "objective", objective)
    ranking, selected = context.rank_families(retained)
    assert [row["norad"] for row in ranking] == [30, 10, 20]
    assert selected == [10, 20]
    assert ranking[0]["points"] == 20 and ranking[0]["tracks"] == 1
    assert ranking[1]["rank_score"] == pytest.approx(2.0)


def adoption_fixture(monkeypatch, *, qualified=True):
    problem = SimpleNamespace(
        reference=np.zeros(1), calculate=lambda x: dict(negative_twice_elbo=1.0)
    )
    d = dict(
        problems={a: (problem, np.zeros(2)) for a in ("c0", "fitted_c")},
        replay_checks={},
        families=[],
        scan=object(),
        model={},
    )
    arms = {
        a: dict(endpoint_east_north_km=[0.0, 0.0], negative_twice_elbo=1.0)
        for a in ("c0", "fitted_c")
    }
    owners = {a: {"old": 10} for a in arms}
    entry = dict(observation_ids=["new"], norad=20)
    row = dict(
        endpoint_east_north_km=[1.0, 2.0],
        phase_reference=[0.0],
        negative_twice_elbo=5.0,
        all_checked_gates_pass=True,
    )
    recovery = dict(
        decisions={
            "72h_30s": dict(status="qualified" if qualified else "rejected", trial="t", source="f")
        },
        control={a: dict(all_checked_gates_pass=True) for a in arms},
        trials={"t": dict(status="qualified", entry=entry, arms={a: deepcopy(row) for a in arms})},
    )
    screen = dict(
        targets=[
            dict(
                source=dict(fragment_id="f"),
                summaries=[
                    dict(policy="72h_30s", arms={"c0": dict(folds=dict(full=dict(winner={})))})
                ],
            )
        ]
    )
    monkeypatch.setattr(context, "build", lambda d, a, r: (problem, d))
    monkeypatch.setattr(context, "objective", lambda *a: 5.0)
    monkeypatch.setattr(context, "family_score", lambda *a: 4.0)
    monkeypatch.setattr(context, "add_target", lambda *a: entry)
    monkeypatch.setattr(context, "prediction_scan", lambda s, b: s)
    monkeypatch.setattr(context, "NewFamily", lambda *a, **kw: object())
    return d, arms, owners, recovery, screen


def test_qualified_handoff_replays_full_objective_and_does_not_mutate_published_owners(monkeypatch):
    d, arms, owners, recovery, screen = adoption_fixture(monkeypatch)
    result = context.adopt_additional(lambda: d, arms, owners, None, recovery, screen, {}, [])
    assert result["owners"] == {a: {"old": 10, "new": 20} for a in arms}
    assert owners == {a: {"old": 10} for a in arms}
    assert all(result["replay"]["algo06"][a]["objective_difference"] == 0 for a in arms)
    assert all(arms[a]["negative_twice_elbo"] == 1.0 for a in arms)


@pytest.mark.parametrize("fault", ["score", "control", "collision", "entry"])
def test_corrupt_adopted_trial_cannot_authorize_new_ownership(monkeypatch, fault):
    d, arms, owners, recovery, screen = adoption_fixture(monkeypatch)
    if fault == "score":
        recovery["trials"]["t"]["arms"]["c0"]["negative_twice_elbo"] = 6.0
    elif fault == "control":
        recovery["control"]["fitted_c"]["all_checked_gates_pass"] = False
    elif fault == "collision":
        owners["fitted_c"]["new"] = 99
    else:
        recovery["trials"]["t"]["entry"] = dict(observation_ids=["wrong"], norad=20)
    before = deepcopy(owners)
    with pytest.raises(ValueError):
        context.adopt_additional(lambda: d, arms, owners, None, recovery, screen, {}, [])
    assert owners == before


def test_rejection_preserves_exact_selected_arms_and_owners(monkeypatch):
    d, arms, owners, recovery, screen = adoption_fixture(monkeypatch, qualified=False)
    monkeypatch.setattr(context, "add_target", lambda *a: pytest.fail("Rejected trial appended"))
    result = context.adopt_additional(lambda: d, arms, owners, None, recovery, screen, {}, [])
    assert result["arms"] == arms and result["owners"] == owners
    assert "algo06" not in result["replay"]
