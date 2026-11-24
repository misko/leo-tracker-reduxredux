from copy import deepcopy

import pytest

from reports.ALGO08.v3.cross_lag_twelve_ms_transfer import compare


def result(cpu):
    channels = {"full": 16, "short_primary": 86}
    scope = {"prefix_inventory": "original", "iq": ["pinned"],
             "vectors": [dict(mode="full", factors=[])] * 16 + [dict(mode="short_primary", factors=[])],
             "receiver_audit": {"native": {"native_calls": channels}, "acquire": {"cpu_ns": cpu}}}
    native = {"clock_anchor": 7, "delivery_clocks": [3], "provenance": {"excluded_windows": []},
              "source": {"probes": ["selected"], "raw_recording_authority_digest": "original"}}
    measures = dict(original=["before"], acquired=["measurement"], route="history", paid=[9])
    return dict(scope=scope, native=native, measurements=measures)


def test_strict_gate_requires_signed_row_parity_and_paid_member_cpu():
    ordinary = result(100)
    assert compare(ordinary, result(90))["both_conditions"]
    assert not compare(ordinary, result(100))["both_conditions"]
    candidate = deepcopy(result(90))
    candidate["measurements"]["acquired"] = []
    assert not compare(ordinary, candidate)["both_conditions"]


def test_a_changed_full_anchor_is_rejected():
    a, b = result(100), result(90)
    b["scope"]["vectors"][0] = dict(mode="full", factors=["new"])
    with pytest.raises(ValueError, match="cancellation vector changed"):
        compare(a, b)
