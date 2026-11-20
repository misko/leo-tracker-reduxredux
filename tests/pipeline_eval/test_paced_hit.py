import pytest

from tools.pipeline_eval.qualification import paced_hit as trial
from tools.pipeline_eval.qualification import paced_hit_deadline_audit as deadline
from tools.pipeline_eval.qualification import paced_hit_results as results


def packet(positive):
    return dict(
        probes=[
            dict(
                receiver_id=rx,
                actual_rf_hz=100,
                candidates=[dict(passed_fractional_margin_gate=value, candidate_rank=0)],
            )
            for rx, value in enumerate(positive)
        ]
    )


def test_original_fractional_gate_alone_activates_partner():
    stock = packet((False, True))
    miss, hit = trial.projection(stock, 0)
    assert hit is False
    assert miss["probes"][0] == stock["probes"][0]
    assert miss["probes"][1] == dict(stock["probes"][1], candidates=[])
    same, hit = trial.projection(stock, 1)
    assert hit is True
    assert same == stock


def test_count_only_measured_lane_calls_and_actual_omitted_positive_rows():
    stock = [packet((False, True)), packet((True, True)), packet((True, False))]
    rows = []
    for visit, raw in enumerate(stock):
        expected, hit = trial.projection(raw, visit % 2)
        rows.append(
            dict(
                visit=visit,
                primary_receiver=visit % 2,
                primary_hit=hit,
                measured_lanes=1 + hit,
                full_visit_sha256=trial.pace.fingerprint(expected),
                outcome="queue_drop" if visit == 2 else "emitted",
            )
        )
    probes, kept, stats = results.observed_factors(rows, stock, trial.HIT)
    assert kept == [0, 1]
    assert len(probes) == 4
    assert stats == dict(
        primary_hits=1,
        omitted_partner_calls=1,
        omitted_positive_partner_probes=1,
        native_lane_calls=3,
        positive_probes=2,
    )
    rows[0]["measured_lanes"] = 2
    with pytest.raises(ValueError, match="native call count"):
        results.observed_factors(rows, stock, trial.HIT)


def test_exact_deadline_and_positive_support_are_counted_separately():
    rows = [
        dict(
            visit=i,
            outcome="emitted",
            primary_hit=bool(i),
            arrival_ns=0,
            emitted_ns=20_000_000 + i,
            native_wall_ns=10_000_000,
        )
        for i in range(2)
    ]
    probes = [dict(p, visit_index=i) for i in range(2) for p in packet((True, True))["probes"]]
    miss, hit = deadline.deadline_support(rows, probes)
    assert miss["timely_visits"] == 1
    assert miss["timely_positive_probes"] == 2
    assert hit["timely_visits"] == 0
    assert hit["timely_positive_probes"] == 0
    with pytest.raises(ValueError, match="exact actual retained"):
        deadline.deadline_support(rows[:1], probes)
