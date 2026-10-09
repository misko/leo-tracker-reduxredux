"""Receipt-only verification of the terminal negative continuation; no evaluation."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


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
    summary = read(HERE / "summary.json")
    assert result["protocol_sha256"] == digest
    assert result["status"] == summary["status"] == "calibration-unqualified"
    stages = list((HERE / "stages").glob("*.json"))
    assert len(stages) == 1
    stage = read(stages[0])
    assert stage["protocol_sha256"] == digest
    assert stage["key"] == "recovered-calibration"
    assert stage["value"] == result["calibration"]
    assert stage["value"]["result"]["postfit"] == summary["postfit"]
    assert summary["postfit"]["converged"] is False
    assert summary["postfit"]["stationarity"] > 0.001
    assert stage["value"]["result"]["calibration"] is None
    inventory = result["prefit_selection"]["inventory"]
    selected = min((row for row in inventory if row["qualified"]), key=lambda row: row["objective"])
    assert selected["path"] == result["prefit_selection"]["selected_path"]
    assert selected["path"].endswith("position_error_iter96/result.json")
    assert selected["stationarity"] <= 0.001
    assert summary["fresh_baseline_parity"].startswith("Not measured")
    assert summary["candidate_position_results"] == "Neither c arm reached regional finals or B7"
    paths = [
        HERE / "protocol.json",
        HERE / "result.json",
        HERE / "summary.json",
        HERE / "RESULTS.md",
        HERE / "qualification.png",
        *stages,
    ]
    receipt = dict(
        protocol_sha256=digest,
        frozen_closure_files_verified=len(plan["source_sha256"]),
        terminal_status=result["status"],
        original_stage_receipts=1,
        stages=dict(
            prefit_selection="completed; iteration96 qualified",
            receiver_correction="attempted",
            corrected_fixed_position_postfit="attempted; unqualified",
            association="not reached",
            fitted_c_regional_final="not reached",
            zero_c_regional_final="not reached",
            regional_winner_selection="not reached",
            ordinary_only_B7_replay="not reached; parity unmeasured",
            candidate_B7="not reached",
        ),
        archived_baseline_position_errors_km={
            row["arm"]: row["error_km"] for row in summary["archived_baseline"]
        },
        new_position_result=None,
        no_numerical_evaluation=True,
        file_sha256={str(path.relative_to(HERE)): sha(path) for path in paths},
    )
    (HERE / "verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps({key: value for key, value in receipt.items() if key != "file_sha256"}, indent=2)
    )


if __name__ == "__main__":
    main()
