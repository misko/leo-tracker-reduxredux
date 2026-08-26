from __future__ import annotations

import csv
import gzip
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
TOOL_PATH = ROOT / "tools" / "run_fixed500_calibration.py"
SPEC = importlib.util.spec_from_file_location("run_fixed500_calibration", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


def _endpoint(
    scenario_id: str,
    endpoint_index: int,
    *,
    error: float | None,
    sigma: float | None,
    split: str = "calibration",
) -> dict[str, object]:
    complete = error is not None and sigma is not None
    return {
        "scenario_id": scenario_id,
        "row_id": "C01" if split == "calibration" else "E01",
        "split": split,
        "alignment": "oracle_true_resampled_lattice",
        "background_session_id": "background-a",
        "snr_db": -12.0,
        "frame_occupancy": 1.0,
        "acceleration_hz_s2": 0.0,
        "jerk_hz_s3": 0.0,
        "alias_change_hz": 0.0,
        "cfo_step_hz": 0.0,
        "sample_clock_offset_ppm": 0.0,
        "endpoint_index": endpoint_index,
        "endpoint_target_time_s": 0.5 * (endpoint_index + 1),
        "frame_start_sample": endpoint_index,
        "reference_time_s": 0.5 * (endpoint_index + 1),
        "step_stratum": "no_step",
        "estimator": "fixed_500ms_linear",
        "status": "complete" if complete else "no_result",
        "estimate_rate_hz_s": error,
        "legacy_sigma_hz_s": sigma,
        "interval_half_width_hz_s": None if sigma is None else 1.96 * sigma,
        "receiver_truth_rate_hz_s": 0.0,
        "physical_truth_rate_hz_s": 0.0,
        "receiver_error_hz_s": error,
        "physical_error_hz_s": error,
        "covered": None if not complete else abs(float(error)) <= 1.96 * float(sigma),
        "failure": None if error is None else abs(error) > 500.0,
        "odd_heldout_cfo_error_hz": 100_000.0,
    }


def test_grouped_calibration_uses_whole_scenario_maximum_and_retains_points() -> None:
    rows = [
        *[
            _endpoint("C1", index, error=value, sigma=10.0)
            for index, value in enumerate((5, 10, 20))
        ],
        *[
            _endpoint("C2", index, error=value, sigma=10.0)
            for index, value in enumerate((5, 30, 10))
        ],
    ]

    augmented, scores, quantile = tool._calibrate_intervals(rows)

    assert [row["maximum_standardized_error"] for row in scores] == [2.0, 3.0]
    assert quantile.finite_sample_available is False
    assert quantile.required_order == 3
    assert quantile.multiplier is None
    assert quantile.diagnostic_max_multiplier == 3.0
    diagnostic = [
        row for row in augmented if row["estimator"] == "fixed_500ms_max_score_diagnostic"
    ]
    assert [row["estimate_rate_hz_s"] for row in diagnostic] == [
        row["estimate_rate_hz_s"] for row in rows
    ]
    assert all(row["interval_half_width_hz_s"] == 30.0 for row in diagnostic)
    assert tool._diagnostic_points_are_exact_clones(augmented)

    diagnostic[0]["estimate_rate_hz_s"] = 999.0
    assert not tool._diagnostic_points_are_exact_clones(augmented)


def test_scenario_metrics_require_all_three_frozen_endpoints() -> None:
    complete = [
        _endpoint("E1", index, error=10.0, sigma=10.0, split="evaluation") for index in range(3)
    ]
    incomplete = [
        _endpoint("E2", 0, error=10.0, sigma=10.0, split="evaluation"),
        _endpoint("E2", 1, error=None, sigma=None, split="evaluation"),
        _endpoint("E2", 2, error=None, sigma=None, split="evaluation"),
    ]

    metrics = tool._scenario_metrics(complete + incomplete)

    first = next(row for row in metrics if row["scenario_id"] == "E1")
    second = next(row for row in metrics if row["scenario_id"] == "E2")
    assert first["evaluable"] is True
    assert first["scenario_simultaneous_coverage"] is True
    assert second["evaluable"] is False
    assert second["scenario_simultaneous_coverage"] is None


def test_step_strata_apply_frozen_transition_exclusion() -> None:
    assert (
        tool._step_stratum(
            cfo_step_hz=400.0,
            endpoint_time_s=1.0,
            cfo_step_time_s=1.1,
            transition_exclusion_s=0.5,
        )
        == "pre_step"
    )
    assert (
        tool._step_stratum(
            cfo_step_hz=400.0,
            endpoint_time_s=1.5,
            cfo_step_time_s=1.1,
            transition_exclusion_s=0.5,
        )
        == "transition_excluded"
    )
    assert (
        tool._step_stratum(
            cfo_step_hz=400.0,
            endpoint_time_s=1.7,
            cfo_step_time_s=1.1,
            transition_exclusion_s=0.5,
        )
        == "post_exclusion"
    )


def test_compressed_frame_ledger_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "ledger.csv.gz"
    rows = [{"scenario_id": "F5-1-E01", "status": "complete"}]

    tool._write_csv(path, rows, compressed=True)

    with gzip.open(path, mode="rt", newline="", encoding="utf-8") as source:
        assert list(csv.DictReader(source)) == rows
