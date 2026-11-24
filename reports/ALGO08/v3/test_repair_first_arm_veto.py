"""Exercise the original repair boundary with in-memory fit stand-ins."""

from hashlib import sha256
from types import SimpleNamespace

import pytest

import repair_first_arm_veto as veto
from fallback_accounting_0147 import remainder, stats


REPAIR = '''\
def repair_once(signed, region, measured):
    cpu, wall = 0, 0
    details = measured["repair"] = {}
    repaired = {}
    for arm in ARMS:
        repaired[arm] = arm_finish(signed, arm)
    measured["repair_fit_clocks"] = elapsed(cpu, wall)
    accepted = pair_passes(repaired)
    details.update(attempted_refits=1, status="complete" if accepted else "rejected",
                   reason=None if accepted else "repair_original_joint_pair_gate",
                   finish={arm: readout(record) for arm, record in repaired.items()})
    return (dict(signed, arms=repaired) if accepted else None), details["reason"]
'''
POLICY = '''\
def pair_passes(pair):
    for arm in ARMS:
        tracks = pair[arm]["gates"]["tracks"]
        if not tracks or not all(track["compatible"] for track in tracks):
            return False
    return True
'''


@pytest.fixture
def repair(tmp_path, monkeypatch):
    calls, compatibility = [], dict(c0=True, fitted_c=True)

    def finish(signed, arm):
        calls.append(arm)
        return dict(gates={"tracks": [dict(compatible=compatibility[arm])]})

    namespace = dict(ARMS=("c0", "fitted_c"), arm_finish=finish, elapsed=lambda *args: {},
                     readout=lambda record: record["gates"]["tracks"])
    for name, source in (("POLICY", POLICY), ("REPAIR", REPAIR)):
        path = tmp_path / f"{name.lower()}.py"
        path.write_bytes(source.encode())
        monkeypatch.setattr(veto, f"{name}_SHA256", sha256(path.read_bytes()).hexdigest())
        exec(compile(source, str(path), "exec"), namespace)
    return namespace["repair_once"], calls, compatibility, SimpleNamespace(half_width_km=12.5)


@pytest.mark.parametrize("c0,fitted,expected_arms", [
    (False, True, ["c0"]),
    (False, False, ["c0"]),
    (True, False, ["c0", "fitted_c"]),
    (True, True, ["c0", "fitted_c"]),
    (0, True, ["c0", "fitted_c"]),
])
def test_veto_keeps_original_pair_decision(repair, c0, fitted, expected_arms):
    original, calls, compatibility, region = repair
    compatibility.update(c0=c0, fitted_c=fitted)
    original_receipt, updated_receipt = {}, {}
    expected_result = original({}, region, original_receipt)
    assert calls == ["c0", "fitted_c"]
    calls.clear()
    enabled = veto.with_first_arm_veto(original, enabled=True)
    assert enabled({}, region, updated_receipt) == expected_result
    assert calls == expected_arms
    if len(expected_arms) == 2:
        assert updated_receipt == original_receipt
    else:
        details = updated_receipt["repair"]
        assert details["reason"] == "repair_original_joint_pair_gate"
        assert details["fitted_arms"] == ["c0"]
        assert details["skipped_fit_arms"] == ["fitted_c"]
        assert set(details["finish"]) == {"c0"}


def test_disabled_and_unpinned_sources(repair, monkeypatch):
    original, *_ = repair
    monkeypatch.setattr(veto, "REPAIR_SHA256", "invalid pin")
    assert veto.with_first_arm_veto(original) is original
    with pytest.raises(ValueError, match="original charted repair and policy sources"):
        veto.with_first_arm_veto(original, enabled=True)


def test_accounting_rejects_scopes_that_cannot_be_disjoint():
    total = dict(cpu_s=8, elapsed_s=10)
    fit = dict(cpu_s=2, elapsed_s=3)
    fallback = dict(cpu_s=5, elapsed_s=7)
    assert remainder(total, fit, fallback) == dict(cpu_s=1, elapsed_s=0)
    with pytest.raises(ValueError, match="disjoint"):
        remainder(total, fit, fallback, fit)


def test_panel_keeps_each_denominator_matched():
    result = stats([(8, 2), (2, 4)])
    assert result["summed_ratio"] == 10 / 6
    assert result["median_ratio"] == 1 / (0.5 * (2 / 8 + 4 / 2))
    assert result["excess_s"] == 1
