"""Guard schedule geometry and visit-grouped validation in the stride study."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

TOOLS = Path(__file__).parents[2] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("scan_stride", TOOLS / "replay_scan_glrt_stride.py")
stride = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stride)
evaluation_spec = importlib.util.spec_from_file_location(
    "stride_evaluation", TOOLS / "evaluate_scan_glrt_stride.py"
)
evaluation = importlib.util.module_from_spec(evaluation_spec)
evaluation_spec.loader.exec_module(evaluation)


@pytest.mark.parametrize("step,count", [(120, 1), (60, 2), (40, 3), (20, 6), (10, 11)])
def test_schedule_stays_within_valid_visit(step, count):
    starts = stride.probe_starts(step)
    assert len(starts) == count
    assert starts[0] == 0 and starts[-1] + 20 <= 120


def test_projected_overlap_matches_twenty_millisecond_stride():
    assert stride.probe_starts(10, project_nonoverlap=True) == stride.probe_starts(20)


@pytest.mark.parametrize("fs", [2_500_000, 5_000_000])
@pytest.mark.parametrize("epoch", [0, 19, 2033])
def test_epoch_propagation_returns_local_first_frame(fs, epoch):
    for start in range(0, 101, 10):
        value = stride.shifted_epoch(epoch, start, fs)
        assert 0 <= value <= fs / 750 + 1
    for start in range(0, 101, 20):
        assert stride.shifted_epoch(epoch, start, fs) == epoch


def test_all_probes_from_heldout_visit_are_excluded():
    baseline = {v: {"t_s": float(v)} for v in range(10)}
    dense = [
        {"visit_index": v, "t_s": v + j / 100, "y_hz": 30 - 2 * (v + j / 100)}
        for v in range(10)
        for j in range(6)
    ]
    a = evaluation.fit_from_visits(dense, baseline, set(range(6)), [6, 7, 8, 9])
    poisoned = [{**r, "y_hz": 1e9} if r["visit_index"] >= 6 else r for r in dense]
    b = evaluation.fit_from_visits(poisoned, baseline, set(range(6)), [6, 7, 8, 9])
    assert a == pytest.approx(b)
    assert a == pytest.approx([18, 16, 14, 12])


def test_replicating_a_visit_does_not_increase_its_total_weight():
    baseline = {v: {"t_s": float(v)} for v in range(10)}
    dense = [{"visit_index": v, "t_s": float(v), "y_hz": float(np.sin(v))} for v in range(10)]
    a = evaluation.fit_from_visits(dense, baseline, set(range(10)), list(range(10)))
    duplicated = dense + [dense[5]] * 12
    b = evaluation.fit_from_visits(duplicated, baseline, set(range(10)), list(range(10)))
    assert a == pytest.approx(b)


def test_discarded_overlap_still_counts_toward_compute():
    document = {
        "session_id": "synthetic",
        "sample_rate_hz": 2500000,
        "input_visits": 10,
        "results": [
            {
                "visit_index": v,
                "start_ms": s,
                "t_s": v + s / 1000,
                "y_hz": 30 - 2 * (v + s / 1000),
                "margin": 0.5,
                "runtime_ms": 1,
            }
            for v in range(10)
            for s in range(0, 101, 10)
        ],
    }
    row = evaluation.evaluate(
        document, "stride_10ms_projected", stride.probe_starts(20), stride.probe_starts(10)
    )
    assert row["status"] == "ok"
    assert row["eligible_probes_per_visit"] == 6
    assert row["scheduled_probes_per_visit"] == row["compute_ms_per_visit"] == 11
