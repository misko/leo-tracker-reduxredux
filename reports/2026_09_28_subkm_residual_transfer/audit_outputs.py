"""Independent exported-residual arithmetic and denominator checks."""

import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    summary = json.loads((HERE / "results/summary.json").read_text())
    launch = json.loads((HERE / "launch.json").read_text())
    assert (HERE / "exit-code.txt").read_text().strip() == "0"
    for name, expected in launch["sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    counts = {"joint_tracks": 0, "joint_records": 0, "paired_records": 0, "input_bindings": 0}
    for number, record in enumerate(summary["recordings"], 1):
        assert record["unit_id"] == f"single-{number:03}"
        detail = json.loads((HERE / f"results/{record['unit_id']}.json").read_text())
        for arm in ("joint", "independent"):
            rows = detail[arm + "_tracks"]
            if rows is None:
                assert arm == "independent" and record["independent_qualified"] is False
                assert record["joint_minus_independent_held"] is None
                continue
            totals = record[arm]
            assert totals["tracks"] == len(rows)
            for role in ("training", "held"):
                squares, count = 0.0, 0
                for row in rows:
                    values = [
                        value
                        for value, mask in zip(
                            row["map_centered_residual_hz"], row["training_mask"], strict=True
                        )
                        if bool(mask) == (role == "training")
                    ]
                    assert len(values) == row[role + "_observations"]
                    square = math.fsum(value * value for value in values)
                    assert math.isclose(
                        math.sqrt(square / len(values)),
                        row[role + "_rms_hz"],
                        rel_tol=1e-12,
                        abs_tol=1e-10,
                    )
                    squares += square
                    count += len(values)
                assert count == totals[role + "_observations"]
                assert math.isclose(
                    math.sqrt(squares / count), totals[role + "_rms_hz"], rel_tol=1e-12
                )
            for key in ("training_log_score", "held_predictive_log_density"):
                assert math.isclose(math.fsum(row[key] for row in rows), totals[key], rel_tol=1e-12)
        counts["joint_tracks"] += detail["joint"]["tracks"]
        counts["joint_records"] += 1
        counts["paired_records"] += int(record["independent_qualified"])
        counts["input_bindings"] += len(detail["artifact_hashes"])
    assert counts == {
        "joint_tracks": 5131,
        "joint_records": 88,
        "paired_records": 87,
        "input_bindings": 264,
    }
    result = {
        "status": "pass",
        **counts,
        "scope": "Exported residual arithmetic and source bindings; no second orbit propagation.",
    }
    with (HERE / "audit-results.json").open("x") as stream:
        json.dump(result, stream, indent=2)
    print(result)


if __name__ == "__main__":
    main()
