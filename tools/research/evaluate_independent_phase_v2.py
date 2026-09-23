"""Acquired-only random holdout with a frozen circular estimator score."""

import argparse
import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

import leo.analysis.qam.pilot as pilot
import leo.analysis.starlink.templates as templates
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from tools.research.evaluate_independent_phase_holdout import held_rows
from tools.research.extract_independent_phase_arc import serial
from tools.research.extract_longarc_phase import frame_opportunities
from tools.research.fit_independent_phase import FIGURE, digest, predict_model, verify_frozen_inputs
from tools.research.independent_phase_split_gauge import circular_response

DIRECTORY = FIGURE / "v2"
ROOT = Path(__file__).resolve().parents[2]
SIGMA_HZ = 250.0


def circular_score(observed, predicted, period):
    observed, predicted = np.asarray(observed, float), np.asarray(predicted, float)
    if observed.shape != predicted.shape or not np.all(np.isfinite(observed - predicted)):
        raise ValueError("invalid circular prediction/response")
    if not np.isfinite(period) or period < 100 * SIGMA_HZ:
        raise ValueError("period does not support frozen three-image approximation")
    residual = (observed - predicted + period / 2) % period - period / 2
    images = residual[:, None] + period * np.asarray([-1, 0, 1])[None, :]
    log_density = -0.5 * (images / SIGMA_HZ) ** 2 - np.log(SIGMA_HZ * np.sqrt(2 * np.pi))
    nll = -np.logaddexp.reduce(log_density, axis=1)
    return residual, nll


def score_responses(responses, predictions):
    models = {}
    for name, vectors in predictions.items():
        rows = []
        for response, predicted in zip(responses, vectors, strict=True):
            residual, nll = circular_score(
                response["observed_hz"], predicted, response["period_hz"]
            )
            rows.append(
                {
                    "visit_index": response["visit_index"],
                    "frame_count": len(residual),
                    "abstention": not len(residual),
                    "mean_squared_principal_residual_hz2": float(np.mean(residual**2))
                    if len(residual)
                    else None,
                    "mean_principal_residual_hz": float(np.mean(residual))
                    if len(residual)
                    else None,
                    "nll": float(np.mean(nll)) if len(nll) else None,
                }
            )
        covered = [row for row in rows if not row["abstention"]]
        models[name] = {
            "total_held_visits": len(rows),
            "covered_held_visits": len(covered),
            "conditional_equal_visit_rms_hz": float(
                np.sqrt(np.mean([r["mean_squared_principal_residual_hz2"] for r in covered]))
            )
            if covered
            else None,
            "conditional_equal_visit_nll": float(np.mean([r["nll"] for r in covered]))
            if covered
            else None,
            "visits": rows,
        }
    return models


def extract_acquired_row(binding, observation, iq, receiver):
    rate = binding["sample_rate_hz"]
    epoch = round(observation["probe_start_ms"] * rate / 1000) + observation["integer_epoch_sample"]
    opportunities = frame_opportunities(len(iq), rate, epoch)
    if len(opportunities) != 24 or {group for group, _ in opportunities} != set(range(6)):
        raise ValueError("frame opportunities changed")
    frames = []
    content = round(302 * rate * templates.OFDM_SYMBOL_DURATION_S)
    for group, start in opportunities:
        measured = pilot.estimate_edge_pilot_frame_complex_split(
            iq[start - 1 : start + content + 1, receiver],
            rate,
            frame_start_sample=start,
            acquisition_absolute_cfo_hz=observation["acquired_cfo_hz"],
            edge=observation["edge"],
        )
        frames.append(
            {
                "group_id": group,
                "frame": serial(asdict(measured)),
                "session_time_s": (
                    observation["valid_start_counter"]
                    - binding["source_first_counter"]
                    + measured.reference_sample
                )
                / rate,
            }
        )
    return {
        "observation": observation,
        "selected_seed_index": 0,
        "branches": [{"seed_cfo_hz": observation["acquired_cfo_hz"], "frames": frames}],
    }


def sealed_model(path, expected):
    if digest(path) != expected:
        raise ValueError("model seal differs")
    model = json.loads(path.read_text())
    if model.get("schema") != "independent-phase-training-model/v2":
        raise ValueError("only the v2 frozen model is accepted")
    for dependency in (Path(__file__), ROOT / "tools/research/extract_longarc_phase.py"):
        key = str(dependency.relative_to(ROOT))
        if model.get("implementation_sha256", {}).get(key) != digest(dependency):
            raise ValueError("held measurement/scoring code is not sealed")
    verify_frozen_inputs(model)
    return model


def extract(path, expected):
    sealed_model(path, expected)
    destination = DIRECTORY / "held-frames.json.gz"
    if destination.exists():
        raise ValueError("held replay already exists")
    binding = json.loads((FIGURE / "binding.json").read_text())
    observations = held_rows(binding)
    with gzip.open(FIGURE / "train-frames.json.gz", "rt") as stream:
        training = json.load(stream)
    for label, module in (("pilot", pilot), ("templates", templates)):
        if training["protocol"]["source_sha256"][label] != digest(Path(module.__file__)):
            raise ValueError("waveform dependency changed since training")
    rows = []
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        with AdaptiveHopAnalysisInputStore(store).source(binding["session_id"]) as source:
            geometry = source.receipt.plan.geometry
            if source.input_manifest_sha256 != binding["input_manifest_sha256"]:
                raise ValueError("capture manifest changed")
            if geometry.sample_rate_hz != binding["sample_rate_hz"] or geometry.receiver_ids != (
                0,
                1,
            ):
                raise ValueError("capture geometry changed")
            for observation in observations:
                ordinal = observation["iq_ordinal"]
                if source.visits[ordinal].event.visit_index != observation["visit_index"]:
                    raise ValueError("IQ ordinal changed")
                iq = source.read_visit(ordinal)
                if iq.ndim != 2 or iq.shape[1] != 2:
                    raise ValueError("receiver shape changed")
                row = extract_acquired_row(
                    binding,
                    observation,
                    iq,
                    geometry.receiver_ids.index(observation["receiver_id"]),
                )
                row["iq_sha256"] = hashlib.sha256(iq.tobytes()).hexdigest()
                rows.append(row)
    finally:
        store.close()
    payload = {
        "schema": "independent-phase-v2-held-frames/v1",
        "model_sha256": expected,
        "source_sha256": digest(Path(__file__)),
        "binding_sha256": digest(FIGURE / "binding.json"),
        "fresh_held_visits_read": len(rows),
        "old_reserved_visits_read": 0,
        "rows": rows,
    }
    with gzip.open(destination, "xt") as stream:
        json.dump(payload, stream, allow_nan=False, separators=(",", ":"))


def evaluate(path, expected):
    artifact = sealed_model(path, expected)
    frames_path = DIRECTORY / "held-frames.json.gz"
    with gzip.open(frames_path, "rt") as stream:
        held = json.load(stream)
    if held["model_sha256"] != expected or held["source_sha256"] != digest(Path(__file__)):
        raise ValueError("held extraction seal differs")
    binding = json.loads((FIGURE / "binding.json").read_text())
    if held["binding_sha256"] != digest(FIGURE / "binding.json"):
        raise ValueError("held source binding changed")
    expected_visits = {row["visit_index"] for row in held_rows(binding)}
    if (
        len(held["rows"]) != 12
        or {row["observation"]["visit_index"] for row in held["rows"]} != expected_visits
    ):
        raise ValueError("held population changed")
    responses = [circular_response(row) for row in held["rows"]]
    predictions = {
        name: [
            predict_model(
                model, np.asarray(row["time_s"]), artifact, visit_time_s=row["observation_time_s"]
            )
            for row in responses
        ]
        for name, model in artifact["selected_models"].items()
    }
    result = {
        "schema": "independent-phase-v2-circular-comparison/v1",
        "scope": "acquired-only circular estimator score; not raw-IQ likelihood or identity proof",
        "models": score_responses(responses, predictions),
        "responses": responses,
        "fixed_sigma_hz": SIGMA_HZ,
        "model_sha256": expected,
        "held_frames_sha256": digest(frames_path),
        "source_sha256": digest(Path(__file__)),
    }
    destination = DIRECTORY / "held-evaluation.json"
    if destination.exists():
        raise ValueError("evaluation already exists")
    destination.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
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
    (extract if args.extract else evaluate)(args.model, args.model_sha256)
