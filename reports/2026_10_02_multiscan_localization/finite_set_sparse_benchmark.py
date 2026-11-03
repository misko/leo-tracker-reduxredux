"""No-fit dense/packed parity and runtime benchmark on sealed development fits."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from alias_family_joint import load_unit_with_family_exports
from capture_reset_gn import apply_capture_offsets
from finite_set_fit import assert_snapshot_unchanged, build_likelihood_arms, digest, snapshot_files
from finite_set_sparse import SparseFiniteSetLikelihoodAdapter
from prediction_plan import SharedPredictionPlan

ROOT = Path(__file__).resolve().parent
CASES = (
    ("finite-set-tau-profile-v1", "DS10-S01", "leader"),
    ("finite-set-tau-profile-v1", "DS11-S02", "leader"),
    ("finite-set-reset-cohort-v1", "DS11-Q02", "largest"),
)


def run():
    rows = []
    for run_id, unit_id, bank in CASES:
        fit_path = ROOT / "runs" / run_id / unit_id / "fit.json"
        initial_hash = digest(fit_path)
        record = json.loads(fit_path.read_text())
        assert_snapshot_unchanged(record["source_hashes"])
        paths = [
            fit_path, Path(__file__), ROOT / "finite_set_sparse.py",
            ROOT / "capture_reset_gn.py", ROOT / "finite_set_fit.py",
            *record["source_hashes"],
        ]
        snapshot = snapshot_files(dict.fromkeys(str(Path(path).resolve()) for path in paths))
        if digest(fit_path) != initial_hash:
            raise RuntimeError("fit changed before benchmark")
        exports = ROOT / "runs/alias-family-cohort-v1"
        _, data, input_paths = load_unit_with_family_exports(
            unit_id, exports,
            expected_manifest_sha256=record["source_hashes"][str(exports / "manifest.json")],
        )
        if any(record["source_hashes"].get(str(path)) != digest(path) for path in input_paths):
            raise ValueError("benchmark loader inputs differ from sealed inputs")
        trial = (record["fit"]["selection"]["score_leader"] if bank == "leader"
                 else max(record["fit"]["trials"], key=lambda value: value["satellite_count"]))
        satellites = np.asarray(trial["satellite_indices"])
        parameters = np.asarray(trial["parameters"])
        count = len(satellites)
        predicted, visible, _ = SharedPredictionPlan(data, satellites).predict(parameters)
        shape = (len(data.times), count)
        predicted, visible = predicted.reshape(shape), visible.reshape(shape)
        if "capture_jumps_hz" in trial:
            predicted = apply_capture_offsets(data, predicted, trial["capture_jumps_hz"], count)
        dense = build_likelihood_arms(data, count, len(record["fit"]["full_bank"]))["finite_set"]
        sparse = SparseFiniteSetLikelihoodAdapter(dense.prepared, dense.detection_probability)
        results, timings = {}, {"dense": [], "sparse": []}
        for _repetition in range(3):
            for name, adapter in (("dense", dense), ("sparse", sparse)):
                started = time.perf_counter()
                results[name] = adapter.evaluate(
                    predicted, visible, sigma_hz=200, satellite_weights=np.ones(count),
                    background_mass=.2, return_gradient=True, return_precision=True,
                )
                timings[name].append(time.perf_counter() - started)
        objective = (-results["dense"]["total_log_likelihood"]
                     + .5 * np.sum(parameters[6 + satellites]**2))
        if not np.isclose(objective, trial["objective"], rtol=0, atol=1e-6):
            raise ValueError("dense evaluation does not reproduce sealed objective")
        differences = {name: float(np.max(np.abs(results["dense"][name] - results["sparse"][name])))
                       for name in ("log_likelihood", "prediction_gradient", "prediction_precision",
                                    "row_association_probability", "nonempty_probability")}
        assert_snapshot_unchanged(snapshot)
        rows.append({
            "unit_id": unit_id, "source_run": run_id, "source_hashes": snapshot,
            "bank_selection": bank, "satellite_count": count, "row_count": len(data.times),
            "source_objective_error": float(abs(objective - trial["objective"])),
            "maximum_absolute_differences": differences,
            "total_log_likelihood_difference": results["dense"]["total_log_likelihood"]
            - results["sparse"]["total_log_likelihood"],
            "packed_satellite_count": results["sparse"]["packed_satellite_count"],
            "omitted_log_likelihood_bound": results["sparse"][
                "total_omitted_log_likelihood_upper_bound"
            ],
            "timings_s": timings,
            "median_speedup": float(np.median(timings["dense"]) / np.median(timings["sparse"])),
        })
    return {"schema": "finite-set-sparse-benchmark/v1", "rows": rows,
            "reference_accessed": False, "fit_performed": False,
            "scope": "Fixed-parameter parity and runtime only; no convergence or accuracy claim."}


if __name__ == "__main__":
    receipt = run()
    with (ROOT / "finite-set-sparse-benchmark-v1.json").open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
    for row in receipt["rows"]:
        print(json.dumps({key: value for key, value in row.items() if key != "source_hashes"}))
