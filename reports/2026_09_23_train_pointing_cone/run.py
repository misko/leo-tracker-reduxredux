#!/usr/bin/env python3
"""Profile required mount cones at six frozen TRAIN locations."""

import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).parents[2]
HERE = Path(__file__).parent
CACHE_ROOTS = {
    "first_train": Path("/tmp/leo-long-training-cache-full8h"),
    "second_train": Path("/tmp/leo-long-training-cache-second8h"),
}
METADATA = Path("/tmp/leo-train-rx-metadata-checkpoints")


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def weighted_quantile(values, weights, fraction):
    order = np.argsort(values)
    values, weights = np.asarray(values)[order], np.asarray(weights)[order]
    index = np.searchsorted(np.cumsum(weights), fraction * np.sum(weights), side="left")
    return float(values[min(index, len(values) - 1)])


def weighted_quantiles_batched(values, weights, fractions):
    """Return weighted quantiles for every row, sorting each row only once."""
    values, weights = np.asarray(values), np.asarray(weights)
    order = np.argsort(values, axis=1)
    ordered_values = np.take_along_axis(values, order, axis=1)
    cumulative = np.cumsum(weights[order], axis=1)
    targets = np.sum(weights) * np.asarray(fractions)
    indices = np.asarray(
        [np.sum(cumulative < target, axis=1) for target in targets], dtype=np.int64
    ).T
    return np.take_along_axis(ordered_values, np.minimum(indices, values.shape[1] - 1), axis=1)


def enu_directions(single, latitude, longitude, receiver, positions):
    lat, lon = np.radians([latitude, longitude])
    east = np.asarray([-np.sin(lon), np.cos(lon), 0.0])
    north = np.asarray([-np.sin(lat) * np.cos(lon), -np.sin(lat) * np.sin(lon), np.cos(lat)])
    up = np.asarray([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    delta = positions - receiver
    delta /= np.linalg.norm(delta, axis=1)[:, None]
    return delta @ np.column_stack((east, north, up))


def axes(tilt_deg, azimuth_deg, yaw_deg):
    angle = np.radians(10.0)
    body = np.asarray([[-np.sin(angle), 0.0, np.cos(angle)], [np.sin(angle), 0.0, np.cos(angle)]])
    common = (
        Rotation.from_euler("z", azimuth_deg, degrees=True)
        * Rotation.from_euler("y", tilt_deg, degrees=True)
        * Rotation.from_euler("z", -azimuth_deg, degrees=True)
    )
    transform = common * Rotation.from_euler("z", yaw_deg, degrees=True)
    result = transform.apply(body)
    assert np.isclose(np.degrees(np.arccos(np.clip(result[0] @ result[1], -1, 1))), 20.0)
    return result


def orientation_grid(maximum_tilt=30):
    rows = [(0, 0, yaw) for yaw in range(0, 360, 5)]
    rows.extend(
        (tilt, azimuth, yaw)
        for tilt in range(1, maximum_tilt + 1)
        for azimuth in range(0, 360, 5)
        for yaw in range(0, 360, 5)
    )
    return np.asarray(rows, dtype=np.int16)


def axes_batched(orientations):
    """Apply body yaw, then common tilt: yaw is about tilted body-up."""
    orientations = np.asarray(orientations)
    tilt, azimuth, yaw = orientations.T.astype(float)
    common = (
        Rotation.from_euler("z", azimuth[:, None], degrees=True)
        * Rotation.from_euler("y", tilt[:, None], degrees=True)
        * Rotation.from_euler("z", -azimuth[:, None], degrees=True)
    )
    transform = common * Rotation.from_euler("z", yaw[:, None], degrees=True)
    angle = np.radians(10.0)
    body = np.asarray([[-np.sin(angle), 0.0, np.cos(angle)], [np.sin(angle), 0.0, np.cos(angle)]])
    result = np.stack((transform.apply(body[0]), transform.apply(body[1])), axis=1)
    separation = np.degrees(
        np.arccos(np.clip(np.sum(result[:, 0] * result[:, 1], axis=1), -1.0, 1.0))
    )
    if not np.allclose(np.linalg.norm(result, axis=2), 1.0, atol=1e-12):
        raise AssertionError("mount axes are not unit vectors")
    if not np.allclose(separation, 20.0, atol=1e-10):
        raise AssertionError("mount axes are not 20 degrees apart")
    return result


def profile(midpoint, endpoints, receiver_ids, weights, mapping, fractions, *, batch_size=1024):
    """Profile one shared 0..30 degree sweep and derive all tilt bounds."""
    midpoint, endpoints = np.asarray(midpoint, float), np.asarray(endpoints, float)
    receiver_ids, weights = np.asarray(receiver_ids, int), np.asarray(weights, float)
    if midpoint.ndim != 2 or midpoint.shape[1] != 3 or len(midpoint) == 0:
        raise ValueError("midpoint directions must be a nonempty Nx3 array")
    if endpoints.shape != (len(midpoint), 2, 3):
        raise ValueError("endpoint directions must be Nx2x3")
    if not np.all(np.isin(receiver_ids, (0, 1))):
        raise ValueError("receiver IDs must be 0 or 1")
    if not np.all(np.isfinite(weights)) or np.any(weights <= 0):
        raise ValueError("duration weights must be finite and positive")
    orientations = orientation_grid(30)
    mounts = axes_batched(orientations)[:, list(mapping)]
    bounds = (0, 15, 30)
    best = {bound: {fraction: None for fraction in fractions} for bound in bounds}
    for start in range(0, len(orientations), batch_size):
        stop = min(start + batch_size, len(orientations))
        selected = mounts[start:stop, receiver_ids, :]
        cosine = np.einsum("ntc,tc->nt", selected, midpoint, optimize=True)
        angles = np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))
        quantiles = weighted_quantiles_batched(angles, weights, fractions)
        batch_orientations = orientations[start:stop]
        for bound in bounds:
            eligible_indices = np.flatnonzero(batch_orientations[:, 0] <= bound)
            if len(eligible_indices) == 0:
                continue
            for column, fraction in enumerate(fractions):
                local = eligible_indices[np.argmin(quantiles[eligible_indices, column])]
                value = float(quantiles[local, column])
                current = best[bound][fraction]
                if current is None or value < current["midpoint_cone_deg"]:
                    best[bound][fraction] = {
                        "midpoint_cone_deg": value,
                        "orientation_index": start + int(local),
                    }
    output = {}
    for bound in bounds:
        output[str(bound)] = {}
        for fraction in fractions:
            item = best[bound][fraction]
            orientation_index = item.pop("orientation_index")
            mount = mounts[orientation_index]
            cosine = np.einsum("tec,tc->te", endpoints, mount[receiver_ids], optimize=True)
            endpoint_angles = np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))
            endpoint_track_angles = np.max(endpoint_angles, axis=1)
            tilt, azimuth, yaw = (int(value) for value in orientations[orientation_index])
            item.update(
                endpoint_cone_deg=weighted_quantile(endpoint_track_angles, weights, fraction),
                tilt_deg=tilt,
                tilt_azimuth_deg=azimuth,
                yaw_deg=yaw,
            )
            output[str(bound)][str(fraction)] = item
    return output


def main():
    started = time.monotonic()
    locations_path = HERE / "locations.json"
    frozen = json.loads(locations_path.read_text())
    single_path = ROOT / "reports/2026_09_23_long_training_search/search.py"
    loader_path = ROOT / "reports/2026_09_23_long_training_fast_score/loader.py"
    single, loader = load(single_path, "cone_single"), load(loader_path, "cone_loader")
    manifests = {
        "first_train": ROOT / "reports/2026_09_23_long_training_cache_full8h/manifest.json",
        "second_train": ROOT / "reports/2026_09_23_long_training_cache_second8h/manifest.json",
    }
    results, bindings = [], {}
    for view in frozen["views"]:
        group, cache_root = view["group"], CACHE_ROOTS[view["group"]]
        ids = json.loads(manifests[group].read_text())["source_group"]["session_ids"][:6]
        sessions = [loader.load_session(single, cache_root / sid, sid) for sid in ids]
        metadata, evidence = {}, {}
        group_bindings = []
        for sid in ids:
            path = METADATA / f"{sid}.json"
            data = json.loads(path.read_text())
            metadata[sid] = {row["track_id"]: row for row in data["tracks"]}
            receipt = json.loads((cache_root / sid / "cache_receipt.json").read_text())
            evidence[sid] = {row["track_id"]: row for row in receipt["prepared_evidence"]["tracks"]}
            group_bindings.append(
                {
                    "session_id": sid,
                    "metadata": digest(path),
                    "receipt": digest(cache_root / sid / "cache_receipt.json"),
                    "cache": digest(cache_root / sid / "state_cache.npz"),
                }
            )
        bindings[group] = {"manifest": digest(manifests[group]), "sessions": group_bindings}
        for location in view["locations"]:
            objective, scan_rows = 0.0, []
            loss, total = 0.0, 0
            for session in sessions:
                value, tracks = single.score_point(
                    session["prepared"],
                    session["candidate_ids"],
                    location["latitude_deg"],
                    location["longitude_deg"],
                    False,
                )
                loss += session["weight"] * value**2
                total += session["weight"]
                scan_rows.append((session["session_id"], tracks))
            objective = float(np.sqrt(loss / total))
            midpoint, endpoint, receiver_ids, weights, identities = [], [], [], [], []
            maximum_time_alignment_error_ns = 0.0
            receiver, _ = single.receiver_ecef(location["latitude_deg"], location["longitude_deg"])
            for sid, tracks in scan_rows:
                with np.load(cache_root / sid / "state_cache.npz", allow_pickle=False) as archive:
                    candidates = {
                        str(value): index for index, value in enumerate(archive["candidate_id"])
                    }
                    grid, positions = (
                        archive["receive_plus_tau_offset_ns"],
                        archive["position_ecef_km"],
                    )
                    for track in tracks:
                        if not track.get("candidate_id"):
                            raise ValueError(
                                f"missing winning candidate for {sid}/{track['track_id']}"
                            )
                        meta = metadata[sid][track["track_id"]]
                        source = evidence[sid][track["track_id"]]
                        rid = int(meta["receiver_id"])
                        if rid not in (0, 1):
                            raise ValueError(
                                f"invalid receiver ID {rid} for {sid}/{track['track_id']}"
                            )
                        centers = np.asarray(meta["support_center_utc_ns"], dtype=np.int64)
                        relative = np.asarray(source["times_s"], dtype=float)
                        if len(centers) != len(relative):
                            raise ValueError("receiver metadata and evidence lengths differ")
                        anchors = centers - np.rint(relative * 1e9).astype(np.int64)
                        anchor = int(np.median(anchors))
                        maximum_time_alignment_error_ns = max(
                            maximum_time_alignment_error_ns,
                            float(np.max(np.abs(anchors - anchor))),
                        )
                        times = (
                            np.asarray(
                                [
                                    meta["support_start_utc_ns"],
                                    (meta["support_start_utc_ns"] + meta["support_end_utc_ns"])
                                    // 2,
                                    meta["support_end_utc_ns"],
                                ],
                                dtype=np.int64,
                            )
                            - anchor
                        ) / 1e9
                        if track["candidate_id"] not in candidates:
                            raise ValueError(
                                f"winning candidate absent from cache for {sid}/{track['track_id']}"
                            )
                        index = candidates[track["candidate_id"]]
                        pos, _ = single.interpolate_track(
                            positions[index : index + 1],
                            np.zeros_like(positions[index : index + 1]),
                            grid,
                            times,
                        )
                        pos = pos[0]
                        direction = enu_directions(
                            single,
                            location["latitude_deg"],
                            location["longitude_deg"],
                            receiver,
                            pos,
                        )
                        endpoint.append(direction[[0, 2]])
                        midpoint.append(direction[1])
                        receiver_ids.append(rid)
                        weights.append(track["weight_s"])
                        identities.append(
                            {
                                "session_id": sid,
                                "track_id": track["track_id"],
                                "candidate_id": track["candidate_id"],
                                "receiver_id": rid,
                                "weight_s": track["weight_s"],
                            }
                        )
            midpoint, endpoint = np.asarray(midpoint), np.asarray(endpoint)
            receiver_ids, weights = np.asarray(receiver_ids), np.asarray(weights)
            scenarios = []
            for mapping in ((0, 1), (1, 0)):
                profiles = profile(
                    midpoint, endpoint, receiver_ids, weights, mapping, (0.5, 0.8, 0.95)
                )
                for maximum_tilt in (0, 15, 30):
                    scenarios.append(
                        {
                            "maximum_tilt_deg": maximum_tilt,
                            "receiver_to_axis": mapping,
                            "quantiles": profiles[str(maximum_tilt)],
                        }
                    )
            results.append(
                {
                    "group": group,
                    "location": location,
                    "doppler_training_objective_rmse_hz": objective,
                    "track_count": len(weights),
                    "receiver_counts": {str(r): int(np.sum(receiver_ids == r)) for r in (0, 1)},
                    "maximum_center_time_alignment_error_ns": maximum_time_alignment_error_ns,
                    "identities": identities,
                    "scenarios": scenarios,
                }
            )
    output = {
        "schema": "train-pointing-cone/v1",
        "truth_used": False,
        "held_rows_used": False,
        "orientation_count": int(len(orientation_grid(30))),
        "elapsed_s": float(time.monotonic() - started),
        "results": results,
        "bindings": {
            "locations": digest(locations_path),
            "protocol": digest(HERE / "PROTOCOL.md"),
            "executed_source": digest(Path(__file__)),
            "preexecution_amendment": digest(HERE / "PREEXECUTION_AMENDMENT.json"),
            "single": digest(single_path),
            "loader": digest(loader_path),
            "groups": bindings,
        },
    }
    path = HERE / "results.json"
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    (HERE / "results.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")


if __name__ == "__main__":
    main()
