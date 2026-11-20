from tools.pipeline_eval.qualification import adaptive_visits_trial as trial
from tools.pipeline_eval.qualification.adaptive_visits_results import ideal_serial
from tools.pipeline_eval.variants import adaptive_visits as policy


def test_causal_schedule_has_no_future_influence_and_spends_one_earned_token():
    rows = [
        dict(visit=i, rf_hz=100 + i % 2, score=3 if i in (24, 36, 77, 98) else 0, arrival_ns=i)
        for i in range(102)
    ]
    selected, windows = policy.schedule(rows, 1.5)
    prefix, _ = policy.schedule(rows[:64], 1.5)
    assert prefix == [row for row in selected if row["visit"] < 64]
    assert len(selected) == len({(r["rf_hz"], r["token"]) for r in selected})
    assert all((row["visit"] // 2 + 1) // policy.STRIDE == row["token"] for row in selected)
    assert all(row["visit"] >= 30 for row in selected)
    control = policy.matched_control("manifest", selected, windows)
    assert {(r["rf_hz"], r["token"]) for r in selected} == {
        (r["rf_hz"], r["token"]) for r in control
    }
    assert 36 in {r["visit"] for r in selected if r["trigger"] == "novelty"}


def test_track_prediction_wraps_both_fields_and_flags_fresh_missing_track():
    frame = 1000.0
    tracks = []
    assert policy.novelty(tracks, (0.0, policy.ALIAS - 600, 998.0), 0, frame) == 0
    assert policy.novelty(tracks, (1.0, 400, 1.0), 1, frame) < 1
    assert policy.novelty(tracks, (2.0, 1400, 4.0), 2, frame) < 1e-8
    assert policy.novelty(tracks, None, 3.0, frame) == 2
    assert policy.novelty(tracks, None, 15.0, frame) == 0


def test_original_packet_replacement_preserves_exact_both_antenna_payloads():
    def probe(i, rx, passed):
        return dict(
            visit_index=i,
            receiver_id=rx,
            actual_rf_hz=100,
            candidates=[
                {
                    policy.GATE: passed,
                    policy.RANK: 0,
                    policy.MARGIN: 0.1 if passed else 0.01,
                }
            ],
        )

    def document(probes):
        keys = (
            "session_id",
            "input_manifest_sha256",
            "raw_recording_authority_digest",
            "sample_rate_hz",
            "probe_ms",
            "radio_id",
            "stream_generation",
            "capture_mode",
        )
        return dict(
            schema_version=1,
            clock_anchor={},
            delivery_clocks=[],
            last_sample_counter=2,
            provenance={"excluded_windows": []},
            source=dict(dict.fromkeys(keys), probes=probes),
        )

    fast = document([probe(i, rx, rx == 0) for i in range(2) for rx in range(2)])
    original = document([probe(i, rx, rx == 1) for i in range(2) for rx in range(2)])
    selection = [dict(visit=1, rf_hz=100, trigger="novelty")]
    rows, lineage = policy.project(fast, original, selection)
    assert rows[:2] == fast["source"]["probes"][:2]
    assert rows[2:] == original["source"]["probes"][2:]
    observed = trial.summarize(lineage)
    assert observed == dict(calls=1, gained=1, lost=1, changed=2, changed_winners=2, actions=1)


def test_serial_arrival_model_charges_work_that_finishes_after_close():
    selected = {5: 298.0, 6: 299.0}
    timings = {5: (1.0, 1.3), 6: (0.3, 1.2)}
    complete, final = ideal_serial(selected, timings, fast_delay_s=0.1)
    assert complete == 1
    assert final > 300
