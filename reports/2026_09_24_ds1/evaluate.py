"""Evaluate sealed paired DS1 inferences; never select or refit a model."""

import argparse
import csv
import hashlib
import importlib.util
import json
import math
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def sealed(path):
    if digest(path).split(":")[1] != path.with_suffix(".sha256").read_text().strip():
        raise ValueError(f"Seal mismatch: {path}")
    return json.loads(path.read_text())


def load_runner():
    spec = importlib.util.spec_from_file_location("ds1_evaluation_runner", HERE / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_arm(arm, case, prior, bindings):
    if not arm["complete"] or arm["case_id"] != case["case_id"] or arm["prior"] != prior:
        raise ValueError("Incomplete or mismatched paired arm")
    for key, expected in bindings.items():
        if arm["bindings"][key] != expected:
            raise ValueError(f"Changed inference binding: {key}")
    if "failure" in arm:
        missing = "scan-hop-6cd2560365a058bc"
        failure = arm["failure"]
        if (
            case["case_id"] != "test_20260922_00_all"
            or len(case["session_ids"]) != 64
            or case["session_ids"][47] != missing
            or failure["session_id"] != missing
            or "counter-continuity authority" not in failure["reason"]
        ):
            raise ValueError("Unrecognized DS1 input failure")
        return
    if arm["held_used_for_fit"] or arm["truth_used_for_fit"]:
        raise ValueError("Inference used evaluation evidence")
    if [s["session_id"] for s in arm["session_bindings"]] != case["session_ids"]:
        raise ValueError("Inference membership changed")
    pairs = arm["visited_pairs"]
    if not pairs:
        raise ValueError("No evaluated pairs")
    for pair in pairs:
        if (
            not math.isfinite(pair["training_capped_loss"])
            or not 0 <= pair["training_capped_loss"] <= 1
        ):
            raise ValueError("Invalid training score")
        if not -5 - 1e-9 <= pair["tau_s"] <= 5 + 1e-9:
            raise ValueError("Time search outside protocol")
    for model in ("baseline", "shared_time"):
        winner = arm["models"][model]
        eligible = [p for p in pairs if model != "baseline" or p["tau_s"] == 0]
        expected = min(
            eligible,
            key=lambda p: (
                p["training_capped_loss"],
                abs(p["tau_s"]),
                p["tau_s"],
                p["latitude_deg"],
                p["longitude_deg"],
            ),
        )
        if winner != expected:
            raise ValueError("Winner violates deterministic TRAIN selection")
        if (
            winner not in eligible
            or abs(
                winner["training_capped_loss"] - min(p["training_capped_loss"] for p in eligible)
            )
            > 1e-12
        ):
            raise ValueError("Selected point is not an evaluated TRAIN minimum")
    if (
        arm["models"]["shared_time"]["training_capped_loss"]
        > arm["models"]["baseline"]["training_capped_loss"] + 1e-12
    ):
        raise ValueError("Shared model lost baseline support")


def evaluate_arm(task):
    case, prior, arm, reference = task
    common = {k: case[k] for k in ("case_id", "partition", "group_id", "view", "scan_count")}
    common["prior"] = prior
    if "failure" in arm:
        return [
            {**common, "model": model, "status": "input_failure", "failure": arm["failure"]}
            for model in ("baseline", "shared_time")
        ]
    runner = load_runner()
    _, engine = runner.make_engine(case)
    if engine.bindings != arm["session_bindings"]:
        raise ValueError("Caches changed after inference")
    weights = sum(t["weight"] for s in engine.sessions for t in s["tracks"])
    output = []
    for model, winner in arm["models"].items():
        lat, lon, tau = winner["latitude_deg"], winner["longitude_deg"], winner["tau_s"]
        train, held, assignments = engine.profile(lat, lon, np.array([tau]), True, True)
        if abs(float(train[0]) - winner["training_capped_loss"]) > 1e-10:
            raise ValueError("Sealed winner failed training replay")
        receiver, _ = engine.search.receiver_ecef(lat, lon)
        selected = {(a["session_id"], a["track_id"]): a for a in assignments[0]}
        uncapped = support = held_observations = training_observations = 0
        track_rows = []
        for session in engine.sessions:
            id_index = {str(value): i for i, value in enumerate(session["candidate_ids"])}
            for track in session["tracks"]:
                assignment = selected[(session["session_id"], track["track_id"])]
                mask = track["train"]
                held_observations += int((~mask).sum())
                training_observations += int(mask.sum())
                row = {**assignment, "occupied_second_weight": track["weight"]}
                if assignment["candidate_id"] is not None:
                    index = id_index[assignment["candidate_id"]]
                    single = {
                        **session,
                        "position": session["position"][index : index + 1],
                        "velocity": session["velocity"][index : index + 1],
                    }
                    p, v = engine.interpolate(single, track["times"], np.array([tau]))
                    delta = p[0, :, 0] - receiver
                    pred = (
                        -engine.search.REFERENCE_RF_HZ
                        / engine.search.LIGHT_KM_S
                        * np.sum(delta * v[0, :, 0], axis=1)
                        / np.linalg.norm(delta, axis=1)
                    )
                    error = track["measured"] - pred - assignment["training_cfo_hz"]
                    mean_square = float(np.mean(error[~mask] ** 2))
                    uncapped += track["weight"] * mean_square
                    support += track["weight"]
                    row["held_rms_hz"] = math.sqrt(mean_square)
                track_rows.append(row)
        baseline_ids = None
        if output:
            baseline_ids = {
                (r["session_id"], r["track_id"]): r["candidate_id"] for r in output[0]["tracks"]
            }
        result = {
            **common,
            **winner,
            "model": model,
            "status": "completed",
            "reference_error_km": engine.search.haversine_km((lat, lon), reference),
            "held_capped_loss": float(held[0]),
            "held_capped_rms_hz": 800 * math.sqrt(float(held[0])),
            "held_uncapped_supported_rms_hz": math.sqrt(uncapped / support) if support else None,
            "occupied_second_weight": weights,
            "supported_occupied_second_weight": support,
            "track_count": len(track_rows),
            "training_observations": training_observations,
            "held_observations": held_observations,
            "tracks": track_rows,
            "global_tau_boundary": abs(tau) >= 5 - 1e-9,
            "pair_count": len(arm["visited_pairs"]),
            "paired_inference_runtime_s": arm["elapsed_s"],
        }
        if baseline_ids is not None:
            result["assignment_changes_from_baseline"] = sum(
                baseline_ids[(r["session_id"], r["track_id"])] != r["candidate_id"]
                for r in track_rows
            )
        output.append(result)
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    dataset = sealed(HERE / "dataset.json")
    index = sealed(HERE / "inference_index.json")
    bindings = {
        "dataset": digest(HERE / "dataset.json"),
        "protocol": digest(HERE / "PROTOCOL.md"),
        "source": digest(HERE / "run.py"),
    }
    if not index["complete"] or index["arm_count"] != 40:
        raise ValueError("DS1 inference is not fully accounted for")
    for key, value in bindings.items():
        if index["bindings"][key] != value:
            raise ValueError("Index binding mismatch")
    loaded = []
    for case in dataset["cases"]:
        for prior in dataset["priors"]:
            path = HERE / "inference" / f"{case['case_id']}__{prior}.json"
            arm = sealed(path)
            validate_arm(arm, case, prior, bindings)
            if "failure" not in arm:
                for key, relative in (
                    ("clock_engine", "reports/2026_09_24_shared_clock_grid/run.py"),
                    ("search_engine", "reports/2026_09_23_long_training_search/search.py"),
                ):
                    if arm["bindings"][key] != digest(ROOT / relative):
                        raise ValueError("Inference dependency changed")
            loaded.append((case, prior, arm))
    # Deliberately introduce the evaluation-only reference after every arm passes.
    reference = (37.84903264307456, -122.4856541910174)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        groups = list(pool.map(evaluate_arm, [(c, p, a, reference) for c, p, a in loaded]))
    rows = [r for group in groups for r in group]
    result = {
        "schema": "ds1-comparison-evaluation/v1",
        "dataset": "DS1",
        "rows": rows,
        "expected_rows": 80,
        "completed_rows": sum(r["status"] == "completed" for r in rows),
        "failure_rows": sum(r["status"] != "completed" for r in rows),
        "reference_coordinate": reference,
        "reference_role": "post-seal evaluation only",
        "exposure": "retrospective regression; not untouched validation or test",
        "bindings": {
            **bindings,
            "evaluator": digest(Path(__file__)),
            "inference_index": digest(HERE / "inference_index.json"),
        },
    }
    if len(rows) != 80:
        raise ValueError("Incomplete evaluation accounting")
    if result["completed_rows"] != 76 or result["failure_rows"] != 4:
        raise ValueError("Unexpected DS1 outcome accounting")
    path = HERE / "evaluation.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    path.with_suffix(".sha256").write_text(digest(path).split(":")[1] + "\n")
    columns = [
        "case_id",
        "partition",
        "group_id",
        "view",
        "scan_count",
        "prior",
        "model",
        "status",
        "latitude_deg",
        "longitude_deg",
        "tau_s",
        "reference_error_km",
        "training_capped_loss",
        "held_capped_rms_hz",
        "held_uncapped_supported_rms_hz",
        "track_count",
        "occupied_second_weight",
        "assignment_changes_from_baseline",
        "global_tau_boundary",
        "paired_inference_runtime_s",
    ]
    with (HERE / "comparison.csv").open("w") as handle:
        writer = csv.DictWriter(handle, columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "bindings")}))


if __name__ == "__main__":
    main()
