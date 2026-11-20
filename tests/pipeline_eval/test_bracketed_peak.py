from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import bracketed_peak_ceiling as ceiling
from tools.pipeline_eval.qualification import bracketed_peak_trial as trial
from tools.pipeline_eval.variants import bracketed_peak as model

RATE = 10_000_000
START = (1 << 53) + 879


def candidate(epoch, cfo, margin, rank=0):
    return {
        "integer_epoch_sample": int(epoch),
        "fractional_epoch_offset_samples": epoch % 1,
        "fractional_tracking_cfo_hz": cfo,
        "fractional_margin": margin,
        "fractional_exact_score": 0.1 + margin,
        "fractional_control_score": 0.1,
        "candidate_rank": rank,
        model.GATE: margin >= 0.025,
    }


def probe(visit, counter, rows, edge="upper"):
    return dict(
        visit_index=visit,
        receiver_id=0,
        actual_rf_hz=12e9,
        channel=1,
        edge=edge,
        valid_start_counter=counter,
        probe_start_ms=0,
        candidates=rows,
    )


def measured(visit, ticks, cfo, margin, delta_epoch=0, edge="upper"):
    epoch = (123 + 10 * ticks / RATE - model.counter_phase(ticks, RATE) + delta_epoch) % (
        RATE / 750
    )
    return probe(visit, START + ticks, [candidate(epoch, cfo, margin)], edge)


def three():
    return [
        measured(1, 0, 113_000, 0.03),
        measured(2, 5_001_025, 114_000 - model.FOLD_HZ, 0.01),
        measured(3, 10_002_050, 115_000 - model.FOLD_HZ, 0.04),
    ]


def test_counter_phase_and_doppler_wrap_preserve_an_actual_weak_peak():
    records = three()
    before = deepcopy(records)
    edits, counts = model.select(iter(records), RATE)
    assert edits == [
        dict(probe_index=1, candidate_index=0, left_visit=1, right_visit=3, delay_samples=5_001_025)
    ]
    assert counts["bracketed_negative_with_candidates"] == 1
    assert not model.select(records, RATE, sham=True)[0]
    assert before == records


def test_null_reaches_the_complementary_epoch():
    records = three()
    row = records[1]["candidates"][0]
    epoch = row["integer_epoch_sample"] + row["fractional_epoch_offset_samples"]
    records[1]["candidates"] = [
        candidate(epoch + RATE / 1500, row["fractional_tracking_cfo_hz"], 0.01)
    ]
    assert not model.select(records, RATE)[0]
    assert len(model.select(records, RATE, sham=True)[0]) == 1


def test_duplicate_alias_members_use_measured_margin_and_native_rank():
    records = three()
    first = records[1]["candidates"][0]
    duplicate = dict(
        first,
        fractional_tracking_cfo_hz=first["fractional_tracking_cfo_hz"] + model.FOLD_HZ,
        fractional_margin=0.02,
        candidate_rank=2,
    )
    records[1]["candidates"] += [duplicate, dict(duplicate, candidate_rank=1)]
    assert model.select(records, RATE)[0][0]["candidate_index"] == 2
    first["fractional_tracking_cfo_hz"] -= 850
    duplicate["fractional_tracking_cfo_hz"] += 850
    assert not model.select(records, RATE)[0]


@pytest.mark.parametrize("reason", ["edge", "gap", "phase", "frequency", "gate", "no_right"])
def test_rejects_unsupported_or_already_admitted_points(reason):
    records = three()
    if reason == "edge":
        records[2]["edge"] = "lower"
    if reason == "gap":
        records[2]["valid_start_counter"] += 2 * RATE
    if reason == "phase":
        records[2]["candidates"][0]["integer_epoch_sample"] += 1000
    if reason == "frequency":
        records[2]["candidates"][0]["fractional_tracking_cfo_hz"] += 12000
    if reason == "gate":
        records[1]["candidates"][0][model.GATE] = True
    if reason == "no_right":
        records.pop()
    assert not model.select(records, RATE)[0]


def test_chronology_and_memory_limit():
    records = three()
    with pytest.raises(ValueError, match="counters"):
        model.select([records[0], records[0]], RATE)
    pending = [measured(i, i * 10000, 113_000, 0.01) for i in range(2, 137)]
    _, counts = model.select([records[0], *pending], RATE)
    assert counts["largest_pending_lane"] == 128
    assert counts["capacity_evictions"] == 7


def test_incomplete_weak_candidate_never_supplies_a_measurement():
    records = three()
    source = records[1]["candidates"][0]
    records[1]["candidates"] = [
        dict(source, fractional_exact_score=None),
        dict(source, fractional_tracking_cfo_hz=float("nan")),
        dict(source, fractional_margin=0),
    ]
    assert not model.select(records, RATE)[0]


def test_availability_distinguishes_missing_epoch_from_score_and_cfo():
    reference = candidate(120, 50, 0.1)
    p = probe(7, START, [])
    assert ceiling.classification(p, reference, RATE) == ("no_complete_row", False)
    cases = [
        (candidate(130, 50, 0.01), ("no_near_epoch", True)),
        (candidate(120, 1550, 0.01), ("only_wrong_cfo", False)),
        (candidate(119, 51, 0), ("family_nonpositive_margin", True)),
        (candidate(120, 50 - model.FOLD_HZ, 0.02), ("family_positive_margin", True)),
    ]
    for row, result in cases:
        assert ceiling.classification(dict(p, candidates=[row]), reference, RATE) == result


def test_scoring_counts_one_held_opportunity_and_authenticates_full_probe():
    source = dict(session_id="roster", sample_rate_hz=RATE, probes=three())
    doc = dict(source=source, clock_anchor=dict(sample_counter=START))
    teacher = deepcopy(doc)
    teacher["source"]["probes"][1]["candidates"][0][model.GATE] = True
    edits, _ = model.select(source["probes"], RATE)
    assert trial.agreement(doc, teacher, edits) == dict(
        capture_positive=3,
        capture_positive_wide_negative=1,
        selected=1,
        capture_positive_at_selection=1,
        same_capture_winner=1,
    )
    teacher["source"]["probes"][1]["actual_rf_hz"] += 1
    with pytest.raises(ValueError, match="opportunity"):
        trial.agreement(doc, teacher, edits)
