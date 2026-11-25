from copy import deepcopy

import pytest

from reports.ALGO08.v3 import held_cfo_complement as check


def factor(hz, rank=0, margin=.2, passed=True):
    return {check.stage.HERTZ: hz, "candidate_rank": rank, "fractional_margin": margin,
            "passed_fractional_margin_gate": passed, "integer_epoch_sample": 2,
            "fractional_epoch_offset_samples": 0.}


def native(schedule):
    rows = [dict(edge="upper", channel=ch, actual_rf_hz=10_000+ch, receiver_id=radio,
                 visit_index=visit, valid_start_counter=100_000*visit, candidates=[factor(10.)])
            for visit,ch in schedule for radio in (0,1)]
    count = max(visit for visit,_ in schedule)+1
    seen = {visit for visit,_ in schedule}
    return dict(source=dict(session_id="sample", raw_recording_authority_digest="raw", probes=rows),
                provenance=dict(excluded_windows=[dict(visit=visit) for visit in set(range(count))-seen],
                                detector_sha256="sha256:detector", window_count=count, processed_windows=len(seen)))


def test_complement_discards_both_held_arrays_without_reading_and_preserves_anchors():
    source = native([(i,0) for i in range(13) if i != 1] + [(13,1),(14,1),(15,1)])
    even_visits = {3,5,7,11,15}
    for row in source["source"]["probes"]:
        if row["visit_index"] in even_visits:
            row["candidates"] = object()  # Selection or serialization of a target would fail.
    packet, held, retained, anchors = check.masked_even(source)
    assert len(held) == 2*len(even_visits)
    assert {row["row"]["visit_index"] for row in held.values()} == even_visits
    assert {retained[oid]["row"]["visit_index"] for oid in anchors} == {0,9,13}
    assert not held.keys() & retained.keys()
    for old,new in zip(source["source"]["probes"],packet["source"]["probes"],strict=True):
        if old["visit_index"] in even_visits:
            assert new == dict(old,candidates=[])
        else:
            assert old is new
    corrupt = deepcopy(source)
    corrupt["source"]["probes"][1]["actual_rf_hz"] += 1
    with pytest.raises(ValueError,match="stereo opportunities"):
        check.masked_even(corrupt)


def test_releases_original_winner_precedence_for_donors():
    source = native([(0,0),(1,0),(2,0)])
    candidates = [factor(1.,rank=1),factor(2.,rank=0),factor(3.,margin=.9,passed=False)]
    source["source"]["probes"][2]["candidates"] = candidates
    _, _, retained, _ = check.masked_even(source)
    winner = next(row for row in retained.values() if row["row"] is source["source"]["probes"][2])
    assert winner["factor"] is candidates[1]


def test_forecast_audit_rejects_any_target_used_as_donor_before_edits():
    with pytest.raises(ValueError,match="Only retained measured donors"):
        check.audited_features(None,{"held":{}},{"valid":{}},{"held":dict(donors=["valid","held"])},{},{})


def test_paired_fold_metrics_counts_missing_empty_changed_and_unchanged_exactly():
    def lane(value):
        return dict(counter=2**54,factor=factor(value) if value is not None else None)
    original = dict(a=lane(300),b=lane(117),c=lane(2),d=lane(None),e=lane(None))
    installed = dict(a=lane(0),b=lane(100),c=lane(None),d=lane(1),e=lane(None))
    edit = dict(original_hz=300,forecast_hz=100,updated_hz=200,
                arrival=check.stage.arrival(original["a"]["counter"],original["a"]["factor"]))
    missing = dict(original_hz=2,forecast_hz=3,updated_hz=2.5,
                   arrival=check.stage.arrival(original["c"]["counter"],original["c"]["factor"]))
    scope, changed, unchanged, absent = check.metrics(original,{"a":edit,"c":missing},original,installed)
    assert scope == dict(both_positive=2,candidate_only=1,installed_only=1,both_empty=1)
    assert absent == 1 and changed == [(300,200,0.)] and unchanged == [(17,17,0.)]
    scored = check.scoring.evaluate(changed+unchanged,absent)
    assert scored["scored"] == 2 and scored["installed_empty"] == 1
    assert scored["windows"]["250Hz_2samples"]["joint_before"] == 1
    assert scored["windows"]["250Hz_2samples"]["joint_after"] == 2
