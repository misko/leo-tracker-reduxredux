import pytest

from reports.ALGO08.v3 import balanced_stereo as experiment


def ledger(count, *, exclude=(), channels=(1, 2)):
    probes = []
    for visit in range(count*len(channels)+len(exclude)):
        if visit in exclude:
            continue
        channel = channels[visit % len(channels)]
        for radio in (0, 1):
            probes.append(dict(visit_index=visit, receiver_id=radio, edge="lower", channel=channel,
                               actual_rf_hz=1_000_000*channel, payload_start_sample=visit*10_000_000,
                               valid_start_counter=(visit+1)*10_000_000, candidates=[]))
    full = len(probes)//2+len(exclude)
    return dict(source=dict(probes=probes), provenance=dict(excluded_windows=[dict(visit=n) for n in exclude],
                processed_windows=len(probes)//2, window_count=full, invalid_capture=len(exclude)),
                delivery_clocks=[{} for _ in range(full)])


def test_complementary_channel_and_cycle_phase_preserves_anchors():
    rows = experiment.schedule(ledger(16))
    by_channel = [[row for row in rows if row["stream"][1] == n] for n in (1, 2)]
    assert [row["slot"] for row in by_channel[0] if row["paid"]] == [0, 2, 4, 6, 0, 1, 3, 5, 7]
    assert [row["slot"] for row in by_channel[1] if row["paid"]] == [0, 1, 3, 5, 7, 0, 2, 4, 6]
    assert experiment.donor_budget(rows) == {0: 3, 1: 4, 16: 4, 17: 3}
    assert all(row["omitted_short_calls"] == 14 for row in experiment.support(rows))


def test_exclusions_do_not_advance_stream_and_schedule_is_outcome_blind():
    original = ledger(17, exclude=(1,), channels=(1,))
    expected = experiment.schedule(original)
    assert expected[1]["visit"] == 2 and expected[1]["slot"] == 1
    assert [row["visit"] for row in expected if row["slot"] == 0] == [0, 9, 17]
    for probe in original["source"]["probes"]:
        probe["candidates"] = object()
    assert experiment.schedule(original) == expected


def test_held_score_pays_only_measured_donors_and_full_set_matches():
    import anchor_cycle_route

    original = ledger(16)
    a = [row for row in original["source"]["probes"] if row["channel"] == 1]
    for row in a[:4]:
        row["candidates"] = [dict(fractional_tracking_cfo_hz=10., fractional_margin=.50, candidate_rank=0,
                                  passed_fractional_margin_gate=True)]
    scheduled = experiment.schedule(original)
    anchors = experiment.donor_budget(scheduled)
    regular = anchor_cycle_route.select_route(original)
    assert experiment.paid_route(original, dict.fromkeys(anchors, 7)) == regular

    omitted = {row["visit"] for row in scheduled if not row["paid"]}
    for row in original["source"]["probes"]:
        if row["visit_index"] in omitted:
            row["candidates"] = []
    report = experiment.paid_route(original, anchors, audit=True)
    assert {(row["n"], row["scheduled_donors"]) for row in report["cycles"]} == {(3, 7), (4, 7)}
    for row in report["cycles"]:
        assert row["probabilities"]["unfiltered"] == (row["counts"]["unfiltered"]+.5)/(row["n"]+1)
    assert sum(row["outcome"] for row in report["cycles"]) == 2
    with pytest.raises(ValueError, match="denominator"):
        experiment.paid_route(original, {})


def test_refuses_partial_stereo_or_nonchronological_sample_counter():
    original = ledger(3)
    original["source"]["probes"][5]["valid_start_counter"] += 1
    with pytest.raises(ValueError, match="stereo"):
        experiment.schedule(original)
