"""Actual historical robust-filter kernels on cached and actual-V2 frames."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent.parent
REPO = REPORT.parents[1]
CACHE = Path("/srv/bulk/leo-dev/scan-32a202-phase-replay-cache/frame-folds")
SPEC = importlib.util.spec_from_file_location(
    "historical_d3_filters", REPO / "tools/report_d3_pilot_filter_prototypes.py"
)
assert SPEC and SPEC.loader
H = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = H
SPEC.loader.exec_module(H)


def window(index, time, cfo, sigma, support, exact, control, **kw):
    n = len(time)
    values = dict(
        index=index,
        center_time_s=float(np.mean(time)),
        raw_disjoint=True,
        frame_index=np.arange(n),
        absolute_time_s=np.array(time),
        cfo_hz=np.array(cfo),
        sigma_hz=np.array(sigma),
        supported=np.array(support, bool),
        exact_coherence=np.array(exact),
        control_coherence=np.array(control),
        frequency_innovation_hz=np.zeros(n),
        tracked_cfo_hz=np.zeros(n),
        tracked_rate_hz_s=np.zeros(n),
        tracked_rate_sigma_hz_s=np.zeros(n),
        phase_innovation_rad=np.zeros(n),
        phase_update=np.zeros(n, bool),
        reacquired=np.zeros(n, bool),
    )
    values.update(kw)
    return H.WindowRows(**values)


def score(models, target, common_names, times):
    common = set.intersection(*(set(models[name].prediction_by_key) for name in common_names))
    common = {key for key in common if times[key[1]] >= 0.020}
    results = {}
    for name, model in models.items():
        keys = sorted(key for key in model.prediction_by_key if times[key[1]] >= 0.020)
        own = [target[key[1]] - model.prediction_by_key[key] for key in keys]
        paired = [
            target[key[1]] - model.prediction_by_key[key]
            for key in sorted(common & model.prediction_by_key.keys())
        ]
        results[name] = {
            "own_count": len(own),
            "common_count": len(paired),
            "own_rms_hz": float(np.sqrt(np.mean(np.square(own)))) if own else None,
            "common_rms_hz": float(np.sqrt(np.mean(np.square(paired)))) if paired else None,
            "offline_fit": name == "offline-block-smoother",
        }
    return results


def cached_rows():
    rows = []
    for path in sorted(CACHE.glob("visit-*.frame-folds.json")):
        document = json.loads(path.read_text())
        for receiver in document["receivers"]:
            frames = [
                frame
                for frame in receiver.get("frames", [])
                if frame.get("even_odd_split", {}).get("status") == "complete"
            ]
            if not frames:
                continue
            even = [frame["even_odd_split"]["even"] for frame in frames]
            odd = [frame["even_odd_split"]["odd"] for frame in frames]
            # The historical adapter makes support a binary admission flag.
            # Raw exact coherence (often 0.02) is not that flag.
            w = window(
                document["visit_index"] * 2 + receiver["receiver_id"],
                [
                    (frame["device_counter"] - frames[0]["device_counter"]) / 10_000_000
                    for frame in frames
                ],
                [frame["absolute_cfo_hz"] for frame in even],
                [frame["frequency_uncertainty_hz"] for frame in even],
                [frame["even_odd_split"]["training_supported"] for frame in frames],
                [frame["exact_coherence"] for frame in even],
                [frame["control_coherence"] for frame in even],
            )
            line = H.trailing_line_predictions(w, history_s=0.020)
            jump, _ = H.jump_filter_predictions(w)
            offline, degree = H.offline_block_smoother(w)
            models = {model.name: model for model in (line, jump, offline)}
            rows.append(
                {
                    "visit_index": document["visit_index"],
                    "receiver_id": receiver["receiver_id"],
                    "split": document["split"],
                    "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "frame_count": len(frames),
                    "supported_frames": int(w.supported.sum()),
                    "offline_degree": degree,
                    "metrics": score(
                        models,
                        [frame["absolute_cfo_hz"] for frame in odd],
                        (line.name, jump.name),
                        w.absolute_time_s,
                    ),
                }
            )
    return rows


def actual_rows():
    selected = {}
    fullspan = HERE.parent / "fullspan/fullspan-trackers.json"
    if fullspan.exists():
        for row in json.loads(fullspan.read_text())["rows"]:
            if row.get("disposition") == "processed" and row["pnt_v2"].get("frames"):
                row = {**row, "duration_ms": row["actual_support_ms"]}
                selected[row["visit_index"], row["receiver_id"]] = row
    for path in sorted(HERE.parent.glob("visit-*.frame-methods.json")):
        doc = json.loads(path.read_text())
        for row in doc.get("span_observations", []):
            if not row.get("pnt_v2", {}).get("frames"):
                continue
            key = row["visit_index"], row["receiver_id"]
            if key not in selected or row["duration_ms"] > selected[key]["duration_ms"]:
                selected[key] = row
    rows = []
    for (visit, rx), row in sorted(selected.items()):
        frames = row["pnt_v2"]["frames"]
        def values(key, frames=frames):
            return np.array([frame[key] for frame in frames])
        w = window(
            visit * 2 + rx,
            values("time_s"),
            values("absolute_cfo_measurement_hz"),
            values("frequency_sigma_hz"),
            values("measurement_supported"),
            values("exact_coherence"),
            values("control_coherence"),
            frequency_innovation_hz=values("frequency_innovation_hz"),
            tracked_cfo_hz=values("tracked_absolute_cfo_hz"),
            tracked_rate_hz_s=values("tracked_doppler_rate_hz_s"),
            tracked_rate_sigma_hz_s=values("doppler_rate_sigma_hz_s"),
            phase_innovation_rad=values("phase_innovation_modulo_pi_rad"),
            phase_update=values("phase_update_applied"),
            reacquired=values("reacquired"),
        )
        line = H.trailing_line_predictions(w, history_s=0.020)
        v2 = H.v2_predictions(w)
        jump, _ = H.jump_filter_predictions(w)
        gated, _ = H.jump_filter_predictions(w, phase_gated=True)
        offline, degree = H.offline_block_smoother(w)
        models = {model.name: model for model in (line, v2, jump, gated, offline)}
        rows.append(
            {
                "visit_index": visit,
                "receiver_id": rx,
                "split": row["split"],
                "duration_ms": row["duration_ms"],
                "frame_count": len(frames),
                "offline_degree": degree,
                "metrics": score(
                    models, w.cfo_hz, (line.name, v2.name, jump.name, gated.name), w.absolute_time_s
                ),
            }
        )
    return rows


def summarize(rows):
    evaluation = [row for row in rows if row["split"] == "evaluation"]
    summary = {
        "receiver_arcs": len(rows),
        "evaluation_receiver_arcs": len(evaluation),
        "models": {},
    }
    names = sorted({name for row in rows for name in row["metrics"]})
    for name in names:
        metrics = [row["metrics"][name] for row in evaluation]
        summary["models"][name] = {
            "evaluation_predictions": sum(row["own_count"] for row in metrics),
            "evaluation_common_predictions": sum(row["common_count"] for row in metrics),
            "median_receiver_arc_rms_hz": float(
                np.median([row["own_rms_hz"] for row in metrics if row["own_rms_hz"] is not None])
            )
            if any(row["own_rms_hz"] is not None for row in metrics)
            else None,
            "median_common_receiver_arc_rms_hz": float(
                np.median(
                    [row["common_rms_hz"] for row in metrics if row["common_rms_hz"] is not None]
                )
            )
            if any(row["common_rms_hz"] is not None for row in metrics)
            else None,
        }
    return summary


def main():
    cached, actual = cached_rows(), actual_rows()
    result = {
        "schema": "scan-phase-row16/v1",
        "cached_even_to_odd": cached,
        "bounded_actual_v2": actual,
        "summary": {
            "cached_even_to_odd": summarize(cached),
            "bounded_actual_v2": summarize(actual),
        },
        "limitations": [
            "Cached lane fits even-symbol CFO histories and scores odd-symbol CFO; "
            "no truth CFO is known.",
            "Bounded actual lane uses historical posterior-sigma weighting "
            "and noisy same-frame frequency innovations.",
            "Offline smoother is in-sample in time and is not a causal competitor.",
            "Phase-gated and V2 comparisons are bounded to actual tracker checkpoints; "
            "no substituted state filter.",
            "Scored forecast times start at least 20 ms after the seed origin, "
            "when acquisition evidence is available.",
        ],
    }
    (HERE / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
