from __future__ import annotations

import copy
import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("arm_probe_assess", HERE / "assess.py")
assert SPEC and SPEC.loader
assess = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = assess
SPEC.loader.exec_module(assess)


def plan() -> dict:
    cases = [
        ("dev-25", "real_ds5", "dev", 2_500_000, "lower"),
        ("dev-50", "real_ds5", "dev", 5_000_000, "upper"),
        ("control-pilot-lower-test", "synthetic_control", "control", 2_500_000, "lower"),
        ("control-noise-upper-test", "synthetic_control", "control", 2_500_000, "upper"),
        ("control-tone-lower-test", "synthetic_control", "control", 5_000_000, "lower"),
    ]
    return {
        "schema": "org.leo.research.arm-stateless-probe-plan/v1",
        "holdout_excluded": True,
        "methods": list(assess.METHODS),
        "warmups": 1,
        "repetitions": 3,
        "max_confirmations": 1,
        "seeded": False,
        "cases": [
            {
                "case_id": case_id,
                "origin": origin,
                "split": split,
                "rate_hz": rate,
                "edge": edge,
            }
            for case_id, origin, split, rate, edge in cases
        ],
    }


def candidate(case_id: str) -> dict:
    kind = assess.control_kind(case_id)
    positive = kind in (None, "pilot")
    exact = 0.01 if kind in ("noise", "tone") else 0.2
    control = 0.02 if kind in ("noise", "tone") else 0.03
    return {
        "epoch": 100,
        "fractional_complete": 1,
        "acquired_cfo_hz": -120000.0,
        "fractional_offset_samples": -0.25,
        "tracking_cfo_hz": -119999.5,
        "exact_score": exact,
        "control_score": control,
        "margin": exact - control,
        "acquire_score": 0.0,
        "verify_score": 0.0,
        "verify_control_score": 0.0,
        "conditioned_score": 0.0,
        "coarse_score": 0.0,
        "exact_grid": [exact] * 5,
        "control_grid": [control] * 5,
        "fixture_positive": positive,
    }


def receiver(case_id: str, rx: int, method: str) -> dict:
    if method == "packed_builtin_fp64":
        packing, detector, native = 0.10, 1.00, 0.90
    elif method == "packed_fftw_fp64":
        packing, detector, native = 0.10, 0.90, 0.80
    else:
        packing, detector, native = 0.0, 0.70, 0.60
    value = candidate(case_id)
    result = {
        "rank": {
            "scores": [6.0, 5.0, 4.0, 3.0, 2.0, 1.0],
            "order": [0, 1, 2, 3, 4, 5],
            "projected_epoch_samples": [100, 101, 102, 103, 104, 105],
            "fold_cpu_ms": 0.08,
            "correlation_cpu_ms": 0.05,
            "total_cpu_ms": 0.15,
            "total_wall_ms": 0.15,
        },
        "confirmation_count": 1,
        "confirmation_window_mask": 1,
        "confirmations": [
            {
                "candidate_count": 1,
                "candidates": [
                    {key: item for key, item in value.items() if key != "fixture_positive"}
                ],
                "conversion_cpu_ms": 0.05,
                "coarse_cpu_ms": 0.15,
                "fine_cpu_ms": 0.10,
                "fractional_cpu_ms": 0.10,
                "total_cpu_ms": 0.45,
                "total_wall_ms": 0.45,
            }
        ],
        "nuisances": [
            {
                "enabled": 1,
                "applied": 0,
                "frequency_hz": -1000.0,
                "spectral_fraction": 0.01,
                "fitted_power_fraction": 0.02,
                "cpu_ms": 0.02,
            }
        ],
        "prefix_cpu_ms": [native],
        "prefix_wall_ms": [native],
        "timing_proposals": [
            {
                "epoch": 0,
                "score": 0.1,
                "fold_cpu_ms": 0.01,
                "correlation_cpu_ms": 0.01,
                "total_cpu_ms": 0.03,
                "total_wall_ms": 0.03,
            }
        ],
        "total_cpu_ms": native,
        "total_wall_ms": native,
    }
    screens = {
        "available_mask": 3,
        "selected": 0,
        "scores": [[6.0, 5.0, 4.0, 3.0, 2.0, 1.0]] * 2,
        "contrast": [1.2, 1.1],
        "order": [[0, 1, 2, 3, 4, 5]] * 2,
        "epochs": [[100, 101, 102, 103, 104, 105]] * 2,
    }
    return {
        "receiver": rx,
        "packing_cpu_ms": packing,
        "packing_wall_ms": packing,
        "detector_cpu_ms": detector,
        "detector_wall_ms": detector,
        "result": result,
        "screens": screens,
    }


def probe_result(case: dict, method: str) -> dict:
    repetitions = []
    for index in range(3):
        receivers = [receiver(case["case_id"], rx, method) for rx in (0, 1)]
        stage = sum(row["packing_cpu_ms"] + row["detector_cpu_ms"] for row in receivers)
        repetitions.append(
            {
                "index": index,
                "receivers": receivers,
                "visit_cpu_ms": stage + 0.05,
                "visit_wall_ms": stage + 0.06,
            }
        )
    return {
        "schema": "org.leo.research.arm-stateless-probe-result/v1",
        "method": method,
        "fft_backend": "fixture",
        "case_id": case["case_id"],
        "rate_hz": case["rate_hz"],
        "edge": case["edge"],
        "io_cpu_ms": 0.03,
        "io_wall_ms": 0.04,
        "initialization_cpu_ms": 0.05,
        "initialization_wall_ms": 0.06,
        "warmups": 1,
        "repetitions": repetitions,
    }


def remote_receipt(probe_plan: dict) -> dict:
    rows = []
    for case_index, case in enumerate(probe_plan["cases"]):
        order = assess.METHODS[case_index % 3 :] + assess.METHODS[: case_index % 3]
        for position, method in enumerate(order):
            rows.append(
                {
                    "schedule_position": position,
                    "case": {
                        name: case[name]
                        for name in ("case_id", "origin", "split", "rate_hz", "edge")
                    },
                    "result": probe_result(case, method),
                }
            )
    hashes = {"probe": "a" * 64}
    attestation = {"tx_safe": True, "idle": True}
    return {
        "schema": "org.leo.research.arm-stateless-remote-result/v1",
        "status": "complete",
        "execution_environment": "physical_arm_saved_iq",
        "qemu": False,
        "host": "192.0.2.1",
        "serial": "serial",
        "firmware": "fixture",
        "case_limit": len(probe_plan["cases"]),
        "plan_complete": True,
        "rf_collection": False,
        "firmware_written": False,
        "temporary_files_removed": True,
        "before": attestation,
        "after": copy.deepcopy(attestation),
        "remote_hashes_before": hashes,
        "remote_hashes_after": copy.deepcopy(hashes),
        "rows": rows,
    }


def find_result(receipt: dict, case_id: str, method: str) -> dict:
    return next(
        item["result"]
        for item in receipt["rows"]
        if item["result"]["case_id"] == case_id and item["result"]["method"] == method
    )


def test_complete_receipt_reports_both_baselines_groups_and_stage_ceilings() -> None:
    probe_plan = plan()
    result = assess.assess(remote_receipt(probe_plan), probe_plan)
    assert result["timing_valid"] is True
    assert result["scientific_pass"] is True
    assert set(result["costs"]) == {
        "all",
        "real_dev",
        "controls",
        "rate_2500000",
        "rate_5000000",
    }
    all_costs = result["costs"]["all"]
    assert all_costs["aligned_v5_fftw_fp32"]["boundary_cpu_ms"] == 0.0
    for baseline in assess.BASELINES:
        comparison = result["cost_comparisons"]["all"][baseline]["aligned_v5_fftw_fp32"]
        assert comparison["total_cpu_speedup"] > 1
        assert "fine_cpu_ms" in comparison["baseline_perfect_stage_removal_ceiling"]


def test_signed_cfo_fraction_and_negative_margin_are_valid() -> None:
    probe_plan = plan()
    result = assess.assess(remote_receipt(probe_plan), probe_plan)
    labels = result["control_labels"]
    for method in assess.METHODS:
        assert labels[method]["noise"]["all_exact_labels_match"]
        assert labels[method]["tone"]["all_exact_labels_match"]


@pytest.mark.parametrize(
    "mutation", ["missing", "repetitions", "nonfinite", "nested_nonfinite", "timing"]
)
def test_incomplete_nonfinite_or_invalid_timing_is_rejected(mutation: str) -> None:
    probe_plan = plan()
    receipt = remote_receipt(probe_plan)
    if mutation == "missing":
        receipt["rows"].pop()
    else:
        row = receipt["rows"][0]["result"]
        if mutation == "repetitions":
            row["repetitions"].pop()
        elif mutation == "nonfinite":
            row["repetitions"][0]["visit_cpu_ms"] = math.nan
        elif mutation == "nested_nonfinite":
            row["repetitions"][0]["receivers"][0]["result"]["timing_proposals"][0][
                "total_wall_ms"
            ] = math.inf
        else:
            row["repetitions"][0]["visit_cpu_ms"] = 0.01
    with pytest.raises(ValueError):
        assess.assess(receipt, probe_plan)


def test_rank_change_and_control_label_change_fail_scientific_gate() -> None:
    probe_plan = plan()
    receipt = remote_receipt(probe_plan)
    aligned = find_result(receipt, "dev-25", "aligned_v5_fftw_fp32")
    for repetition in aligned["repetitions"]:
        rank = repetition["receivers"][0]["result"]["rank"]
        rank["order"] = [1, 0, 2, 3, 4, 5]
        repetition["receivers"][0]["result"]["confirmation_window_mask"] = 2
    tone = find_result(receipt, "control-tone-lower-test", "aligned_v5_fftw_fp32")
    for repetition in tone["repetitions"]:
        candidate_row = repetition["receivers"][0]["result"]["confirmations"][0]["candidates"][0]
        candidate_row["exact_score"] = 0.2
        candidate_row["margin"] = 0.18
    result = assess.assess(receipt, probe_plan)
    assert result["scientific_pass"] is False
    assert not result["scientific_identity"]["all"]["packed_builtin_fp64"]["aligned_v5_fftw_fp32"][
        "all_identity_gates_pass"
    ]
    assert not result["control_labels"]["aligned_v5_fftw_fp32"]["tone"]["all_exact_labels_match"]


def test_qemu_fixture_is_functional_only_and_never_has_costs() -> None:
    receipt = json.loads((HERE / "qemu.functional.json").read_text())
    result = assess.assess(receipt)
    assert result["timing_valid"] is False
    assert result["functional_identity_pass"] is True
    assert result["costs"] is None
    receipt["timing_valid"] = True
    with pytest.raises(ValueError, match="QEMU"):
        assess.assess(receipt)


def test_prefix_or_qemu_marked_remote_receipt_is_rejected() -> None:
    probe_plan = plan()
    for field, value in (("plan_complete", False), ("qemu", True)):
        receipt = remote_receipt(probe_plan)
        receipt[field] = value
        with pytest.raises(ValueError):
            assess.assess(receipt, probe_plan)
