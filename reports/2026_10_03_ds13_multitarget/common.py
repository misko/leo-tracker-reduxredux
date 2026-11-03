"""Shared immutable-input adapter for the bounded multi-target replay experiment.

This is a retrospective, positive-group-conditioned diagnostic. The reference
position and nuisance fit saw all rows. It is not held-out validation.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "2026_10_02_ds13_timing_em"
sys.path.insert(0, str(SOURCE))
from plot_all_glrt_doppler_overlay import load_archived_session

SESSIONS = {"A": "scan-fw-911c4e5db9243281", "B": "scan-fw-ffa1cc19d8d7c09f"}
FREF = 11.085e9
SIGMA_NATIVE_HZ = 200.0
ALIAS_HZ = 1.0 / 4.4e-6
CLUTTER_RATE = 2.0
GATE_NATIVE_HZ = 1000.0


def distinct_peak_rows(rows, measured):
    """Collapse exact-period copies, retaining stable original representative IDs."""
    kept, duplicates = [], {}
    for row in rows:
        value = float(measured[row])
        for representative in kept:
            other = float(measured[representative])
            distance = (value - other + ALIAS_HZ/2) % ALIAS_HZ - ALIAS_HZ/2
            tolerance = 8*np.finfo(float).eps*max(ALIAS_HZ, abs(value), abs(other), 1.)
            if abs(distance) <= tolerance:
                duplicates[int(row)] = int(representative)
                break
        else:
            kept.append(int(row))
    return np.asarray(kept, int), duplicates


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_scan(label, rf_variant=None):
    session = SESSIONS.get(label, label)
    label = next(k for k, v in SESSIONS.items() if v == session)
    archive, metadata, path, receipt = load_archived_session(session)
    arrays = {k: archive[k].copy() for k in archive.files}
    archive.close()
    rf_variant = rf_variant or os.environ.get("DS13_RF_VARIANT", "sealed")
    if rf_variant not in ("sealed", "fitted-c", "zero-c"):
        raise ValueError("Unknown RF control variant")
    extra_provenance = {}
    refit_visible = None
    if rf_variant != "sealed":
        refit_path = ROOT / "rf-control" / f"{label}-{rf_variant}.npz"
        refit_receipt_path = ROOT / "rf-control/receipt.json"
        refit_receipt = json.loads(refit_receipt_path.read_text())
        refit = next(s for s in refit_receipt["scans"] if s["scan"] == label)["arms"][rf_variant]["fit"]
        if not refit["success"]:
            raise ValueError("RF ablation requires converged physical refits")
        with np.load(refit_path) as refit_arrays:
            for key in refit_arrays.files:
                if key == "visible":
                    refit_visible = refit_arrays[key].copy()
                else:
                    arrays[key] = refit_arrays[key].copy()
        extra_provenance = {str(p): digest(p) for p in (refit_path, refit_receipt_path)}
        metadata = {**metadata, "rf_control_variant": rf_variant,
                    "rf_coefficient_hz_per_ghz": refit["rf_coefficient_hz_per_ghz"]}
    profile_path = SOURCE / "pruned-position-profile-grid" / f"{session}.json"
    profile = json.loads(profile_path.read_text())
    pdet = float(profile["detection_probability"])
    native = arrays["residual_hz"] * arrays["rf_hz"][:, None] / FREF
    nearest = np.clip(np.rint(arrays["times_s"] / .25).astype(int), 0,
                      len(arrays["dense_times_s"]) - 1)
    visible = arrays["dense_visible"][nearest] if refit_visible is None else refit_visible
    gain = (np.log(pdet / (1 - pdet)) - np.log(SIGMA_NATIVE_HZ * np.sqrt(2*np.pi))
            - .5 * (native / SIGMA_NATIVE_HZ)**2 - np.log(CLUTTER_RATE / ALIAS_HZ))
    gain[~visible | (np.abs(native) > GATE_NATIVE_HZ)] = -np.inf
    groups = []
    duplicates = {}
    for group_id in np.unique(arrays["group"]):
        rows = np.flatnonzero(arrays["group"] == group_id)
        rx = np.unique(arrays["receiver"][rows])
        channel = np.unique(arrays["channel"][rows])
        if len(rx) != 1 or len(channel) != 1:
            raise ValueError("A group crosses receiver/channel boundaries")
        rows, copies = distinct_peak_rows(rows, arrays["measured_raw_hz"])
        duplicates.update(copies)
        groups.append(dict(rows=rows, time_s=float(np.mean(arrays["times_s"][rows])),
                           receiver=int(rx[0]), channel=int(channel[0]), group_id=int(group_id)))
    groups.sort(key=lambda g: (g["time_s"], g["group_id"]))
    if duplicates:
        gain[list(duplicates)] = -np.inf
    return dict(scan=label, session=session, arrays=arrays, groups=groups,
                log_gain=gain, native_residual_hz=native, visible=visible,
                metadata=metadata, detection_probability=pdet, duplicate_rows=duplicates,
                rf_variant=rf_variant,
                provenance={str(path): digest(path), str(receipt): digest(receipt),
                            str(profile_path): digest(profile_path), **extra_provenance},
                scope="Frozen reference-position/nuisance replay; observed positive groups only; not held out")


def group_map(log_gain):
    """Exact joint MAP relative to all-clutter/all-missed; rows x satellites.

    One peak per satellite and one satellite per peak. A subset DP across
    satellites avoids enumerating all (satellite_count+1)**peak_count labels.
    Returns [(local_row, satellite_column), ...], relative log score.
    """
    gains = np.asarray(log_gain, float)
    nr, ns = gains.shape
    states = {0: (0.0, ())}
    for satellite in range(ns):
        updated = dict(states)
        for mask, (score, pairs) in states.items():
            for row in range(nr):
                value = gains[row, satellite]
                if mask & (1 << row) or not np.isfinite(value) or value <= 0:
                    continue
                newmask = mask | (1 << row)
                candidate = score + float(value)
                if candidate > updated.get(newmask, (-np.inf, ()))[0]:
                    updated[newmask] = (candidate, pairs + ((row, satellite),))
        states = updated
    score, pairs = max(states.values(), key=lambda value: value[0])
    return list(pairs), score


def assignment_record(data, row, column, probability=None):
    a = data["arrays"]
    return dict(scan=data["scan"], row_index=int(row),
                catalog_number=int(a["catalog_numbers"][column]),
                receiver=int(a["receiver"][row]), channel=int(a["channel"][row]),
                time_s=float(a["times_s"][row]), residual_hz=float(a["residual_hz"][row, column]),
                probability=probability)


def write_assignments(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["scan", "row_index", "catalog_number", "receiver", "channel", "time_s", "residual_hz", "probability"]
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def baseline(data):
    records = []
    score = 0.0
    for group in data["groups"]:
        rows = group["rows"]
        pairs, group_score = group_map(data["log_gain"][rows])
        score += group_score
        records.extend(assignment_record(data, rows[row], column) for row, column in pairs)
    return records, score
