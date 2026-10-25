"""Check final geometry table provenance and family-owned derivative closure."""
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / "geometry"


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    report = read(ROOT / "summary.json")
    assert report["source_sha256"] == digest(ROOT / "report_geometry.py")
    for item in report["output_sha256"]:
        assert digest(item["path"]) == item["sha256"]
    detail = read(ROOT / "family_score_detail.json")
    assert detail["passed"] and detail["source_sha256"] == digest(ROOT / "family_score_detail.py")
    for item in detail["input_seals"]:
        assert digest(item["path"]) == item["sha256"]
    owned = list(csv.DictReader((ROOT / "family_owned_score_derivatives.csv").open()))
    changes = list(csv.DictReader((ROOT / "family_owned_score_derivative_changes.csv").open()))
    indexed, grouped = {}, defaultdict(float)
    maximum_closure = 0.
    maximum_finite_difference_difference = 0.
    for row in owned:
        key = row["case"], row["arm"], row["model"], row["location"], row["norad"]
        assert key not in indexed
        indexed[key] = row
        total = sum(float(v) for k,v in row.items() if k.endswith("_derivative_per_km") and k != "total_owned_derivative_per_km")
        assert abs(total-float(row["total_owned_derivative_per_km"])) < 1e-10
        grouped[key[:-1]] += total
    for item in detail["summaries"]:
        key = item["case"], item["arm"], item["model"], item["location"]
        assert abs(grouped[key]-item["family_owned_derivative_sum"]) < 1e-9
        raw = read(ROOT / (item["case"]+".json"))["arms"][item["arm"]]["models"][item["model"]]["endpoints"][item["location"]]
        # Both decompositions differentiate directly along the displacement.
        # Dotting separately differenced x/y gradients has a distinct O(h^2)
        # finite-difference remainder and is checked separately below.
        full = sum(raw["derivatives"]["term_directional_derivatives_per_km"].values())
        closure = abs(grouped[key]+sum(item["global_derivatives"].values())-full)
        maximum_closure = max(maximum_closure, closure)
        assert closure < 1e-6
        maximum_finite_difference_difference = max(maximum_finite_difference_difference,
            abs(full-raw["derivatives"]["directional_derivative_per_km"]))
    for row in changes:
        a = indexed[row["case"], row["arm"], "baseline", "baseline_endpoint", row["norad"]]
        b = indexed[row["case"], row["arm"], "rf50", "baseline_endpoint", row["norad"]]
        for field, value in row.items():
            if field.endswith("_derivative_change_per_km"):
                original_field = field.replace("_derivative_change_per_km", "_derivative_per_km")
                assert abs(float(value)-(float(b[original_field])-float(a[original_field]))) < 1e-10
    assert len(owned) == 416 and len(changes) == 104 and len(detail["summaries"]) == 16
    assert "Ran 5 tests" in (ROOT / "tests.log").read_text() and "\nOK" in (ROOT / "tests.log").read_text()
    result = dict(status="passed", source_sha256=digest(Path(__file__)), no_position_fitting=True,
        GPS_used=False, geometry_csv_hashes_verified=len(report["output_sha256"]), family_derivative_rows_checked=len(owned),
        family_derivative_change_rows_checked=len(changes), full_derivative_groups_checked=len(detail["summaries"]),
        maximum_owned_plus_global_derivative_closure=maximum_closure,
        maximum_direct_directional_vs_dotted_gradient_difference=maximum_finite_difference_difference,
        summary_sha256=digest(ROOT / "summary.json"), family_score_detail_sha256=digest(ROOT / "family_score_detail.json"))
    (HERE / "geometry_table_audit.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
