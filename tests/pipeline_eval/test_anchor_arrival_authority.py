import json
from pathlib import Path

import pytest

from reports.ALGO08.v3 import anchor_arrival_authority as audit


def probe(visit, radio, epoch, fraction=0.0, hz=0.0):
    factor = dict(integer_epoch_sample=epoch, fractional_epoch_offset_samples=fraction,
                  fractional_tracking_cfo_hz=hz)
    return dict(visit_index=visit, receiver_id=radio, valid_start_counter=10**17 + visit * 2_500_000,
                edge="lower", channel=4, actual_rf_hz=11_800_000_000,
                candidates=[] if epoch is None else [factor])


def test_physical_epoch_wrap_and_signed_cfo_have_different_periods():
    a = probe(0, 0, 13_332, 0.25, 0.0)
    b = probe(0, 1, 0, 0.125, audit.CFO_ALIAS + 1000.0)
    delta = audit.epoch_difference(a, b)
    assert delta["samples"] == pytest.approx(29 / 24)
    assert delta["signed_cfo_hz"] == audit.CFO_ALIAS + 1000.0
    assert delta["folded_cfo_hz"] == pytest.approx(1000.0)
    assert audit.epoch_difference(a, probe(0, 1, None)) is None
    with pytest.raises(ValueError, match="same original stereo"):
        audit.epoch_difference(a, probe(1, 1, 0))


def test_circular_offset_checks_wrap_and_abstains_on_tied_support():
    clustered = audit.modal_interval([-1.25, 0, 1.25, 2000])
    assert clustered == dict(count=3, tied_sets=1, center=0, span=2.5)
    tied = audit.modal_interval([0, 1, 100, 101])
    assert tied == dict(count=2, tied_sets=2, center=None, span=None)


def test_anchor_epoch_is_excluded_from_both_short_offset_halves():
    rows = [probe(i, radio, 20 + radio) for i in range(8) for radio in (0, 1)]
    before = audit.inventory(rows)
    after = audit.inventory([rows[0], probe(0, 1, 1000), *rows[2:]])
    assert before["offsets"] == after["offsets"]
    assert len(before["anchors"]) == 2
    assert before["anchors"][0]["short_before"] == 0
    assert before["anchors"][0]["short_after"] == 7
    assert before["anchors"][0]["peer"] != after["anchors"][0]["peer"]


def test_sealed_evidence_cannot_adjudicate_the_disputed_0049_owners_by_peer_timing():
    path = Path(audit.__file__).parent / "measurements/anchor-arrival-authority.json"
    report = json.loads(path.read_text())
    case = report["cases"]["DS30-0049"]
    assert case["totals"]["installed_owned"]["total"] - case["totals"]["installed_owned"]["peer"] == 20
    assert [row["peer"] is not None for row in case["owned_extras"]] == [False, False, False, True]
    last = case["owned_extras"][-1]
    assert last["short_before"] == last["short_after"] == 0
    assert max(map(abs, last["offset_fit_residuals"])) < 0.2
