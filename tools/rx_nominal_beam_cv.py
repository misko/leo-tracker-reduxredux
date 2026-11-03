"""Fit one omitted-record nominal-beam calibration fold."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

from tools.rx_background_crossvalidation import calibration_rows
from tools.rx_causal_full_calibration import full_reception_scaler
from tools.rx_causal_geometry_cv import training_reception_document
from tools.rx_empirical_background import fit as fit_background
from tools.rx_geometry_temporal_transfer import (
    _calibration_record,
    score_lanes,
    within_center_from_reception,
)
from tools.rx_joint_geometry import attach_reference
from tools.rx_joint_geometry_fit import BETA_SD
from tools.rx_nominal_beam import beam_features, fit_beam_arms, fit_shared_beam_scale
from tools.rx_orbit_increment import attach_orbit_increment
from tools.rx_presence_geometry import prepare_lanes
from tools.rx_within_geometry_cv import prepare_reception_lanes, within_center


def _json_hash(value) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def calibration_sessions(document):
    sessions = sorted(
        {
            lane["lane"]["session_id"]
            for lane in document.get("lanes", [])
            if lane.get("recording_split") == "calibration"
        }
    )
    lanes = [
        lane for lane in document.get("lanes", []) if lane.get("recording_split") == "calibration"
    ]
    if len(sessions) != 6 or len(lanes) != 12:
        raise ValueError("expected six calibration recordings and twelve lanes")
    return sessions


def _compact_diagnostics(receipt):
    modes = Counter()
    windows = 0
    nominees = 0
    for lane in receipt:
        for receiver in lane["receivers"]:
            for window in receiver["windows"]:
                windows += 1
                for nominee in window["nominees"]:
                    nominees += 1
                    modes[nominee["mode"]] += 1
    return {
        "sha256": _json_hash(receipt),
        "receiver_windows": windows,
        "nominee_rows": nominees,
        "mode_counts": dict(sorted(modes.items())),
    }


def _held_uniform(record, background, center, scale):
    lanes = prepare_lanes(record, center, scale)
    lanes = attach_reference(lanes, background, 500.0, center=center, scale=scale)
    return within_center_from_reception(lanes)


def prepare_five_record_training(document):
    """Prepare a physically restricted five-record reception training document."""
    rows = calibration_rows(document, expected_records=5)
    background = fit_background(rows, "joint")
    center, scale = full_reception_scaler(document)
    lanes = prepare_reception_lanes(document, center, scale)
    lanes = attach_reference(lanes, background, 500.0, calibration_only=True)
    return {
        "rows": rows,
        "background": background,
        "center": center,
        "scale": scale,
        "uniform": within_center(lanes),
    }


def run_fold(document, fold_index):
    sessions = calibration_sessions(document)
    if not 0 <= fold_index < len(sessions):
        raise ValueError("fold must be in 0..5")
    held_session = sessions[fold_index]
    training_sessions = sorted(set(sessions) - {held_session})
    restricted = training_reception_document(document, held_session)
    prepared = prepare_five_record_training(restricted)
    actual_training = sorted({row["session_id"] for row in prepared["rows"]})
    if actual_training != training_sessions:
        raise ValueError("training extraction membership mismatch")
    training_orbit, training_receipt = attach_orbit_increment(prepared["uniform"])
    beam_scale = fit_shared_beam_scale(training_orbit)
    training_e = beam_features(training_orbit, beam_scale, tilt_deg=0.0)
    training_b = beam_features(training_orbit, beam_scale, tilt_deg=10.0)
    fits = fit_beam_arms(training_e, training_b)

    held = _calibration_record(document, held_session)
    uniform = _held_uniform(held, prepared["background"], prepared["center"], prepared["scale"])
    base, held_receipt = attach_orbit_increment(uniform)
    zero_motion, zero_receipt = attach_orbit_increment(uniform, motion_control="zero")
    reverse_motion, reverse_receipt = attach_orbit_increment(uniform, motion_control="reverse")
    reference = [lane["reference"].tolist() for lane in base]
    if any(
        [lane["reference"].tolist() for lane in lanes] != reference
        for lanes in (zero_motion, reverse_motion)
    ):
        raise ValueError("motion control changed causal reference")
    base_signal = [lane["signal"].tolist() for lane in base]
    e_lanes = beam_features(base, beam_scale, tilt_deg=0.0)
    b_lanes = beam_features(base, beam_scale, tilt_deg=10.0)
    controls = {
        "B_swap": beam_features(base, beam_scale, tilt_deg=10.0, control="swap"),
        "B_geometry_reverse": beam_features(
            base, beam_scale, tilt_deg=10.0, control="geometryreverse"
        ),
        "B_geometry_permute": beam_features(
            base, beam_scale, tilt_deg=10.0, control="geometrypermute"
        ),
        "B_zero_motion": beam_features(zero_motion, beam_scale, tilt_deg=10.0),
        "B_reverse_motion": beam_features(reverse_motion, beam_scale, tilt_deg=10.0),
    }
    for name in ("B_swap", "B_geometry_reverse", "B_geometry_permute"):
        if [lane["signal"].tolist() for lane in controls[name]] != base_signal:
            raise ValueError("geometry-only beam control changed signal ratios")
        if [lane["reference"].tolist() for lane in controls[name]] != reference:
            raise ValueError("geometry-only beam control changed reference")
        for original, controlled in zip(b_lanes, controls[name], strict=True):
            if not np.array_equal(original["visible"], controlled["visible"]):
                raise ValueError("geometry-only beam control changed visibility")
            if not np.array_equal(original["prior"], controlled["prior"]):
                raise ValueError("geometry-only beam control changed nominee priors")
    for name in ("B_zero_motion", "B_reverse_motion"):
        for original, controlled in zip(b_lanes, controls[name], strict=True):
            if not np.array_equal(original["x"], controlled["x"]):
                raise ValueError("motion-only beam control changed geometry features")
    evaluations = {
        "D": score_lanes(e_lanes, fits["fits"]["D"]["selected"]),
        "E": score_lanes(e_lanes, fits["fits"]["E"]["selected"]),
        "B": score_lanes(b_lanes, fits["fits"]["B"]["selected"]),
    }
    for name, lanes in controls.items():
        evaluations[name] = score_lanes(lanes, fits["fits"]["B"]["selected"])
    training_ids = sorted(row["window_id"] for row in prepared["rows"])
    held_ids = sorted(
        window["source_window_id"] for lane in held["lanes"] for window in lane["windows"]
    )
    scaler = {
        "feature_center": prepared["center"].tolist(),
        "feature_scale": prepared["scale"].tolist(),
    }
    return {
        "schema": "rx-nominal-beam-cv-fold/v1",
        "status": "complete",
        "fold": fold_index,
        "held_session": held_session,
        "training_sessions": training_sessions,
        "training_source_window_ids": training_ids,
        "training_source_window_count": len(training_ids),
        "training_source_window_ids_sha256": _json_hash(training_ids),
        "held_source_window_ids": held_ids,
        "held_source_window_count": len(held_ids),
        "held_source_window_ids_sha256": _json_hash(held_ids),
        "background_model": prepared["background"],
        "background_model_sha256": _json_hash(prepared["background"]),
        **scaler,
        "feature_scaler_sha256": _json_hash(scaler),
        "beam_scale": beam_scale,
        "priors": {
            "beta_sd": BETA_SD[:4].tolist(),
            "occupancy_logit_sd": 2.0,
            "log_tau_sd": 1.5,
            "beta_bounds": [-12.0, 12.0],
            "monotone_fourth_beta_bounds": [0.0, 12.0],
            "tau_bounds_s": [0.1, 10.0],
        },
        "fits": fits["fits"],
        "evaluations": evaluations,
        "diagnostics": {
            "training": _compact_diagnostics(training_receipt),
            "held": _compact_diagnostics(held_receipt),
            "held_zero_motion": _compact_diagnostics(zero_receipt),
            "held_reverse_motion": _compact_diagnostics(reverse_receipt),
        },
        "isolation": (
            "Five-record calibration reception trains the fold; only the omitted "
            "calibration record is scored."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--fold", type=int, required=True, choices=range(6))
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
