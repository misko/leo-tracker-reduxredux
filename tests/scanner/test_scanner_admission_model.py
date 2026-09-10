"""Causal, bounded model tests; no hardware or external corpus required."""

import copy
import gzip
import json
from pathlib import Path

import pytest

from tools.evaluate_scanner_admission import POLICIES, Visit, evaluate, simulate, summarize


def cycle(n=240, period=120.0):
    return [Visit(i, i % 8, (i + 1) * period) for i in range(n)]


@pytest.mark.parametrize("policy", POLICIES)
@pytest.mark.parametrize("cost", [50.0, 120.0, 172.62, 240.0, 500.0])
def test_single_worker_causal_and_bounded(policy, cost):
    visits = cycle()
    checks = simulate(visits, cost, policy)
    assert len({r.visit for r in checks}) == len(checks)
    for i, r in enumerate(checks):
        assert visits[r.visit].target == r.target
        assert 0 <= r.started_ms - r.ready_ms <= 120.0
        assert r.completed_ms == r.started_ms + cost
        if i:
            assert r.started_ms >= checks[i - 1].completed_ms
    assert checks[-1].completed_ms <= visits[-1].ready_ms + 120 + cost


def test_even_stride_starves_half_the_targets_and_coprime_stride_does_not():
    visits = cycle()
    even = summarize(visits, [r.visit for r in simulate(visits, 173, "every_2")])
    odd = summarize(visits, [r.visit for r in simulate(visits, 173, "every_3")])
    assert even["starved_targets"] == [1, 3, 5, 7]
    assert odd["starved_targets"] == []


def test_immediate_busy_drop_can_alias_even_without_explicit_stride():
    visits = cycle()
    immediate = simulate(visits, 173, "immediate")
    fair = simulate(visits, 173, "oldest_target_one_pending")
    assert summarize(visits, [r.visit for r in immediate])["starved_targets"]
    assert not summarize(visits, [r.visit for r in fair])["starved_targets"]
    assert len(fair) > len(immediate)


def test_exact_completion_boundary_is_available_before_arrival():
    assert len(simulate(cycle(40), 120, "immediate")) == 40


@pytest.mark.parametrize("policy", POLICIES)
def test_future_visits_cannot_change_past_admission(policy):
    visits = cycle()
    prefix = visits[:53]
    cut = prefix[-1].ready_ms
    full = [r for r in simulate(visits, 170.5, policy) if r.started_ms <= cut]
    truncated = [r for r in simulate(prefix, 170.5, policy) if r.started_ms <= cut]
    assert full == truncated


def test_freshness_guard_does_not_wait_for_targets_never_seen():
    visits = [Visit(i, 3, (i + 1) * 120) for i in range(40)]
    checks = simulate(visits, 173, "freshness_guard_one_pending")
    assert len(checks) > 20


def test_freshness_guard_does_not_shed_work_without_overload():
    visits = cycle()
    assert len(simulate(visits, 100, "freshness_guard_one_pending")) == len(visits)


def test_pending_work_expires_instead_of_growing_without_bound():
    checks = simulate(cycle(2), 500, "oldest_target_one_pending", maximum_queue_age_ms=120)
    assert [r.visit for r in checks] == [0]


def test_sparse_targets_are_not_confused_with_detector_starvation():
    visits = [Visit(i, 3, (i + 1) * 120) for i in range(10)]
    result = summarize(visits, [0])
    assert result["starved_targets"] == []
    assert result["unvisited_targets"] == [0, 1, 2, 4, 5, 6, 7]


@pytest.mark.parametrize("cost", [0, -1, float("inf"), float("nan")])
def test_invalid_cost_rejected(cost):
    with pytest.raises(ValueError):
        simulate(cycle(), cost, "immediate")


@pytest.mark.parametrize(
    "visits",
    [
        [Visit(0, 8, 120)],
        [Visit(1, 0, 120)],
        [Visit(0, 0, 120), Visit(1, 1, 120)],
        [Visit(0, 0, float("nan"))],
    ],
)
def test_invalid_schedule_rejected(visits):
    with pytest.raises(ValueError):
        simulate(visits, 100, "immediate")


@pytest.fixture
def snapshot():
    root = Path(__file__).resolve().parents[2]
    source = (
        root
        / "reports/evidence/2026_09_10_scanner_cooperative_skips_checkpoint"
        / "production-snapshot.json.gz"
    )
    return json.loads(gzip.decompress(source.read_bytes()))


def test_saved_evidence_is_accounted_without_inventing_verdicts(snapshot):
    original = copy.deepcopy(snapshot)
    result = evaluate(snapshot)
    assert result["observed"]["screened"] == 660
    assert result["observed"]["visits"] == 2363
    assert len(result["scenarios"]) == 20
    assert all("verdict" not in row for s in result["scenarios"] for row in s["checks"])
    assert snapshot == original


def test_freshness_guard_reduces_recorded_schedule_long_gap_case(snapshot):
    scenarios = evaluate(snapshot)["scenarios"]
    selected = {
        s["policy"]: max(t["maximum_source_screen_gap_ms"] for t in s["per_target"])
        for s in scenarios
        if s["cost_basis"] == "wall_median" and s["additional_serial_reserve_ms"] == 20
    }
    assert selected["oldest_target_one_pending"] > 12000
    assert selected["freshness_guard_one_pending"] < 3200


def test_integer_counter_translation_above_2_to_53_changes_no_result(snapshot):
    baseline = evaluate(snapshot)
    shifted = copy.deepcopy(snapshot)
    for row in shifted["responses"]["glrt"]["body"]["evidence"]["results"]:
        for key in ("valid_start", "valid_end"):
            row[key] = str(int(row[key]) + 2**60)
    assert evaluate(shifted) == baseline


@pytest.mark.parametrize("mutation", ["dropped", "missing", "mixed_rx", "partial", "overlap"])
def test_untrustworthy_public_inventory_rejected(snapshot, mutation):
    evidence = snapshot["responses"]["glrt"]["body"]["evidence"]
    rows = evidence["results"]
    if mutation == "dropped":
        evidence["dropped_results"] = 1
    elif mutation == "missing":
        rows.pop()
    elif mutation == "mixed_rx":
        rows[0]["rx"] = 0
    elif mutation == "partial":
        rows[0]["search_window_mask"] = 1
    else:
        rows[1]["valid_start"] = rows[0]["valid_start"]
    with pytest.raises(ValueError):
        evaluate(snapshot)
