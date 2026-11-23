from types import SimpleNamespace

import pytest

from reports.ALGO08.v3 import owner_loss_0402 as experiment


def record(failed=(), *, tracks=20, points=5, predictive_failed=False):
    rows = [dict(component=f"c{i}", compatible=f"c{i}" not in failed, points=points) for i in range(tracks)]
    linear = [dict(component="p1", compatible=not predictive_failed, points=5)]
    return dict(gates={"tracks": rows}, linear_gates=linear)


def test_scope_requires_one_small_curved_failure_across_the_pair():
    assert experiment.eligible(dict(c0=record(), fitted_c=record({"c1"})))
    assert not experiment.eligible(dict(c0=record({"c1"}), fitted_c=record({"c2"})))
    assert not experiment.eligible(dict(c0=record({"c1"}, tracks=5), fitted_c=record({"c1"}, tracks=5)))
    assert not experiment.eligible(dict(c0=record({"c1"}), fitted_c=record(predictive_failed=True)))


def test_attempt_uses_original_pair_and_adjusted_means_once_for_each_arm(monkeypatch):
    import blind_joint_signed
    import lighter_joint_estimator

    means, prepared, candidate, detail = object(), object(), object(), {}
    calls = []

    def warm(pair, new_means, arm):
        assert pair is candidate and new_means is means
        calls.append(arm)
        return record(), None

    def qualify(p, pair, trace, *, fit_pair):
        assert p is prepared and pair is candidate and trace is detail
        return fit_pair(pair, means)

    monkeypatch.setattr(lighter_joint_estimator, "warm_arm", warm)
    monkeypatch.setattr(blind_joint_signed, "update", qualify)
    assert set(experiment.earlier_signed(prepared, candidate, detail)) == set(experiment.ARMS)
    assert calls == list(experiment.ARMS)
    assert set(detail["refit_gates"]) == set(experiment.ARMS)


def test_warm_rejection_has_no_extra_cold_fit(monkeypatch):
    import blind_joint_signed
    import lighter_joint_estimator

    monkeypatch.setattr(blind_joint_signed, "update", lambda _, c, d, *, fit_pair: fit_pair(c, None))
    monkeypatch.setattr(lighter_joint_estimator, "warm_arm", lambda *_: (None, "unfinished"))
    detail = {}
    with pytest.raises(ValueError, match="unaligned warm"):
        experiment.earlier_signed(SimpleNamespace(), {}, detail)
    assert detail["warm_reasons"] == dict.fromkeys(experiment.ARMS, "unfinished")
