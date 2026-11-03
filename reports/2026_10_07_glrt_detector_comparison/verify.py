"""Independently audit frozen score artifacts and production-equivalent results."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from leo.analysis.starlink.pilot_methods import _glrt_pair, _SymbolCorrelations

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_detection_counts(scores, threshold, count, detected) -> np.ndarray:
    scores = np.asarray(scores)
    if scores.shape != (count,) or not np.all(np.isfinite(scores)):
        raise ValueError("invalid score geometry or nonfinite score")
    decisions = scores > threshold
    if int(decisions.sum()) != detected:
        raise ValueError("saved detection count disagrees with scores and frozen threshold")
    return decisions


def check_common_bank(row: dict) -> None:
    ids = [candidate["candidate_id"] for candidate in row["candidate_bank"]]
    if len(ids) != 8 or len(set(ids)) != 8:
        raise ValueError("invalid common candidate inventory")
    for candidates in row["methods"].values():
        if sorted(c["candidate_id"] for c in candidates) != sorted(ids):
            raise ValueError("method did not score the identical candidate bank")


def verify_synthetic() -> dict:
    directory = HERE / "synthetic/pooled14"
    summary = json.loads((directory / "summary.json").read_text())
    config = summary["config"]
    assert config["frames_per_trial"] == 14
    assert config["synthetic_source_sha256"] == sha(HERE / "synthetic.py")
    assert config["methods_source_sha256"] == sha(HERE / "methods.py")
    assert summary["protocol_sha256"] == sha(directory / "frozen_protocol.json")
    frozen = json.loads((directory / "frozen_thresholds.json").read_text())
    assert frozen["protocol_sha256"] == summary["protocol_sha256"]
    nulls = np.load(directory / "heldout_null_scores.npz", allow_pickle=False)
    calibration = np.load(directory / "calibration_null_scores.npz", allow_pickle=False)
    signals = np.load(directory / "heldout_signal_scores.npz", allow_pickle=False)
    comparisons = 0
    joint_comparisons = 0
    for environment, results in summary["environments"].items():
        for method, null in results["null"].items():
            key = f"{environment}__{method}"
            threshold = frozen["thresholds"][environment][method]
            assert calibration[key].shape == (config["calibration_null_count"],)
            expected = np.quantile(calibration[key], 1 - config["target_false_alarm"],
                                   method="higher")
            assert threshold == float(expected) == null["threshold"]
            check_detection_counts(nulls[key], threshold, null["count"], null["false_alarms"])
            assert null["rate"] == null["false_alarms"] / null["count"]
            comparisons += 1
        for snr, methods in results["signals"].items():
            prefix = f"{environment}__snr_{snr}"
            truth = signals[f"{prefix}__truth_cfo_hz"]
            period = 1 / config["symbol_step_s"]
            for method, result in methods.items():
                threshold = frozen["thresholds"][environment][method]
                decisions = check_detection_counts(signals[f"{prefix}__{method}__score"],
                                                   threshold, result["count"], result["detected"])
                estimates = signals[f"{prefix}__{method}__cfo_hz"]
                errors = np.abs((estimates - truth + period / 2) % period - period / 2)
                assert int(np.sum(decisions & (errors <= 1000))) == result[
                    "detected_and_cfo_within_1khz"]
                assert result["cfo_detection_conditional"]["count"] == int(decisions.sum())
                assert result["cfo_unconditional"]["count"] == len(truth)
                comparisons += 1
                joint_comparisons += 1
    return {
        "null_and_signal_count_checks": comparisons,
        "joint_detection_cfo_checks": joint_comparisons,
        "thresholds_recomputed_from_independent_calibration": len(nulls.files),
        "source_and_protocol_hashes_valid": True,
        "artifacts": {path.name: sha(path) for path in sorted(directory.iterdir())
                      if path.suffix in (".npz", ".json", ".csv")},
    }


def verify_recorded(name: str) -> dict:
    directory = HERE / "recorded" / name
    results = json.loads((directory / "results.json").read_text())
    provenance = json.loads((directory / "provenance.json").read_text())
    for path, digest in provenance["sources"].items():
        assert "sha256:" + sha(ROOT / path) == digest, path
    for field, filename in (("provenance_sha256", "provenance.json"),
                            ("training_sha256", "training.npz"),
                            ("matrices_sha256", "matrices.npz")):
        assert results[field] == "sha256:" + sha(directory / filename)
    assert provenance["selection_sha256"] == "sha256:" + sha(directory / "selection.json")
    matrices = np.load(directory / "matrices.npz", allow_pickle=False)
    count = 0
    maximum_error = 0.0
    for index, row in enumerate(results["rows"]):
        check_common_bank(row)
        current = {c["candidate_id"]: c for c in row["methods"]["current_glrt64_margin"]}
        gaussian = {c["candidate_id"]: c for c in row["methods"]["gaussian_glrt64"]}
        for candidate in row["candidate_bank"]:
            cid = candidate["candidate_id"]
            exact = matrices[f"r{index}_b{cid}_exact"]
            control = matrices[f"r{index}_b{cid}_control"]
            times = np.broadcast_to(np.arange(64) * 4.4e-6, exact.shape)
            expected, expected_control = _glrt_pair(
                _SymbolCorrelations(exact, np.zeros_like(times), times),
                _SymbolCorrelations(control, np.zeros_like(times), times), size=512,
            )
            actual = current[cid]
            errors = (abs(actual["score"] - (expected[0] - expected_control[0])),
                      abs(actual["exact_score"] - expected[0]),
                      abs(actual["control_score"] - expected_control[0]))
            maximum_error = max(maximum_error, *errors)
            assert max(errors) < 5e-12
            assert abs(actual["cfo_hz"] - candidate["seed_cfo_hz"] - expected[1]) < 1e-7
            assert actual["cfo_hz"] == gaussian[cid]["cfo_hz"]
            count += 1
    assert len(results["rows"]) == 96 and count == 768
    return {"windows": len(results["rows"]), "production_oracle_candidates": count,
            "maximum_production_score_error": maximum_error,
            "same_candidate_gaussian_cfo_equal": True,
            "source_cache_and_provenance_hashes_valid": True,
            "results_sha256": sha(directory / "results.json")}


def run() -> dict:
    receipt = {"synthetic": verify_synthetic(),
               "recorded": {name: verify_recorded(name)
                            for name in ("production_final", "coarse_final")}}
    receipt["reviewer_source_sha256"] = sha(Path(__file__))
    (HERE / "verification.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
