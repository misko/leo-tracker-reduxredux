from types import SimpleNamespace

import pytest

from tools.pipeline_eval.variants.v5_cavity_isolation import curved_phase_receipt
from tools.pipeline_eval.variants.v5_optional_cavity import (
    NONCONVERGENCE,
    incumbent_publishable,
    try_family,
)


def test_failed_excluded_family_leaves_other_nominations_in_order():
    context = {"scan": SimpleNamespace(norads=[123, 456, 789])}
    rejected = []

    def family(_context, target):
        if target == 1:
            raise ValueError(NONCONVERGENCE)
        return {"values": [target]}

    assert [try_family(family, context, i, rejected)["values"] for i in range(3)] == [
        [0],
        (),
        [2],
    ]
    assert rejected == [{"norad": 456, "reason": NONCONVERGENCE}]


@pytest.mark.parametrize("message", ["missing TLE", NONCONVERGENCE])
def test_other_faults_are_not_reclassified_as_optional(message):
    context = {"scan": SimpleNamespace(norads=[123])}
    rejected = []

    def numerical_fault():
        raise ValueError(message)

    def family(_context, _target):
        numerical_fault()

    with pytest.raises(ValueError, match=message):
        try_family(family, context, 0, rejected)
    assert rejected == []


def test_incumbent_requires_original_paired_gate_and_finite_outputs():
    fits = {
        arm: dict(endpoint_latlon=[1.0, 2.0], final_phase_change_s=0.002, RMS_hz=60.0)
        for arm in ("c0", "fitted_c")
    }
    region = SimpleNamespace(half_width_km=12.5)
    context = dict(
        arms=fits, signed={"policy_arms": fits}, scan=SimpleNamespace(search_region=region)
    )

    def valid(arms, *, half_width_km):
        assert arms is fits and half_width_km == 12.5
        return True

    assert incumbent_publishable(valid, context)
    assert not incumbent_publishable(lambda *_args, **_kwargs: False, context)
    fits["fitted_c"]["RMS_hz"] = float("nan")
    assert not incumbent_publishable(valid, context)


def test_curved_gate_uses_exact_last_phase_and_keeps_signed_fit_intact():
    fits = {
        arm: dict(history=[{"phase_change_s": 0.2}, {"phase_change_s": delay}])
        for arm, delay in (("c0", 0.001), ("fitted_c", 0.02))
    }
    curved = dict(arms=fits, signed=dict(policy_arms=fits, accepted=False), entries=[])
    adapted = curved_phase_receipt(curved)
    assert adapted["signed"]["policy_arms"] is adapted["arms"]
    assert [r["final_phase_change_s"] for r in adapted["arms"].values()] == [0.001, 0.02]
    assert "final_phase_change_s" not in fits["c0"]
    signed = dict(curved, signed=dict(policy_arms=fits, accepted=True))
    assert curved_phase_receipt(signed)["arms"] is fits
