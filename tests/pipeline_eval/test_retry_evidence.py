from tools.pipeline_eval.qualification import retry_evidence_trial as trial
from tools.pipeline_eval.variants import retry_evidence as rule


def factor(margin, epoch=0, cfo=0):
    return {
        rule.MARGIN: margin,
        rule.GATE: margin >= 0.025,
        "integer_epoch_sample": epoch,
        "fractional_epoch_offset_samples": 0.0,
        "fractional_tracking_cfo_hz": cfo,
    }


def test_rule_reads_primary_failed_and_passing_lanes_only():
    policy = {
        "operator": "all",
        "clauses": [("failed_margin", 0.005, None), ("peer_margin", 0.25, None)],
    }
    assert rule.passes(policy, [factor(0.005)], [factor(0.25)])
    assert not rule.passes(policy, [factor(0.0049)], [factor(0.25)])
    assert not rule.passes(policy, [factor(0.005)], [factor(0.2499)])
    assert not rule.passes(policy, [], [factor(0.30)])


def test_agreement_accepts_circular_epoch_but_uses_literal_frequency():
    policy = {"operator": "all", "clauses": [("agreement", 2, 1000)]}
    assert rule.passes(policy, [factor(0.02, 13_332, -500)], [factor(0.25, 0, 500)])
    assert not rule.passes(policy, [factor(0.02, 13_332, -500)], [factor(0.25, 0, 501)])


def test_time_spread_matches_count_deterministically_with_one_choice_per_interval():
    visits = [10 * i for i in range(25)]
    selected = trial.time_spread(visits, 6, "case")
    assert trial.time_spread(visits, 6, "case") == selected
    assert trial.time_spread(visits, 0, "case") == []
    assert trial.time_spread(visits, len(visits), "case") == visits
    for index, visit in enumerate(selected):
        assert visit in visits[index * 25 // 6 : (index + 1) * 25 // 6]


def probe(visit, rx, *candidates):
    return dict(visit_index=visit, receiver_id=rx, candidates=list(candidates))


def document(rows):
    return dict(
        clock_anchor=1,
        delivery_clocks=2,
        last_sample_counter=3,
        provenance=dict(excluded_windows=[]),
        source=dict(probes=rows),
    )


def test_every_original_opportunity_includes_both_successful_and_failed_retries():
    p0, p1 = probe(0, 0, factor(0.3)), probe(0, 1, factor(0.02))
    p2, p3 = probe(1, 0, factor(0.01)), probe(1, 1, factor(0.4))
    p4, p5 = probe(2, 0, factor(0.3)), probe(2, 1, factor(0.3))
    first = document([p0, p1, p2, p3, p4, p5])
    second = document([p0, probe(0, 1, factor(0.03)), probe(1, 0, factor(0.02)), p3, p4, p5])
    rows = list(trial.opportunities(first, second))
    assert [(r["visit"], r["rx"], r["rescue"]) for r in rows] == [(0, 1, True), (1, 0, False)]
    assert len(list(trial.opportunities(first, second, before=1))) == 1


def test_easiest_qualifying_rule_wins_when_pairing_adds_no_evidence():
    rows = [
        dict(rescue=bool(i), failed=[factor(0.015 if i else -0.01)], peer=[factor(0.1)])
        for i in (0, 0, 1, 1)
    ]
    result, _ = trial.choose(rows)
    assert result["qualified"]
    assert (result["rescues"], result["attempts"]) == (2, 2)
    assert len(result["policy"]["clauses"]) == 1
