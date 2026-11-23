from pathlib import Path

import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    import mixed_stereo_paid

    return mixed_stereo_paid


def stereo(visits):
    return [dict(channel=channel, actual_rf_hz=11e9+channel, edge="upper", visit_index=visit,
                 valid_start_counter=visit * 80, receiver_id=rx, candidates=[])
            for visit, channel in enumerate(visits) for rx in (0, 1)]


def test_quintets_alternate_orientation_by_stream_and_group_and_leave_tails_unpaid(trial):
    rows = stereo([1, 2] * 12)
    normal, streams = trial.slots(rows, inverted=False)
    opposite, observed = trial.slots(rows, inverted=True)
    assert streams == observed
    assert [s["complete_groups"] for s in streams] == [2, 2]
    assert [s["unpaid_tail_visits"] for s in streams] == [2, 2]
    assert {i ^ 1 for i in normal} == opposite
    assert sorted(normal) == [0, 1, 2, 3, 8, 11, 17, 18, 20, 21, 22, 23, 29, 30, 36, 39]
    assert len(normal) * 5 <= len(rows) * 2


def test_mixing_rejects_broken_stereo_and_backward_counter(trial):
    rows = stereo([1] * 5)
    rows[1]["edge"] = "lower"
    with pytest.raises(ValueError, match="paired stereo"):
        trial.slots(rows, inverted=False)
    rows = stereo([1] * 5)
    rows[4]["valid_start_counter"] = rows[5]["valid_start_counter"] = -1
    with pytest.raises(ValueError, match="counter order"):
        trial.slots(rows, inverted=False)


def test_selector_uses_only_paid_verified_peaks_and_prices_each_paid_antenna(trial):
    rows = stereo([1] * 5)
    chosen = dict(candidate_rank=1, fractional_margin=14., passed_fractional_margin_gate=True)
    for row in rows:
        row["candidates"] = [dict(chosen, fractional_margin=14.1, passed_fractional_margin_gate=False),
                             dict(chosen, candidate_rank=2), chosen]
    clocks = [10**8 * (i + 1) for i in range(len(rows))]
    results, metadata = trial.select(rows, clocks, inverted=False)
    assert results == [[chosen], [chosen], [], [], [chosen], [], [], [], [], [chosen]]
    assert metadata["paid_lanes"] == 4
    assert metadata["paid_visits"] == 3
    assert metadata["stereo_visits"] == 1
    assert metadata["paid_lanes_by_receiver"] == {"0": 2, "1": 2}
    assert metadata["paid_native_cpu_s"] == 1.8


def test_acquisition_keeps_full_non_detector_cost_and_charges_fallback_inside_solver(trial):
    full = dict(identity=dict(all_native_cpu_s=4., ledger={"acquisition_cpu_s": 7.}), cpu_s=5., elapsed_s=5.1)
    paid = dict(identity=dict(selection={"paid_native_cpu_s": 1.65, "charged_selection_cpu_s": .01}),
                cpu_s=4.5, elapsed_s=4.7)
    result = trial.account(paid, full)
    assert result["projected_acquisition_cpu_s"] == pytest.approx(4.66)
    assert result["projected_total_ratio"] == pytest.approx(9.16 / 12)
    assert result["solve_elapsed_ratio"] == pytest.approx(4.7 / 5.1)


def test_displaced_outcome_requires_completed_original_exterior_witness(trial):
    result = {"complete": True, "evaluated": True, "would_withhold": True}
    row = dict(status="withheld", reason="no_passing_calibration", exterior_checks=[{"result": result}])
    assert not trial.checked_exterior(row)
    row["reason"] = "both_receivers_support_far_exterior"
    assert trial.checked_exterior(row)
    row["exterior_checks"][0]["result"]["complete"] = False
    assert not trial.checked_exterior(row)
