"""Component tests for bounded extraction and waveform measurement semantics."""

import dataclasses
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "ds11_replication16_run_test", Path(__file__).with_name("run.py")
)
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def fake_plan():
    return {
        "rows": [
            {
                "ordinal": i,
                "track_id": f"track-{i // 60}",
                "observation_index": i,
                "visit": 1000 + i,
            }
            for i in range(124)
        ]
    }


def test_interrupted_row_is_terminal_and_never_silently_retried():
    value = run.initial_extraction(fake_plan(), "plan-digest")
    value["rows"][0]["status"] = "reading"
    run.terminalize_interrupted(value, stage="reading", exhaust_pending=False)
    assert value["rows"][0] == {
        "ordinal": 0,
        "track_id": "track-0",
        "observation_index": 0,
        "visit": 1000,
        "status": "failed",
        "reason": "reading_process_interrupted",
    }
    assert value["rows"][1]["status"] == "pending"
    run.terminalize_interrupted(value, stage="reading", exhaust_pending=True)
    assert run.status_counts(value["rows"]) == {"failed": 1, "not_attempted": 123}


@dataclasses.dataclass
class Candidate:
    candidate_rank: int
    fractional_tracking_cfo_hz: float


def bound_row():
    candidate = Candidate(3, -417.25)
    matched = [
        SimpleNamespace(
            visit_index=7,
            support_center_utc_ns=101,
            receiver_id=0,
            channel=1,
            probe_index=2,
            candidate_rank=3,
        )
    ]
    probe = SimpleNamespace(actual_rf_hz=10.71e9, probe_start_ms=20, edge="lower")
    row = {
        "observation_index": 0,
        "support_center_utc_ns": 101,
        "receiver_id": 0,
        "visit": 7,
        "channel": 1,
        "probe_index": 2,
        "candidate_rank": 3,
        "actual_rf_hz": 10.71e9,
        "probe_start_ms": 20,
        "edge": "lower",
        "candidate": dataclasses.asdict(candidate),
    }
    freeze = {"visits": [7], "training_mask": [True]}
    return row, freeze, matched, probe, candidate


def test_metadata_binding_accepts_exact_row_and_rejects_timestamp_change():
    row, freeze, matched, probe, candidate = bound_row()
    run.validate_row_metadata(row, freeze, matched, probe, candidate)
    matched[0].support_center_utc_ns += 1
    with pytest.raises(ValueError, match="frozen row"):
        run.validate_row_metadata(row, freeze, matched, probe, candidate)


def test_arm_windows_and_canonical_mapping_are_exact():
    calls = []

    def fit_function(frames, indices):
        calls.append(indices.copy())
        return float(indices[0] + indices[-1])

    def error_function(frames, frequency):
        return np.array([frequency, frequency + 1])

    row = {"actual_rf_hz": 10.71e9, "measured_hz": 500.0, "additive_alias": -2}
    result = run.measure_frames(np.zeros((2, 300, 1)), row, fit_function, error_function)
    assert list(result) == ["cached", "pilot_2_65", "pilot_22_221"]
    assert np.array_equal(calls[0], np.arange(64))
    assert np.array_equal(calls[1], np.arange(20, 220))
    expected = (20 + 219) * 11.2e9 / 10.71e9
    assert result["pilot_22_221"]["canonical_delta_hz"] == pytest.approx(expected)
    assert result["pilot_22_221"]["corrected_measured_hz"] == pytest.approx(500 + expected)
    assert all(arm["additive_alias"] == -2 for arm in result.values())


def test_actual_estimator_fit_does_not_use_symbols_222_through_301():
    estimator_path = (
        run.ROOT / "reports/2026_09_29_training_waveform/estimator.py"
    )
    estimator_spec = importlib.util.spec_from_file_location(
        "ds11_waveform_estimator_test", estimator_path
    )
    estimator = importlib.util.module_from_spec(estimator_spec)
    estimator_spec.loader.exec_module(estimator)
    rng = np.random.default_rng(65512)
    symbols = np.arange(300)
    frames = np.exp(2j * np.pi * 137.0 * symbols * estimator.TS)[None, :, None]
    frames = np.repeat(frames, 2, axis=0) * np.array([1.0 + 0.2j, 0.7 - 0.3j])[:, None, None]
    changed = frames.copy()
    changed[:, 220:300] = rng.normal(size=(2, 80, 1)) + 1j * rng.normal(size=(2, 80, 1))
    assert run.arm_frequencies(frames, estimator.fit) == run.arm_frequencies(changed, estimator.fit)
    assert not np.array_equal(estimator.errors(frames, 0.0), estimator.errors(changed, 0.0))


def test_measurement_denominator_preserves_extraction_failures(tmp_path, monkeypatch):
    plan = fake_plan()
    extraction = run.initial_extraction(plan, "plan-digest")
    for row in extraction["rows"]:
        row["status"] = "ok"
    extraction["rows"][4].update(status="failed", reason="unreadable chunk")
    inventory = tmp_path / "extraction.json"
    inventory.write_text("frozen extraction checkpoint")
    monkeypatch.setattr(run, "INVENTORY", inventory)
    value = run.initial_measurements(plan, "plan-digest", extraction)
    assert len(value["rows"]) == value["denominator"] == 124
    assert value["rows"][4]["status"] == "not_available"
    assert "unreadable chunk" in value["rows"][4]["reason"]
    assert run.status_counts(value["rows"]) == {"pending": 123, "not_available": 1}
