from types import SimpleNamespace

import numpy as np
import pytest

from reports.ALGO08.v3 import endpoint_track_repair as variant
from reports.ALGO08.v3.fragment_gate_cross import local_gate


def sample(outlier):
    times = np.linspace(0, 35, 110)
    residual = np.random.default_rng(0).normal(0., 30., len(times))
    if outlier is not None:
        residual[outlier] = 900
    orbit = 10*(times-17.5)**2
    return dict(ids=np.array([str(i) for i in range(len(times))]), times=times, orbit_hz=orbit,
                raw_hz=orbit+residual, hardware_hz=np.zeros(len(times)), smooth_hz=np.zeros(len(times)),
                residual_hz=residual, elevation=np.full(len(times), 30.), alias=0, mask=np.ones(len(times), bool))


def gates(fragment):
    ids = fragment["ids"].tolist()
    return dict(component="synthetic", observation_ids=ids, **local_gate(fragment, ids))


def pair(fragment):
    row = gates(fragment)
    return {arm: dict(gates={"tracks": [row]}, linear_gates=[]) for arm in variant.ARMS}


def test_interior_outlier_does_not_authorize_an_interior_deletion():
    fragment = sample(3)
    assert variant.failing_pair(pair(fragment)) is not None
    ids = fragment["ids"].tolist()
    assert local_gate(fragment, ids[:3]+ids[4:])["compatible"]
    tested = variant.trim_choices(fragment, ids)
    assert set(tested) == {"first", "last"}
    assert variant.unique_endpoint(dict.fromkeys(variant.ARMS, tested)) is None


@pytest.mark.parametrize(("outlier", "end"), [(0, "first"), (-1, "last")])
def test_each_unique_endpoint_can_clear_the_released_local_gates(outlier, end):
    fragment = sample(outlier)
    assert variant.failing_pair(pair(fragment)) is not None
    tested = variant.trim_choices(fragment, fragment["ids"].tolist())
    assert variant.unique_endpoint(dict.fromkeys(variant.ARMS, tested)) == end


def test_ambiguous_or_disagreeing_endpoints_keep_the_original_route():
    yes, no = {"compatible": True}, {"compatible": False}
    first = {"first": yes, "last": no}
    last = {"first": no, "last": yes}
    both = {"first": yes, "last": yes}
    assert variant.unique_endpoint(dict(c0=first, fitted_c=last)) is None
    assert variant.unique_endpoint(dict(c0=first, fitted_c=both)) is None
    assert variant.unique_endpoint(dict(c0=both, fitted_c=both)) is None


def test_currently_valid_track_bypasses_repair():
    fragment = sample(None)
    assert gates(fragment)["compatible"]
    assert variant.failing_pair(pair(fragment)) is None


def test_unfinished_phase_refit_returns_original_support_and_pays_one_trial(monkeypatch):
    import blind_joint_finish
    import blind_joint_repair

    broken = sample(-1)
    before = pair(broken)
    for record in before.values():
        record.update(endpoint_east_north_km=np.array([1., 2.]), state={"phases": np.array([.1])})
    candidate = dict(scan=None, node={"seed": {"rows": [{"candidate_index": 0}]}}, powers=None, means=None,
                     model=None, entries=[], keep=np.ones(len(broken["ids"]), bool), arms=before)
    yes, no = {"compatible": True}, {"compatible": False}
    checks = {arm: {"endpoints": {"first": no, "last": yes}} for arm in variant.ARMS}
    monkeypatch.setattr(variant, "frozen_choices", lambda *_: ({"first": 0, "last": len(broken["ids"])-1}, checks))
    monkeypatch.setattr(blind_joint_finish, "readout", lambda record: {"phase": record["final_phase_change_s"]})
    attempts, fallbacks = [], []

    def fit(scan, node, keep, arm, phases, powers, means, model, entries, seed):
        attempts.append((arm, keep.copy()))
        return dict(gates={"tracks": [{"compatible": True}]}, linear_gates=[], endpoint_east_north_km=seed,
                    final_phase_change_s=.02 if arm == "fitted_c" else 0.)

    def fallback(first, region, measured):
        fallbacks.append(first["keep"].copy())
        return first, None

    monkeypatch.setattr(blind_joint_finish, "arm_finish", fit)
    monkeypatch.setattr(blind_joint_repair, "repair_once", fallback)
    measured = {}
    region = SimpleNamespace(half_width_km=12.5)
    with variant.binding():
        assert blind_joint_repair.repair_once(candidate, region, measured) == (candidate, None)
        assert blind_joint_repair.repair_once(candidate, region, {}) == (candidate, None)
    assert measured["endpoint_trim"]["reason"] == "original_paired_gate_after_refit"
    assert [arm for arm, _ in attempts] == list(variant.ARMS)
    assert all(int((~mask).sum()) == 1 and not mask[-1] for _, mask in attempts)
    assert len(fallbacks) == 2 and all(mask.all() for mask in fallbacks)


def test_transfer_counts_a_rejected_attempt_before_history_retry():
    from reports.ALGO08.v3.endpoint_track_repair_0160 import observe_repair

    rejected = {"status": "rejected", "refit_calls": 1}
    research = dict(route_details={"pair_passes": True},
                    recovered_inference={"attempts": [{"endpoint_trim": rejected}]})
    assert observe_repair(research) == [rejected]
    assert observe_repair(dict(route_details={"pair_passes": True}, recovered_inference=None)) == []
