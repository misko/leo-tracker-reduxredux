"""Open and score the 12 random held dwells only against a frozen predictor."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from tools.research import extract_independent_phase_arc as extraction

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "reports/figures/2026_09_23_independent_phase"
NATIVE_ALIAS_HZ = 1 / 4.4e-6


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def held_rows(binding):
    split = {
        row["visit_index"]: row["partition"] for row in binding["fresh_random_whole_visit_split"]
    }
    rows = binding["observations"]
    if set(split.values()) != {"train", "held"} or list(split.values()).count("train") != 15:
        raise ValueError("unexpected training partition")
    if len(rows) != 27 or set(split) != {row["visit_index"] for row in rows}:
        raise ValueError("bound observation population differs from frozen split")
    selected = [row for row in rows if split[row["visit_index"]] == "held"]
    if len(selected) != 12:
        raise ValueError("expected exactly 12 fresh-held dwells")
    return selected


def odd_response(row):
    """One model-independent response; seed fixes alias before seeing odd CFO."""
    observation = row["observation"]
    branch = row["branches"][row["selected_seed_index"]]
    lift = round((observation["dealiased_native_cfo_hz"] - branch["seed_cfo_hz"]) / NATIVE_ALIAS_HZ)
    frames = [
        frame
        for frame in branch["frames"]
        if frame["group_id"] in (1, 2, 4)
        and frame["frame"]["training_supported"]
        and frame["frame"]["odd"] is not None
    ]
    return {
        "visit_index": observation["visit_index"],
        "observation_time_s": observation["time_s"],
        "time_s": [frame["session_time_s"] for frame in frames],
        "observed_hz": [
            (frame["frame"]["odd"]["absolute_cfo_hz"] + lift * NATIVE_ALIAS_HZ)
            * observation["rf_normalization_scale"]
            for frame in frames
        ],
        "alias_lift_index": lift,
        "seed_alias_closure_hz": observation["dealiased_native_cfo_hz"]
        - (branch["seed_cfo_hz"] + lift * NATIVE_ALIAS_HZ),
        "frame_count": len(frames),
        "odd_search_boundary_count": sum(
            frame["frame"]["odd"]["search_boundary"] for frame in frames
        ),
    }


def score_responses(responses, model_predictions):
    """Equal whole-dwell scores, exposing abstentions rather than hiding them."""
    output = {}
    for name, predictions in model_predictions.items():
        if len(predictions) != len(responses):
            raise ValueError("prediction and response populations differ")
        rows = []
        for response, prediction in zip(responses, predictions, strict=True):
            observed = np.asarray(response["observed_hz"], float)
            predicted = np.asarray(prediction, float)
            if observed.shape != predicted.shape or not np.all(np.isfinite(predicted)):
                raise ValueError("invalid response prediction")
            if not len(observed):
                rows.append({"visit_index": response["visit_index"], "abstention": True})
                continue
            residual = observed - predicted
            rows.append(
                {
                    "visit_index": response["visit_index"],
                    "abstention": False,
                    "frame_count": len(observed),
                    "mean_residual_hz": float(np.mean(residual)),
                    "mean_squared_error_hz2": float(np.mean(residual**2)),
                    "nll": float(
                        np.mean(0.5 * (residual / 250) ** 2 + np.log(250) + 0.5 * np.log(2 * np.pi))
                    ),
                }
            )
        covered = [row for row in rows if not row["abstention"]]
        output[name] = {
            "total_held_visits": len(rows),
            "covered_held_visits": len(covered),
            "all_held_covered": len(covered) == len(rows),
            "conditional_equal_visit_rms_hz": (
                float(np.sqrt(np.mean([row["mean_squared_error_hz2"] for row in covered])))
                if covered
                else None
            ),
            "conditional_equal_visit_nll": (
                float(np.mean([row["nll"] for row in covered])) if covered else None
            ),
            "visits": rows,
        }
    return output


def extract_held(model_path, expected_model_hash):
    if digest(model_path) != expected_model_hash:
        raise ValueError("frozen model seal does not match")
    # Import only after the caller supplies a model seal; the fitter must not run.
    from tools.research import fit_independent_phase as fit

    model = json.loads(model_path.read_text())
    fit.verify_frozen_inputs(model)
    binding = json.loads((DIRECTORY / "binding.json").read_text())
    with gzip.open(DIRECTORY / "train-frames.json.gz", "rt") as stream:
        training = json.load(stream)
    if training["protocol"]["binding_sha256"] != digest(DIRECTORY / "binding.json"):
        raise ValueError("training replay binding changed")
    if training["protocol"]["source_sha256"]["extractor"] != digest(extraction.__file__):
        raise ValueError("measurement pipeline changed since training")
    for key, module in (
        ("pilot", extraction.pilot_module),
        ("templates", extraction.template_module),
    ):
        if training["protocol"]["source_sha256"][key] != digest(module.__file__):
            raise ValueError("waveform dependency changed since training")
    destination = DIRECTORY / "held-frames.json.gz"
    if destination.exists():
        raise ValueError("held replay already exists; do not silently replace it")
    protocol = {
        **training["protocol"],
        "read_scope": "exactly 12 fresh-held dwells; original 19 reserved excluded",
        "frozen_model_sha256": expected_model_hash,
        "held_driver_sha256": digest(__file__),
        "training_frames_sha256": digest(DIRECTORY / "train-frames.json.gz"),
    }
    rows = []
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        with AdaptiveHopAnalysisInputStore(store).source(binding["session_id"]) as source:
            if source.input_manifest_sha256 != binding["input_manifest_sha256"]:
                raise ValueError("held capture binding changed")
            geometry = source.receipt.plan.geometry
            if geometry.sample_rate_hz != binding["sample_rate_hz"]:
                raise ValueError("sample rate changed")
            if geometry.receiver_ids != (0, 1):
                raise ValueError("receiver mapping differs from training replay")
            for observation in held_rows(binding):
                ordinal = observation["iq_ordinal"]
                if source.visits[ordinal].event.visit_index != observation["visit_index"]:
                    raise ValueError("held IQ ordinal changed")
                iq = source.read_visit(ordinal)
                if iq.ndim != 2 or iq.shape[1] != 2:
                    raise ValueError("held receiver-column shape differs from training")
                column = geometry.receiver_ids.index(observation["receiver_id"])
                row = extraction._extract_row(binding, observation, iq, column, protocol)
                if row["train_odd_diagnostic"]["frame_count"] == 0:
                    # Preserve a complete abstention without JSON NaNs from an empty mean.
                    row["train_odd_diagnostic"]["exact_coherence"] = None
                    row["train_odd_diagnostic"]["control_coherence"] = None
                rows.append(row)
    finally:
        store.close()
    payload = {
        "schema": "independent-held-phase-frames/v1",
        "protocol": protocol,
        "fresh_held_visits_read": len(rows),
        "old_reserved_visits_read": 0,
        "rows": rows,
    }
    with gzip.open(destination, "xt") as stream:
        json.dump(extraction.serial(payload), stream, allow_nan=False, separators=(",", ":"))


def evaluate(model_path, expected_model_hash):
    from tools.research import fit_independent_phase as fit

    if digest(model_path) != expected_model_hash:
        raise ValueError("frozen model seal does not match")
    artifact = json.loads(model_path.read_text())
    fit.verify_frozen_inputs(artifact)
    frames_path = DIRECTORY / "held-frames.json.gz"
    with gzip.open(frames_path, "rt") as stream:
        held = json.load(stream)
    if held["protocol"]["frozen_model_sha256"] != expected_model_hash:
        raise ValueError("held replay was extracted against another model")
    if held["protocol"]["held_driver_sha256"] != digest(__file__):
        raise ValueError("held driver changed after response extraction")
    if held["protocol"]["training_frames_sha256"] != digest(DIRECTORY / "train-frames.json.gz"):
        raise ValueError("training replay changed after response extraction")
    binding = json.loads((DIRECTORY / "binding.json").read_text())
    if held["protocol"]["binding_sha256"] != digest(DIRECTORY / "binding.json"):
        raise ValueError("held binding changed")
    expected = {row["visit_index"] for row in held_rows(binding)}
    if (
        len(held["rows"]) != 12
        or {row["observation"]["visit_index"] for row in held["rows"]} != expected
    ):
        raise ValueError("held response population differs from frozen partition")
    responses = [odd_response(row) for row in held["rows"]]
    predictions = {
        name: [
            fit.predict_model(
                model, np.asarray(row["time_s"]), artifact, visit_time_s=row["observation_time_s"]
            )
            for row in responses
        ]
        for name, model in artifact["selected_models"].items()
    }
    result = {
        "schema": "independent-phase-held-comparison/v1",
        "scope": "conditional fixed-protocol CFO prediction; no identity or position claim",
        "models": score_responses(responses, predictions),
        "responses": responses,
        "fixed_sigma_hz": 250.0,
        "model_sha256": expected_model_hash,
        "held_frames_sha256": digest(frames_path),
        "source_sha256": digest(__file__),
    }
    (DIRECTORY / "held-evaluation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                name: {k: v for k, v in row.items() if k != "visits"}
                for name, row in result["models"].items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--model-sha256", required=True)
    parser.add_argument("--extract", action="store_true")
    args = parser.parse_args()
    if args.extract:
        extract_held(args.model, args.model_sha256)
    else:
        evaluate(args.model, args.model_sha256)
