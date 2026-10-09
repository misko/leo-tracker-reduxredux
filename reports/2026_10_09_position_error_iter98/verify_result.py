"""Independent receipt-only audit of matched continuation and original baseline."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARMS = ("fitted-c", "zero-c")
STAGES = ("B3", "B4", "B4W", "B5", "C6", "B7")


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    plan = read(HERE / "protocol.json")
    digest = sha(HERE / "protocol.json")
    for name, expected in plan["source_sha256"].items():
        assert sha(ROOT / name) == expected, name
    result = read(HERE / "result.json")
    assert result["status"] == "complete" and result["protocol_sha256"] == digest
    assert sha(HERE / "ordinary-winner-checkpoints.json") == sha(
        HERE.parent / "2026_10_09_position_error_iter95/ordinary-winner-checkpoints.json"
    )
    document = read(HERE.parent / "2026_10_09_position_error_iter93/published-v3.json")["manifest"][
        "document"
    ]
    expected_keys = {"recovered-calibration", "recovered-association"}
    expected_keys.update(
        f"recovered-final:{arm}:{start}"
        for arm in ARMS
        for start in ("association", "zero-timing", "own-continuation")
    )
    expected_keys.update(
        f"{context}:b7:{stage}:{arm}"
        for context in ("baseline", "candidate")
        for stage in STAGES
        for arm in ARMS
    )
    receipts, receipt_hashes = {}, {}
    for path in (HERE / "stages").glob("*.json"):
        row = read(path)
        assert row["protocol_sha256"] == digest
        assert row["key"] not in receipts
        receipts[row["key"]] = row
        receipt_hashes[str(path.relative_to(HERE))] = sha(path)
        assert row["value"]["reason"] is None
    assert set(receipts) == expected_keys and len(receipts) == 32
    qualified100 = read(HERE.parent / "2026_10_09_position_error_iter100/result.json")
    calibration = receipts["recovered-calibration"]["value"]["result"]["calibration"]
    assert calibration["postfit"]["vector"] == qualified100["fit"]["vector"]
    assert calibration["postfit"]["converged"]
    assert (
        result["regional_after"][ARMS[0]]["satellites"]
        == result["regional_after"][ARMS[1]]["satellites"]
    )
    margins, baseline_parity = {}, {}
    for arm in ARMS:
        original = document["diagnostics"]["b7"]["attempts"]["B7"][arm]
        baseline = result["baseline_operational"][arm]["fit"]
        assert baseline["vector"] == original["vector"]
        assert baseline["objective"] == original["objective"]
        baseline_parity[arm] = dict(vector_exact=True, objective_delta=0.0)
        before, after = result["regional_before"][arm], result["regional_after"][arm]
        recovered = [
            row
            for row in result["recovered_finals"]
            if row["arm"] == arm and row["fit"] and row["fit"]["converged"]
        ]
        best = min(
            recovered,
            key=lambda row: (
                row["fit"]["objective"] + row["calibration_penalty"],
                row["basin"],
                row["start"],
            ),
        )
        assert best["fit"]["vector"] == after["fit"]["vector"]
        old_score = before["fit"]["objective"] + before["calibration_penalty"]
        new_score = after["fit"]["objective"] + after["calibration_penalty"]
        assert new_score < old_score
        margins[arm] = dict(
            original_score=old_score,
            recovered_score=new_score,
            strict_improvement=old_score - new_score,
            original_calibration_penalty=before["calibration_penalty"],
            recovered_calibration_penalty=after["calibration_penalty"],
        )
        for context in ("baseline_attempts", "attempts"):
            for stage in STAGES:
                fit = result[context][stage][arm]
                assert fit["converged"] and fit["stationarity"] <= 0.001
                if arm == "zero-c":
                    assert fit["vector"][6] == 0
                    assert fit.get("rf_drift_coefficients", [0, 0]) == [0, 0]
    assert not result["baseline_reasons"] and not result["reasons"]
    output = dict(
        protocol_sha256=digest,
        frozen_hashes_verified=len(plan["source_sha256"]),
        complete_stage_receipts=32,
        qualified_joint_arm_stages=24,
        stage_receipt_sha256=receipt_hashes,
        original_candidate_checkpoint_copy_exact=True,
        baseline_parity=baseline_parity,
        regional_score_margins=margins,
        unexpected_failures=[],
        reference_coordinates_scope="Evaluation only; no operational winner input",
        c_scope="Shared fitted-derived calibration/association and search budgets; c0 static-c/RF-time locked",
        numerical_evaluations_run_by_audit=0,
    )
    (HERE / "verification.json").write_text(json.dumps(output, indent=2) + "\n")
    print(
        json.dumps(
            {key: value for key, value in output.items() if key != "stage_receipt_sha256"}, indent=2
        )
    )


if __name__ == "__main__":
    main()
