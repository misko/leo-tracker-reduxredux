"""Freeze full calibration-only geometry models for fresh DS8 evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from tools.rx_background_crossvalidation import calibration_rows
from tools.rx_causal_geometry import attach_causal_frequency
from tools.rx_empirical_background import fit
from tools.rx_geometry_fit import raw_features
from tools.rx_joint_geometry import attach_reference
from tools.rx_joint_geometry_fit import fit_arms
from tools.rx_within_geometry_cv import prepare_reception_lanes, reception_document, within_center

SIGMA_HZ = 500.0


def _json_hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def full_reception_scaler(document):
    """Compute the original scaler convention from calibration reception only."""
    restricted = reception_document(document)
    blocks = []
    for lane in restricted["lanes"]:
        raw = raw_features(lane)[0][:, :-1]
        blocks.append(raw.reshape(-1, 8))
    if not blocks:
        raise ValueError("empty calibration reception geometry")
    values = np.concatenate(blocks)
    center, scale = values.mean(axis=0), values.std(axis=0)
    center[0], scale[0] = 0.0, 1.0
    scale[scale < 1e-12] = 1.0
    return center, scale


def prepare_families(document):
    """Prepare common uniform and causal training arrays without fitting."""
    rows = calibration_rows(document)
    background = fit(rows, "joint")
    center, scale = full_reception_scaler(document)
    restricted = reception_document(document)
    lanes = prepare_reception_lanes(restricted, center, scale)
    uniform = within_center(attach_reference(lanes, background, SIGMA_HZ, calibration_only=True))
    causal, diagnostics = attach_causal_frequency(uniform, sigma_hz=SIGMA_HZ)
    return {
        "rows": rows,
        "background": background,
        "center": center,
        "scale": scale,
        "uniform": uniform,
        "causal": causal,
        "causal_diagnostics": diagnostics,
    }


def run(document):
    prepared = prepare_families(document)
    sessions = sorted({row["session_id"] for row in prepared["rows"]})
    calibration_lanes = [
        lane for lane in document.get("lanes", []) if lane.get("recording_split") == "calibration"
    ]
    if len(sessions) != 6 or len(calibration_lanes) != 12:
        raise ValueError("expected six calibration records and twelve calibration lanes")
    for family in ("uniform", "causal"):
        lane_sessions = {lane["source"]["lane"]["session_id"] for lane in prepared[family]}
        if lane_sessions != set(sessions):
            raise ValueError(f"{family} training membership mismatch")
        if sum(len(lane["times"]) for lane in prepared[family]) != len(prepared["rows"]):
            raise ValueError(f"{family} training window count mismatch")
    old_fits = {"D": {"parameters": [-2.0, 0.0, 0.0]}}
    fits = {}
    for family in ("uniform", "causal"):
        print(json.dumps({"family": family, "stage": "fit"}), flush=True)
        fits[family] = fit_arms(prepared[family], old_fits)
    window_ids = sorted(row["window_id"] for row in prepared["rows"])
    return {
        "schema": "rx-causal-full-calibration/v1",
        "status": "complete",
        "sigma_hz": SIGMA_HZ,
        "calibration_sessions": sessions,
        "training_source_window_ids": window_ids,
        "training_source_window_count": len(window_ids),
        "training_source_window_ids_sha256": _json_hash(window_ids),
        "background_model": prepared["background"],
        "background_model_sha256": _json_hash(prepared["background"]),
        "feature_center": prepared["center"].tolist(),
        "feature_scale": prepared["scale"].tolist(),
        "families": {family: {"fits": fits[family]["fits"]} for family in ("uniform", "causal")},
        "causal_frequency_diagnostics": prepared["causal_diagnostics"],
        "interpretation": "Calibration-reception-only frozen models for prospective DS8 scoring; "
        "no evaluation or held outcome was read.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    payload = args.dataset.read_bytes()
    result = run(json.loads(payload))
    result["dataset_sha256"] = hashlib.sha256(payload).hexdigest()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
