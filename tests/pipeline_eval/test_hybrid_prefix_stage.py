"""Check exact disjoint stage accounting and the two native source cases."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
from hybrid_prefix_stage import disjoint, verify_partition


def test_embedded_prefix_cpu_is_charged_exactly_once():
    sample = dict(receiver_audit=dict(native=dict(
        native_cpu_ns=dict(full=40, short_primary=65), cfo_refinement=dict(cpu_ns=4), exact_prefix=dict(cpu_ns=25))))
    assert disjoint(sample) == dict(full_lane_cpu_ns=40, primary_cpu_ns=40, refinement_cpu_ns=29,
                                    all_native_and_refinement_cpu_ns=109)
    sample["receiver_audit"]["native"]["exact_prefix"]["cpu_ns"] = 66
    with pytest.raises(ValueError, match="nested prefix CPU"):
        disjoint(sample)


def test_independently_verify_short_from_a_and_full_from_b():
    def arm(short, full):
        return (dict(source={"probes": [dict(visit_index=0, receiver_id=1, candidates=[short]),
                                       dict(visit_index=1, receiver_id=0, candidates=[full])]}),
                dict(vectors=[dict(visit=0, lane=1, mode="short_primary", factors=[short]),
                              dict(visit=1, lane=0, mode="full", factors=[full])]))
    a, ar = arm("exact short", "exact full")
    b, br = arm("anchored short", "anchored full")
    c, cr = arm("exact short", "anchored full")
    verify_partition(a, b, c, ar, br, cr)
    copied = copy.deepcopy(c)
    copied["source"]["probes"][0]["candidates"] = ["modified continuation"]
    with pytest.raises(ValueError, match="realized short_primary"):
        verify_partition(a, b, copied, ar, br, cr)
    with pytest.raises(ValueError, match="changed full"):
        verify_partition(a, b, c, ar, br, ar)
