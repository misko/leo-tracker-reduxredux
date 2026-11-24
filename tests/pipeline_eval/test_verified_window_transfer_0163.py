from copy import deepcopy

import pytest

from reports.ALGO08.v3.verified_window_transfer_0163 import ARMS, MODES, audit_prefix, lane_key


def case():
    visit = dict(sequence=0, sample_start=900, sample_end=1000, iq_sha256="same", admitted=True,
                 channel=3, actual_rf_hz=10940312500, edge="lower", clock=dict(realtime_ns=123))
    rows = [dict(visit_index=0, receiver_id=id_, valid_start_counter=900, channel=3, candidates=[]) for id_ in (0, 1)]
    suffix = [dict(visit_index=1, receiver_id=0, valid_start_counter=1900, channel=4, candidates=[])]
    stock = dict(source=dict(session_id="original"), provenance=dict(window_count=2))
    observed = deepcopy(rows)
    mixed = deepcopy(rows)
    mixed[1]["candidates"] = [dict(fractional_tracking_cfo_hz=-123.5)]
    rosters = {mode: {arm: {} for arm in ARMS} for mode in MODES}
    return stock, {lane_key(row): row for row in rows+suffix}, {}, rosters, dict(visits=[visit]), [visit], dict(installed=observed, mixed=mixed)


def test_genuine_gain_on_original_empty_lane_is_kept():
    args = case()
    result, rows = audit_prefix(*args)
    assert result["exact_installed_parity"] and result["matched_changes"] == 1
    assert result["owners"]["routed"]["c0"] == dict(total=0, prefix=0)
    assert len(rows) == 3 and rows[1]["candidates"] == args[-1]["mixed"][1]["candidates"]
    assert rows[2] is args[1][(1, 0)]


def test_noncontiguous_and_changed_scope_fail_before_constructing_hybrid():
    args = case()
    args[-2][0] = dict(args[-2][0], sequence=2)
    with pytest.raises(ValueError, match="contiguous"):
        audit_prefix(*args)
    args = case()
    args[-1]["installed"][0]["candidates"] = [dict(fractional_tracking_cfo_hz=-18.0)]
    result, rows = audit_prefix(*args)
    assert not result["exact_installed_parity"] and rows is None
