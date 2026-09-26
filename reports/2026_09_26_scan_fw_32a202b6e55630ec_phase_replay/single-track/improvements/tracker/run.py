"""Run bounded causal phase trackers against the frozen five-dwell cache."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
CACHE = HERE.parent / "pilot-cache.npz"
METADATA = HERE.parent / "pilot-cache.json"
spec = importlib.util.spec_from_file_location("phase_tracker", HERE / "track.py")
T = importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model_uncertainty(fit, times):
    distance = np.maximum(0.0, np.asarray(times) - np.max(np.asarray(times)[fit.used]))
    span = max(np.ptp(np.asarray(times)[fit.used]), np.finfo(float).eps)
    return fit.scale_rad * (1.0 + distance / span)


def metrics(errors, support):
    values = errors[support & np.any(np.isfinite(errors), axis=1)]
    flat = values[np.isfinite(values)]
    if len(flat) == 0:
        return {"supported_frames": 0, "held_tone_samples": 0, "wrapped_rmse_deg": None,
                "circular_concentration": None, "mean_error_deg": None}
    return {
        "supported_frames": int(len(values)),
        "held_tone_samples": int(len(flat)),
        "wrapped_rmse_deg": float(np.degrees(np.sqrt(np.mean(flat**2)))),
        "circular_concentration": float(abs(np.mean(np.exp(1j * flat)))),
        "mean_error_deg": float(np.degrees(np.angle(np.mean(np.exp(1j * flat))))),
    }


def main():
    cache = np.load(CACHE)
    metadata = json.loads(METADATA.read_text())
    products = cache["products"]
    weights = np.where(cache["valid"], cache["weights"], 0.0)
    rows, results = [], []
    for visit in metadata["visit_indices"]:
        global_indices = np.flatnonzero(cache["frame_visit_index"] == visit)
        local_time = cache["frame_time_in_dwell_s"][global_indices]
        local_products = products[global_indices]
        local_weights = weights[global_indices]
        training = cache["training"][global_indices]
        held = cache["held"][global_indices]
        models = T.early_models(local_time, local_products, local_weights, train_mask=training)
        predictions = {}
        for name, fit in models.items():
            predictions[(name, "early_forecast")] = (
                fit.predict(local_time), model_uncertainty(fit, local_time), np.zeros(len(local_time), int), fit
            )
        rolling, rolling_uncertainty, segments = T.rolling_predictions(local_time, local_products, local_weights)
        predictions[("cautious_robust", "rolling_one_step")] = (rolling, rolling_uncertainty, segments, None)
        baselines, baseline_uncertainty, baseline_segments = T.causal_baselines(local_time, local_products, local_weights)
        for baseline_name, baseline_prediction in baselines.items():
            predictions[(baseline_name, "rolling_one_step_baseline")] = (
                baseline_prediction, baseline_uncertainty, baseline_segments, None
            )
        for (name, kind), (predicted, uncertainty, segment, fit) in predictions.items():
            errors, valid = T.held_tone_errors(predicted, local_products, local_weights)
            # Both experiments are scored on the same frozen forward support;
            # rolling differs only by being allowed to update from prior frames.
            evaluation = held
            record = {"visit_index": int(visit), "model": name, "prediction_kind": kind,
                      "training_frames": int(training.sum()) if fit is not None else None,
                      "held_frames": int(held.sum()),
                      "unsupported_evaluation_frames": int(np.sum(evaluation & ~np.isfinite(predicted))),
                      **metrics(errors, evaluation & np.isfinite(predicted))}
            total_held_samples = int(held.sum() * len(T.HELD_TONES))
            missing_samples = total_held_samples - record["held_tone_samples"]
            conditional = np.deg2rad(record["wrapped_rmse_deg"] or 0.0)
            record["all_held_failure_inclusive_rmse_deg"] = float(np.degrees(np.sqrt(
                (conditional**2 * record["held_tone_samples"] + np.pi**2 * missing_samples) / total_held_samples
            )))
            if fit is not None:
                record.update({"phase_at_reference_deg": float(np.degrees(fit.coefficients[0])),
                               "differential_frequency_hz": float(fit.coefficients[1] / T.TAU) if fit.order >= 1 else 0.0,
                               "differential_frequency_rate_hz_s": float(fit.coefficients[2] * 2 / T.TAU) if fit.order == 2 else 0.0,
                               "robust_training_scale_deg": float(np.degrees(fit.scale_rad))})
            results.append(record)
            for j, global_index in enumerate(global_indices):
                per_frame = errors[j]
                finite = np.isfinite(per_frame)
                rows.append({
                    "visit_index": int(visit), "frame_time_s": float(cache["frame_time_s"][global_index]),
                    "frame_time_in_dwell_s": float(local_time[j]),
                    "support_start_s": float(cache["support_start_s"][global_index]),
                    "support_end_s": float(cache["support_end_s"][global_index]),
                    "training_early20ms": bool(training[j]), "held_forward100ms": bool(held[j]),
                    "model": name, "prediction_kind": kind,
                    "predicted_phase_rad": float(predicted[j]) if np.isfinite(predicted[j]) else "",
                    "predicted_phase_deg": float(np.degrees(T.wrap(predicted[j]))) if np.isfinite(predicted[j]) else "",
                    "uncertainty_rad": float(uncertainty[j]) if np.isfinite(uncertainty[j]) else "",
                    "uncertainty_deg": float(np.degrees(uncertainty[j])) if np.isfinite(uncertainty[j]) else "",
                    "supported": bool(np.isfinite(predicted[j])), "segment_id": int(segment[j]),
                    "train_tone_indices": "0,2,4,6", "held_tone_indices": "1,3,5,7",
                    "held_valid_count": int(finite.sum()),
                    "held_wrapped_rmse_deg": float(np.degrees(np.sqrt(np.mean(per_frame[finite]**2)))) if finite.any() and np.isfinite(predicted[j]) else "",
                })
    with (HERE / "tracker-predictions.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    payload = {
        "schema": "single-track-differential-tracker/v1",
        "cache": {"npz_sha256": digest(CACHE), "json_sha256": digest(METADATA), "metadata": metadata},
        "method": {"training_tones": [0, 2, 4, 6], "held_tones": [1, 3, 5, 7],
                   "early_training_rule": "full frame support ends at or before 20 ms",
                   "early_evaluation_rule": "full frame support begins at or after 20 ms",
                   "held_phase_calibration": "none",
                   "qualification": "tone holdout tests only the differential tracker; the shared RX0 residual fit used all tones"},
        "results": results,
    }
    aggregates = []
    for name, kind in sorted({(r["model"], r["prediction_kind"]) for r in results}):
        selected = [r for r in results if r["model"] == name and r["prediction_kind"] == kind]
        aggregate_errors = []
        for row in rows:
            if row["model"] == name and row["prediction_kind"] == kind and row["held_forward100ms"] and row["supported"] and row["held_wrapped_rmse_deg"] != "":
                # Frame RMS cannot reconstruct individual residuals; retain an
                # exact pooled RMS via sum of four equal-count tone squares.
                aggregate_errors.extend([float(row["held_wrapped_rmse_deg"])] * int(row["held_valid_count"]))
        aggregates.append({"model": name, "prediction_kind": kind,
                           "training_frames": int(sum((r["training_frames"] or 0) for r in selected)),
                           "held_frames": int(sum((r["held_frames"] or 0) for r in selected)),
                           "supported_frames": int(sum(r["supported_frames"] for r in selected)),
                           "held_tone_samples": int(sum(r["held_tone_samples"] for r in selected)),
                           "gate_conditional_wrapped_rmse_deg": float(np.sqrt(np.mean(np.square(aggregate_errors)))),
                           "all_held_failure_inclusive_rmse_deg": float(np.sqrt((
                               np.sum(np.square(aggregate_errors)) +
                               (sum((r["held_frames"] or 0) for r in selected) * 4 - len(aggregate_errors)) * 180.0**2
                           ) / (sum((r["held_frames"] or 0) for r in selected) * 4))),
                           "per_dwell_rmse_deg": [r["wrapped_rmse_deg"] for r in selected]})
    payload["aggregates"] = aggregates
    (HERE / "tracker-results.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
