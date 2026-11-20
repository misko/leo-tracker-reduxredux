from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import rf_lane_panel as panel
from tools.pipeline_eval.qualification.rf_lane_panel_results import publish, scores
from tools.pipeline_eval.scoring import ARMS, ROLES
from tools.pipeline_eval.variants.rf_routing import choose_rf

SEED = "ab" * 32
CENTERS = {(1, "lower"): 10709687500, (2, "lower"): 10959687500, (3, "lower"): 11209687500}


def document():
    source = dict.fromkeys(
        (
            "session_id",
            "raw_recording_authority_digest",
            "sample_rate_hz",
            "probe_ms",
            "radio_id",
            "stream_generation",
            "capture_mode",
        ),
        "common",
    )
    source["input_manifest_sha256"] = f"sha256:{SEED}"
    source["probes"] = [
        dict(
            visit_index=visit,
            channel=channel,
            edge="lower",
            actual_rf_hz=float(CENTERS[channel, "lower"]),
            receiver_id=receiver,
            candidates=[{"passed_fractional_margin_gate": True}],
        )
        for visit, channel in enumerate((1, 2, 0, 3, 1, 2, 3, 1, 2, 3))
        if channel
        for receiver in (0, 1)
    ]
    return dict(
        source=source,
        schema_version=1,
        clock_anchor={},
        delivery_clocks=list(range(10)),
        last_sample_counter=10,
        provenance=dict(processed_windows=9, excluded_windows=[{"visit": 2}], window_count=10),
    )


def test_whole_and_count_matched_routes_preserve_full_negative_pairs():
    fast = document()
    original = deepcopy(fast)
    for probe in original["source"]["probes"]:
        probe["candidates"] = []
    plan = panel.schedule(fast, CENTERS)
    rf = choose_rf(SEED, CENTERS.values())
    assert plan["assigned_rf_hz"] == rf
    assert plan["invalid"] == [2]
    assert plan["whole_original_visits"] == [
        visit for visit, center in plan["visits"] if center == rf
    ]
    assert len(plan["whole_original_visits"]) == len(plan["spread_original_visits"]) == 3
    assert {
        center for visit, center in plan["visits"] if visit in plan["spread_original_visits"]
    } == set(CENTERS.values())
    streams, census, lineage = panel.project(fast, original, plan)
    for policy in ("whole", "spread"):
        decisions = set(plan[f"{policy}_original_visits"])
        assert len(streams[policy]) == 18
        for probe in streams[policy]:
            assert bool(probe["candidates"]) == (probe["visit_index"] not in decisions)
        assert sum(v[policy]["original_visits"] for v in census.values()) == 3
        assert sum(v[policy]["lost_positive_probes"] for v in census.values()) == 6
    assert all(w["fast_pair_sha256"] != w["original_pair_sha256"] for w in lineage)
    assert streams["fast"] == fast["source"]["probes"]
    assert streams["original"] == original["source"]["probes"]


def test_schedule_rejects_bad_stereo_rf_and_invalid_census():
    fast = document()
    fast["source"]["probes"][1]["actual_rf_hz"] += 1
    with pytest.raises(ValueError, match="configured physical RF"):
        panel.schedule(fast, CENTERS)
    fast = document()
    fast["provenance"]["excluded_windows"] = [{"visit": 3}]
    with pytest.raises(ValueError, match="partition all physical visits"):
        panel.schedule(fast, CENTERS)


def test_parent_time_support_must_match():
    fast = document()
    original = deepcopy(fast)
    original["delivery_clocks"][-1] += 1
    with pytest.raises(ValueError, match="recording and clock authority"):
        panel.project(fast, original, panel.schedule(fast, CENTERS))


def test_exact_allocation_is_deterministic_and_proportional():
    groups = {50: [0, 6], 60: [1, 7, 9], 70: list(range(10, 16))}
    visits = panel.spread_visits(groups, 6, f"sha256:{SEED}")
    reversed_groups = dict(reversed(groups.items()))
    assert visits == panel.spread_visits(reversed_groups, 6, SEED.upper())
    assert [len(visits.intersection(v)) for v in groups.values()] == [1, 2, 3]


def test_figure_scoring_counts_a_guarded_failure_in_the_denominator(tmp_path):
    panel.pack(tmp_path / "prior-original-first-attempts.jsonl.gz", [])
    ident = "DS26-0999"
    rows = [
        dict(
            id=ident,
            condition=policy,
            method=f"rf_lane_{policy}",
            tile={"center": [0, 0]},
            result=dict(
                status="ok",
                boundary="test compact fit",
                metrics={"c0_frequency_score": 12.0, "fitted_c_frequency_score": 13.0},
                arms={
                    "c0": {"latlon": [12.5 / 111.0, 0], "rf_rms_hz": 4.0},
                    "fitted_c": {"latlon": [0, 0], "rf_rms_hz": 3.0},
                },
            ),
        )
        for policy in panel.POLICIES
    ]
    references = {
        ident: {
            "truth": [0, 0],
            "reference": {role: {arm: {"error_km": 1.0} for arm in ARMS} for role in ROLES},
        }
    }
    before, guarded, receipt, _ = publish(tmp_path, rows)
    assert before == rows
    assert receipt[0]["guarded_result"] == "withheld"
    geography, frequency, summary, _ = scores(guarded, references, {"all": [ident]})
    assert not any(r["error_km"] is not None or r["within_10pct"] for r in geography)
    assert all(r["forced_error_km"] is not None for r in geography)
    assert [(r["frequency_score"], r["rf_rms_hz"]) for r in frequency[:2]] == [(12, 4), (13, 3)]
    assert len(summary) == 2 * (len(panel.POLICIES) + len(ROLES))
    assert all(
        r["scheduled"] == 1 and r["published"] == 0
        for r in summary
        if r["method"].startswith("rf_lane_")
    )
