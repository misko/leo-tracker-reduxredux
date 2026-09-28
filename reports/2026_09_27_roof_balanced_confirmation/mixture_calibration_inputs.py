"""Calibration-only exact joins and feature tensors for mixture reception fits."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
DIRECTION = HERE.parent / "2026_09_27_roof_direction_subset"
FIRST = HERE.parent / "2026_09_27_roof_geometry_confirmation"
LOCATION = HERE.parent / "2026_09_27_roof_location_geometry"
sys.path[:0] = [str(DIRECTION), str(FIRST)]
from calibrate_topology_reception import topology_filtered_rows


@dataclass(frozen=True)
class JoinedRow:
    session_id: str
    track_id: str
    observation_id: str
    receiver_id: str
    channel_edge: str
    sample_rate: str
    anchor_margin: float
    matched: bool
    log_ratio: float
    east: np.ndarray


@dataclass(frozen=True)
class JoinedTrack:
    session_id: str
    track_id: str
    candidate_ids: tuple[int, ...]
    log_weights: np.ndarray
    rows: tuple[JoinedRow, ...]


@dataclass(frozen=True)
class FeatureSchema:
    detection_channel_edges: tuple[str, ...]
    detection_sample_rates: tuple[str, ...]
    ratio_channel_edges: tuple[str, ...]
    ratio_sample_rates: tuple[str, ...]
    log_margin_mean: float
    log_margin_scale: float
    detection_east_mean: float
    detection_east_scale: float
    ratio_east_mean: float
    ratio_east_scale: float
    detection_nuisance_names: tuple[str, ...]
    ratio_nuisance_names: tuple[str, ...]


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _logsumexp(values: np.ndarray) -> float:
    maximum = float(np.max(values))
    return maximum + math.log(float(np.exp(values - maximum).sum()))


def load_joined() -> tuple[tuple[JoinedTrack, ...], dict]:
    rows_path = DIRECTION / "model_rows.json"
    directions_path = HERE / "calibration_directions_data.json"
    frequency_path = LOCATION / "topology_frequency_fixedpoint.json"
    audit_path = FIRST / "audit_source_topology.json"
    design_path = HERE / "CANDIDATE_MIXTURE_CALIBRATION_DESIGN.md"
    payloads = {name: path.read_bytes() for name, path in {
        "model_rows": rows_path, "calibration_directions_data": directions_path,
        "topology_frequency_fixedpoint": frequency_path,
        "topology_audit": audit_path, "design": design_path}.items()}
    model_rows = json.loads(payloads["model_rows"])
    direction_data = json.loads(payloads["calibration_directions_data"])
    frequency = json.loads(payloads["topology_frequency_fixedpoint"])
    audit = json.loads(payloads["topology_audit"])
    if (not frequency.get("converged") or
            frequency.get("topology_audit_sha256") != digest(payloads["topology_audit"])):
        raise ValueError("frozen frequency extraction is not converged/audit-bound")
    if direction_data["source_hashes"]["topology_frequency_fixedpoint"] != digest(
            payloads["topology_frequency_fixedpoint"]):
        raise ValueError("direction data frequency extraction binding changed")
    if direction_data["source_hashes"]["calibration_topology_audit"] != digest(
            payloads["topology_audit"]):
        raise ValueError("direction data topology audit binding changed")
    if direction_data["source_hashes"]["model_rows"] != digest(payloads["model_rows"]):
        raise ValueError("direction data model rows binding changed")
    if direction_data["frozen_parameters"] != frequency["frozen_final_parameters"]:
        raise ValueError("direction/frequency parameter binding changed")
    sessions = sorted(frequency["source_digests"])
    if len(sessions) != 6:
        raise ValueError("expected six frozen calibration sessions")
    retained, accounting = topology_filtered_rows(model_rows, audit, set(sessions))
    if len(retained) != 6378 or accounting["retained_calibration_tracks"] != 344:
        raise ValueError("expected exact 6,378-row/344-track retained calibration join")
    excluded = {(row["session_id"], track_id) for row in audit["sessions"]
                if row["split"] == "calibration" for track_id in row["removed_track_ids"]}
    if {(row["session_id"], row["track_id"]) for row in retained} & excluded:
        raise ValueError("excluded topology track remains in calibration rows")

    directions = {(row["session_id"], row["track_id"], row["observation_id"]): row
                  for row in direction_data["rows"]}
    if len(directions) != len(direction_data["rows"]):
        raise ValueError("duplicate calibration direction key")
    row_keys = {(row["session_id"], row["track_id"], row["observation_id"])
                for row in retained}
    if len(row_keys) != len(retained):
        raise ValueError("duplicate retained model-row join key")
    if set(directions) != row_keys:
        raise ValueError("calibration direction/model-row join is not exact")
    fixed_rows = [(sid, row["track_id"], row)
                  for sid, tracks in frequency["final_tracks"].items() for row in tracks]
    fixed = {(sid, track_id): row for sid, track_id, row in fixed_rows}
    if len(fixed) != len(fixed_rows):
        raise ValueError("duplicate frozen frequency track key")
    retained_tracks = {(row["session_id"], row["track_id"]) for row in retained}
    if set(fixed) != retained_tracks:
        raise ValueError("frozen frequency track membership differs from retained rows")
    grouped: dict[tuple[str, str], list[JoinedRow]] = {}
    track_meta = {}
    candidate_digest = {}
    for row in retained:
        key = (row["session_id"], row["track_id"])
        source = directions[(key[0], key[1], row["observation_id"])]
        fitted = fixed.get(key)
        if fitted is None:
            raise ValueError("retained track lacks frozen frequency identity")
        candidate_ids = tuple(int(value) for value in fitted["candidate_ids"])
        if len(candidate_ids) != 3 or len(set(candidate_ids)) != 3:
            raise ValueError("frozen shortlist must contain three unique candidates")
        observed_ids = tuple(int(item["candidate_id"])
                             for item in source["robust_candidates"])
        if observed_ids != candidate_ids:
            raise ValueError("candidate direction order differs from frozen shortlist")
        log_weights = np.asarray(fitted["log_weights"], float)
        if (log_weights.shape != (3,) or not np.all(np.isfinite(log_weights)) or
                not np.isclose(_logsumexp(log_weights), 0., rtol=0, atol=1e-10)):
            raise ValueError("frozen candidate log weights are invalid")
        prior = track_meta.setdefault(key, (candidate_ids, log_weights))
        if prior[0] != candidate_ids or not np.array_equal(prior[1], log_weights):
            raise ValueError("track identity prior changes across observations")
        east = np.asarray([item["east"] for item in source["robust_candidates"]], float)
        if east.shape != log_weights.shape or not np.all(np.isfinite(east)):
            raise ValueError("invalid candidate direction array")
        if row["receiver_id"] not in {"rx0", "rx1"}:
            raise ValueError("invalid receiver identity")
        if not math.isfinite(float(row["anchor_margin"])) or float(row["anchor_margin"]) <= 0:
            raise ValueError("anchor margin must be positive and finite")
        ratio = row["log_margin_ratio_rx1_rx0"]
        if bool(row["matched"]) != (ratio is not None):
            raise ValueError("matched/ratio outcome disagreement")
        if ratio is not None and not math.isfinite(float(ratio)):
            raise ValueError("matched ratio must be finite")
        grouped.setdefault(key, []).append(JoinedRow(
            session_id=key[0], track_id=key[1], observation_id=row["observation_id"],
            receiver_id=row["receiver_id"], channel_edge=f'{row["channel"]}:{row["edge"]}',
            sample_rate=str(row["sample_rate_hz"]),
            anchor_margin=float(row["anchor_margin"]), matched=bool(row["matched"]),
            log_ratio=float(ratio) if ratio is not None else 0., east=east))
    tracks = []
    for key in sorted(grouped):
        candidate_ids, log_weights = track_meta[key]
        rows = tuple(grouped[key])
        tracks.append(JoinedTrack(key[0], key[1], candidate_ids,
                                  log_weights.copy(), rows))
        body = json.dumps({"candidate_ids": candidate_ids,
                           "log_weights": log_weights.tolist()},
                          sort_keys=True, separators=(",", ":")).encode()
        candidate_digest[f"{key[0]}:{key[1]}"] = digest(body)
    if len(tracks) != 344 or sum(len(track.rows) for track in tracks) != 6378:
        raise ValueError("joined calibration dimensions changed")
    return tuple(tracks), {
        "sessions": sessions, "rows": 6378, "tracks": 344,
        "excluded_track_keys": [list(key) for key in sorted(excluded)],
        "join_accounting": accounting,
        "candidate_prior_sha256": candidate_digest,
        "source_hashes": {name: digest(payload) for name, payload in payloads.items()},
    }


def fit_schema(tracks: tuple[JoinedTrack, ...]) -> FeatureSchema:
    rows = [row for track in tracks for row in track.rows]
    if not rows:
        raise ValueError("training tracks are required")
    matched_rows = [row for row in rows if row.matched]
    if not matched_rows:
        raise ValueError("matched training rows are required")
    detection_channel_edges = tuple(sorted({row.channel_edge for row in rows}))
    detection_sample_rates = tuple(sorted({row.sample_rate for row in rows}))
    ratio_channel_edges = tuple(sorted({row.channel_edge for row in matched_rows}))
    ratio_sample_rates = tuple(sorted({row.sample_rate for row in matched_rows}))
    log_margin = np.log([row.anchor_margin for row in rows])
    means = []
    detection_east = []
    ratio_east = []
    for track in tracks:
        weights = np.exp(track.log_weights)
        for row in track.rows:
            mean = float(weights @ row.east)
            detection_east.append(mean if row.receiver_id == "rx0" else -mean)
            if row.matched:
                ratio_east.append(mean)
    def center_scale(values):
        mean = float(np.mean(values)); scale = float(np.std(values))
        return mean, scale if scale > 1e-12 else 1.
    margin_mean, margin_scale = center_scale(log_margin)
    detection_mean, detection_scale = center_scale(detection_east)
    ratio_mean, ratio_scale = center_scale(ratio_east)
    detection_common = tuple(
        [f"channel_edge={level}" for level in detection_channel_edges[1:]]
        + [f"sample_rate_hz={level}" for level in detection_sample_rates[1:]]
        + ["receiver=rx1"])
    ratio_common = tuple(
        [f"channel_edge={level}" for level in ratio_channel_edges[1:]]
        + [f"sample_rate_hz={level}" for level in ratio_sample_rates[1:]]
        + ["receiver=rx1"])
    return FeatureSchema(
        detection_channel_edges, detection_sample_rates,
        ratio_channel_edges, ratio_sample_rates, margin_mean, margin_scale,
        detection_mean, detection_scale, ratio_mean, ratio_scale,
        ("intercept",) + detection_common + ("log_anchor_margin",),
        ("intercept",) + ratio_common)


def _nuisance(row: JoinedRow, schema: FeatureSchema, detection: bool) -> list[float]:
    channels = (schema.detection_channel_edges if detection
                else schema.ratio_channel_edges)
    rates = (schema.detection_sample_rates if detection
             else schema.ratio_sample_rates)
    values = [1.]
    values += [float(row.channel_edge == level) for level in channels[1:]]
    values += [float(row.sample_rate == level) for level in rates[1:]]
    values += [float(row.receiver_id == "rx1")]
    if detection:
        values += [(math.log(row.anchor_margin) - schema.log_margin_mean)
                   / schema.log_margin_scale]
    return values


def build_arm(tracks: tuple[JoinedTrack, ...], schema: FeatureSchema,
              arm: str, core_module):
    if arm not in {"M0", "mean", "mixture"}:
        raise ValueError("unknown calibration arm")
    output = []
    for track in tracks:
        k = len(track.candidate_ids); n = len(track.rows)
        pd0 = len(schema.detection_nuisance_names)
        pr0 = len(schema.ratio_nuisance_names)
        detection = np.empty((k, n, pd0 + (arm != "M0")))
        ratio = np.empty((k, n, pr0 + (arm != "M0")))
        weights = np.exp(track.log_weights)
        for index, row in enumerate(track.rows):
            detection[:, index, :pd0] = _nuisance(row, schema, True)
            ratio[:, index, :pr0] = _nuisance(row, schema, False)
            if arm != "M0":
                east = row.east if arm == "mixture" else np.repeat(weights @ row.east, k)
                signed = east if row.receiver_id == "rx0" else -east
                detection[:, index, -1] = ((signed - schema.detection_east_mean)
                                           / schema.detection_east_scale)
                ratio[:, index, -1] = ((east - schema.ratio_east_mean)
                                       / schema.ratio_east_scale)
        output.append(core_module.TrackData(
            log_weights=track.log_weights.copy(), detection_design=detection,
            matched=np.asarray([row.matched for row in track.rows], bool),
            ratio_design=ratio,
            log_ratio=np.asarray([row.log_ratio for row in track.rows], float)))
    detection_names = schema.detection_nuisance_names + (("signed_east",) if arm != "M0" else ())
    ratio_names = schema.ratio_nuisance_names + (("east",) if arm != "M0" else ())
    layout = core_module.ParameterLayout(
        detection_size=len(detection_names), ratio_size=len(ratio_names),
        detection_penalty_mask=np.asarray([False] + [True] * (len(detection_names) - 1)),
        ratio_penalty_mask=np.asarray([False] + [True] * (len(ratio_names) - 1)))
    return tuple(output), layout, {"detection": detection_names, "ratio": ratio_names}


def structural_signature(tracks: tuple[JoinedTrack, ...]) -> str:
    """Candidate/direction/prior signature deliberately excluding outcomes."""
    body = [{"session_id": track.session_id, "track_id": track.track_id,
             "candidate_ids": track.candidate_ids,
             "log_weights": track.log_weights.tolist(),
             "observations": [{"observation_id": row.observation_id,
                               "east": row.east.tolist()} for row in track.rows]}
            for track in tracks]
    return digest(json.dumps(body, sort_keys=True, separators=(",", ":")).encode())
