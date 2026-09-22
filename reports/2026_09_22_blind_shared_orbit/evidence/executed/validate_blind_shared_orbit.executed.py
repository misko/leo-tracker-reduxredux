#!/usr/bin/env python3
"""Bounded truth-free multi-scan blind position/shared-orbit validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import tempfile
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize
from sgp4.api import SatrecArray

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.research.blind_shared_orbit import (
    BlindOrbitCandidateBatch,
    BlindOrbitEpisode,
    BlindSharedOrbitConfig,
    acquire_blind_orbit_episode,
    fit_retained_blind_shared_orbit,
    score_retained_blind_shared_orbit_transfer,
)
from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region
from leo.sky.frames import (
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets

FIT_SESSIONS = (
    "scan-hop-66cae29c39756be7",
    "scan-hop-fa8b9ec97ff14b97",
    "scan-hop-163ca5acea5cce6b",
    "scan-hop-7a31f1dfb82a20e3",
)
TRANSFER_SESSIONS = ("scan-hop-6c9417eeec67a616", "scan-hop-d04702aa7553ee39")
CATALOGUE_BATCH = 64
MAXIMUM_BRANCHES = 4
MINIMUM_BRANCH_SEPARATION_KM = 1_000.0
MAXIMUM_OUTER_EVALUATIONS = 160
TOTAL_BUDGET_S = 30 * 60
RSS_LIMIT_KIB = 2 * 1024 * 1024
REGION = Region(39.7392, -104.9903, 14_484.096, 14_484.096)
COARSE_RUNNER_SHA256 = "sha256:4acc357827f479e080f265cab6506d883c2013ea4e78f130c7df63ba2a251eb1"


def _digest(value: Any) -> str:
    payload = json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _atomic_create(path: Path, document: Any) -> None:
    payload = json.dumps(_jsonable(document), indent=2, sort_keys=True).encode() + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == payload:
            return
        raise FileExistsError(f"sealed output differs: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load_shards(root: Path):
    documents = {}
    for path in sorted(root.glob("*.json")):
        document = json.loads(path.read_text())
        session_id = document["session"]["session_id"]
        documents[session_id] = (document, _file_digest(path))
    expected = set(FIT_SESSIONS + TRANSFER_SESSIONS)
    if set(documents) != expected:
        raise ValueError("shard inventory differs from the sealed six-session cohort")
    return documents


def _load_catalogues(archive, documents):
    by_digest = {item.digest: item for item in archive.list_snapshots()}
    result = {}
    for document, _digest_value in documents.values():
        reference = document["catalogue_snapshot"]
        digest = reference["digest"]
        if digest in result:
            continue
        snapshot = by_digest.get(digest)
        if snapshot is None or snapshot.collected_utc_ns != reference["collected_utc_ns"]:
            raise ValueError("causal catalogue snapshot is unavailable or changed")
        payload, _excluded = exclude_labelled_starlink_debris(archive.read(snapshot))
        catalogue = parse_element_sets(payload)
        earliest = min(
            row["support_start_utc_ns"]
            for value, _ in documents.values()
            if value["catalogue_snapshot"]["digest"] == digest
            for track in value["tracks"]
            for row in track["observations"]
        )
        epoch = catalogue.element_epoch_utc_ns()
        indices = np.asarray(
            [
                index
                for index, (name, value) in enumerate(zip(catalogue.names, epoch, strict=True))
                if name.upper().startswith("STARLINK") and value < earliest
            ],
            dtype=np.int64,
        )
        if len(indices) != reference["full_retained_starlink_count"]:
            raise ValueError("causal full-catalogue membership differs from exported reference")
        result[digest] = {
            "catalogue": catalogue,
            "indices": indices,
            "epoch": np.asarray(epoch)[indices],
        }
    return result


def _tracks(documents, session_ids=FIT_SESSIONS):
    accepted, exclusions = [], []
    for session_id in session_ids:
        document = documents[session_id][0]
        for track in document["tracks"]:
            rows = track["observations"]
            if len(rows) < 4:
                exclusions.append(
                    {
                        "session_id": session_id,
                        "tracklet_id": track["tracklet_id"],
                        "reason": "fewer-than-four-observations",
                    }
                )
                continue
            count = len(rows)
            training_count = min(count - 2, max(2, math.ceil(0.6 * count)))
            training = np.arange(count) < training_count
            accepted.append(
                {
                    "episode_id": session_id + ":" + track["tracklet_id"],
                    "session_id": session_id,
                    "snapshot_digest": document["catalogue_snapshot"]["digest"],
                    "utc_ns": np.asarray(
                        [row["support_center_utc_ns"] for row in rows], dtype=np.int64
                    ),
                    "observed_hz": np.asarray(
                        [row["measured_cfo_hz"] for row in rows], dtype=float
                    ),
                    "segment": np.zeros(count, dtype=np.int64),
                    "training": training,
                }
            )
    return tuple(accepted), tuple(exclusions)


def _propagate(catalogue, indices, utc_ns, phase_s):
    satellites = SatrecArray([catalogue.satellites[int(index)] for index in indices])
    shifted = np.asarray(utc_ns) + np.rint(np.asarray(phase_s) * 1e9).astype(np.int64)
    jd, fraction = julian_day_from_utc_ns(shifted)
    errors, position, velocity = satellites.sgp4(jd, fraction)
    receive_jd, receive_fraction = julian_day_from_utc_ns(utc_ns)
    angle = greenwich_mean_sidereal_time_rad(receive_jd, receive_fraction)
    position, velocity = teme_to_ecef(position, velocity, angle)
    usable = (
        np.all(errors == 0, axis=1)
        & np.all(np.isfinite(position), axis=(1, 2))
        & np.all(np.isfinite(velocity), axis=(1, 2))
    )
    return usable, np.nan_to_num(position), np.nan_to_num(velocity)


def _doppler(receiver, position, velocity):
    delta = position - receiver[None, None, :]
    return (
        -REFERENCE_RF_HZ
        / LIGHT_KM_S
        * np.sum(delta * velocity, axis=-1)
        / np.linalg.norm(delta, axis=-1)
    )


def _candidate_batch(track, info, receiver, receiver_up, selected):
    catalogue = info["catalogue"]
    supports = []
    usable = np.ones(len(selected), dtype=bool)
    nominal_position = None
    for phase in (-2.0, -1.0, 0.0, 1.0, 2.0):
        good, position, velocity = _propagate(catalogue, selected, track["utc_ns"], phase)
        usable &= good
        supports.append(_doppler(receiver, position, velocity))
        if phase == 0.0:
            nominal_position = position
    delta = nominal_position - receiver[None, None, :]
    elevation_sine = np.sum(delta * receiver_up[None, None, :], axis=-1) / np.linalg.norm(
        delta, axis=-1
    )
    usable &= np.min(elevation_sine[:, track["training"]], axis=1) >= math.sin(math.radians(-1.0))
    offset_by_index = {int(index): offset for offset, index in enumerate(info["indices"])}
    epoch = np.asarray([info["epoch"][offset_by_index[int(index)]] for index in selected])
    age = (track["utc_ns"][None, :] - epoch[:, None]) / 3.6e12
    return BlindOrbitCandidateBatch(
        norad=np.asarray(catalogue.satellite_numbers)[selected],
        nominal_hz=supports[2],
        phase_minus1_hz=supports[1],
        phase_plus1_hz=supports[3],
        phase_minus2_hz=supports[0],
        phase_plus2_hz=supports[4],
        age_h=age,
        visible=usable,
    )


def _episodes(
    tracks, catalogues, latitude_deg, longitude_deg, branch_id, tokens=None, deadline=None
):
    receiver = geodetic_to_ecef_km(latitude_deg, longitude_deg, 0.0)
    lat_rad, lon_rad = np.deg2rad([latitude_deg, longitude_deg])
    receiver_up = np.asarray(
        [
            math.cos(lat_rad) * math.cos(lon_rad),
            math.cos(lat_rad) * math.sin(lon_rad),
            math.sin(lat_rad),
        ]
    )
    episodes = []
    contexts = {}
    token_by_episode = {} if tokens is None else {token.episode_id: token for token in tokens}
    for track in tracks:
        info = catalogues[track["snapshot_digest"]]
        catalogue, indices = info["catalogue"], info["indices"]
        token = token_by_episode.get(track["episode_id"])
        if token is None:

            def batches(
                track=track, info=info, receiver=receiver, receiver_up=receiver_up, indices=indices
            ):
                for begin in range(0, len(indices), CATALOGUE_BATCH):
                    if deadline is not None and time.monotonic() >= deadline:
                        raise TimeoutError(
                            "validation wall-time budget exhausted during catalogue scan"
                        )
                    if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > RSS_LIMIT_KIB:
                        raise MemoryError("validation exceeded the 2 GiB RSS limit")
                    yield _candidate_batch(
                        track, info, receiver, receiver_up, indices[begin : begin + CATALOGUE_BATCH]
                    )

            catalogue_size = len(indices)
        else:
            numbers = np.asarray(catalogue.satellite_numbers)[indices]
            lookup = {
                int(number): int(index) for number, index in zip(numbers, indices, strict=True)
            }
            selected = np.asarray(
                [lookup[number] for number in token.retained_norad], dtype=np.int64
            )
            batches = (_candidate_batch(track, info, receiver, receiver_up, selected),)
            catalogue_size = token.full_catalogue_size
        episodes.append(
            BlindOrbitEpisode(
                episode_id=track["episode_id"],
                observed_hz=track["observed_hz"],
                segment=track["segment"],
                training=track["training"],
                catalogue_size=catalogue_size,
                batches=batches() if callable(batches) else batches,
                spatial_branch_id=branch_id,
            )
        )
        contexts[track["episode_id"]] = (receiver, catalogue, indices, track["utc_ns"])
    return tuple(episodes), contexts


class _ExactReplay:
    def __init__(self, contexts):
        self.contexts = contexts

    def predict_hz(self, episode_id, norad, phase_offset_s):
        receiver, catalogue, indices, utc_ns = self.contexts[episode_id]
        numbers = np.asarray(catalogue.satellite_numbers)[indices]
        found = np.flatnonzero(numbers == norad)
        if len(found) != 1:
            raise ValueError("exact replay NORAD is absent or duplicated")
        selected = indices[found]
        usable, position, velocity = _propagate(catalogue, selected, utc_ns, phase_offset_s)
        if not bool(usable[0]):
            raise ValueError("exact replay propagation failed")
        return _doppler(receiver, position, velocity)[0]


def _separated_branches(coarse):
    selected = []
    grid = REGION.grid(float(coarse["spacing_km"]))
    for item in coarse["alternatives"]:
        ecef = geodetic_to_ecef_km(item["latitude_deg"], item["longitude_deg"], 0.0)
        if all(
            np.linalg.norm(ecef - prior[1]) >= MINIMUM_BRANCH_SEPARATION_KM for prior in selected
        ):
            enriched = dict(item)
            index = int(item["grid_index"])
            enriched.update(
                east_km=float(grid.east_km[index]), north_km=float(grid.north_km[index])
            )
            selected.append((enriched, ecef))
        if len(selected) == MAXIMUM_BRANCHES:
            break
    return tuple(item for item, _ecef in selected)


def _load_coarse_result(path, documents):
    coarse = json.loads(path.read_text())
    configuration_path = path.parent / "configuration.json"
    configuration = json.loads(configuration_path.read_text())
    source_path = Path(__file__).with_name("run_blind_shared_orbit_coarse.py")
    expected_shards = sorted(documents[session_id][1] for session_id in FIT_SESSIONS)
    if (
        _file_digest(source_path) != COARSE_RUNNER_SHA256
        or coarse.get("track_count") != 205
        or coarse.get("observation_count") != 4895
        or coarse.get("spacing_km") != 1000.0
        or sorted(configuration.get("source_shard_digests", ())) != expected_shards
        or configuration.get("truth_accessed") is not False
    ):
        raise ValueError("coarse acquisition provenance or chronological protocol differs")
    return coarse, configuration_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shards", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, required=True)
    parser.add_argument("--coarse-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from leo.operations.tle_archive import TleArchiveReader

    started = time.monotonic()
    documents = _load_shards(args.shards)
    tracks, exclusions = _tracks(documents)
    transfer_tracks, transfer_exclusions = _tracks(documents, TRANSFER_SESSIONS)
    catalogues = _load_catalogues(TleArchiveReader(args.tle_root), documents)
    coarse, coarse_configuration_path = _load_coarse_result(args.coarse_result, documents)
    branches = _separated_branches(coarse)
    if len(branches) < 2:
        raise ValueError("coarse acquisition did not retain multiple separated branches")
    config = BlindSharedOrbitConfig(refinement_candidates_per_episode=8)
    evaluations = []
    deadline = started + TOTAL_BUDGET_S

    def evaluate(east, north, branch_id, tokens=None, exact=False, fit_config=None):
        selected_config = config if fit_config is None else fit_config
        if time.monotonic() >= deadline:
            raise TimeoutError("validation wall-time budget exhausted")
        point = REGION.points(np.asarray([east]), np.asarray([north]))
        latitude, longitude = float(point.latitude_deg[0]), float(point.longitude_deg[0])
        episodes, contexts = _episodes(
            tracks, catalogues, latitude, longitude, branch_id, tokens=tokens, deadline=deadline
        )
        if tokens is None:
            tokens = tuple(
                acquire_blind_orbit_episode(episode, config=config) for episode in episodes
            )
            episodes, contexts = _episodes(
                tracks, catalogues, latitude, longitude, branch_id, tokens=tokens, deadline=deadline
            )
            full_score = -sum(token.full_catalogue_training_log_evidence for token in tokens)
        else:
            full_score = None
        result = fit_retained_blind_shared_orbit(
            episodes,
            tokens,
            config=selected_config,
            exact_prediction=_ExactReplay(contexts) if exact else None,
        )
        score = result["outer_position_scores"]
        row = {
            "branch_id": branch_id,
            "east_km": float(east),
            "north_km": float(north),
            "latitude_deg": float(latitude),
            "longitude_deg": float(longitude),
            "full_catalogue_nominal_negative_log_evidence": full_score,
            "matched_nominal_negative_log_posterior": score[
                "matched_shortlist_nominal_negative_log_posterior"
            ],
            "matched_shared_negative_log_posterior": score[
                "matched_shortlist_shared_negative_log_posterior"
            ],
            "runtime_seconds": time.monotonic() - started,
            "result": result,
            "acquisition_tokens": tokens,
        }
        evaluations.append(row)
        return row

    initial = [
        evaluate(item["east_km"], item["north_km"], f"coarse-{rank + 1}")
        for rank, item in enumerate(branches)
    ]
    leader = min(initial, key=lambda row: row["full_catalogue_nominal_negative_log_evidence"])
    calls = 0

    nominal_config = replace(config, optimize_shared_rates=False)

    def objective(value, key, label, fit_config):
        nonlocal calls
        calls += 1
        east = float(np.clip(value[0], -REGION.width_km / 2, REGION.width_km / 2))
        north = float(np.clip(value[1], -REGION.height_km / 2, REGION.height_km / 2))
        row = evaluate(
            east,
            north,
            label,
            tokens=leader["acquisition_tokens"],
            fit_config=fit_config,
        )
        return row[key]

    start = np.asarray([leader["east_km"], leader["north_km"]])
    simplex = np.asarray([start, start + [100.0, 0.0], start + [0.0, 100.0]])
    simplex[:, 0] = np.clip(simplex[:, 0], -REGION.width_km / 2, REGION.width_km / 2)
    simplex[:, 1] = np.clip(simplex[:, 1], -REGION.height_km / 2, REGION.height_km / 2)
    bounds = [
        (-REGION.width_km / 2, REGION.width_km / 2),
        (-REGION.height_km / 2, REGION.height_km / 2),
    ]

    shared_answer = minimize(
        lambda value: objective(
            value, "matched_shared_negative_log_posterior", "shared-local", config
        ),
        start,
        method="Nelder-Mead",
        bounds=bounds,
        options={
            "maxfev": MAXIMUM_OUTER_EVALUATIONS // 2,
            "xatol": 0.05,
            "fatol": 0.1,
            "initial_simplex": simplex,
        },
    )
    nominal_answer = minimize(
        lambda value: objective(
            value,
            "matched_nominal_negative_log_posterior",
            "nominal-local",
            nominal_config,
        ),
        start,
        method="Nelder-Mead",
        bounds=bounds,
        options={
            "maxfev": MAXIMUM_OUTER_EVALUATIONS // 2,
            "xatol": 0.05,
            "fatol": 0.1,
            "initial_simplex": simplex,
        },
    )
    final = evaluate(
        float(shared_answer.x[0]),
        float(shared_answer.x[1]),
        "shared-final",
        tokens=leader["acquisition_tokens"],
        exact=True,
    )
    nominal = min(
        (row for row in evaluations if row["branch_id"] == "nominal-local"),
        key=lambda row: row["matched_nominal_negative_log_posterior"],
    )
    transfer_episodes, transfer_contexts = _episodes(
        transfer_tracks,
        catalogues,
        final["latitude_deg"],
        final["longitude_deg"],
        "transfer-frozen-shared-position",
        deadline=deadline,
    )
    transfer_tokens = tuple(
        acquire_blind_orbit_episode(episode, config=config) for episode in transfer_episodes
    )
    transfer_episodes, transfer_contexts = _episodes(
        transfer_tracks,
        catalogues,
        final["latitude_deg"],
        final["longitude_deg"],
        "transfer-frozen-shared-position",
        tokens=transfer_tokens,
        deadline=deadline,
    )
    frozen_rates = {
        int(norad): float(rate) for norad, rate in final["result"]["rate_corrections_s_h"].items()
    }
    for token in transfer_tokens:
        for norad in token.retained_norad:
            frozen_rates.setdefault(int(norad), 0.0)
    transfer_result = score_retained_blind_shared_orbit_transfer(
        transfer_episodes,
        transfer_tokens,
        frozen_rates,
        config=config,
        exact_prediction=_ExactReplay(transfer_contexts),
    )
    result = {
        "schema": "blind-shared-orbit-six-scan-validation/v1",
        "state": (
            "complete" if shared_answer.success and nominal_answer.success else "insufficient"
        ),
        "truth_accessed": False,
        "known_position_used": False,
        "site_conditioned_candidates_used": False,
        "protocol": {
            "fit_sessions": FIT_SESSIONS,
            "transfer_sessions": TRANSFER_SESSIONS,
            "partition": "contiguous-first-60-percent-training-final-40-percent-heldout-per-track",
            "coarse_spacing_km": coarse["spacing_km"],
            "maximum_branches": MAXIMUM_BRANCHES,
            "minimum_branch_separation_km": MINIMUM_BRANCH_SEPARATION_KM,
            "maximum_outer_evaluations": MAXIMUM_OUTER_EVALUATIONS,
            "total_budget_seconds": TOTAL_BUDGET_S,
            "global_resolution_status": "insufficient-no-whole-region-50km-search",
            "configuration": asdict(config),
        },
        "provenance": {
            "runner_sha256": _file_digest(Path(__file__)),
            "coarse_result_sha256": _file_digest(args.coarse_result),
            "coarse_configuration_sha256": _file_digest(coarse_configuration_path),
            "coarse_runner_sha256": COARSE_RUNNER_SHA256,
            "shards": {sid: digest for sid, (_document, digest) in documents.items()},
            "catalogue_snapshot_digests": sorted(catalogues),
        },
        "accounting": {
            "fit_track_count": len(tracks),
            "fit_observation_count": sum(len(track["utc_ns"]) for track in tracks),
            "excluded_track_count": len(exclusions),
            "transfer_track_count": len(transfer_tracks),
            "transfer_observation_count": sum(len(track["utc_ns"]) for track in transfer_tracks),
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        },
        "coarse_branches": branches,
        "outer_evaluations": [
            {
                key: value
                for key, value in row.items()
                if key not in {"result", "acquisition_tokens"}
            }
            for row in evaluations
        ],
        "selected_nominal": {
            key: value
            for key, value in nominal.items()
            if key not in {"result", "acquisition_tokens"}
        },
        "selected_shared": {
            key: value
            for key, value in final.items()
            if key not in {"result", "acquisition_tokens"}
        },
        "selected_shared_result": final["result"],
        "selected_nominal_result": nominal["result"],
        "outer_optimizer": {
            "shared_success": bool(shared_answer.success),
            "shared_message": str(shared_answer.message),
            "nominal_success": bool(nominal_answer.success),
            "nominal_message": str(nominal_answer.message),
            "evaluations": calls,
        },
        "transfer_evaluation": transfer_result,
        "exclusions": {"fit": exclusions, "transfer": transfer_exclusions},
        "limitations": (
            "corrected support is top-eight per episode and uncertified",
            "nominal-state visibility is frozen during correction",
            "global 50 km acquisition was excluded by the declared resource budget",
            "local refinement freezes top-eight identities acquired at the 1000 km basin origin",
            "single archived six-scan cohort is not an independent accuracy validation",
        ),
        "runtime_seconds": time.monotonic() - started,
    }
    result = _jsonable(result)
    result["seal_sha256"] = _digest(result)
    _atomic_create(args.output, result)
    print(
        json.dumps(
            {
                "state": result["state"],
                "output": str(args.output),
                "seal_sha256": result["seal_sha256"],
                "runtime_seconds": result["runtime_seconds"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
