import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
from numpy.testing import assert_array_equal

from tools.pipeline_eval.variants.v5_recovery_bank_reuse import (
    RecoveryBank,
    ledger_key,
    reuse_recovery_bank,
)


class ImmutableBank:
    def __init__(self, bank):
        self.values = {
            key: (value.shape, value.dtype, value.tobytes()) for key, value in bank.items()
        }

    def __getitem__(self, key):
        shape, dtype, data = self.values[key]
        return np.frombuffer(data, dtype=dtype).reshape(shape)


def ledger():
    return {"41": {"lines": ["a", "b"]}, "19": {"lines": ["c", "d"]}}


def position_bank():
    return {
        "time_s": np.array([0.0, 1.0]),
        "position_km": np.ones((1, 2, 3)),
        "velocity_km_s": np.zeros((1, 2, 3)),
    }


@pytest.mark.parametrize("changed", ("tle", "origin", "grid", "grid_dtype"))
def test_handoff_requires_exact_inputs_and_is_single_use(changed):
    records = ledger()
    bank = ImmutableBank(position_bank())
    times = bank["time_s"]
    origin = 118
    handoff = RecoveryBank()
    handoff.capture(ledger_key(records), origin, times, [True, False], bank)
    if changed == "tle":
        records["19"]["lines"][0] = "new TLE with same identity"
    elif changed == "origin":
        origin += 1
    elif changed == "grid":
        times = np.array([-0.0, 1.0])
    else:
        times = times.astype(np.float32)
    assert handoff.take(records, origin, times) is None
    assert handoff.take(ledger(), 118, bank["time_s"]) is None


def test_mask_is_snapshotted_and_shared_bank_rejects_mutation():
    records = ledger()
    arrays = position_bank()
    bank = ImmutableBank(arrays)
    usable = np.array([True, False])
    handoff = RecoveryBank()
    handoff.capture(ledger_key(records), 118, arrays["time_s"], usable, bank)
    usable[:] = False
    arrays["position_km"].fill(99)
    nums, reused, failed = handoff.take(records, 118, arrays["time_s"])
    assert reused is bank and nums.tolist() == [19] and failed == [41]
    assert_array_equal(reused["position_km"], np.ones((1, 2, 3)))
    with pytest.raises(ValueError, match="WRITEABLE"):
        reused["position_km"].setflags(write=True)
    assert handoff.take(records, 118, arrays["time_s"]) is None


def test_recovery_reuses_geometry_and_keeps_the_original_audit(monkeypatch):
    owner = ModuleType("leo.analysis.localization_v3")
    residual = owner.residual_screen = SimpleNamespace(FrozenOrbitBank=ImmutableBank)
    catalogue = owner.reassociation_catalogue = SimpleNamespace(GRID=np.array([0.0, 1.0]))
    admission = owner.reassociation_admission = SimpleNamespace()
    monkeypatch.setitem(sys.modules, owner.__name__, owner)
    calls = []
    records = ledger()
    arrays = position_bank()

    def ecef(cat, origin, times):
        calls.append("residual propagation")
        return None, None, np.array([True, False])

    def screen(packet, catalogue, region):
        residual.ecef_states(SimpleNamespace(satellite_numbers=(19, 41)), 118, arrays["time_s"])
        if packet["targets"]:
            return residual.FrozenOrbitBank(arrays)

    def bank_for(records, origin):
        calls.append("reassociation propagation")
        return np.array([19]), position_bank(), [41]

    def prepare(book, receipt):
        nums, bank, failures = catalogue.bank_for(book["elements"], receipt["origin_utc_ns"])
        calls.append("raw audit")
        return dict(nums=nums, bank=bank, failures=failures, eligible=receipt["eligible"])

    book = {"elements": records}
    residual.screen_candidates = screen
    residual.ecef_states = ecef
    catalogue.bank_for = bank_for
    admission.prepare_catalogue = prepare
    with reuse_recovery_bank() as counts:
        original = residual.screen_candidates({"targets": [1]}, book, None)
        result = admission.prepare_catalogue(book, {"origin_utc_ns": 118, "eligible": False})
        assert result["bank"] is original
        assert not result["eligible"]
        assert calls == ["residual propagation", "raw audit"]
        assert counts["reused"] == 1 and counts["frozen_in_admission"] == 0

        residual.screen_candidates({"targets": []}, book, None)
        result = admission.prepare_catalogue(book, {"origin_utc_ns": 118, "eligible": True})
        assert isinstance(result["bank"], ImmutableBank)
        assert calls[-3:] == ["residual propagation", "reassociation propagation", "raw audit"]
        assert counts["reused"] == 1 and counts["frozen_in_admission"] == 1
    assert residual.screen_candidates is screen
    assert admission.prepare_catalogue is prepare
