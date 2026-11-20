from copy import deepcopy

import pytest

from tools.pipeline_eval.variants.quarter_miss import phase, project


def synthetic(flip_partner=False):
    gate = "passed_fractional_margin_gate"
    groups = ((11_325_000_000, 0), (11_325_000_000, 1), (11_575_000_000, 0))
    rows, schedule = [], []
    visit = 1
    for round_number in range(11):
        for center, primary in groups:
            hit = round_number in (1, 5, 7)
            visit += 1
            schedule.append(dict(visit=visit, rf_center_hz=center, selected_receiver=primary))
            for lane in (0, 1):
                candidate = hit if lane == primary else flip_partner
                rows.append(
                    dict(
                        visit_index=visit,
                        receiver_id=lane,
                        sample=10000 + visit,
                        candidates=[{gate: candidate, "cfo": 20.0}, {gate: False, "cfo": 4.0}],
                    )
                )
    doc = dict(
        clock_anchor=1,
        provenance=dict(excluded_windows=[dict(visit=1)]),
        source=dict(probes=rows, analysis_manifest_sha256="frozen"),
    )
    return doc, schedule


def test_quarter_is_counted_after_misses_independently_per_tune_and_physical_lane():
    doc, schedule = synthetic()
    untouched = deepcopy(doc)
    out, decisions, counts = project(doc, schedule)
    opposite, opposite_schedule = synthetic(flip_partner=True)
    _, independent, scored = project(opposite, opposite_schedule)
    assert decisions == independent
    assert counts["audited_misses"] == 6 and counts["primary_hits"] == 9
    assert counts["audited_partner_hits"] == 0 and scored["audited_partner_hits"] == 6
    assert counts["invalid_visits"] == 1
    by_tune = {}
    for r in decisions:
        if r["primary_hit"]:
            assert r["keep_partner"] is True and r["audited_miss"] is False
        else:
            key = r["rf_center_hz"], r["selected_receiver"]
            marks = by_tune.setdefault(key, [])
            assert r["audited_miss"] == (len(marks) % 4 == phase(*key))
            marks.append(r["audited_miss"])
    assert all(len(bucket) == 8 and sum(bucket) == 2 for bucket in by_tune.values())
    for i, r in enumerate(decisions):
        p = r["selected_receiver"]
        before, after = (d["source"]["probes"][2 * i : 2 * i + 2] for d in (doc, out))
        assert before[p] is after[p]
        assert after[1 - p] == (
            before[1 - p] if r["keep_partner"] else dict(before[1 - p], candidates=[])
        )
    assert doc == untouched


def test_reject_changed_schedule_visit():
    doc, schedule = synthetic()
    with pytest.raises(ValueError, match="original ordered RF/lane"):
        project(doc, [dict(schedule[0], visit=1), *schedule[1:]])
