from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("mixed_aperture_crossed")


def test_axes_change_only_visit_support_or_verified_rank(experiment):
    def peak(rank, margin, verified=True):
        return dict(candidate_rank=rank, fractional_margin=margin, passed_fractional_margin_gate=verified)

    rows = [dict(channel=0, actual_rf_hz=11.0e9, edge="lower", visit_index=visit,
                 valid_start_counter=1 + 2 * visit, receiver_id=lane,
                 candidates=[peak(0, 1.), peak(1, 2. if lane == 0 else 1.), peak(1, 3., verified=False)])
            for visit in range(11) for lane in (0, 1)]
    cells = {}
    for mode, (all_times, all_ranks) in experiment.FACTORS.items():
        selected, stats = experiment.select(rows, [1_000_000] * len(rows), all_times=all_times, all_ranks=all_ranks)
        cells[mode] = [choice[0]["candidate_rank"] if choice else None for choice in selected]
        assert sum(stats["counts"].values()) == len(rows)
        assert stats["full_call_cpu_s_by_slot"]["full"] == pytest.approx(.001 * stats["counts"]["full"])
    for visit in range(11):
        idx = visit % 8
        available = idx == 0 or idx % 2
        for mode, (all_times, all_ranks) in experiment.FACTORS.items():
            retained = all_times or available
            left = 1 if idx == 0 or all_ranks else 0
            assert cells[mode][2 * visit:2 * visit + 2] == ([left, 0] if retained else [None, None])

    rows[2]["candidates"].pop(0)
    full_choice, _ = experiment.select(rows, [1] * len(rows), all_ranks=True)
    primary_choice, _ = experiment.select(rows, [1] * len(rows))
    assert full_choice[2][0]["candidate_rank"] == 1
    assert primary_choice[2] == []


def test_charged_projection_counts_each_paid_lane_and_unavoidable_work(experiment):
    identity = dict(ledger={"acquisition_cpu_s": 7.}, all_native_cpu_s=5., selection={
        "full_call_cpu_s_by_slot": {"full": .5, "primary": 4.5},
        "counts": {"full": 2, "primary": 400}, "charged_selection_cpu_s": .25,
    })
    costs = experiment.charge(dict(identity=identity, cpu_s=2.), {"cpu_s": 5.}, {"cpu_s": 3.})
    assert costs["free_all_native_and_selector_floor_cpu_s"] == 4.
    assert costs["zero_short_floor_cpu_s"] == 4.75
    assert costs["maximum_short_cpu_ms_per_lane"] == .625
    assert costs["projected_cpu_s"]["dense"] == pytest.approx(4.75 + 400 * .0010733641875)
    assert not costs["passes_dense_projection"]
