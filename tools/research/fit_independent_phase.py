"""Freeze training-only candidate models for the independent phase arc."""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports/2026_09_23_long_cache_feasibility/helper"))

from regular_cache import interpolate_states  # noqa: E402

from leo.analysis.adaptive_tle_prediction import propagate_candidate_states  # noqa: E402
from leo.analysis.research.formal_orbit import doppler_hz  # noqa: E402
from leo.analysis.research.regional_doppler import Region  # noqa: E402
from leo.operations.adaptive_tle_position_inputs import (  # noqa: E402
    prepare_adaptive_tle_position_inputs,
)
from leo.operations.tle_archive import TleArchiveReader  # noqa: E402
from leo.sky.propagation import find_element_set_record, parse_element_sets  # noqa: E402
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore  # noqa: E402

FIGURE = ROOT / "reports/figures/2026_09_23_independent_phase"
CACHE_ROOT = ROOT / "reports/2026_09_23_long_cache_feasibility/results"
PRIORS = {
    "sacramento": (38.5816, -121.4944, 250.0),
    "reno": (39.5296, -119.8138, 500.0),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regional_grid() -> tuple[np.ndarray, list[dict]]:
    points, metadata = [], []
    seen = set()
    for name, (latitude, longitude, radius) in PRIORS.items():
        region = Region(latitude, longitude, 2 * radius, 2 * radius)
        offsets = np.arange(-radius, radius + 0.1, 50.0)
        for east in offsets:
            for north in offsets:
                if np.hypot(east, north) > radius + 1e-9:
                    continue
                lat, lon = region.coordinates(east, north)
                key = (round(float(lat), 10), round(float(lon), 10))
                if key in seen:
                    continue
                seen.add(key)
                point = region.points([east], [north])
                points.append(point.ecef_km[0])
                metadata.append(
                    {
                        "prior": name,
                        "east_km": float(east),
                        "north_km": float(north),
                        "latitude_deg": float(lat),
                        "longitude_deg": float(lon),
                        "up": point.up[0].tolist(),
                    }
                )
    return np.asarray(points), metadata


def affine_score(observed, predicted, times):
    """Equal-observation affine profile for candidate rows."""
    observed, predicted, times = map(np.asarray, (observed, predicted, times))
    centre = float(times.mean())
    design = np.column_stack([np.ones(len(times)), times - centre])
    inverse = np.linalg.inv(design.T @ design) @ design.T
    coefficient = (observed[None, :] - predicted) @ inverse.T
    fitted = predicted + coefficient @ design.T
    rms = np.sqrt(np.mean((observed[None, :] - fitted) ** 2, axis=1))
    return rms, coefficient, centre


def phase_cfo(row: dict) -> tuple[float, float]:
    observation = row["observation"]
    branch = row["branches"][row["selected_seed_index"]]
    frames = [
        item
        for item in branch["frames"]
        if item["group_id"] in (0, 3, 5)
        and item["frame"]["training_supported"]
        and item["frame"]["even"] is not None
        and not item["frame"]["even"]["search_boundary"]
    ]
    native_period = 1 / 4.4e-6
    fixed_lift = round(
        (observation["dealiased_native_cfo_hz"] - branch["seed_cfo_hz"]) / native_period
    )
    values = []
    for frame in frames:
        native = frame["frame"]["even"]["absolute_cfo_hz"]
        values.append((native + fixed_lift * native_period) * observation["rf_normalization_scale"])
    return float(np.mean(values)), float(np.mean([item["session_time_s"] for item in frames]))


def exact_models(prepared, candidate_ids, sites, ups, observed, geometry_times, nuisance_times):
    catalogue_ids = np.asarray(prepared.catalogue.satellite_numbers)
    results = []
    for candidate_id, site, up in zip(candidate_ids, sites, ups, strict=True):
        candidate_index = int(np.flatnonzero(catalogue_ids == candidate_id)[0])
        p, v, valid = propagate_candidate_states(
            prepared.catalogue,
            np.asarray([candidate_index]),
            prepared.start_utc_ns,
            geometry_times,
            np.asarray([0.0]),
        )
        if len(valid) != 1:
            raise ValueError(f"exact propagation failed for candidate {candidate_id}")
        if not np.all(np.sum((p[0, 0] - site) * up, axis=-1) > 0):
            raise ValueError(f"exact candidate {candidate_id} falls below the training horizon")
        predicted = doppler_hz(site, p[0, 0], v[0, 0])[None, :]
        rms, coefficient, centre = affine_score(observed, predicted, nuisance_times)
        results.append((float(rms[0]), coefficient[0], centre))
    return results


def verify_frozen_inputs(artifact: dict) -> None:
    for relative, expected in artifact["input_sha256"].items():
        if digest(ROOT / relative) != expected:
            raise ValueError(f"frozen model input changed: {relative}")
    for relative, expected in artifact["implementation_sha256"].items():
        if digest(ROOT / relative) != expected:
            raise ValueError(f"frozen model implementation changed: {relative}")


def predict_model(
    model: dict,
    times_s: np.ndarray,
    artifact: dict,
    *,
    visit_time_s: float | None = None,
) -> np.ndarray:
    """Predict normalized CFO from one sealed model without refitting."""
    times = np.asarray(times_s, float)
    if not len(times):
        return np.empty(0)
    if model["model_type"] == "constant_rate":
        base = np.zeros(len(times))
    else:
        query = times
        if model["wrong_time"]:
            if visit_time_s is None:
                raise ValueError("wrong-time prediction requires a dwell observation time")
            query = artifact["wrong_time_mirror_sum_s"] - 2 * visit_time_s + times
        catalogue = parse_element_sets("\n".join(model["tle_lines"]) + "\n")
        p, v, valid = propagate_candidate_states(
            catalogue,
            np.asarray([0]),
            artifact["start_utc_ns"],
            query,
            np.asarray([0.0]),
        )
        if len(valid) != 1:
            raise ValueError("sealed exact SGP4 propagation failed")
        base = doppler_hz(np.asarray(model["receiver_ecef_km"]), p[0, 0], v[0, 0])
    return base + model["offset_hz"] + model["drift_hz_s"] * (times - model["time_centre_s"])


def main() -> None:
    binding_path = FIGURE / "binding.json"
    frames_path = FIGURE / "train-frames.json.gz"
    cache_path = CACHE_ROOT / "state_cache.npz"
    receipt_path = CACHE_ROOT / "cache_receipt.json"
    protocol_path = ROOT / "reports/2026_09_23_independent_phase_protocol.md"
    output_path = FIGURE / "training-model.json"
    if output_path.exists():
        raise ValueError("fresh model output required")
    binding = json.loads(binding_path.read_text())
    with gzip.open(frames_path, "rt") as stream:
        frames = json.load(stream)
    receipt = json.loads(receipt_path.read_text())
    if frames["fresh_held_visits_read"] or frames["old_reserved_visits_read"]:
        raise ValueError("training replay opened reserved IQ")
    rows = sorted(frames["rows"], key=lambda row: row["observation"]["time_s"])
    split = {
        row["visit_index"]: row["partition"] for row in binding["fresh_random_whole_visit_split"]
    }
    expected_visits = sorted(index for index, partition in split.items() if partition == "train")
    actual_visits = sorted(row["observation"]["visit_index"] for row in rows)
    if len(rows) != 15 or actual_visits != expected_visits:
        raise ValueError("training replay rows differ from the frozen 15-dwell split")
    glrt_y = np.asarray([row["observation"]["normalized_cfo_hz"] for row in rows])
    glrt_t = np.asarray([row["observation"]["time_s"] for row in rows])
    phase_values = [phase_cfo(row) for row in rows]
    phase_y, phase_t = map(np.asarray, zip(*phase_values, strict=True))
    with np.load(cache_path, allow_pickle=False) as opened:
        cache = {key: opened[key] for key in opened.files}
    sites, site_metadata = regional_grid()
    candidate_ids = cache["candidate_id"].astype(int)

    mirror_sum = float(glrt_t.min() + glrt_t.max())

    def screen(observed, times, observation_times, mirrored=False):
        query = mirror_sum - 2 * observation_times + times if mirrored else times
        offsets = np.rint(query * 1e9).astype(np.int64)
        p, v = interpolate_states(cache, offsets)
        models = []
        for site_index, site in enumerate(sites):
            delta = p - site
            up = np.asarray(site_metadata[site_index]["up"])
            visible = np.all(np.sum(delta * up, axis=-1) > 0, axis=1)
            prediction = doppler_hz(site, p, v)
            rms, coefficient, centre = affine_score(observed, prediction, times)
            for index in np.flatnonzero(visible):
                models.append(
                    (
                        float(rms[index]),
                        int(candidate_ids[index]),
                        site_index,
                        coefficient[index],
                        centre,
                    )
                )
        return sorted(models, key=lambda row: (row[0], row[1], row[2]))[:16]

    source_store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        prepared = prepare_adaptive_tle_position_inputs(
            binding["session_id"],
            inputs=source_store,
            archive=TleArchiveReader(Path("/var/lib/leo/tle")),
        )
    finally:
        source_store.close()
    if prepared.snapshot_digest != receipt["prepared_evidence"]["snapshot_digest"]:
        raise ValueError("causal snapshot changed")
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    matching_snapshots = [
        item
        for item in archive.list_snapshots()
        if item.digest == prepared.snapshot_digest
        and item.collected_utc_ns == prepared.snapshot_collected_utc_ns
    ]
    if len(matching_snapshots) != 1:
        raise ValueError("prepared causal snapshot does not resolve uniquely")
    snapshot = matching_snapshots[0]
    snapshot_text = archive.read(snapshot)

    arms = {}
    for name, observed, times in (("glrt", glrt_y, glrt_t), ("phase", phase_y, phase_t)):
        for suffix, mirrored in (("candidate", False), ("wrong_time", True)):
            finalists = screen(observed, times, glrt_t, mirrored)
            geometry_times = mirror_sum - 2 * glrt_t + times if mirrored else times
            exact = exact_models(
                prepared,
                [row[1] for row in finalists],
                [sites[row[2]] for row in finalists],
                [np.asarray(site_metadata[row[2]]["up"]) for row in finalists],
                observed,
                geometry_times,
                times,
            )
            ranked = sorted(zip(finalists, exact, strict=True), key=lambda row: row[1][0])
            cached, result = ranked[0]
            arms[f"{name}_{suffix}"] = {
                "candidate_norad": cached[1],
                "site": site_metadata[cached[2]],
                "cache_training_rms_hz": cached[0],
                "exact_training_rms_hz": result[0],
                "offset_hz": float(result[1][0]),
                "drift_hz_s": float(result[1][1]),
                "time_centre_s": result[2],
                "finalists": [
                    {"cache_rms_hz": row[0], "norad": row[1], "site_index": row[2]}
                    for row in finalists
                ],
            }
        rms, coefficient, centre = affine_score(observed, np.zeros((1, len(times))), times)
        arms[f"{name}_constant_rate"] = {
            "training_rms_hz": float(rms[0]),
            "offset_hz": float(coefficient[0, 0]),
            "drift_hz_s": float(coefficient[0, 1]),
            "time_centre_s": centre,
        }
    output = {
        "schema": "independent-phase-training-model/v1",
        "training_visit_count": 15,
        "held_iq_read": False,
        "candidate_count": len(candidate_ids),
        "site_count": len(sites),
        "exact_rerank_count_per_model": 16,
        "arms": arms,
        "input_sha256": {
            str(path.relative_to(ROOT)): digest(path)
            for path in (binding_path, frames_path, cache_path, receipt_path, protocol_path)
        },
        "source_sha256": digest(Path(__file__)),
        "implementation_sha256": {
            str(path.relative_to(ROOT)): digest(path)
            for path in (
                Path(__file__),
                ROOT / "src/leo/analysis/adaptive_tle_prediction.py",
                ROOT / "src/leo/analysis/research/formal_orbit.py",
                ROOT / "src/leo/sky/propagation.py",
                ROOT / "reports/2026_09_23_long_cache_feasibility/helper/regular_cache.py",
            )
        },
    }
    selected_models = {}
    for name, row in arms.items():
        if name.endswith("constant_rate"):
            selected_models[name] = {"model_type": "constant_rate", **row}
        else:
            site = Region(row["site"]["latitude_deg"], row["site"]["longitude_deg"], 1, 1)
            record = find_element_set_record(snapshot_text, row["candidate_norad"])
            if record is None:
                raise ValueError("selected candidate absent from causal snapshot")
            selected_models[name] = {
                "model_type": "exact_nominal_sgp4",
                "candidate_norad": row["candidate_norad"],
                "receiver_ecef_km": site.points([0], [0]).ecef_km[0].tolist(),
                "wrong_time": name.endswith("wrong_time"),
                "tle_lines": [record.name, record.first_line, record.second_line],
                "offset_hz": row["offset_hz"],
                "drift_hz_s": row["drift_hz_s"],
                "time_centre_s": row["time_centre_s"],
            }
    output["selected_models"] = selected_models
    output["state_cache_path"] = str(cache_path.relative_to(ROOT))
    output["start_utc_ns"] = prepared.start_utc_ns
    output["wrong_time_mirror_sum_s"] = mirror_sum
    output["tle_authority"] = {
        "snapshot_digest": prepared.snapshot_digest,
        "snapshot_collected_utc_ns": prepared.snapshot_collected_utc_ns,
    }
    output_path.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
