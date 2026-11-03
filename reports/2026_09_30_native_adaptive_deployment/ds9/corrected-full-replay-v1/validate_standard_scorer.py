#!/usr/bin/env python3
"""Evaluate native and reference LOC1 artifacts with the frozen public scorer."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DEPLOYMENT = HERE.parents[1]
REFERENCE = DEPLOYMENT / "tracking"
DEFAULT_ORACLE = Path("/var/tmp/leo-arm-realtime-publication/src")
TAUS = np.arange(-5.0, 6.0)
LIGHT_KM_S = 299_792.458
REFERENCE_RF_HZ = 11.2e9


@dataclass(frozen=True)
class Track:
    track_id: str
    observation_ids: tuple[str, ...]
    times: np.ndarray
    measured: np.ndarray
    training: np.ndarray


@dataclass(frozen=True)
class Fixture:
    sites: np.ndarray
    tracks: tuple[Track, ...]
    satellite_ids: np.ndarray
    states: np.ndarray
    knot_start: float
    knot_step: float


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite(values: np.ndarray, label: str) -> None:
    if not np.all(np.isfinite(values)):
        raise ValueError(f"non-finite {label}")


def validate_mask_and_weight(times: np.ndarray, mask: np.ndarray, weight: int) -> np.ndarray:
    if np.any((mask != 0) & (mask != 1)):
        raise ValueError("training mask is not binary")
    expected_weight = len(np.unique(np.floor(times).astype(np.int64)))
    if weight != expected_weight:
        raise ValueError("encoded track weight differs from scorer weight")
    training = mask.astype(bool)
    if not np.any(training) or np.all(training):
        raise ValueError("training and held-out observations are required")
    return training


def load_audit(path: Path) -> list[dict[str, object]]:
    tracks: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line in path.read_text().splitlines():
        fields = line.split("\t")
        if fields[0] == "TRACK":
            if len(fields) != 6:
                raise ValueError("invalid tracks audit header")
            current = {
                "track_id": fields[2],
                "declared": int(fields[5]),
                "observation_ids": [],
                "times": [],
                "measured": [],
                "training": [],
            }
            tracks.append(current)
        elif fields[0] == "POINT":
            if current is None or len(fields) != 6:
                raise ValueError("invalid tracks audit point")
            current["observation_ids"].append(fields[2])
            current["times"].append(float(fields[3]))
            current["measured"].append(float(fields[4]))
            current["training"].append(int(fields[5]))
        else:
            raise ValueError("unknown tracks audit row")
    for track in tracks:
        if track["declared"] != len(track["observation_ids"]):
            raise ValueError("tracks audit count mismatch")
    return tracks


def load_fixture(path: Path, audit_path: Path) -> Fixture:
    payload = path.read_bytes()
    if len(payload) < struct.calcsize("<5I2d"):
        raise ValueError("truncated LOC1 header")
    magic, satellite_count, knot_count, track_count, site_count, knot_start, knot_step = (
        struct.unpack_from("<5I2d", payload)
    )
    if (
        magic != 0x31434F4C
        or not 1 <= satellite_count <= 20_000
        or not 2 <= knot_count <= 2_000
        or not 1 <= track_count <= 128
        or not 1 <= site_count <= 128
        or not math.isfinite(knot_start)
        or not math.isfinite(knot_step)
        or knot_step <= 0
    ):
        raise ValueError("invalid LOC1 header")
    audit = load_audit(audit_path)
    if len(audit) != track_count:
        raise ValueError("LOC1/audit track count mismatch")
    offset = struct.calcsize("<5I2d")
    sites = np.frombuffer(payload, dtype="<f8", count=site_count * 6, offset=offset).copy()
    sites = sites.reshape(site_count, 6)
    offset += site_count * 6 * 8
    finite(sites, "site authority")
    tracks: list[Track] = []
    track_ids: set[str] = set()
    observation_ids: set[str] = set()
    for index in range(track_count):
        if offset + 8 > len(payload):
            raise ValueError("truncated LOC1 track header")
        observation_count, weight = struct.unpack_from("<2I", payload, offset)
        offset += 8
        if observation_count < 6 or weight == 0:
            raise ValueError("invalid LOC1 track dimensions")
        times = np.frombuffer(payload, dtype="<f8", count=observation_count, offset=offset).copy()
        offset += observation_count * 8
        measured = np.frombuffer(
            payload, dtype="<f8", count=observation_count, offset=offset
        ).copy()
        offset += observation_count * 8
        raw_training = np.frombuffer(
            payload, dtype="u1", count=observation_count, offset=offset
        ).copy()
        offset += observation_count
        finite(times, "track time")
        finite(measured, "track measurement")
        training = validate_mask_and_weight(times, raw_training, weight)
        row = audit[index]
        track_id = str(row["track_id"])
        row_ids = tuple(row["observation_ids"])
        if track_id in track_ids:
            raise ValueError("duplicate track identity")
        if len(set(row_ids)) != len(row_ids) or observation_ids.intersection(row_ids):
            raise ValueError("duplicate observation identity")
        track_ids.add(track_id)
        observation_ids.update(row_ids)
        if (
            tuple(row["times"]) != tuple(times)
            or tuple(row["measured"]) != tuple(measured)
            or tuple(bool(value) for value in row["training"]) != tuple(training)
        ):
            raise ValueError("LOC1/audit track values differ")
        tracks.append(
            Track(
                track_id,
                row_ids,
                times,
                measured,
                training,
            )
        )
    satellite_bytes = satellite_count * 4
    state_values = satellite_count * knot_count * 6
    if offset + satellite_bytes + state_values * 8 != len(payload):
        raise ValueError("invalid LOC1 tail size")
    satellite_ids = np.frombuffer(payload, dtype="<i4", count=satellite_count, offset=offset).copy()
    if len(set(int(value) for value in satellite_ids)) != satellite_count:
        raise ValueError("duplicate satellite identity")
    offset += satellite_bytes
    states = np.frombuffer(payload, dtype="<f8", count=state_values, offset=offset).copy()
    states = states.reshape(satellite_count, knot_count, 6)
    finite(states, "orbit state")
    return Fixture(sites, tuple(tracks), satellite_ids, states, knot_start, knot_step)


def interpolate(states: np.ndarray, coordinate: np.ndarray, step: float) -> tuple[np.ndarray, ...]:
    """Hermite-interpolate one candidate block at tau-by-observation coordinates."""
    if not np.all(np.isfinite(coordinate)):
        raise ValueError("non-finite interpolation coordinate")
    lower = np.floor(coordinate).astype(np.int64)
    if np.any(lower < 0) or np.any(coordinate > states.shape[1] - 1):
        raise ValueError("interpolation coordinate outside saved authority")
    lower = np.minimum(lower, states.shape[1] - 2)
    u = coordinate - lower
    u2 = u * u
    u3 = u2 * u
    a = states[:, lower, :]
    b = states[:, lower + 1, :]
    position = (
        (2 * u3 - 3 * u2 + 1)[None, :, :, None] * a[..., :3]
        + ((u3 - 2 * u2 + u) * step)[None, :, :, None] * a[..., 3:]
        + (-2 * u3 + 3 * u2)[None, :, :, None] * b[..., :3]
        + ((u3 - u2) * step)[None, :, :, None] * b[..., 3:]
    )
    velocity = (
        (
            (6 * u2 - 6 * u)[None, :, :, None] * a[..., :3]
            + (-6 * u2 + 6 * u)[None, :, :, None] * b[..., :3]
        )
        / step
        + (3 * u2 - 4 * u + 1)[None, :, :, None] * a[..., 3:]
        + (3 * u2 - 2 * u)[None, :, :, None] * b[..., 3:]
    )
    finite(position, "interpolated position")
    finite(velocity, "interpolated velocity")
    return position, velocity


def possible_satellites(
    states: np.ndarray,
    times: np.ndarray,
    receiver: np.ndarray,
    up: np.ndarray,
    knot_start: float,
    knot_step: float,
) -> np.ndarray:
    """Apply the saved-state scorer's conservative horizon prefilter."""
    lo = max(int(math.floor((times[0] + TAUS[0] - knot_start) / knot_step)), 0)
    hi = min(
        int(math.floor((times[-1] + TAUS[-1] - knot_start) / knot_step)),
        states.shape[1] - 2,
    )
    if hi < lo:
        return np.zeros(states.shape[0], dtype=bool)
    a = states[:, lo : hi + 1]
    b = states[:, lo + 1 : hi + 2]
    plane = float(np.sum(receiver * up))
    x = np.sum(a[..., :3] * up, axis=-1) - plane
    y = np.sum(b[..., :3] * up, axis=-1) - plane
    x_bound = x + knot_step * np.sum(a[..., 3:] * up, axis=-1) / 3.0
    y_bound = y - knot_step * np.sum(b[..., 3:] * up, axis=-1) / 3.0
    return np.any((x >= 0) | (y >= 0) | (x_bound >= 0) | (y_bound >= 0), axis=1)


def predictions(fixture: Fixture, site_index: int, prediction_type, block: int = 256):
    site = fixture.sites[site_index]
    receiver, up = site[:3], site[3:]
    for track in fixture.tracks:
        coordinate = (track.times[None, :] + TAUS[:, None] - fixture.knot_start) / fixture.knot_step
        yielded = False
        for begin in range(0, len(fixture.satellite_ids), block):
            stop = min(begin + block, len(fixture.satellite_ids))
            possible = possible_satellites(
                fixture.states[begin:stop],
                track.times,
                receiver,
                up,
                fixture.knot_start,
                fixture.knot_step,
            )
            if not np.any(possible):
                continue
            position, velocity = interpolate(
                fixture.states[begin:stop][possible], coordinate, fixture.knot_step
            )
            delta = position - receiver
            distance = np.sqrt(np.sum(delta * delta, axis=-1))
            if np.any(distance <= 0) or not np.all(np.isfinite(distance)):
                raise ValueError("invalid orbit range")
            visible = np.max(np.sum(delta * up, axis=-1), axis=(1, 2)) >= 0
            prediction = (
                -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * velocity, axis=-1) / distance
            )
            yield prediction_type(
                track.track_id,
                track.observation_ids,
                track.times,
                track.measured,
                track.training,
                fixture.satellite_ids[begin:stop][possible],
                TAUS,
                prediction,
                visible,
            )
            yielded = True
        if not yielded:
            yield prediction_type(
                track.track_id,
                track.observation_ids,
                track.times,
                track.measured,
                track.training,
                np.empty(0, dtype=np.int32),
                TAUS,
                np.empty((0, len(TAUS), len(track.times))),
                np.empty(0, dtype=bool),
            )


def compare_point(
    actual,
    expected: dict,
    fixture: Fixture,
    tolerance: float,
) -> dict[str, object]:
    if len(actual.tracks) != len(expected["tracks"]):
        raise ValueError("score track count differs")
    actual_by_id = {track.track_id: track for track in actual.tracks}
    if len(actual_by_id) != len(actual.tracks):
        raise ValueError("duplicate scorer track identity")
    maximum = 0.0
    for index, (track, right) in enumerate(zip(fixture.tracks, expected["tracks"], strict=True)):
        left = actual_by_id[track.track_id]
        if left.candidate_id is None or left.tau_s is None:
            raise ValueError(f"unmatched scorer track {index}")
        if int(left.candidate_id) != int(right["candidate_id"]) or left.tau_s != right["tau_s"]:
            raise ValueError(f"winner differs at track {index}")
        for field, attribute in (
            ("held_hz", "heldout_rms_hz"),
            ("fit_hz", "training_rms_hz"),
            ("offset_hz", "frequency_offset_hz"),
        ):
            observed = float(getattr(left, attribute))
            reference = float(right[field])
            if not math.isfinite(observed) or not math.isfinite(reference):
                raise ValueError(f"non-finite score at track {index}")
            delta = abs(observed - reference)
            maximum = max(maximum, delta)
            if delta > tolerance:
                raise ValueError(f"numeric score differs at track {index} field {field}: {delta}")
    aggregate = abs(float(actual.residual_rmse_hz) - float(expected["score_hz"]))
    if not math.isfinite(aggregate) or aggregate > tolerance:
        raise ValueError(f"aggregate score differs: {aggregate}")
    return {
        "tracks": len(actual.tracks),
        "satellite_and_tau_exact": len(actual.tracks),
        "maximum_absolute_track_field_delta_hz": maximum,
        "aggregate_score_hz": actual.residual_rmse_hz,
        "aggregate_score_delta_hz": aggregate,
    }


def evaluate_cell(label: str, fixture_path: Path, audit_path: Path, score_path: Path, scorer):
    fixture = load_fixture(fixture_path, audit_path)
    expected = json.loads(score_path.read_text())
    if len(expected["points"]) != len(fixture.sites):
        raise ValueError(f"{label} site count differs")
    points = []
    for index, expected_point in enumerate(expected["points"]):
        actual = scorer.score_point(
            0.0,
            0.0,
            predictions(fixture, index, scorer.AdaptiveTrackPrediction),
        )
        points.append(compare_point(actual, expected_point, fixture, 1e-6))
    return {
        "status": "pass",
        "loc1": str(fixture_path),
        "loc1_sha256": sha256(fixture_path),
        "tracks_audit": str(audit_path),
        "tracks_audit_sha256": sha256(audit_path),
        "expected_score": str(score_path),
        "expected_score_sha256": sha256(score_path),
        "sites": len(points),
        "points": points,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle-source", type=Path, default=DEFAULT_ORACLE)
    parser.add_argument("--output", type=Path, default=HERE / "standard-scorer-validation.json")
    parser.add_argument(
        "--reference-checkpoint",
        type=Path,
        default=HERE / "standard-scorer-reference-control.json",
    )
    args = parser.parse_args()
    sys.path.insert(0, str(args.oracle_source.resolve()))
    from leo.analysis import adaptive_tle_position as scorer

    started = time.monotonic()
    scorer_path = args.oracle_source / "leo" / "analysis" / "adaptive_tle_position.py"
    reference = evaluate_cell(
        "reference",
        REFERENCE / "native-e2.loc1",
        REFERENCE / "native-e2.loc1.tracks.tsv",
        REFERENCE / "native-e2-score.json",
        scorer,
    )
    reference_checkpoint = {
        "schema": "org.leo.corrected-native-standard-scorer-reference-control/v1",
        "status": "pass",
        "scorer_sha256": sha256(scorer_path),
        "reference": reference,
    }
    args.reference_checkpoint.write_text(
        json.dumps(reference_checkpoint, indent=2, sort_keys=True) + "\n"
    )
    native = evaluate_cell(
        "native",
        HERE / "full-public-c3-c4" / "native-e2.loc1",
        HERE / "full-public-c3-c4" / "native-e2.loc1.tracks.tsv",
        HERE / "full-public-c3-c4" / "location-score.json",
        scorer,
    )
    result = {
        "schema": "org.leo.corrected-native-standard-scorer-validator/v1",
        "status": "pass",
        "reference_control_executed_first": True,
        "scorer": str(scorer_path.resolve()),
        "scorer_sha256": sha256(scorer_path),
        "reference": reference,
        "fresh_native": native,
        "absolute_numeric_tolerance_hz": 1e-6,
        "elapsed_seconds": time.monotonic() - started,
        "scope": (
            "Frozen public score_point over each artifact's own IDs, masks, measurements, and "
            "saved orbit authority; no storage preparation, TLE propagation, search, or runtime "
            "dependency."
        ),
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
