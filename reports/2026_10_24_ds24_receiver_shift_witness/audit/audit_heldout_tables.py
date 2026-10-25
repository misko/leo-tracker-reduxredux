"""Recompute every heldout report table from raw results, without fitting."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / "heldout"


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    movement, own, endpoints = {}, {}, {}
    phase_failures = []
    for path in sorted((ROOT / "results").glob("*.json")):
        result = read(path)
        case, fold = result["case"], result["fold"]
        for arm, data in result["arms"].items():
            xa, xb = (np.asarray(data["fits"][m]["endpoint_east_north_km"]) for m in ("baseline", "sharedRF50"))
            delta = xb-xa
            distance = float(np.linalg.norm(delta))
            endpoints[case, fold, arm] = dict(baseline_east_km=xa[0], baseline_north_km=xa[1],
                shared_east_km=xb[0], shared_north_km=xb[1], movement_east_km=delta[0],
                movement_north_km=delta[1], movement_km=distance)
            for model, fit in data["fits"].items():
                if fit["final_phase_change_s"] >= .01:
                    phase_failures.append(dict(case=case, fold=fold, arm=arm, model=model,
                        final_phase_change_s=fit["final_phase_change_s"]))
            for predictor, views in data["crossover"].items():
                for scale, a in views["baseline"]["scores"].items():
                    b = views["sharedRF50"]["scores"][scale]
                    movement[case, fold, arm, predictor, float(scale)] = dict(
                        movement_support_gain=a["negative_twice_log_density"]-b["negative_twice_log_density"],
                        quadratic_gain=a["quadratic"]-b["quadratic"], logdet_gain=a["logdet"]-b["logdet"],
                        baseline_endpoint_loss=a["negative_twice_log_density"], shared_endpoint_loss=b["negative_twice_log_density"],
                        baseline_endpoint_mean_RMS_hz=a["mean_prediction_RMS_hz"], shared_endpoint_mean_RMS_hz=b["mean_prediction_RMS_hz"],
                        held_dimensions=a["dimensions"], movement_km=distance)
            for scale, a in data["crossover"]["baseline"]["baseline"]["scores"].items():
                b = data["crossover"]["sharedRF50"]["sharedRF50"]["scores"][scale]
                own[case, fold, arm, float(scale)] = dict(
                    own_model_gain=a["negative_twice_log_density"]-b["negative_twice_log_density"],
                    quadratic_gain=a["quadratic"]-b["quadratic"], logdet_gain=a["logdet"]-b["logdet"],
                    baseline_mean_RMS_hz=a["mean_prediction_RMS_hz"], shared_mean_RMS_hz=b["mean_prediction_RMS_hz"],
                    held_dimensions=a["dimensions"])
    aggregates, sensitivity = {}, {}
    for case, _, arm, predictor, scale in movement:
        group = [v for (c, _, a, p, s), v in movement.items() if (c, a, p, s) == (case, arm, predictor, scale)]
        aggregates[case, arm, predictor, scale] = dict(complete_folds=len(group),
            total_movement_support_gain=sum(v["movement_support_gain"] for v in group),
            positive_folds=sum(v["movement_support_gain"] > 0 for v in group),
            total_quadratic_gain=sum(v["quadratic_gain"] for v in group), total_logdet_gain=sum(v["logdet_gain"] for v in group))
        if case == "DS24-0095":
            subset = [v for (c, f, a, p, s), v in movement.items() if (c, a, p, s) == (case, arm, predictor, scale) and f != 2]
            sensitivity[case, arm, predictor, scale] = dict(excluded_zero_based_fold=2, retained_folds=len(subset),
                movement_support_gain=sum(v["movement_support_gain"] for v in subset))
    report_tables = [
        ("movement_support.csv", ("case", "fold", "arm", "predictor", "native_sigma_multiplier"), movement),
        ("own_model_prediction.csv", ("case", "fold", "arm", "native_sigma_multiplier"), own),
        ("train_endpoints.csv", ("case", "fold", "arm"), endpoints),
        ("movement_summary.csv", ("case", "arm", "predictor", "native_sigma_multiplier"), aggregates),
        ("convergence_sensitivity.csv", ("case", "arm", "predictor", "native_sigma_multiplier"), sensitivity),
    ]
    rows_checked = cells_checked = 0
    bindings = []
    for name, keys, expected in report_tables:
        rows = list(csv.DictReader((ROOT / name).open()))
        assert len(rows) == len(expected), name
        seen = set()
        for row in rows:
            key = tuple(int(row[k]) if k == "fold" else float(row[k]) if k == "native_sigma_multiplier" else row[k] for k in keys)
            assert key not in seen and key in expected
            seen.add(key)
            for field, value in expected[key].items():
                assert abs(float(row[field])-value) < 1e-8, (name, key, field)
                cells_checked += 1
            if "primary" in row:
                assert (row["primary"] == "True") == (float(row["native_sigma_multiplier"]) == np.sqrt(2))
            rows_checked += 1
        bindings.append(dict(path=str(ROOT / name), sha256=digest(ROOT / name), rows=len(rows)))
    summary = read(ROOT / "summary.json")
    assert summary["original_phase_criterion_failures"] == phase_failures
    receipt = read(ROOT / "test_receipt.json")
    assert receipt["exit_code"] == 0
    for name, sha256 in receipt["source_sha256"].items():
        assert digest(ROOT / name) == sha256
    assert digest(ROOT / "tests.log") == receipt["log_sha256"]
    assert "Ran 5 tests" in (ROOT / "tests.log").read_text()
    assert all(row["movement_support_gain"] < 0 for row in sensitivity.values())
    output = dict(status="passed", source_sha256=digest(Path(__file__)), GPS_used=False, no_position_fitting=True,
        rows_checked=rows_checked, numeric_cells_checked=cells_checked, tables=bindings,
        phase_failure_count=len(phase_failures), convergence_sensitivity_all_12_signs_negative=True,
        heldout_test_receipt_hashes_valid=True)
    (HERE / "heldout_table_audit.json").write_text(json.dumps(output, indent=2)+"\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
