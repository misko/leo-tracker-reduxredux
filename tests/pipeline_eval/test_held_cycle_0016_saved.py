"""Bind the offline selector witness to measured stereo opportunities and their original factors."""

from copy import deepcopy

import pytest

from held_cycle_0016_saved import witness
from held_cycle_refined import CFO


def packets():
    rows = [dict(visit_index=visit, receiver_id=radio, edge="lower", channel=1, actual_rf_hz=10_709_687_500,
                 candidates=[{"candidate_rank": 0, "integer_epoch_sample": 31, CFO: -1500.0}])
            for visit in (123, 127) for radio in (0, 1)]
    old = dict(source=dict(probes=rows))
    new = deepcopy(old)
    return old, new


def test_real_cfo_delta_restores_ordered_unmodified_probe_fields():
    old, new = packets()
    probes = new["source"]["probes"]
    probes[-1]["candidates"][0][CFO] = -1420.0
    changes = witness(old, new, 2)
    assert changes.attempted == 2
    assert changes.changed == {(127, 1): (-1500.0, -1420.0)}
    assert changes.original_rows(probes) == old["source"]["probes"]


def test_offline_witness_rejects_a_new_anchor_or_refinement_outside_original_fields():
    old, new = packets()
    probes = new["source"]["probes"]
    probes[0]["candidates"][0][CFO] = -1420.0
    with pytest.raises(ValueError, match="changed an anchor"):
        witness(old, new, 2)
    probes[0]["candidates"][0][CFO] = -1500.0
    probes[-1]["candidates"][0]["integer_epoch_sample"] += 1
    with pytest.raises(ValueError, match="besides CFO"):
        witness(old, new, 2)
