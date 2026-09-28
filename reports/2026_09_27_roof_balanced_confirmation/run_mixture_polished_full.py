"""Numerically polish the nine immutable full-six mixture-calibration runs."""
from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path
import time

import numpy as np

import mixture_calibration_inputs as adapter
import mixture_newton_polish as polish
import mixture_reception_core as core
import run_mixture_calibration as original


HERE = Path(__file__).resolve().parent
ARMS = original.ARMS


def json_value(value):
    """Return the exact JSON representation used by immutable artifacts."""
    return json.loads(json.dumps(value, sort_keys=True))


def verify_original_artifact(raw, tracks, receipt) -> tuple[object, dict]:
    """Fail closed on the frozen full-fit artifact without running a polish."""
    expected_bindings = original.source_bindings(receipt)
    expected_bindings["structural_input_sha256"] = adapter.structural_signature(tracks)
    if (raw.get("kind") != "descriptive_full_six" or raw.get("fit_index") != 0 or
            raw.get("held_session") is not None or raw.get("training_track_count") != 344 or
            raw.get("score_track_count") != 344 or raw.get("bindings") != expected_bindings or
            raw.get("calibration_sessions") != receipt["sessions"] or
            set(raw.get("models", {})) != set(ARMS)):
        raise ValueError("immutable original full-six artifact binding changed")
    schema = adapter.fit_schema(tracks)
    if raw.get("feature_schema") != json_value(asdict(schema)):
        raise ValueError("original feature schema no longer reproduces")
    return schema, expected_bindings


def verify_raw_objectives(raw_runs, tracks, layout, tolerance=1e-9) -> list[dict]:
    checks = []
    if len(raw_runs) != 3:
        raise ValueError("expected exactly the three immutable original starts")
    for index, run in enumerate(raw_runs):
        objective, gradient = core.objective_gradient(
            run["theta"], tracks, layout, ridge=original.RIDGE)
        difference = abs(objective - float(run["objective"]))
        if not math.isfinite(difference) or difference > tolerance:
            raise ValueError("original run objective no longer reproduces")
        checks.append({"run_index": index, "stored_objective": run["objective"],
                       "recomputed_objective": objective,
                       "absolute_difference": difference,
                       "recomputed_gradient_max_abs": float(np.max(np.abs(gradient)))})
    return checks


def serialize_model(arm, feature_names, layout, polished, tracks) -> dict:
    theta = np.asarray(polished["theta"], float)
    pd, pr = layout.detection_size, layout.ratio_size
    return {
        "arm": arm, "feature_names": feature_names,
        "penalty_masks": {
            "detection": np.asarray(layout.detection_penalty_mask, bool).tolist(),
            "ratio": np.asarray(layout.ratio_penalty_mask, bool).tolist()},
        "coefficients": {"detection": theta[:pd].tolist(),
                         "ratio": theta[pd:pd + pr].tolist()},
        "log_sigma": float(theta[-1]),
        "variance": float(math.exp(2 * theta[-1])),
        "polish": polished,
        "converged": bool(polished["accepted"]),
        "training_components": original.component_summary(theta, tracks, layout),
        "score_components": original.component_summary(theta, tracks, layout),
    }


def verify_reserve_denominators(tracks) -> dict:
    extraction = json.loads(
        (adapter.LOCATION / "topology_frequency_fixedpoint.json").read_text())
    expected = {(sid, row["track_id"]): int(row["reserve_observations"])
                for sid, rows in extraction["final_tracks"].items() for row in rows}
    actual = {(track.session_id, track.track_id): len(track.rows) for track in tracks}
    if expected != actual:
        raise ValueError("reception rows differ from frozen frequency reserve denominators")
    return {"tracks_checked": len(actual), "mismatches": 0,
            "reception_rows": sum(actual.values()),
            "reserve_observations": sum(expected.values())}


def main() -> None:
    target = HERE / "mixture-calibration-polished-full.json"
    if target.exists():
        raise FileExistsError(target)
    raw_path = HERE / "mixture-calibration-full.json"
    raw_bytes = raw_path.read_bytes()
    raw = json.loads(raw_bytes)
    tracks, receipt = adapter.load_joined()
    schema, expected_bindings = verify_original_artifact(raw, tracks, receipt)
    denominator_check = verify_reserve_denominators(tracks)
    started = time.monotonic()
    models = {}
    objective_checks = {}
    for arm in ARMS:
        training, layout, feature_names = adapter.build_arm(tracks, schema, arm, core)
        raw_runs = raw["models"][arm]["optimizer"]["runs"]
        objective_checks[arm] = verify_raw_objectives(raw_runs, training, layout)
        print("POLISH_ARM", arm, flush=True)
        refined = polish.polish_multistart(
            raw_runs, training, layout, ridge=original.RIDGE)
        models[arm] = serialize_model(arm, feature_names, layout, refined, training)
    protocol_path = HERE / "MIXTURE_NUMERICAL_REFINEMENT.md"
    output = {
        "kind": "descriptive_full_six_numerically_polished",
        "scope": "Six calibration scans only; Newton refinement of the nine existing full-six optimizer results; no new starts, LOSO, RF, or geographic data.",
        "calibration_sessions": receipt["sessions"],
        "rows": receipt["rows"], "tracks": receipt["tracks"],
        "ridge": original.RIDGE, "feature_schema": json_value(asdict(schema)),
        "bindings": expected_bindings,
        "original_full_artifact_sha256": original.digest(raw_bytes),
        "original_objective_checks": objective_checks,
        "reserve_denominator_check": denominator_check,
        "models": models,
        "all_models_converged": all(model["converged"] for model in models.values()),
        "elapsed_s": time.monotonic() - started,
        "source_hashes": {
            "original_runner": original.digest((HERE / "run_mixture_calibration.py").read_bytes()),
            "original_core": original.digest((HERE / "mixture_reception_core.py").read_bytes()),
            "original_adapter": original.digest((HERE / "mixture_calibration_inputs.py").read_bytes()),
            "polish_core": original.digest((HERE / "mixture_newton_polish.py").read_bytes()),
            "polish_runner": original.digest(Path(__file__).read_bytes()),
            "refinement_protocol": original.digest(protocol_path.read_bytes()),
        },
        "acceptance": "Unchanged predeclared gates: gradient <=1e-6, total objective range <=1e-7, prediction difference <=1e-4, minimum Hessian eigenvalue >1e-7.",
    }
    original.atomic(target, output)
    print("POLISHED_FULL_DONE", round(output["elapsed_s"], 2),
          "converged", output["all_models_converged"], flush=True)


if __name__ == "__main__":
    main()
