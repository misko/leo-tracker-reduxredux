"""Independent integrity audit for bounded T4 continuation attempts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def audit(folder: Path) -> dict:
    failures: list[str] = []
    attempts = 0
    winning_query_bounds: dict[str, list[float]] = {}
    for launch_path in sorted(folder.glob("*-resume.launch.json")):
        attempts += 1
        unit = launch_path.name.removesuffix("-resume.launch.json")
        launch = json.loads(launch_path.read_text())
        receipt_path = launch_path.with_name(f"{unit}-resume.json")
        seal_path = launch_path.with_name(f"{unit}-resume.seal.json")

        def require(condition: bool, message: str, unit_label: str = unit) -> None:
            if not condition:
                failures.append(f"{unit_label}: {message}")

        require(launch.get("status") in {"complete", "error", "timeout"},
                "launcher lacks a terminal status")
        if launch.get("status") == "complete":
            require(launch.get("returncode") == 0, "completed launcher has nonzero return code")
        require(launch.get("timeout_seconds") == 90, "external budget is not 90 seconds")
        require(launch.get("threads_per_worker") == 1, "thread count is not one")
        if launch.get("status") == "complete":
            require(receipt_path.is_file() and seal_path.is_file(), "missing receipt or seal")
        require(receipt_path.is_file() == seal_path.is_file(), "partial receipt/seal pair")
        if not receipt_path.is_file() or not seal_path.is_file():
            continue
        receipt = json.loads(receipt_path.read_text())
        seal = json.loads(seal_path.read_text())
        require(seal.get("prediction_sha256") == digest(receipt_path), "seal mismatch")
        require(receipt.get("schema") == "fixed-height-joint-greedy-resume/v1",
                "schema mismatch")
        require(receipt.get("unit_id") == unit, "unit mismatch")
        require(receipt.get("student_degrees_of_freedom") == 4.0,
                "likelihood mismatch")
        require(receipt.get("additional_iterations_per_seed") == 24,
                "iteration budget mismatch")
        for group in ("source_sha256", "inputs"):
            for path_string, expected in receipt.get(group, {}).items():
                path = Path(path_string)
                require(path.is_file(), f"missing {group} path: {path}")
                if path.is_file():
                    require(digest(path) == expected, f"{group} digest mismatch: {path}")
        height = receipt.get("height_input_bindings", {})
        grid = Path(height.get("grid_path", ""))
        require(grid.is_file(), "missing GEOID grid")
        if grid.is_file():
            require(digest(grid) == height.get("grid_sha256"), "GEOID grid digest mismatch")
        parent_binding = receipt.get("parent_binding", {})
        parent_path = Path(parent_binding.get("path", ""))
        require(parent_path.is_file(), "missing parent receipt")
        if not parent_path.is_file():
            continue
        parent = json.loads(parent_path.read_text())
        parent_seal_path = parent_path.with_suffix(".seal.json")
        require(digest(parent_path) == parent_binding.get("sha256"), "parent binding mismatch")
        require(parent_seal_path.is_file(), "missing parent seal")
        if parent_seal_path.is_file():
            parent_seal = json.loads(parent_seal_path.read_text())
            require(parent_seal.get("prediction_sha256") == digest(parent_path),
                    "parent seal mismatch")
        parent_launch_path = parent_path.with_suffix(".launch.json")
        require(parent_launch_path.is_file(), "missing parent launch receipt")
        if parent_launch_path.is_file() and receipt.get("best", {}).get("converged"):
            parent_launch = json.loads(parent_launch_path.read_text())
            total_runtime = (float(parent_launch.get("wall_seconds", float("inf")))
                             + float(launch.get("wall_seconds", float("inf"))))
            require(launch.get("status") == "complete" and launch.get("returncode") == 0,
                    "converged native result has unsuccessful launcher")
            require(total_runtime <= 180.0,
                    "converged native result exceeds two-stage 180-second budget")
        require(receipt.get("inputs") == parent.get("inputs"), "parent input set changed")
        require(receipt.get("planned_factors") == parent.get("planned_factors"),
                "planned factor count changed")
        require(receipt.get("parent_fits") == parent.get("fits"),
                "embedded parent fits changed")
        unresolved = sorted(
            (fit for fit in parent.get("fits", [])
             if not fit.get("converged") and fit.get("objectives")),
            key=lambda fit: fit["objectives"][-1],
        )
        resumed = receipt.get("resumed_fits", [])
        require(len(resumed) <= len(unresolved), "too many resumed fits")
        require([fit.get("parent_seed") for fit in resumed]
                == [fit.get("seed") for fit in unresolved[:len(resumed)]],
                "unresolved seeds were not resumed best-first")
        for index, fit in enumerate(resumed):
            label = f"resumed seed {index}"
            objectives = fit.get("objectives", [])
            steps = fit.get("accepted_step_norms", [])
            require(fit.get("initial_objective_not_above_parent") is True,
                    f"{label} lacks initial objective audit")
            require(bool(objectives) and objectives[0] <= fit["parent_final_objective"] + 1e-6,
                    f"{label} initial objective exceeds parent")
            require(len(steps) == max(0, len(objectives) - 1),
                    f"{label} objective/step count mismatch")
            require(all(right < left for left, right in zip(
                objectives, objectives[1:], strict=False)),
                f"{label} accepted objective is not decreasing")
            require(len(fit.get("associations", [])) == receipt.get("planned_factors"),
                    f"{label} does not cover the full scan")
            if fit.get("reason") == "objective_stable":
                require(bool(steps) and steps[-1] < 1e-4,
                        f"{label} objective_stable step is too large")
        candidates = [fit for fit in parent.get("fits", []) + resumed if fit.get("objectives")]
        expected_best = min(candidates, key=lambda fit: fit["objectives"][-1])
        require(receipt.get("best") == expected_best, "winner is not global attempted minimum")
        expected_status = "converged_local_mode" if expected_best["converged"] else "unresolved"
        require(receipt.get("status") == expected_status, "status disagrees with winner")
        evidence_paths = [Path(path) for path in receipt.get("inputs", {})
                          if path.endswith(f"/{unit}.json")]
        original_meta_paths = [Path(path) for path in receipt.get("inputs", {})
                               if path.endswith(f"/{unit}-orbits.json")
                               and "extended" not in path]
        extended_meta_paths = [Path(path) for path in receipt.get("inputs", {})
                               if path.endswith(f"/{unit}-orbits-extended.json")]
        require(len(evidence_paths) == len(original_meta_paths) == len(extended_meta_paths) == 1,
                "orbit/evidence binding set is ambiguous")
        if evidence_paths and original_meta_paths and extended_meta_paths:
            evidence = json.loads(evidence_paths[0].read_text())
            source = json.loads(Path(evidence["source"]["path"]).read_text())
            relative_times = [
                (timestamp - source["start_utc_ns"]) / 1e9
                for track in evidence["tracks"] for timestamp in track["times_utc_ns"]
            ]
            clock = expected_best["mean"][2]
            epochs = expected_best["satellite_epoch_s"] or [0.0]
            query_min = min(relative_times) + clock + min(epochs)
            query_max = max(relative_times) + clock + max(epochs)
            winning_query_bounds[unit] = [query_min, query_max]
            original = json.loads(original_meta_paths[0].read_text())
            original_bounds = (original["knot_start_s"], original["knot_stop_s"])
            extended = json.loads(extended_meta_paths[0].read_text())
            extended_bounds = tuple(extended["extension"]["new_query_bounds_s"])
            require(query_min >= original_bounds[0] and query_max <= original_bounds[1],
                    "winner exceeds original candidate-union time envelope")
            require(query_min >= extended_bounds[0] and query_max <= extended_bounds[1],
                    "winner exceeds extended four-knot interpolation support")
    return {
        "schema": "fixed-height-joint-greedy-continuation-audit/v1",
        "attempts": attempts,
        "checks_passed": not failures,
        "failures": failures,
        "winning_query_bounds_s": winning_query_bounds,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = audit(arguments.folder)
    encoded = json.dumps(result, indent=2) + "\n"
    if arguments.output:
        arguments.output.write_text(encoded)
    print(encoded, end="")
    raise SystemExit(0 if result["checks_passed"] else 1)
