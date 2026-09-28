"""Isolated five-record training and omitted-record paired-state scoring."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from tools.rx_paired_state_model import fit_arms, score_lane

ROLES = ("reception", "held_frequency")


def raw_lane(source):
    windows = source["windows"]
    components = source["components"]
    if (
        len(components) < 2
        or components[-1]["kind"] != "other"
        or any(c["kind"] != "track_candidate" for c in components[:-1])
    ):
        raise ValueError("expected nominees followed by other")
    keys = [(c["track_id"], c["catalog_number"]) for c in components[:-1]]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate track/catalog hypothesis")
    ids, timestamps, roles, categories, geometry, visibility = [], [], [], [], [], []
    for window in windows:
        observed = window.get("observed")
        if not isinstance(observed, dict) or set(observed) != {"rx0", "rx1"}:
            raise ValueError("expected both receiver views")
        if any(not isinstance(observed[r], list) for r in ("rx0", "rx1")):
            raise ValueError("receiver views must be candidate lists")
        if any(not isinstance(c, dict) for r in observed for c in observed[r]):
            raise ValueError("candidate must be an object")
        predictions = window["predictions"]
        if [(h["track_id"], h["catalog_number"]) for h in predictions] != keys:
            raise ValueError("forecast nominee alignment mismatch")
        q = np.array([2 * math.sin(math.pi / 18) * h["los_enu_unit"]["east"] for h in predictions])
        up = np.array([h["los_enu_unit"]["up"] for h in predictions])
        geometry.append(np.stack((up, q**2, q), axis=-1))
        visible = [h["visible"] for h in predictions]
        if any(not isinstance(v, bool) for v in visible):
            raise ValueError("visibility must be boolean")
        visibility.append(visible)
        categories.append(int(bool(observed["rx0"])) + 2 * int(bool(observed["rx1"])))
        ids.append(window["source_window_id"])
        timestamps.append(window["prediction_utc_ns"])
        roles.append(window["role"])
    if (
        not windows
        or any(not isinstance(t, int) or isinstance(t, bool) for t in timestamps)
        or any(b <= a for a, b in zip(timestamps, timestamps[1:], strict=False))
    ):
        raise ValueError("nonempty strictly ordered integer timestamps required")
    if len(set(ids)) != len(ids) or any(not isinstance(x, str) or not x for x in ids):
        raise ValueError("unique source window IDs required")
    roles = np.asarray(roles)
    if not np.all(np.isin(roles, ROLES)) or not np.any(roles == "reception"):
        raise ValueError("valid roles with reception support required")
    geom = np.asarray(geometry)
    if not np.all(np.isfinite(geom)):
        raise ValueError("finite forecast geometry required")
    center = geom[roles == "reception"].mean(axis=0)
    times = np.array([(t - timestamps[0]) / 1e9 for t in timestamps])
    rate = source["sample_rate_hz"]
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("positive sample rate required")
    return {
        "lane": source["lane"],
        "ids": ids,
        "timestamps": timestamps,
        "times": times,
        "roles": roles,
        "y": np.array(categories),
        "nuisance": np.column_stack(
            (np.ones(len(times)), np.full(len(times), math.log(rate / 5e6)), times / 60)
        ),
        "geometry": geom - center,
        "geometry_center": center,
        "visible": np.array(visibility),
        "prior": np.array(
            [-np.inf if c["log_prior"] is None else c["log_prior"] for c in components]
        ),
    }


def prepare_fold(document, fold):
    if document.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported dataset")
    source = [lane for lane in document["lanes"] if lane["recording_split"] == "calibration"]
    sessions = sorted({lane["lane"]["session_id"] for lane in source})
    if len(sessions) != 6 or not 0 <= fold < 6:
        raise ValueError("expected six calibration records and fold0..5")
    held_session = sessions[fold]
    training = [
        raw_lane({**lane, "windows": [w for w in lane["windows"] if w["role"] == "reception"]})
        for lane in source
        if lane["lane"]["session_id"] != held_session
    ]
    held = [raw_lane(lane) for lane in source if lane["lane"]["session_id"] == held_session]
    values = np.concatenate([lane["geometry"].reshape(-1, 3) for lane in training])
    scales = np.sqrt(np.mean(values**2, axis=0))
    scales[scales < 1e-12] = 1.0
    y = np.concatenate([lane["y"] for lane in training])
    counts = np.bincount(y, minlength=4)
    background = (counts + 0.5) / (len(y) + 2)
    train_ids = sorted(i for lane in training for i in lane["ids"])
    held_ids = sorted(i for lane in held for i in lane["ids"])
    if len(set(train_ids + held_ids)) != len(train_ids + held_ids):
        raise ValueError("duplicate or overlapping source windows")
    for lane in training + held:
        lane["geometry"] = lane["geometry"] / scales
        lane["background"] = background.copy()
    receipt = {
        "held_session": held_session,
        "training_sessions": [s for s in sessions if s != held_session],
        "training_source_window_ids": train_ids,
        "held_source_window_ids": held_ids,
        "geometry_scales": scales.tolist(),
        "background": background.tolist(),
        "training_category_counts": counts.tolist(),
    }
    return training, held, receipt


def controlled(lanes, name):
    output = []
    for lane in lanes:
        geometry = lane["geometry"].copy()
        if name == "O_swap":
            geometry[..., 2] *= -1
        elif name == "O_reverse":
            for role in ROLES:
                rows = np.flatnonzero(lane["roles"] == role)
                geometry[rows, :, 2] = geometry[rows[::-1], :, 2]
        elif name == "O_permute":
            geometry[..., 2] = np.roll(geometry[..., 2], 1, axis=1)
        else:
            raise ValueError("unknown control")
        assert np.array_equal(geometry[..., :2], lane["geometry"][..., :2])
        output.append({**lane, "geometry": geometry})
    return output


def evaluate(lanes, selected):
    output, all_rows = [], []
    for lane in lanes:
        result = score_lane(lane, selected)
        rows = [
            {
                "source_window_id": identifier,
                "prediction_utc_ns": timestamp,
                "role": str(role),
                "category": int(y),
                "relative_log_score": relative,
                "reference_log_score": reference,
                "full_log_score": full,
            }
            for identifier, timestamp, role, y, relative, reference, full in zip(
                lane["ids"],
                lane["timestamps"],
                lane["roles"],
                lane["y"],
                result["relative_log_scores"],
                result["reference_log_scores"],
                result["full_log_scores"],
                strict=True,
            )
        ]
        output.append(
            {
                "lane": lane["lane"],
                "windows": rows,
                "state_posteriors": np.exp(result["state_log_posteriors"]).tolist(),
                "geometry_center": lane["geometry_center"].tolist(),
            }
        )
        all_rows.extend(rows)
    roles = {}
    for role in ROLES:
        rows = [r for r in all_rows if r["role"] == role]
        if not rows:
            raise ValueError("scored role has no windows")
        summary = {"windows": len(rows)}
        for key in ("relative_log_score", "reference_log_score", "full_log_score"):
            total = math.fsum(r[key] for r in rows)
            summary[key] = total
            summary[key + "_per_window"] = total / len(rows)
        roles[role] = summary
    return {"lanes": output, "roles": roles}


def run_fold(document, fold):
    training, held, receipt = prepare_fold(document, fold)
    fits = fit_arms(training)["fits"]
    evaluations = {arm: evaluate(held, fit["selected"]) for arm, fit in fits.items()}
    for name in ("O_swap", "O_reverse", "O_permute"):
        lanes = controlled(held, name)
        for original, changed in zip(held, lanes, strict=True):
            for key in ("y", "times", "nuisance", "prior", "visible", "background"):
                assert np.array_equal(original[key], changed[key])
        evaluations[name] = evaluate(lanes, fits["O"]["selected"])
    return {
        "schema": "rx-paired-state-cv-fold/v1",
        "status": "complete",
        "fold": fold,
        **receipt,
        "fits": fits,
        "evaluations": evaluations,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--fold", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    payload = args.dataset.read_bytes()
    result = run_fold(json.loads(payload), args.fold)
    result["dataset_sha256"] = hashlib.sha256(payload).hexdigest()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
