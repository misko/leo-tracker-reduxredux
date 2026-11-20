from copy import deepcopy

import pytest

from tools.pipeline_eval.variants.periodic_anchor import CHANNELS, mix, reference_sweeps


def make_schedule(groups):
    result = []
    for sweep, channels in enumerate(groups):
        for channel in channels:
            i = len(result)
            result.append(
                dict(
                    visit=i,
                    sweep=sweep,
                    channel=channel,
                    target_index=channel - 1,
                    edge="lower",
                    iq_sha256=f"digest-{i}",
                    sample_start=i * 100,
                    sample_end=i * 100 + 99,
                )
            )
    return result


def test_complete_sweeps_ignore_invalid_flags_and_partial_cycles_do_not_count():
    groups = [(7, 8), *[CHANNELS] * 130, (1, 2, 3)]
    schedule = make_schedule(groups)
    for row in schedule[3::5]:
        row["status"] = "invalid_capture"
    selected, all_complete = reference_sweeps(schedule)
    assert all_complete == 130
    assert [batch[0]["sweep"] for batch in selected] == [1, 65, 129]
    assert [batch[0]["visit"] for batch in selected] == [2, 514, 1026]


def make_native(schedule, score, invalid=()):
    probes = [
        dict(
            visit_index=record["visit"],
            receiver_id=receiver,
            channel=record["channel"],
            edge=record["edge"],
            probe_index=0,
            probe_start_ms=0,
            valid_start_counter=record["sample_start"],
            actual_rf_hz=11.4e9,
            candidates=[dict(passed_fractional_margin_gate=True, margin=score + receiver)],
        )
        for record in schedule
        if record["visit"] not in invalid
        for receiver in (0, 1)
    ]
    return dict(
        schema_version=2,
        clock_anchor={"sample_counter": 0},
        delivery_clocks=[],
        last_sample_counter=schedule[-1]["sample_end"],
        source=dict(
            session_id="test",
            probe_ms=20,
            sample_rate_hz=10_000_000,
            qualified=True,
            probes=probes,
            analysis_manifest_sha256=str(score),
        ),
        provenance=dict(
            window_count=len(schedule),
            invalid_capture=len(invalid),
            processed_windows=len(schedule) - len(invalid),
            skipped_fast_score=0,
            rf_mapping_authorities=["test"],
            excluded_windows=[
                {
                    k: schedule[visit][k]
                    for k in ("visit", "iq_sha256", "sample_start", "sample_end")
                }
                for visit in invalid
            ],
        ),
    )


def test_splice_substitutes_both_receivers_of_selected_valid_visits_only():
    schedule = make_schedule([CHANNELS] * 2)
    ordinary = make_native(schedule, 8, invalid=(3,))
    capture = make_native(schedule, 41, invalid=(3,))
    before = deepcopy(ordinary)
    probes, receipt = mix(ordinary, capture, schedule)
    assert ordinary == before
    assert probes[:14] == capture["source"]["probes"][:14]
    assert probes[14:] == ordinary["source"]["probes"][14:]
    assert receipt["selected_invalid_visits"] == 1
    assert receipt["selected_valid_visits"] == 7
    assert receipt["changed_visits"] == [0, 1, 2, 4, 5, 6, 7]


@pytest.mark.parametrize("bad", ("clock", "receiver", "exclusion", "probe-key"))
def test_unmatched_original_authority_fails_closed(bad):
    schedule = make_schedule([CHANNELS])
    ordinary = make_native(schedule, 8, invalid=(3,))
    capture = make_native(schedule, 41, invalid=(3,))
    if bad == "clock":
        capture["clock_anchor"]["sample_counter"] = 10
    elif bad == "exclusion":
        capture["provenance"]["excluded_windows"][0]["iq_sha256"] = "bad"
    elif bad == "receiver":
        for doc in (ordinary, capture):
            doc["source"]["probes"][1]["receiver_id"] = 0
    else:
        capture["source"]["probes"][0]["actual_rf_hz"] += 7_000
    with pytest.raises(ValueError):
        mix(ordinary, capture, schedule)
