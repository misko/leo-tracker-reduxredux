"""A calibrated prediction only prunes clearly distant timing-gap work."""

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import gap_prediction as screen


def case():
    ids = [f"p{i}" for i in range(13)]
    times = np.array([*range(12), 18.0])
    parent = dict(observation_ids=ids, times=times, values=np.zeros(13),
                  key="parent", receiver=1, channel=1, rf_hz=11.5e9,
                  source_id="test", pieces=[], residual_rms_hz=1.0)
    scan = SimpleNamespace(tracks=[parent, dict(observation_ids=["old0"]),
                                  dict(observation_ids=["old1"])],
                           norads=np.array([101, 102]), white=[None] * 3,
                           rx_basis=[None] * 3)
    problems = {arm: (SimpleNamespace(arm=arm, scan=scan, members=[1, 2],
                        rows=[dict(candidate_index=0), dict(candidate_index=1)],
                        slices=[slice(0, 1), slice(1, 2)], keep=np.array([True, True])),
                     np.zeros(2)) for arm in screen.ARMS}
    context = dict(scan=scan, problems=problems, entries=[])
    inventory = dict(tracks=[dict(track_id="parent", track_index=0)],
                     policy={arm: dict(proposed_associated_ids=["old0", "old1"])
                             for arm in screen.ARMS})
    observations = [dict(observation_id=oid, time_s=float(t), measured_cfo_hz=0.0,
                         receiver=1, channel=1, actual_rf_hz=11.5e9)
                    for oid, t in zip(ids, times, strict=True)]
    targets = [dict(track_id="parent", branch_id="99d3910a50776a009ba3", points=12)]
    owners = {arm: {"old0": 101, "old1": 102} for arm in screen.ARMS}
    return context, inventory, observations, owners, targets


def posterior(means, covariance=None, invisible=False):
    def predict(d, p, x, i, j):
        n = len(d["scan"].tracks[i]["times"])
        return (np.full((1, n), means[p.arm][j]),
                np.array([np.eye(n) if covariance is None else covariance]),
                np.array([-np.inf if invisible else 0.0]), np.array([2.5]),
                np.array([-1.0 if invisible else 20.0]),
                dict(kind="existing_shared_posterior", active_curved_family=True))
    return predict


def test_profiles_integer_alias_and_preserves_unexplained_frequency_error():
    result = screen.predictive_distance(np.full(4, screen.PERIOD + 2), np.zeros(4), np.eye(4))
    assert result["alias"] == -1
    assert result["predictive_standard_deviations"] == pytest.approx(2)
    assert result["raw_RMS_hz"] == pytest.approx(2)
    assert result["quadratic"] == pytest.approx(16)


def test_alias_profile_uses_correlated_covariance():
    observed = np.array([0.49, 0.9]) * screen.PERIOD
    result = screen.predictive_distance(observed, np.zeros(2), np.diag([1.0, 1e12]))
    assert result["alias"] == 0


def test_retains_any_plausible_arm_and_accepted_family_without_changing_inputs(monkeypatch):
    args = case()
    context, inventory, observations, owners, targets = args
    before = deepcopy((inventory, observations, owners, targets))
    monkeypatch.setattr(screen, "prediction_models", posterior(
        dict(c0=[20.0, 20.0], fitted_c=[20.0, 4.0])))
    result = screen.screen_timing_targets(*args)
    assert result["targets"] == targets
    assert result["rows"][0]["retained"]
    assert result["rows"][0]["predictions"][1]["arms"]["fitted_c"]["phase_s"] == 2.5
    assert (inventory, observations, owners, targets) == before
    assert len(context["scan"].tracks) == 3
    assert all(p.scan is context["scan"] for p, _ in context["problems"].values())
    assert result["no_GPS_inference"] and result["causal_only"]


def test_rejects_only_when_every_accepted_prediction_is_distant(monkeypatch):
    monkeypatch.setattr(screen, "prediction_models", posterior(
        dict(c0=[6.0, 20.0], fitted_c=[20.0, 20.0])))
    result = screen.screen_timing_targets(*case())
    assert result["targets"] == []
    assert result["rows"][0]["reason"] == "all accepted-family predictions distant"


def test_keeps_full_prediction_covariance_instead_of_raw_rms_gate(monkeypatch):
    covariance = np.eye(12) + np.ones((12, 12)) * 300.0 ** 2
    monkeypatch.setattr(screen, "prediction_models", posterior(
        dict(c0=[3000.0, 3000.0], fitted_c=[3000.0, 3000.0]), covariance))
    args = case()
    result = screen.screen_timing_targets(*args)
    assert result["targets"] == args[-1]
    assert result["rows"][0]["predictions"][0]["arms"]["c0"]["raw_RMS_hz"] == 3000


def test_retains_when_shared_calibration_is_absent_or_unobservable(monkeypatch):
    args = case()
    args[3]["fitted_c"] = {"other": 999}
    assert screen.screen_timing_targets(*args)["targets"] == args[-1]
    monkeypatch.setattr(screen, "prediction_models", posterior(
        dict(c0=[20.0, 20.0], fitted_c=[20.0, 20.0]), invisible=True))
    args = case()
    result = screen.screen_timing_targets(*args)
    assert result["targets"] == args[-1]
    assert result["rows"][0]["reason"] == "no observable shared active calibration"


def test_inactive_family_cannot_supply_a_distant_prediction(monkeypatch):
    args = case()
    for p, _ in args[0]["problems"].values():
        p.keep[0] = False
    monkeypatch.setattr(screen, "prediction_models", posterior(
        dict(c0=[20.0, 1.0], fitted_c=[20.0, 1.0])))
    result = screen.screen_timing_targets(*args)
    assert result["targets"] == args[-1]
    assert [p["norad"] for p in result["rows"][0]["predictions"]] == [102]


def test_bad_prediction_and_unmatched_arms_raise(monkeypatch):
    with pytest.raises(ValueError):
        screen.predictive_distance([0.0], [np.nan], [[1.0]])
    with pytest.raises(np.linalg.LinAlgError):
        screen.predictive_distance([0.0], [0.0], [[-1.0]])
    args = case()
    del args[3]["c0"]
    with pytest.raises(ValueError):
        screen.screen_timing_targets(*args)
