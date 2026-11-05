from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import selected_incumbent as replay


def fixture(monkeypatch, *, mixture=False):
    problem = SimpleNamespace(
        scan=SimpleNamespace(index=[0]), calculate=lambda x: dict(negative_twice_elbo=100.0)
    )
    d = dict(
        scan=problem.scan,
        node={},
        keep=np.array([True]),
        powers=[1.0],
        means=[0.0],
        model={},
        entries=[],
        problems={a: (problem, [0, 0]) for a in replay.ARMS},
    )
    owners = {a: dict(old=10, **({"new": 20} if mixture else {})) for a in replay.ARMS}
    arms = {
        a: dict(endpoint_east_north_km=[1, 2], negative_twice_elbo=107.0 if mixture else 100.0)
        for a in replay.ARMS
    }
    monkeypatch.setattr(
        replay, "memberships", lambda *a: (None, None, None, {"old": 10, "extra": 99})
    )
    monkeypatch.setattr(replay, "original_graph_view", lambda p, count: p)
    monkeypatch.setattr(replay, "make_event_problem", lambda *a, **kw: problem)
    monkeypatch.setattr(replay, "attach_recovery_predictive", lambda *a: None)
    monkeypatch.setattr(replay, "cached", lambda p: p)
    return d, arms, owners


def test_baseline_replay_audits_but_does_not_adopt_incidental_extensions(monkeypatch):
    d, arms, owners = fixture(monkeypatch)
    result = replay.reconstruct_incumbent(d, arms, owners)
    assert result is not d and result["entries"] is not d["entries"]
    assert "replay_checks" not in d
    assert owners == {a: {"old": 10} for a in replay.ARMS}
    assert all(
        c["incidental_unpublished_extensions_not_adopted"] == 1
        for c in result["replay_checks"].values()
    )


@pytest.mark.parametrize("failure", ["objective", "nan", "owner", "missing_arm"])
def test_changed_incumbent_fails_reconstruction(monkeypatch, failure):
    d, arms, owners = fixture(monkeypatch)
    if failure == "objective":
        arms["c0"]["negative_twice_elbo"] += 0.01
    elif failure == "nan":
        arms["c0"]["negative_twice_elbo"] = float("nan")
    elif failure == "owner":
        owners["fitted_c"]["old"] = 123
    else:
        del arms["fitted_c"]
    with pytest.raises(ValueError):
        replay.reconstruct_incumbent(d, arms, owners)


def test_new_family_keeps_its_predictive_mixture_in_the_selected_objective(monkeypatch):
    d, arms, owners = fixture(monkeypatch, mixture=True)
    entry = dict(observation_ids=["new"], norad=20)
    family = SimpleNamespace(entries=[entry], evaluate=lambda *a: 7.0)
    monkeypatch.setattr(replay, "NewFamily", lambda *a, **kw: family)
    selection = dict(
        kind="new_family",
        trial=dict(
            protocol=dict(targets=[entry], family_prior=dict(phase_step_s=0.025)),
            new_family=dict(
                arms={
                    a: dict(
                        phase_reference=[0], incumbent_objective=100.0, negative_twice_elbo=107.0
                    )
                    for a in replay.ARMS
                }
            ),
        ),
    )
    result = replay.reconstruct_incumbent(d, arms, owners, selection=selection)
    assert result["families"] == [family]
    assert all(
        c["full_selected_likelihood_difference"] == 0 for c in result["replay_checks"].values()
    )
    family.evaluate = lambda *a: 0.0
    with pytest.raises(ValueError, match="full selected likelihood"):
        replay.reconstruct_incumbent(d, arms, owners, selection=selection)


def test_joint_replay_uses_shared_density_with_original_contraction_order(monkeypatch):
    d, arms, owners = fixture(monkeypatch)
    calls = []
    for a in replay.ARMS:
        arms[a]["negative_twice_elbo"] = 115.0
        owners[a].update(first=20, second=30)
    targets = [[dict(observation_ids=[key], norad=n)] for key, n in [("first", 20), ("second", 30)]]
    monkeypatch.setattr(
        replay, "NewFamily", lambda scan, entries, *a, **kw: SimpleNamespace(entries=entries)
    )
    monkeypatch.setattr(replay, "joint_inputs", lambda *a: ("shared covariance",))
    monkeypatch.setattr(
        replay,
        "two_family_phase_evidence",
        lambda *a, **kw: calls.append((a, kw)) or dict(negative_twice_log_density=15.0),
    )
    selection = dict(
        kind="joint",
        trials={
            a: dict(
                protocol=dict(targets=targets, phase_step_s=0.025),
                result=dict(
                    phase_reference=[0], incumbent_objective=100.0, negative_twice_elbo=115.0
                ),
            )
            for a in replay.ARMS
        },
    )
    result = replay.reconstruct_incumbent(d, arms, owners, selection=selection)
    assert calls == [(("shared covariance",), dict(optimize_contractions=False))] * 2
    assert len(result["families"]) == 2


def test_missing_or_changed_gap_source_is_not_reconstructed(monkeypatch):
    d, *_ = fixture(monkeypatch)
    protocol = dict(native_sources=["digest"])
    with pytest.raises(ValueError, match="owned annotation"):
        replay.replay_view(d, {}, protocol, [], [])
    annotation = dict(
        result=dict(track_id="b"),
        protocol=dict(target=dict(gap_source_sha256="wrong")),
        gap_source={},
    )
    with pytest.raises(ValueError, match="source changed"):
        replay.replay_view(d, {}, protocol, [annotation], [])
