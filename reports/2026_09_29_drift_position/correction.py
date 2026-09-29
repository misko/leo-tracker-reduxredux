"""Training-only differential drift correction; no absolute clock claim."""

import importlib.util
from pathlib import Path

import numpy as np

SOURCE = Path(__file__).resolve().parents[1] / "2026_09_29_rx_alignment/align.py"
spec = importlib.util.spec_from_file_location("published_alignment", SOURCE)
alignment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alignment)

ALLOCATIONS = {"none": None, "symmetric": 0.5, "rx0_anchor": 0.0, "rx1_anchor": 1.0}


def calibrations(scan):
    """Preserve published training-selected pairs, omitting each target response.

    Selection itself used target training data. This is not independent pairing
    validation; target exclusion applies to the donor coefficient fit only.
    """
    pairs = sorted((p for p in scan["pairs"] if p["selected"]), key=lambda p: (p["rx0"], p["rx1"]))
    features = [alignment.feature(p) for p in pairs]
    output = {}
    for i, target in enumerate(pairs):
        indices = [
            j
            for j, p in enumerate(pairs)
            if j != i and p["channel"] == target["channel"] and p["rf_hz"] == target["rf_hz"]
        ]
        donors = []
        for j in indices:
            p = pairs[j]
            mask = np.asarray(p["training"], bool)
            delta = np.asarray(p["rx0_hz"])[mask] - np.asarray(p["rx1_hz"])[mask]
            donors.append({**p, "offset_hz": float(np.median(delta))})
        fitted = alignment.fit(donors, [features[j] for j in indices], "drift")
        if not features[i]["qualified"]:
            fitted = {"qualified": False, "reason": "target_polynomial_unqualified"}
        for rx in (0, 1):
            key = target[f"rx{rx}"]
            if key in output:
                raise ValueError("Selected pairs must be one-to-one")
            output[key] = {
                "receiver": rx,
                "channel": target["channel"],
                "rf_hz": target["rf_hz"],
                "fit": fitted,
                "pair": [target["rx0"], target["rx1"]],
                "donors": [[pairs[j]["rx0"], pairs[j]["rx1"]] for j in indices],
            }
    return output


def correct_track(track, calibration, arm):
    """Return a new measured array and receipt, retaining every observation.

    Correct only linear drift. Track-constant offsets cancel in the downstream
    contrast likelihood. Extrapolation in time within this track is explicit;
    never borrow a different scan/channel/RF's calibration.
    """
    if arm not in ALLOCATIONS:
        raise ValueError("Unknown allocation")
    y = np.asarray(track.get("y", track["measured_hz"]), float)
    times = np.asarray(track["times_s"], float)
    if y.shape != times.shape or not np.isfinite(y).all() or not np.isfinite(times).all():
        raise ValueError("Invalid observations")
    receipt = {"track_id": track["track_id"], "corrected": False, "reason": "no_pair"}
    if arm == "none":
        return y.copy(), {**receipt, "reason": "control"}
    if calibration is None:
        return y.copy(), receipt
    if track["channel"] != calibration["channel"] or track["rf_hz"] != calibration["rf_hz"]:
        raise ValueError("Calibration channel/RF mismatch")
    rx = calibration["receiver"]
    if track["track_id"] != calibration["pair"][rx]:
        raise ValueError("Calibration target mismatch")
    fitted = calibration["fit"]
    if not fitted["qualified"]:
        return y.copy(), {**receipt, "reason": fitted["reason"]}
    fraction = ALLOCATIONS[arm] - rx
    correction = fraction * fitted["drift_hz_s"] * (times - fitted["reference_s"])
    return y - correction, {
        **receipt,
        "corrected": bool(np.any(correction != 0)),
        "reason": "qualified",
        "fraction": fraction,
        "drift_hz_s": fitted["drift_hz_s"],
        "correction_range_hz": float(np.ptp(correction)),
    }


def correct_document(document, scan, arm):
    if document["session_id"] != scan["session_id"]:
        raise ValueError("Calibration scan mismatch")
    mapping = calibrations(scan)
    tracks, receipts = [], []
    for track in document["tracks"]:
        y, receipt = correct_track(track, mapping.get(track["track_id"]), arm)
        tracks.append({**track, "y": y})
        receipts.append(receipt)
    return {**document, "tracks": tracks}, receipts
