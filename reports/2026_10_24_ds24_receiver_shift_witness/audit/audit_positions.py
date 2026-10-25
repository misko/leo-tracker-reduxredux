"""Reporting-only geographic audit after the scientific batch was sealed."""
import csv
import hashlib
import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PRIOR = Path("/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025")


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    assert read(HERE / "artifact_audit.json")["status"] == "passed"
    summary = read(ROOT / "report" / "summary.json")
    truth = tuple(summary["evaluation_only_GPS"])
    center = tuple(read(ROOT / "protocol.json")["region"]["center_latlon"])
    expected = {}
    for case, original in read(HERE / "baseline_membership.json")["cases"].items():
        baseline = read(original["baseline_path"])
        radio = read(PRIOR / "evaluation" / "models" / "receiver_fast_rx1_rf50" / (case+".json"))
        for arm in ("c0", "fitted_c"):
            for model, record in (("baseline", baseline["policy_arms"][arm]), ("sharedRF50", radio["arms"][arm])):
                expected[case, arm, "original_full_data", -1, model] = record
        for fold in range(3):
            result = read(ROOT / "heldout" / "results" / f"{case}_fold{fold}.json")
            for arm, data in result["arms"].items():
                for model, record in data["fits"].items():
                    expected[case, arm, "train_only_fold", fold, model] = record
    maximum_difference = 0.
    csv_rows = list(csv.DictReader((ROOT / "report" / "position_errors.csv").open()))
    json_rows = summary["rows"]
    for rows in (csv_rows, json_rows):
        seen = set()
        for row in rows:
            key = row["case"], row["arm"], row["scope"], int(row["fold"]), row["model"]
            assert key in expected and key not in seen
            seen.add(key)
            record = expected[key]
            east, north = record["endpoint_east_north_km"]
            assert float(row["east_km"]) == east and float(row["north_km"]) == north
            latitude = center[0]+north/111.
            longitude = center[1]+east/(111.32*math.cos(math.radians(center[0])))
            if "endpoint_latlon" in record:
                assert max(abs(a-b) for a,b in zip((latitude, longitude), record["endpoint_latlon"])) < 1e-12
            a, b, ta, tb = map(math.radians, (latitude, longitude, *truth))
            h = math.sin((a-ta)/2)**2+math.cos(a)*math.cos(ta)*math.sin((b-tb)/2)**2
            distance = 12742*math.atan2(math.sqrt(h), math.sqrt(1-h))
            difference = abs(distance-float(row["error_km"]))
            maximum_difference = max(maximum_difference, difference)
            assert difference < 1e-10
            phase = record.get("final_phase_change_s")
            actual = row["phase_change_s"]
            assert (actual is None or actual == "") if phase is None else float(actual) == phase
        assert set(expected) == seen and len(seen) == 32
    for path, sha in summary["source_bindings"].items():
        assert digest(path) == sha
    assert summary["source_sha256"] == digest(ROOT / "report_positions.py")
    result = dict(status="passed", source_sha256=digest(Path(__file__)),
        geographic_reporting_only_after_sealed_scientific_batch=True,
        no_position_fitting=True, no_method_selection_from_GPS=True, geographic_rows_checked=32,
        maximum_error_reconstruction_difference_km=maximum_difference,
        position_csv_sha256=digest(ROOT / "report" / "position_errors.csv"),
        position_summary_sha256=digest(ROOT / "report" / "summary.json"))
    (HERE / "position_reporting_audit.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
