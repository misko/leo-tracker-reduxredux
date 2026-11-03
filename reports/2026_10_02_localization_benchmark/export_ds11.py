"""Export frozen single-capture inputs for the localization benchmark."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import inspect
import json
import math
import os
import signal
import tempfile
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SELECTION_PATH = ROOT / "selection.json"
DS11_MANIFEST_PATH = ROOT.parent / "2026_09_30_ds11_post_ds10" / "local" / "manifest.json"
COMMON_PATH = ROOT.parent / "2026_10_02_coherent_localization" / "common.py"
FULL_CURVE_ROOT = ROOT.parent / "2026_10_02_full_curve_glrt"
SHARED_RX_ROOT = ROOT.parent / "2026_10_02_shared_rx_position"
DEFAULT_API_BASE = "http://127.0.0.1:8090/api/v1/scanner/tracking"
DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
DEFAULT_TLE_ROOT = Path("/var/lib/leo/tle")
PRIOR_LATITUDE_DEG = 38.5816
PRIOR_LONGITUDE_DEG = -121.4944
REFERENCE_RF_HZ = 11.2e9
ALIAS_SPACING_HZ = 1.0 / 4.4e-6
CANDIDATE_COUNT = 64
MAXIMUM_BATCH = 4
SCAN_TIMEOUT_S = 60


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(payload)


def frozen_capture_entry(session_id: str, manifest: dict) -> dict:
    if manifest.get("dataset_id") != "DS11":
        raise ValueError("Frozen population manifest is not DS11")
    matches = [row for row in manifest["captures"] if row["session_id"] == session_id]
    if len(matches) != 1:
        raise ValueError(f"Frozen DS11 manifest does not contain exactly one {session_id}")
    return matches[0]


def geometry_nodes(maximum_observation_time_s: float) -> np.ndarray:
    if not math.isfinite(maximum_observation_time_s):
        raise ValueError("maximum observation time must be finite")
    stop = max(311.0, math.ceil((maximum_observation_time_s + 11.0) * 4.0) / 4.0)
    return np.arange(-11.0, stop + 0.125, 0.25, dtype=np.float64)


def ordered_review_candidates(reviews: list[dict]) -> tuple[list[int], dict[int, dict]]:
    statistics: dict[int, dict] = defaultdict(
        lambda: {"first_support": 0, "first_count": 0, "support": 0, "count": 0, "best_rank": 10**9}
    )
    for review in reviews:
        support = int(review["observation_count"])
        candidates = sorted(
            review["candidates"], key=lambda item: (item["rank"], item["catalog_number"])
        )
        if not candidates:
            continue
        first_rank = candidates[0]["rank"]
        for candidate in candidates:
            number = int(candidate["catalog_number"])
            rank = int(candidate["rank"])
            row = statistics[number]
            row["support"] += support
            row["count"] += 1
            row["best_rank"] = min(row["best_rank"], rank)
            if rank == first_rank:
                row["first_support"] += support
                row["first_count"] += 1
    first = sorted(
        (number for number, row in statistics.items() if row["first_count"]),
        key=lambda number: (
            -statistics[number]["first_support"],
            -statistics[number]["first_count"],
            number,
        ),
    )
    first_set = set(first)
    remaining = sorted(
        (number for number in statistics if number not in first_set),
        key=lambda number: (
            statistics[number]["best_rank"],
            -statistics[number]["support"],
            -statistics[number]["count"],
            number,
        ),
    )
    return [*first, *remaining], {number: dict(row) for number, row in statistics.items()}


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values, kind="stable")
    ordered_values = np.asarray(values, dtype=float)[order]
    ordered_weights = np.asarray(weights, dtype=float)[order]
    if (
        not len(ordered_values)
        or np.any(ordered_weights <= 0)
        or not np.all(np.isfinite(ordered_values))
    ):
        raise ValueError("weighted median requires finite values and positive weights")
    threshold = ordered_weights.sum() / 2.0
    return float(
        ordered_values[np.searchsorted(np.cumsum(ordered_weights), threshold, side="left")]
    )


def conditional_initial(
    product: dict, candidate_count: int = CANDIDATE_COUNT
) -> tuple[np.ndarray, dict]:
    tracks = {track["tracklet_id"]: track for track in product["tracklets"]}
    by_receiver: dict[int, list[tuple[float, int]]] = defaultdict(list)
    for review in product["track_reviews"]:
        if not review["candidates"]:
            continue
        candidate = min(
            review["candidates"], key=lambda item: (item["rank"], item["catalog_number"])
        )
        track = tracks[review["tracklet_id"]]
        rf_hz = float(track["actual_rf_hz"])
        spacing = ALIAS_SPACING_HZ * REFERENCE_RF_HZ / rf_hz
        raw = float(candidate["fitted_offset_hz"])
        branch = math.floor(raw / spacing + 0.5)
        folded_normalized = raw - branch * spacing
        folded_actual = folded_normalized * rf_hz / REFERENCE_RF_HZ
        by_receiver[int(track["receiver_id"])].append(
            (folded_actual, int(review["observation_count"]))
        )
    initial = np.zeros(6 + candidate_count, dtype=np.float64)
    receipt = {
        "position": "Sacramento prior encoded as east_km=0,north_km=0; not reference truth",
        "receiver_offset": (
            "support-weighted median of alias-folded persisted rank-1 known-site "
            "candidate offsets, "
            "converted back to each track's actual RF; initialization only"
        ),
        "receiver_slope_hz_s": 0.0,
        "conditional_on_known_site_candidate_reviews": True,
        "receivers": {},
    }
    for receiver in (0, 1):
        rows = by_receiver.get(receiver, [])
        if rows:
            values = np.asarray([row[0] for row in rows])
            weights = np.asarray([row[1] for row in rows])
            initial[2 + 2 * receiver] = weighted_median(values, weights)
            receipt["receivers"][str(receiver)] = {
                "available": True,
                "track_count": len(rows),
                "intercept_hz": initial[2 + 2 * receiver],
            }
        else:
            receipt["receivers"][str(receiver)] = {
                "available": False,
                "track_count": 0,
                "intercept_hz": 0.0,
            }
    return initial, receipt


def track_rows(candidates, trajectory, reviews: list[dict]) -> tuple[list[dict], dict]:
    row_by_id = {candidate.candidate_id: index for index, candidate in enumerate(candidates)}
    if len(row_by_id) != len(candidates):
        raise ValueError("Projected candidate IDs are not unique")
    tracklet_by_id = {track.tracklet_id: track for track in trajectory.tracklets}
    output = []
    mapped = []
    for review in reviews:
        track_id = review["tracklet_id"]
        if track_id not in tracklet_by_id:
            raise ValueError(f"Persisted review track is absent from reconstruction: {track_id}")
        tracklet = tracklet_by_id[track_id]
        rows = sorted(
            (row_by_id[point.candidate_id] for point in tracklet.points),
            key=lambda index: candidates[index].support_center_utc_ns,
        )
        if len(rows) != int(review["observation_count"]):
            raise ValueError(f"Persisted review count differs for track {track_id}")
        lane = tracklet.lane_key
        output.append(
            {
                "track_id": track_id,
                "rows": rows,
                "candidate_indices": list(range(CANDIDATE_COUNT)),
                "receiver": int(lane[2]),
                "channel": int(lane[0]),
            }
        )
        mapped.extend(rows)
    return output, {
        "policy": "public reconstructed tracklet point candidate_id mapped to projected raw row",
        "track_count": len(output),
        "track_observations": len(mapped),
        "unique_raw_rows": len(set(mapped)),
    }


def raw_arrays(candidates, origin_utc_ns: int) -> tuple[dict[str, np.ndarray], dict]:
    groups = sorted({candidate.source_group_id for candidate in candidates})
    group_index = {group_id: index for index, group_id in enumerate(groups)}
    arrays = {
        "times": np.asarray(
            [(candidate.support_center_utc_ns - origin_utc_ns) / 1e9 for candidate in candidates],
            dtype=np.float64,
        ),
        "measured": np.asarray([candidate.measured_cfo_hz for candidate in candidates]),
        "rf": np.asarray([candidate.actual_rf_hz for candidate in candidates]),
        "receiver": np.asarray([candidate.receiver_id for candidate in candidates], dtype=np.int64),
        "channel": np.asarray([candidate.channel for candidate in candidates], dtype=np.int64),
        "group": np.asarray(
            [group_index[candidate.source_group_id] for candidate in candidates], dtype=np.int64
        ),
        "margin": np.asarray([candidate.margin for candidate in candidates]),
    }
    receipt = {
        "projected_candidate_count": len(candidates),
        "source_group_count": len(groups),
        "candidate_ids_sha256": canonical_sha256(
            [candidate.candidate_id for candidate in candidates]
        ),
        "source_group_ids_sha256": canonical_sha256(groups),
        "scope": (
            "all stored gate-passing nonoverlapping GLRT projections; "
            "no cap or decimation; no IQ"
        ),
    }
    return arrays, receipt


def fetch_tracking(api_base: str, session_id: str) -> tuple[dict, dict]:
    endpoint = f"{api_base.rstrip('/')}/{session_id}"
    with urllib.request.urlopen(endpoint, timeout=10) as response:
        payload = response.read()
    document = json.loads(payload)
    if document.get("session_id") != session_id or document.get("state") != "complete":
        raise ValueError(f"Persisted tracking is not complete for {session_id}")
    product = document.get("product")
    if not product or product.get("session_id") != session_id:
        raise ValueError(f"Persisted tracking product is absent for {session_id}")
    return product, {"endpoint": endpoint, "sha256": sha256_bytes(payload)}


def runtime_source_artifacts(objects) -> list[dict]:
    paths = sorted({Path(inspect.getfile(value)).resolve() for value in objects})
    return [{"path": str(path), "sha256": sha256_file(path)} for path in paths]


def _observer_geometry(latitude_deg: float, longitude_deg: float):
    from leo.sky.frames import geodetic_to_ecef_km

    receiver = geodetic_to_ecef_km(latitude_deg, longitude_deg, 0.0)
    latitude, longitude = np.deg2rad([latitude_deg, longitude_deg])
    up = np.asarray(
        [
            np.cos(latitude) * np.cos(longitude),
            np.cos(latitude) * np.sin(longitude),
            np.sin(latitude),
        ]
    )
    return receiver, up


def candidate_states(catalogue, reviews: list[dict], origin_utc_ns: int, nodes: np.ndarray):
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states

    numbers = np.asarray(catalogue.satellite_numbers, dtype=np.int64)
    starlink_indices = np.asarray(
        [
            index
            for index, name in enumerate(catalogue.names)
            if name.upper().startswith("STARLINK")
        ],
        dtype=int,
    )
    receiver, up = _observer_geometry(PRIOR_LATITUDE_DEG, PRIOR_LONGITUDE_DEG)
    coarse_nodes = np.linspace(nodes[0], nodes[-1], 33)
    visible: list[tuple[float, int]] = []
    valid_indices: set[int] = set()
    for begin in range(0, len(starlink_indices), 256):
        position, _velocity, valid = propagate_candidate_states(
            catalogue,
            starlink_indices[begin : begin + 256],
            origin_utc_ns,
            coarse_nodes,
            np.asarray([0.0]),
        )
        position = position[:, 0]
        delta = position - receiver
        elevation_sine = np.sum(delta * up, axis=-1) / np.linalg.norm(delta, axis=-1)
        maximum = np.max(elevation_sine, axis=1)
        for local, catalogue_index in enumerate(valid):
            index = int(catalogue_index)
            valid_indices.add(index)
            if maximum[local] >= 0.0:
                visible.append((float(maximum[local]), index))
    catalogue_index = {int(number): index for index, number in enumerate(numbers)}
    review_numbers, statistics = ordered_review_candidates(reviews)
    prioritized = [
        catalogue_index[number]
        for number in review_numbers
        if number in catalogue_index and catalogue_index[number] in valid_indices
    ]
    visible.sort(key=lambda item: (-item[0], int(numbers[item[1]])))
    pool = list(dict.fromkeys([*prioritized, *(index for _height, index in visible)]))
    selected_numbers: list[int] = []
    selected_position: list[np.ndarray] = []
    selected_velocity: list[np.ndarray] = []
    for begin in range(0, len(pool), 128):
        position, velocity, valid = propagate_candidate_states(
            catalogue,
            pool[begin : begin + 128],
            origin_utc_ns,
            nodes,
            np.asarray([0.0]),
        )
        for local, index in enumerate(valid):
            selected_numbers.append(int(numbers[int(index)]))
            selected_position.append(position[local, 0])
            selected_velocity.append(velocity[local, 0])
            if len(selected_numbers) == CANDIDATE_COUNT:
                break
        if len(selected_numbers) == CANDIDATE_COUNT:
            break
    if len(selected_numbers) != CANDIDATE_COUNT:
        raise ValueError(
            f"Only {len(selected_numbers)} fully propagatable candidates were available"
        )
    review_selected = [number for number in selected_numbers if number in statistics]
    receipt = {
        "count": CANDIDATE_COUNT,
        "policy": (
            "persisted review first-ranked catalogue numbers by total track support, "
            "then remaining review candidates by rank/support, then response-blind "
            "Sacramento-visible Starlink fill"
        ),
        "conditional_on_known_site_candidate_reviews": True,
        "reference_truth_used_for_order_or_fill": False,
        "review_candidate_count": len(review_selected),
        "visible_fill_count": CANDIDATE_COUNT - len(review_selected),
        "prior_site": {
            "label": "Sacramento initialization prior",
            "latitude_deg": PRIOR_LATITUDE_DEG,
            "longitude_deg": PRIOR_LONGITUDE_DEG,
        },
    }
    return (
        np.asarray(selected_numbers, dtype=np.int64),
        np.asarray(selected_position, dtype=np.float64),
        np.asarray(selected_velocity, dtype=np.float64),
        receipt,
    )


def _snapshot(reader, product: dict, origin_utc_ns: int):
    expected = product["original_tle_snapshot"]
    matches = [
        snapshot
        for snapshot in reader.list_snapshots(expected["provider"])
        if snapshot.digest == expected["digest"]
        and snapshot.collected_utc_ns == int(expected["collected_utc_ns"])
    ]
    if len(matches) != 1 or matches[0].collected_utc_ns >= origin_utc_ns:
        raise ValueError("Persisted review does not bind one causal archived TLE snapshot")
    return matches[0]


def _write_bundle(directory: Path, arrays: dict, manifest: dict, evaluation: dict) -> None:
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{directory.name}-", dir=directory.parent
    ) as temporary:
        staging = Path(temporary)
        archive_path = staging / "bundle.npz"
        np.savez_compressed(archive_path, **arrays)
        manifest["artifacts"]["bundle_npz_sha256"] = sha256_file(archive_path)
        (staging / "bundle.json").write_text(json.dumps(manifest, indent=2) + "\n")
        evaluation["bundle_npz_sha256"] = manifest["artifacts"]["bundle_npz_sha256"]
        (staging / "evaluation.json").write_text(json.dumps(evaluation, indent=2) + "\n")
        directory.mkdir(parents=True, exist_ok=True)
        for name in ("bundle.npz", "bundle.json", "evaluation.json"):
            os.replace(staging / name, directory / name)


def export_ds11(
    session_id: str,
    *,
    output_root: Path,
    api_base: str,
    bulk_root: Path,
    tle_root: Path,
) -> dict:
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets

    product, api_artifact = fetch_tracking(api_base, session_id)
    selection_bytes = SELECTION_PATH.read_bytes()
    selection = json.loads(selection_bytes)
    manifest_bytes = DS11_MANIFEST_PATH.read_bytes()
    dataset_manifest = json.loads(manifest_bytes)
    if sha256_bytes(manifest_bytes) != selection["manifest_sha256"]:
        raise ValueError("Frozen selection does not bind the current DS11 population manifest")
    capture_entry = frozen_capture_entry(session_id, dataset_manifest)
    store = ScannerTrackingInputStore(bulk_root)
    try:
        source = store.load(session_id)
    finally:
        store.close()
    if source.input_manifest_sha256 != product["input_manifest_sha256"]:
        raise ValueError("Capture manifest differs from persisted tracking")
    if source.input_manifest_sha256 != capture_entry["manifest_sha256"]:
        raise ValueError("Scanner source input manifest differs from frozen DS11 capture manifest")
    if source.analysis_manifest_sha256 != product["analysis_manifest_sha256"]:
        raise ValueError("Analysis manifest differs from persisted tracking")
    if source.capture_start_utc_ns != int(capture_entry["capture_start_utc_ns"]):
        raise ValueError("Scanner source start differs from frozen DS11 capture window")
    if source.sample_rate_hz != int(capture_entry["sample_rate_hz"]):
        raise ValueError("Scanner source sample rate differs from frozen DS11 capture entry")
    if source.radio_id != capture_entry["radio_id"]:
        raise ValueError("Scanner source radio differs from frozen DS11 capture entry")
    origin = source.timing.first_sample_estimate_utc_ns
    candidates = project_scanner_candidates(source)
    if len(candidates) != int(product["projected_candidate_count"]):
        raise ValueError("Projected candidate count differs from persisted tracking")
    config = PersistentHopTrajectoryConfig()
    trajectory = reconstruct_persistent_hop_trajectories(candidates, config=config)
    tracks, mapping = track_rows(candidates, trajectory, product["track_reviews"])
    arrays, raw_receipt = raw_arrays(candidates, origin)
    nodes = geometry_nodes(float(np.max(arrays["times"])))
    archive = TleArchiveReader(tle_root)
    snapshot = _snapshot(archive, product, origin)
    payload, exclusions = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    numbers, position, velocity, candidate_receipt = candidate_states(
        catalogue, product["track_reviews"], origin, nodes
    )
    initial, initial_receipt = conditional_initial(product)
    arrays.update(
        nodes=nodes,
        position=position,
        velocity=velocity,
        numbers=numbers,
        initial=initial,
    )
    sources = runtime_source_artifacts(
        (
            ScannerTrackingInputStore,
            project_scanner_candidates,
            reconstruct_persistent_hop_trajectories,
            propagate_candidate_states,
            exclude_labelled_starlink_debris,
            parse_element_sets,
        )
    )
    analysis_evidence_matches = (
        capture_entry["analysis_evidence_sha256"] == source.analysis_manifest_sha256
    )
    manifest = {
        "schema": "coherent-localization-bundle/v1",
        "session_id": session_id,
        "origin_utc_ns": origin,
        "capture_window": {
            "policy": "one complete capture session; never split or pooled",
            "start_utc_ns": capture_entry["capture_start_utc_ns"],
            "end_utc_ns": capture_entry["capture_end_utc_ns"],
            "scanner_tracking_start_utc_ns": source.capture_start_utc_ns,
            "scanner_tracking_end_utc_ns": source.capture_end_utc_ns,
            "scanner_tracking_end_matches_frozen_capture_end": (
                source.capture_end_utc_ns == int(capture_entry["capture_end_utc_ns"])
            ),
            "end_semantics": (
                "frozen capture end and tracking counter-derived source-span end are distinct "
                "recorded authorities; neither is relabelled as the other"
            ),
        },
        "tracks": tracks,
        "track_mapping": mapping,
        "raw_observations": raw_receipt,
        "candidate_bank": candidate_receipt,
        "initialization": initial_receipt,
        "provenance": {
            "scope": (
                "conditional known-site-candidate benchmark input; candidate reviews "
                "do not establish "
                "blind localization validation"
            ),
            "reference_truth_used_to_select_fit_or_hyperparameters": False,
            "input_manifest_sha256": source.input_manifest_sha256,
            "persisted_analysis_manifest_sha256": source.analysis_manifest_sha256,
            "frozen_analysis_evidence_sha256": capture_entry["analysis_evidence_sha256"],
            "analysis_evidence_matches_persisted_analysis": analysis_evidence_matches,
            "analysis_digest_policy": (
                "frozen admission evidence and current persisted reanalysis are "
                "recorded separately; "
                "equality is claimed only by the explicit comparison flag"
            ),
            "raw_recording_authority_digest": source.raw_recording_authority_digest,
            "trajectory_config_digest": str(config.digest),
            "tle_snapshot": {
                "provider": snapshot.provider,
                "collected_utc_ns": snapshot.collected_utc_ns,
                "digest": snapshot.digest,
                "labelled_debris_exclusion_count": len(exclusions),
            },
        },
        "artifacts": {
            "bundle_npz_sha256": None,
            "selection": {"path": str(SELECTION_PATH), "sha256": sha256_bytes(selection_bytes)},
            "ds11_manifest": {
                "path": str(DS11_MANIFEST_PATH),
                "sha256": sha256_bytes(manifest_bytes),
            },
            "ds11_capture_entry": {
                "sha256": canonical_sha256(capture_entry),
                "manifest_sha256": capture_entry["manifest_sha256"],
                "analysis_evidence_sha256": capture_entry["analysis_evidence_sha256"],
            },
            "tracking_api": api_artifact,
            "runtime_sources": sources,
        },
    }
    evaluation = {
        "schema": "coherent-localization-evaluation/v1",
        "session_id": session_id,
        "reference_site": product["observer_site"],
        "policy": (
            "reference site is evaluation-only and is excluded from bundle.json, bundle.npz, "
            "candidate fill, fit selection, and hyperparameter selection"
        ),
        "conditional_known_site_candidate_provenance": True,
        "tracking_api_sha256": api_artifact["sha256"],
    }
    _write_bundle(output_root / session_id, arrays, manifest, evaluation)
    return {
        "session_id": session_id,
        "raw_observations": len(arrays["times"]),
        "source_groups": raw_receipt["source_group_count"],
        "tracks": len(tracks),
        "track_observations": mapping["track_observations"],
        "candidates": len(numbers),
        "budget_s": SCAN_TIMEOUT_S,
    }


def export_original_sample(*, output_root: Path, api_base: str) -> dict:
    import importlib.util

    selection = json.loads(SELECTION_PATH.read_text())
    session_id = selection["original_sample"]
    spec = importlib.util.spec_from_file_location(
        "coherent_localization_common_export", COMMON_PATH
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {COMMON_PATH}")
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    source_data = common.Data()
    if source_data.session_id != session_id:
        raise ValueError("Original frozen Data session differs from selection")
    product, api_artifact = fetch_tracking(api_base, session_id)
    initial, initial_receipt = conditional_initial(product)
    arrays = {
        name: np.asarray(getattr(source_data, name)).copy()
        for name in (
            "times",
            "measured",
            "rf",
            "receiver",
            "channel",
            "group",
            "margin",
            "nodes",
            "position",
            "velocity",
            "numbers",
        )
    }
    arrays["initial"] = initial
    tracks = [
        {
            "track_id": track["track_id"],
            "rows": np.asarray(track["rows"], dtype=int).tolist(),
            "candidate_indices": list(range(CANDIDATE_COUNT)),
            "receiver": int(track["receiver"]),
            "channel": int(track["channel"]),
        }
        for track in source_data.tracks
    ]
    frozen_paths = (
        FULL_CURVE_ROOT / "inputs.npz",
        FULL_CURVE_ROOT / "inputs.json",
        FULL_CURVE_ROOT / "satellite-time-states-10s.npz",
        SHARED_RX_ROOT / "inputs.npz",
        SHARED_RX_ROOT / "inputs.json",
        COMMON_PATH,
    )
    manifest = {
        "schema": "coherent-localization-bundle/v1",
        "session_id": session_id,
        "origin_utc_ns": json.loads((FULL_CURVE_ROOT / "inputs.json").read_text())["source"][
            "start_utc_ns"
        ],
        "capture_window": {
            "policy": "original frozen single-capture sample; no split or pooling",
            "start_utc_ns": product.get("tracklets", [{}])[0].get("start_utc_ns"),
            "end_utc_ns": max(track["end_utc_ns"] for track in product["tracklets"]),
        },
        "tracks": tracks,
        "track_mapping": dict(source_data.join_receipt),
        "raw_observations": {
            "projected_candidate_count": len(arrays["times"]),
            "source_group_count": int(len(np.unique(arrays["group"]))),
            "scope": "exact frozen full-curve GLRT inputs; no cap or decimation; no IQ",
        },
        "candidate_bank": {
            "count": len(arrays["numbers"]),
            "policy": "exact frozen original-sample 64-candidate state bank",
            "conditional_on_known_site_candidate_reviews": True,
            "reference_truth_used_for_order_or_fill": False,
        },
        "initialization": initial_receipt,
        "provenance": {
            "scope": (
                "conversion of exact frozen original-sample arrays and track mapping; conditional "
                "known-site candidate evidence is not blind localization validation"
            ),
            "reference_truth_used_to_select_fit_or_hyperparameters": False,
            "input_manifest_sha256": product["input_manifest_sha256"],
            "analysis_manifest_sha256": product["analysis_manifest_sha256"],
            "conversion_changes": (
                "only initialization is reset to Sacramento 0,0 plus conditional "
                "folded RX consensus"
            ),
        },
        "artifacts": {
            "bundle_npz_sha256": None,
            "selection": {"path": str(SELECTION_PATH), "sha256": sha256_file(SELECTION_PATH)},
            "tracking_api": api_artifact,
            "frozen_sources": [
                {"path": str(path), "sha256": sha256_file(path)} for path in frozen_paths
            ],
        },
    }
    evaluation = {
        "schema": "coherent-localization-evaluation/v1",
        "session_id": session_id,
        "reference_site": product["observer_site"],
        "policy": (
            "reference site is evaluation-only and is excluded from bundle.json, bundle.npz, "
            "fit selection, and hyperparameter selection"
        ),
        "conditional_known_site_candidate_provenance": True,
        "tracking_api_sha256": api_artifact["sha256"],
    }
    _write_bundle(output_root / session_id, arrays, manifest, evaluation)
    return {
        "session_id": session_id,
        "raw_observations": len(arrays["times"]),
        "source_groups": int(len(np.unique(arrays["group"]))),
        "tracks": len(tracks),
        "track_observations": sum(len(track["rows"]) for track in tracks),
        "candidates": len(arrays["numbers"]),
        "budget_s": SCAN_TIMEOUT_S,
    }


@contextlib.contextmanager
def scan_timeout(seconds: int = SCAN_TIMEOUT_S):
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def expired(_signum, _frame):
        raise TimeoutError(f"scan export exceeded {seconds}s bound")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("session_ids", nargs="*")
    parser.add_argument("--original-sample", action="store_true")
    parser.add_argument("--output-root", type=Path, default=ROOT / "scans")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--tle-root", type=Path, default=DEFAULT_TLE_ROOT)
    return parser.parse_args(argv)


def main(argv=None):
    arguments = parse_args(argv)
    selection = json.loads(SELECTION_PATH.read_text())
    requested = list(arguments.session_ids)
    work_count = len(requested) + int(arguments.original_sample)
    if not work_count:
        raise ValueError("Request at least one selected scan or --original-sample")
    if work_count > MAXIMUM_BATCH:
        raise ValueError(f"At most {MAXIMUM_BATCH} scans may be exported per handoff")
    if len(set(requested)) != len(requested):
        raise ValueError("Duplicate scan request")
    unknown = sorted(set(requested) - set(selection["selected"]))
    if unknown:
        raise ValueError(f"Scans are outside frozen selection: {', '.join(unknown)}")
    results = []
    if arguments.original_sample:
        started = time.monotonic()
        with scan_timeout():
            result = export_original_sample(
                output_root=arguments.output_root, api_base=arguments.api_base
            )
        result["elapsed_s"] = time.monotonic() - started
        results.append(result)
    for session_id in requested:
        started = time.monotonic()
        with scan_timeout():
            result = export_ds11(
                session_id,
                output_root=arguments.output_root,
                api_base=arguments.api_base,
                bulk_root=arguments.bulk_root,
                tle_root=arguments.tle_root,
            )
        result["elapsed_s"] = time.monotonic() - started
        results.append(result)
    print(json.dumps({"exports": results}, indent=2), flush=True)


if __name__ == "__main__":
    main()
