"""Independent arithmetic, coverage, and binding audit of the DS8 scores."""

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results.json"
DATASET = HERE / "dataset.json"
PARTITIONS = HERE / "partitions.json"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(left, right, tolerance=1e-10):
    if not math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=tolerance):
        raise AssertionError(f"{left} != {right}")


def summary(values):
    return {
        "records": values,
        "eligible_recordings": len(values),
        "equal_record_mean": math.fsum(values.values()) / len(values),
        "positive_records": sum(value > 0 for value in values.values()),
        "negative_records": sum(value < 0 for value in values.values()),
        "zero_records": sum(value == 0 for value in values.values()),
    }


def main():
    result = json.loads(RESULTS.read_text())
    dataset = json.loads(DATASET.read_text())
    partitions = json.loads(PARTITIONS.read_text())
    assert result["schema"] == "rx-ds8-geometry-score/v1"
    assert result["status"] == "complete"
    assert result["eligible_session_count"] == 4
    assert result["eligible_sessions"] == result["readiness_sessions"]
    assert set(result["records"]) == set(result["readiness_sessions"])

    # Bind the score payload to every direct input and its exclusive launch receipt.
    score_inputs = {
        "model": HERE / "models.json",
        "training_dataset": ROOT / "reports/2026_09_28_rx_geometry_association/dataset.json",
        "dataset": DATASET,
        "readiness": ROOT / "reports/2026_09_28_rx_causal_refit/ds8-readiness.json",
    }
    for name, path in score_inputs.items():
        assert result["source_sha256"][name] == sha256(path)
    launch = json.loads((HERE / "score-launch.json").read_text())
    for relative, expected in launch["sha256"].items():
        assert sha256(ROOT / relative) == expected

    # Unique source-window coverage: partition opportunities are counted once, not once per lane.
    source_roles = {
        row["source_window_id"]: row["role"]
        for row in partitions["windows"]
        if row["role"] in ("reception", "held_frequency")
    }
    assert len(source_roles) == 3551
    dataset_rows = [window for lane in dataset["lanes"] for window in lane["windows"]]
    dataset_ids = [row["source_window_id"] for row in dataset_rows]
    assert len(dataset_ids) == len(set(dataset_ids)) == 1767
    assert set(dataset_ids) <= set(source_roles)
    assert all(row["role"] == source_roles[row["source_window_id"]] for row in dataset_rows)
    assert dataset["accounting"] == {"lanes": 8, "windows": 1767}
    lane_counts = Counter(lane["lane"]["session_id"] for lane in dataset["lanes"])
    assert lane_counts == Counter({session_id: 2 for session_id in result["readiness_sessions"]})
    selected_lanes = {
        (
            lane["lane"]["session_id"], lane["lane"]["channel"],
            lane["lane"]["edge"], float(lane["lane"]["actual_rf_hz"]),
            float(lane["lane"]["actual_rf_hz"]),
        )
        for lane in dataset["lanes"]
    }
    partition_by_id = {row["source_window_id"]: row for row in partitions["windows"]}
    for lane in dataset["lanes"]:
        expected_identity = (
            lane["lane"]["session_id"], lane["lane"]["channel"], lane["lane"]["edge"],
            float(lane["lane"]["actual_rf_hz"]), float(lane["lane"]["actual_rf_hz"]),
        )
        for window in lane["windows"]:
            row = partition_by_id[window["source_window_id"]]
            actual_identity = (
                row["session_id"], row["channel"], row["edge"],
                float(row["actual_rf_hz_by_receiver"]["rx0"]),
                float(row["actual_rf_hz_by_receiver"]["rx1"]),
            )
            assert actual_identity == expected_identity
    omitted_in_selected_lane = []
    for row in partitions["windows"]:
        if row["role"] not in ("reception", "held_frequency"):
            continue
        if row["source_window_id"] in set(dataset_ids):
            continue
        identity = (
            row["session_id"], row["channel"], row["edge"],
            float(row["actual_rf_hz_by_receiver"]["rx0"]),
            float(row["actual_rf_hz_by_receiver"]["rx1"]),
        )
        if identity in selected_lanes:
            omitted_in_selected_lane.append(row["source_window_id"])
    assert not omitted_in_selected_lane

    # Reconstruct every role total from exported per-window values and require one common reference.
    for _session_id, record in result["records"].items():
        assert record["eligible"] is True
        assert record["eligible_lanes"] == 2
        for family in ("uniform", "causal"):
            for _name, evaluation in record["families"][family]["evaluations"].items():
                rows = [row for lane in evaluation["lanes"] for row in lane["windows"]]
                for role in ("reception", "held_frequency"):
                    selected = [row for row in rows if row["role"] == role]
                    totals = evaluation["roles"][role]
                    assert (
                        len(selected)
                        == totals["windows"]
                        == record["references"][role]["windows"]
                    )
                    relative = math.fsum(row["relative_log_score"] for row in selected)
                    reference = math.fsum(row["reference_log_score"] for row in selected)
                    close(relative, totals["relative_log_score"])
                    close(reference, totals["reference_log_score"])
                    close(relative + reference, totals["full_log_score"])
                    close(relative / len(selected), totals["relative_log_score_per_window"])
                    close(reference / len(selected), totals["reference_log_score_per_window"])
                    close(
                        totals["reference_log_score"],
                        record["references"][role]["causal_reference_log_score"],
                    )

    # Reconstruct every exported equal-record contrast from record-level evaluations.
    rebuilt = {}
    eligible = result["eligible_sessions"]
    for role in ("reception", "held_frequency"):
        rebuilt[f"{role}:causal_reference-uniform_reference"] = summary(
            {
                sid: result["records"][sid]["references"][role][
                    "causal_minus_uniform_reference_per_window"
                ]
                for sid in eligible
            }
        )
        specifications = (
            "D", "E", "S", "T", "T_swap", "T_reverse",
            "D_shift", "E_shift", "S_shift", "T_shift",
        )
        contrasts = (
            ("E", "D"), ("S", "D"), ("T", "D"), ("T", "S"),
            ("T", "T_swap"), ("T", "T_reverse"), ("D", "D_shift"),
            ("E", "E_shift"), ("S", "S_shift"), ("T", "T_shift"),
        )
        for family in ("uniform", "causal"):
            def value(sid, name, selected_family=family, selected_role=role):
                evaluation = result["records"][sid]["families"][selected_family][
                    "evaluations"
                ][name]
                return evaluation["roles"][selected_role]["relative_log_score_per_window"]

            for name in specifications:
                rebuilt[f"{role}:{family}_{name}-causal_reference"] = summary(
                    {sid: value(sid, name) for sid in eligible}
                )
            for left, right in contrasts:
                rebuilt[f"{role}:{family}_{left}-{right}"] = summary(
                    {sid: value(sid, left) - value(sid, right) for sid in eligible}
                )
        for name in specifications:
            rebuilt[f"{role}:causal_family-{name}-uniform_family-{name}"] = summary(
                {
                    sid: result["records"][sid]["families"]["causal"]["evaluations"][
                        name
                    ]["roles"][role]["relative_log_score_per_window"]
                    - result["records"][sid]["families"]["uniform"]["evaluations"][name][
                        "roles"
                    ][role]["relative_log_score_per_window"]
                    for sid in eligible
                }
            )
    assert rebuilt.keys() == result["aggregate_equal_record"].keys()
    for key, actual in rebuilt.items():
        expected = result["aggregate_equal_record"][key]
        assert actual["records"].keys() == expected["records"].keys()
        for sid, value in actual["records"].items():
            close(value, expected["records"][sid])
        close(actual["equal_record_mean"], expected["equal_record_mean"])
        for field in (
            "eligible_recordings", "positive_records", "negative_records", "zero_records",
        ):
            assert actual[field] == expected[field]

    output = {
        "schema": "rx-ds8-result-audit/v1",
        "status": "pass",
        "eligible_sessions": 4,
        "dataset_lanes": 8,
        "partition_reception_held_unique_windows": len(source_roles),
        "dataset_unique_windows": len(dataset_ids),
        "outside_selected_geometry_lanes": len(source_roles) - len(dataset_ids),
        "omitted_within_selected_lane": 0,
        "extra_outside_selected_lane": 0,
        "per_window_role_sums_verified": True,
        "common_control_reference_verified": True,
        "equal_record_aggregates_verified": len(rebuilt),
        "source_sha256": {
            str(path.relative_to(ROOT)): sha256(path)
            for path in (RESULTS, DATASET, PARTITIONS, HERE / "score-launch.json", Path(__file__))
        },
    }
    with (HERE / "audit-results.json").open("x") as stream:
        json.dump(output, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
