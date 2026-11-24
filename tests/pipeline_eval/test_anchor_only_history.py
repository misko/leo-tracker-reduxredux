import gzip
import json

import pytest

from reports.ALGO08.v3 import anchor_only_history as replay
from reports.ALGO08.v3.anchor_delayed_history import delayed_plan


def factor(hz, rank=0, margin=0.5):
    return dict(fractional_tracking_cfo_hz=hz, fractional_margin=margin,
                candidate_rank=rank, passed_fractional_margin_gate=True)


def packet(visit, selected=None, *, radio=0, edge="lower"):
    return dict(visit_index=visit, receiver_id=radio, edge=edge, channel=1,
                actual_rf_hz=10_700_000_000, valid_start_counter=visit * 2_500_000,
                candidates=[] if selected is None else [selected])


def trained():
    selector = replay.AnchorHistory()
    for visit in (1, 2, 3):
        row = packet(visit, factor(10_000 + 125 * visit))
        assert selector.choose(row, False)[:2] == (row["candidates"][0], "short")
    return selector


def test_anchor_only_needs_a_measured_same_signed_history():
    candidate = factor(-10_500)
    assert trained().choose(packet(4, candidate), True) == (None, "rejected", 3, [0])
    assert trained().choose(packet(4, candidate, radio=1), True) == (candidate, "insufficient_history", 0, [])
    assert trained().choose(packet(4, candidate, edge="upper"), True) == (candidate, "insufficient_history", 0, [])
    assert trained().choose(packet(4, candidate), False)[:2] == (candidate, "short")


def test_alternative_requires_an_already_paid_verified_factor_and_keeps_prepolicy_history():
    selector = trained()
    original = factor(-10_500)
    alternative = factor(10_500, rank=1, margin=0.3)
    row = packet(4, original)
    assert selector.choose(row, True, [alternative, original]) == (alternative, "paid_alternative", 3, [0, 3])
    lane = 0, *replay.stream(row)
    assert list(selector.history[lane])[-1][1] == (-10_500,)
    with pytest.raises(ValueError, match="disagree"):
        trained().choose(row, True, [alternative])


def test_empty_opportunities_expire_same_stream_history():
    selector = trained()
    for visit in range(4, 17):
        assert selector.choose(packet(visit), False)[:2] == (None, "empty")
    value = factor(-12_000)
    assert selector.choose(packet(17, value), True) == (value, "insufficient_history", 0, [])


def test_stereo_schedule_uses_admitted_stream_order_and_original_empty_lanes():
    rows = [packet(i, radio=radio) for i in range(12) if i not in (2, 3)
            for radio in (0, 1)]
    assert [replay.slot(row) for row, anchor in replay.decisions(rows) if anchor] == [(0, 0), (0, 1), (10, 0), (10, 1)]
    with pytest.raises(ValueError, match="stereo"):
        list(replay.decisions(rows[1:]))


def test_independent_complete_archive_reproduces_sealed_native_diagonals():
    files = ["ds30-0016-full-primary-transfer.json.gz", "late-pilot-rescue.json.gz"]
    originals, archive = (replay.read(replay.MEASUREMENTS / f, replay.PINS[f]) for f in files)
    stock, mixed = (originals["detector_packets"][key]["document"] for key in ("installed", "charted"))
    stock_rows, mix_rows = replay.paired(stock, mixed)
    rows = archive["DS30-0016"]["long-receiver.json"]["document"]
    options = replay.bind_native(rows, stock_rows, mix_rows)
    choices = replay.plan(mix_rows, options)
    scores = replay.assess(stock_rows, mix_rows, choices, mixed["source"]["session_id"],
                           replay.owner_sets(originals["installed_owners"]), replay.owner_sets(originals["charted_owners"]))
    sealed = json.loads((replay.MEASUREMENTS / "anchor-only-history.json").read_text())
    assert json.loads(json.dumps(scores)) == sealed["scopes"]["DS30-0016"]["paid_alternatives"]
    assert scores["counts"]["lost_stock_positive"] == 9


def test_delayed_anchor_can_use_future_short_measurements_but_never_changes_shorts():
    good = [packet(i, factor(10_000 + 125 * i), radio=radio) for i in range(4)
            for radio in (0, 1)]
    outcomes = delayed_plan(good)
    assert outcomes[0]["direction_votes"] == [[], [3]]
    assert outcomes[0]["selected"] == good[0]["candidates"][0]
    bad = [dict(good[0], candidates=[factor(-10_000)]), *good[1:]]
    rejected = delayed_plan(bad)
    assert rejected[0]["direction_votes"] == [[], [0]]
    assert rejected[0]["reason"] == "rejected"
    assert rejected[0]["selected"] is None
    assert rejected[2:] == outcomes[2:]


def test_delayed_history_counts_full_slots_as_empty_donors():
    selector = replay.AnchorHistory(short_donors_only=True)
    for visit in (1, 2, 3):
        selector.choose(packet(visit, factor(10_000 + 125 * visit)), True)
    current = factor(-10_500)
    assert selector.choose(packet(4, current), True) == (current, "insufficient_history", 0, [])


def test_sealed_delayed_transfer_has_false_deletions_in_every_record():
    path = replay.MEASUREMENTS / "anchor-delayed-history.json.gz"
    reports = json.loads(gzip.decompress(path.read_bytes()))["reports"]
    for case, loss in (("DS30-0049", 3), ("DS30-0016", 8), ("DS30-0407", 70)):
        preferred = reports[case]["arms"]["complete_strongest"]
        assert preferred["counts"]["lost_stock_positive"] == loss
    original = reports["DS30-0049"]["arms"]["complete_strongest"]
    owned = [row for row in original["rows"] if row["installed"] is None and row["mixed_owner_arms"]]
    assert [row["direction_votes"][1] for row in owned] == [[3], [5], [6], []]
    assert all(row["selected"] == row["original"] for row in owned)
