import pytest

from tools.pipeline_eval.qualification import two_rate_holdout as roster
from tools.pipeline_eval.qualification import two_rate_holdout_results as results
from tools.pipeline_eval.qualification import two_rate_holdout_trial as trial


def recording(rows):
    source = dict.fromkeys(
        (
            "session_id",
            "raw_recording_authority_digest",
            "sample_rate_hz",
            "probe_ms",
            "radio_id",
            "stream_generation",
            "capture_mode",
        )
    )
    source.update(input_manifest_sha256="sha256:example", probes=[])
    for visit, rf, passing in rows:
        source["probes"].extend(
            dict(
                visit_index=visit,
                receiver_id=lane,
                actual_rf_hz=rf,
                candidates=[dict(passed_fractional_margin_gate=ok, tag=f"{visit}/{lane}/{ok}")],
            )
            for lane, ok in enumerate(passing)
        )
    return dict(
        schema_version="native",
        clock_anchor={"epoch": 0},
        delivery_clocks=[],
        last_sample_counter=22,
        source=source,
        provenance=dict(excluded_windows=[], processed_windows=len(rows)),
    )


def test_membership_uses_each_series_physical_manifest_hash():
    manifests = {key: key for key in roster.ANCHORS} | {
        f"{cohort}-{i:04}": f"sha256:{i + cohort_index:064x}"
        for cohort_index, cohort in enumerate(("DS26", "DS29"), start=5_000)
        for i in range(5)
    }
    selected, ranked, digests = roster.select_recordings(manifests)
    assert selected[:2] == list(roster.ANCHORS)
    for cohort, chosen in (("DS26", selected[2:5]), ("DS29", selected[5:])):
        assert set(chosen) <= set(ranked[cohort]) and len(chosen) == 3
        assert all(
            digests[a] <= digests[b]
            for a, b in zip(ranked[cohort][:-1], ranked[cohort][1:], strict=True)
        )
    assert (selected, ranked, digests) == roster.select_recordings(
        dict(reversed(manifests.items()))
    )


def test_schedule_staggers_independent_rf_ordinals_and_ignores_packet_clarity():
    rows = [(3 * i, 10_700 + i % 2, (True, False)) for i in range(72)]
    first = roster.schedule(recording(rows))
    flipped = recording([(visit, rf, (False, True)) for visit, rf, _ in rows])
    assert first == roster.schedule(flipped)
    assert first["visits_per_rf"] == {10_700: 36, 10_701: 36}
    for rf, offset in first["stagger_per_rf"].items():
        chosen = [x for x in first["selected"] if x["rf_hz"] == rf]
        assert [r["ordinal"] for r in chosen] == [offset, offset + 12, offset + 24]
        assert all(rows[r["visit"] // 3][1] == rf for r in chosen)


def test_projection_replaces_complete_visit_and_fill_keeps_positive_physical_lane():
    fast = recording([(0, 10_701, (True, True)), (1, 10_700, (True, False))])
    original = recording([(0, 10_701, (False, False)), (1, 10_700, (False, True))])
    scheduled = [dict(visit=1, rf_hz=10_700)]
    streams, counts, witness = trial.project(fast, original, scheduled)
    a, b = [x["source"]["probes"] for x in (fast, original)]
    assert streams == dict(wide=a, original=b, replace=a[:2] + b[2:], fill=a[:3] + b[3:])
    assert counts[10_700]["replace"]["lost_positive_probes"] == 1
    assert counts[10_700]["fill"]["lost_positive_probes"] == 0
    assert counts[10_700]["fill"]["gained_positive_probes"] == 1
    assert [row["original"] for row in witness[0]["fill"]] == [False, True]
    assert [row["original"] for row in witness[0]["replace"]] == [True, True]
    assert len(witness) == 1


def test_projection_rejects_clock_mismatch_and_missing_or_wrong_rf_donor():
    doc = recording([(0, 10_700, (True, False))])
    with pytest.raises(ValueError, match="clock authority"):
        trial.project(doc, dict(doc, last_sample_counter=30), [])
    with pytest.raises(ValueError, match="unavailable captures"):
        trial.project(doc, doc, [dict(visit=1, rf_hz=10_700)])
    with pytest.raises(ValueError, match="changed physical RF"):
        trial.project(doc, doc, [dict(visit=0, rf_hz=10_701)])


def test_attempt_counts_retain_first_run_timeout_with_completed_retry():
    first = [
        dict(id="DS26-X", condition="fill", result=dict(status="timed_out")),
        dict(id="DS26-Y", condition="fill", result=dict(status="ok")),
        dict(id="DS26-Z", condition="fill", result=dict(status="failed")),
    ]
    final = [dict(first[0], result=dict(status="ok"), retry_s=420), *first[1:]]
    group = {"sampled": [row["id"] for row in first]}
    by_policy = {row["policy"]: row for row in results.attempt_counts(first, final, group)}
    fill = by_policy["fill"]
    assert fill["first_ok"] == fill["first_timed_out"] == fill["first_failed"] == 1
    assert fill["retry_attempted"] == fill["retry_ok"] == 1
    assert fill["submitted_first_attempts"] == 3
