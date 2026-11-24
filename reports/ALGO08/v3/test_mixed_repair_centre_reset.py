"""Test the scoped operation with tiny, fixed-support numerical stand-ins."""

from types import SimpleNamespace
import sys

import numpy as np
import pytest

from mixed_repair_centre_reset import ARMS, eligible, with_reset
from mixed_repair_centre_reset_trial import charted_adapter, digest, witness_sources


def record(norad=10):
    return {"phase_reference": np.array([5., -4.]), "gates": {"tracks": [
        dict(component="track", norad=norad, observation_ids=["one", "two"])]},
            "linear_gates": [dict(component="extra", norad=20, observation_ids=["three"])]}


@pytest.fixture
def inputs():
    trial = {"repair": {"status": "complete", "attempted_refits": 1},
             "signed": {"status": "unqualified", "selection": {"qualified": False}}}
    scan = SimpleNamespace(search_region=SimpleNamespace(half_width_km=12.5))
    ordinary = dict(scan=scan, node=object(), keep=object(), powers=object(), means=object(), model=object(),
                    entries=[object()], arms={arm: record() for arm in ARMS})
    return ordinary, trial


def update(_, ordinary, measured, *, fit_pair=None):
    return ordinary


def test_disabled_is_exactly_original():
    assert with_reset(update, None, None, None) is update


@pytest.mark.parametrize("repair,signed_status,qualified", [
    ("rejected", "unqualified", False), ("complete", "accepted", True),
    ("complete", "rejected", True), ("complete", "unqualified", None),
])
def test_only_an_eligible_original_pair_can_pay(inputs, repair, signed_status, qualified):
    ordinary, trial = inputs
    trial["repair"]["status"] = repair
    trial["signed"] = dict(status=signed_status, selection=dict(qualified=qualified))
    assert not eligible(trial)
    run = with_reset(update, None, None, None, enabled=True)
    assert run({}, ordinary, trial) is ordinary
    assert trial["ordinary_centre_reset"]["status"] == "ineligible"


@pytest.mark.parametrize("admissible,owner_change", [(True, False), (False, False), (True, True)])
def test_trial_resets_both_matching_arms_and_keeps_original_on_veto(inputs, admissible, owner_change):
    ordinary, trial = inputs
    calls, gates = [], []

    def finish(scan, node, keep, arm, reference, powers, means, model, entries, seed):
        for key, observed in locals().copy().items():
            if key in ("scan", "node", "keep", "powers", "means", "model", "entries"):
                assert observed is ordinary[key]
        np.testing.assert_array_equal(reference, np.zeros(2))
        np.testing.assert_array_equal(seed, np.zeros(2))
        calls.append(arm)
        return record(11 if owner_change and arm == "fitted_c" else 10)

    def pair_passes(arms, *, include_linear, half_width_km):
        assert tuple(arms) == ARMS and include_linear and half_width_km == 12.5
        gates.append(True)
        return admissible

    run = with_reset(update, finish, pair_passes, lambda row: {"finished": True}, enabled=True)
    actual = run({}, ordinary, trial)
    assert calls == list(ARMS)
    assert len(gates) == (0 if owner_change else 1)
    assert (actual is ordinary) == (owner_change or not admissible)
    detail = trial["ordinary_centre_reset"]
    assert set(detail["arm_clocks"]) == set(ARMS)
    assert detail["same_ordered_owners"] == {"c0": True, "fitted_c": not owner_change}
    assert run({}, ordinary, trial) is ordinary and calls == list(ARMS)
    assert trial["ordinary_centre_reset"]["status"] == "already_paid"


def test_failed_numeric_trial_keeps_original(inputs):
    ordinary, trial = inputs

    def fail(*_):
        raise ValueError("stand-in failed")

    assert with_reset(update, fail, None, None, enabled=True)({}, ordinary, trial) is ordinary
    assert trial["ordinary_centre_reset"]["status"] == "original_pair_retained"


def test_adapter_import_does_not_leak_checkout_precedence(tmp_path, monkeypatch):
    name = "ds30_0049_saved_crossover"
    (tmp_path / (name + ".py")).write_text("import sys\nsys.path.insert(0, 'temporary wrapper path')\n"
                                           "def charted(): return 'saved adapter'\n")
    monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.syspath_prepend(str(tmp_path))
    before = list(sys.path)
    try:
        assert charted_adapter()() == "saved adapter"
        assert sys.path == before
    finally:
        sys.modules.pop(name, None)


def test_witness_rejects_same_bytes_from_another_checkout(tmp_path):
    original = tmp_path / "archived/reports/ALGO08/v3"
    original.mkdir(parents=True)
    path = original / "exact_named_raw.py"
    path.write_bytes(b"original publication source\n")
    assert witness_sources(path, [path]) == {"reports/ALGO08/v3/exact_named_raw.py": digest(path)}
    foreign = tmp_path / path.name
    foreign.write_bytes(path.read_bytes())
    with pytest.raises(ValueError):
        witness_sources(path, [foreign])
