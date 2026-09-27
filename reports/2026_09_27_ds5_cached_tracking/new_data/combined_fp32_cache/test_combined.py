from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent.parent
SPEC = importlib.util.spec_from_file_location(
    "combined_fp32_cache_runner", HERE / "run_combined.py"
)
assert SPEC and SPEC.loader
combined = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = combined
SPEC.loader.exec_module(combined)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_source_lock_and_fp32_fftw_backend_are_exact() -> None:
    design, lock = combined.verify_source_lock()
    assert lock["design_sha256"] == digest(HERE / "design.json")
    assert lock["adapter_sha256"] == digest(HERE / "run_combined.py")
    assert design["fp32_fftw_library_sha256"] == digest(combined.FP32)
    receipt = json.loads(combined.FP32.with_name(combined.FP32.name + ".build.json").read_text())
    assert receipt["semantics"] == "FP32 FFTW all FFTs, ESTIMATE plans; not bit-equivalent"
    assert "fft32_fftw.c" in " ".join(receipt["command"])
    assert receipt["binary_sha256"] == digest(combined.FP32).removeprefix("sha256:")


def test_combined_policy_is_the_unchanged_v6_full_aperture_policy() -> None:
    design = json.loads((HERE / "design.json").read_text())
    v6 = json.loads((REPORT / "config.dev.v6.strided.json").read_text())
    assert design["policy"] == v6["policy"]
    assert design["known_state"]["frame_limit"] == v6["frame_limit"] == 16
    assert design["candidate"]["local_recovery"] is v6["local_recovery"] is False
    assert v6["native_module"] == "known_state_v3"


def test_state_update_receives_candidate_only_and_no_reference_argument() -> None:
    candidate = object()

    class SpyTracker:
        def __init__(self):
            self.received = None

        def update(self, key, start, index, observation, *, discovery):
            self.received = (key, start, index, observation, discovery)
            return True

    tracker = SpyTracker()
    assert combined.update_candidate_state(tracker, "key", 100, 7, candidate, True)
    assert tracker.received == ("key", 100, 7, candidate, True)
    assert combined.update_candidate_state(tracker, "key", 101, 8, None, False) is False
    assert tracker.received == ("key", 100, 7, candidate, True)


def test_design_freezes_reference_match_and_no_extras_gate() -> None:
    design = json.loads((HERE / "design.json").read_text())
    decision = design["decision"]
    assert "<=2 us" in decision["reference_match"]
    assert "<=8 kHz" in decision["reference_match"]
    assert decision["identity_gate"] == (
        "retain every packed FP64 reference positive and add no candidate positives"
    )
    assert decision["future_reference_state_use_forbidden"] is True


def test_result_uses_fp32_only_for_every_blind_fallback() -> None:
    result = json.loads((HERE / "results.json").read_text())
    assert result["fallback_backend"]["kind"] == "fp32_fftw"
    assert result["fallback_backend"]["library_sha256"] == digest(combined.FP32)
    fallback = [row for row in result["rows"] if row["used_blind"]]
    assert len(fallback) == result["summary"]["all_visits"]["blind_calls"] == 182
    assert all(row["fallback_backend"] == "fp32_fftw" for row in fallback)
    assert all(not row["fallback_rank_order_changed"] for row in fallback)
    assert all(not row["fallback_selected_window_changed"] for row in fallback)


def test_result_never_feeds_reference_into_causal_state() -> None:
    rows = json.loads((HERE / "results.json").read_text())["rows"]
    assert len(rows) == 256
    assert all(row["reference_used_for_state"] is False for row in rows)
    assert all(row["state_update_source"] in (None, "candidate_observation") for row in rows)
    assert all(
        row["state_update_source"] == "candidate_observation"
        for row in rows
        if row["observation"] is not None and row["candidate_positive"]
    )


def test_identity_failure_and_actual_combined_cost_are_reported() -> None:
    result = json.loads((HERE / "results.json").read_text())
    identity = result["identity_gate"]
    expected = {
        "all": (129, 120, 9, 9),
        "2500000": (62, 60, 2, 2),
        "5000000": (67, 60, 7, 7),
    }
    groups = {"all": identity["all"], **identity["by_rate"]}
    for name, counts in expected.items():
        group = groups[name]
        assert (
            group["reference_positives"],
            group["matched_reference_positives"],
            group["lost_reference_positives"],
            group["additional_candidate_positives"],
        ) == counts
        assert group["gate_pass"] is False
    summary = result["summary"]
    assert summary["all_visits"]["cpu_speedup"] > 1
    assert summary["by_rate"]["2500000"]["cpu_speedup"] > 1
    assert summary["by_rate"]["5000000"]["cpu_speedup"] > 1
