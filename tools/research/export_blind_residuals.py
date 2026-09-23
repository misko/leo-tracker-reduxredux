#!/usr/bin/env python3
"""Export diagnostic residual trajectories from a sealed blind refinement."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

from leo.analysis.research.formal_orbit import (  # type: ignore[import-untyped]
    phase_rate_design_hz_per_s_h,
)
from leo.analysis.research.regional_doppler import (  # type: ignore[import-untyped]
    LIGHT_KM_S,
    REFERENCE_RF_HZ,
    Region,
)
from leo.sky.propagation import parse_element_sets  # type: ignore[import-untyped]


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def content_digest(document: dict) -> str:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def replay_module():
    path = Path(__file__).parents[1] / "replay_regional_doppler.py"
    spec = importlib.util.spec_from_file_location("replay_regional_doppler", path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError("replay module has no loader")
    spec.loader.exec_module(module)
    return module


def verify_refinement(path: Path, evidence: Path) -> tuple[dict, dict]:
    result = json.loads(path.read_text())
    checksum = path.with_name("result.sha256")
    expected_checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    if not checksum.is_file() or checksum.read_text().strip() != expected_checksum:
        raise ValueError("refinement result checksum mismatch")
    if (
        not result.get("complete")
        or result.get("position_truth_used") is not False
        or result.get("prior_matched_norads_used", False)
    ):
        raise ValueError("completed truth-free blind refinement required")
    run = Path(result["run"])
    if not run.is_absolute() or not run.is_dir():
        raise ValueError("refinement acquisition run is unavailable")
    acquisition = run / "result.json"
    if digest(acquisition) != result["source_result_digest"]:
        raise ValueError("refinement acquisition binding mismatch")
    for name, expected in result["acquisition_file_digests"].items():
        if Path(name).name != name or digest(run / name) != expected:
            raise ValueError("refinement acquisition file binding mismatch")
    executed = run.parent / "executed-sources" / "refine_recent_joint_position-v2.py"
    if not executed.is_file() or digest(executed) != result["source_code_digest"]:
        raise ValueError("executed refinement source binding mismatch")
    inventory_path = evidence / "inventory.json"
    inventory = json.loads(inventory_path.read_text())
    acquisition_result = json.loads(acquisition.read_text())
    if digest(inventory_path) != acquisition_result["inventory_digest"]:
        raise ValueError("evidence inventory binding mismatch")
    if inventory.get("prior_matched_norads_used", False):
        raise ValueError("site-conditioned evidence is prohibited")
    return result, inventory


def source_rows(document: dict, episode_id: str) -> list[dict]:
    series = {row["tracklet_id"]: row for row in document["series"]}
    episode = next(row for row in document["episodes"] if row["episode_id"] == episode_id)
    rows = []
    for segment, tracklet_id in enumerate(episode["members"]):
        source = series[tracklet_id]
        count = int(np.floor(len(source["t_s"]) * 0.6))
        order = np.argsort(source["t_s"], kind="stable")
        if min(count, len(order) - count) < 2:
            raise ValueError("source too short for chronological split")
        for part, training in ((order[:count], True), (order[count:], False)):
            for index in part:
                rows.append(
                    {
                        "observation_id": source["candidate_ids"][index],
                        "source_group_id": source["paired_visit_ids"][index],
                        "tracklet_id": tracklet_id,
                        "receiver_id": source["receiver_id"],
                        "channel": source["channel"],
                        "actual_rf_hz": source["actual_rf_hz"],
                        "segment": segment,
                        "time_s": float(source["t_s"][index]),
                        "observed_hz": float(source["y_hz"][index]),
                        "training": training,
                    }
                )
    return rows


def residual_rows(
    rows: list[dict], raw_prediction: np.ndarray
) -> tuple[list[dict], dict[str, float]]:
    observed = np.asarray([row["observed_hz"] for row in rows])
    training = np.asarray([row["training"] for row in rows])
    segments = np.asarray([row["segment"] for row in rows])
    offsets = {}
    prediction = np.asarray(raw_prediction, dtype=float).copy()
    for segment in np.unique(segments):
        mask = (segments == segment) & training
        if not np.any(mask):
            raise ValueError("each path requires training observations")
        offset = float(np.mean(observed[mask] - prediction[mask]))
        offsets[str(int(segment))] = offset
        prediction[segments == segment] += offset
    output = []
    for source, fitted in zip(rows, prediction, strict=True):
        output.append(
            dict(
                source,
                predicted_hz=float(fitted),
                residual_hz=float(source["observed_hz"] - fitted),
            )
        )
    return output, offsets


def run(args) -> None:
    if args.output.exists():
        raise ValueError("fresh output directory required")
    result, _inventory = verify_refinement(args.refinement, args.evidence)
    replay = replay_module()
    region = Region(**result["region"])
    grid = region.points([result["selected"]["east_km"]], [result["selected"]["north_km"]])
    result_tracks = {(row["session_id"], row["episode_id"]): row for row in result["tracks"]}
    args.output.mkdir(parents=True)
    session_files = []
    total_rows = total_candidates = phase_propagation_failures = 0
    for session_id in result["sessions"]:
        evidence_path = args.evidence / "evidence" / f"{session_id}.json"
        document = json.loads(evidence_path.read_text())
        metadata = document["inventory"]
        provenance = result["provenance"][session_id]
        if metadata.get("known_position_used") is not False or metadata.get("fixed_candidates"):
            raise ValueError("truth- or site-conditioned RF evidence is prohibited")
        if digest(evidence_path) != provenance["rf_digest"]:
            raise ValueError("RF evidence binding mismatch")
        tle_name = metadata["tle_file"]
        if Path(tle_name).name != tle_name:
            raise ValueError("unsafe TLE basename")
        if metadata["tle_collected_ns"] >= metadata["reference_utc_ns"] - 5_000_000_000:
            raise ValueError("noncausal TLE snapshot")
        tle_path = evidence_path.parent / tle_name
        if (
            digest(tle_path) != metadata["tle_digest"]
            or digest(tle_path) != provenance["tle_digest"]
        ):
            raise ValueError("TLE evidence binding mismatch")
        catalogue = parse_element_sets(tle_path.read_text())
        indices, population = replay.regional_catalogue(
            catalogue, metadata["reference_utc_ns"], region
        )
        episodes = []
        for episode_id, arc in replay.load_observations(document, max_per_partition=0):
            frozen = result_tracks[(session_id, episode_id)]
            rows = source_rows(document, episode_id)
            if len(rows) != len(arc.time_s) or not np.allclose(
                [row["time_s"] for row in rows], arc.time_s
            ):
                raise ValueError("source row reconstruction differs from scored observations")
            positions, velocities, retained = replay.state_arrays(
                catalogue, indices, metadata["reference_utc_ns"], arc.time_s
            )
            minus_positions, minus_velocities, minus_retained = replay.state_arrays(
                catalogue,
                indices,
                metadata["reference_utc_ns"],
                arc.time_s,
                orbit_time_s=-1.0,
            )
            plus_positions, plus_velocities, plus_retained = replay.state_arrays(
                catalogue,
                indices,
                metadata["reference_utc_ns"],
                arc.time_s,
                orbit_time_s=1.0,
            )
            norads = np.asarray(catalogue.satellite_numbers)[retained]
            support = next(
                row for row in provenance["evaluated_support"] if row["episode_id"] == episode_id
            )
            support_digest = (
                "sha256:" + hashlib.sha256(np.sort(norads).astype("<i8").tobytes()).hexdigest()
            )
            if (
                len(norads) != support["evaluated_candidate_count"]
                or support_digest != support["evaluated_norad_digest"]
            ):
                raise ValueError("evaluated candidate support binding mismatch")
            candidates = []
            for candidate in frozen["candidates"][:8]:
                match = np.flatnonzero(norads == candidate["norad"])
                minus_match = np.flatnonzero(
                    np.asarray(catalogue.satellite_numbers)[minus_retained] == candidate["norad"]
                )
                plus_match = np.flatnonzero(
                    np.asarray(catalogue.satellite_numbers)[plus_retained] == candidate["norad"]
                )
                if len(match) != 1 or len(minus_match) != 1 or len(plus_match) != 1:
                    phase_propagation_failures += 1
                    raise ValueError("frozen top candidate missing from exact support")
                index = int(match[0])
                delta = positions[index] - grid.ecef_km[0]
                distance = np.linalg.norm(delta, axis=-1)
                raw = (
                    -REFERENCE_RF_HZ
                    / LIGHT_KM_S
                    * np.sum(delta * velocities[index], axis=-1)
                    / distance
                )
                exported, offsets = residual_rows(rows, raw)
                receive_utc_ns = metadata["reference_utc_ns"] + np.rint(arc.time_s * 1e9).astype(
                    np.int64
                )
                tle_epoch_ns = catalogue.element_epoch_utc_ns()[retained[index]]
                age_h = (receive_utc_ns - tle_epoch_ns) / 3.6e12
                if np.any(age_h < 0):
                    raise ValueError("candidate TLE epoch is noncausal for observation")
                design = phase_rate_design_hz_per_s_h(
                    grid.ecef_km[0],
                    minus_positions[int(minus_match[0])],
                    minus_velocities[int(minus_match[0])],
                    plus_positions[int(plus_match[0])],
                    plus_velocities[int(plus_match[0])],
                    age_h,
                )
                for row, utc_ns, design_value in zip(exported, receive_utc_ns, design, strict=True):
                    row["utc_ns"] = int(utc_ns)
                    row["satellite_design_hz_per_s_h"] = float(design_value)
                candidates.append(
                    {
                        "catalog_number": candidate["norad"],
                        "soft_weight": candidate["weight"],
                        "training_offset_hz_by_segment": offsets,
                        "rows": exported,
                    }
                )
                total_rows += len(exported)
                total_candidates += 1
            episodes.append(
                {
                    "episode_id": episode_id,
                    "candidate_support": {
                        "full_catalogue_size": population,
                        "evaluated_candidate_count": len(norads),
                        "exported_top_k": len(candidates),
                        "null_probability": frozen["null_weight"],
                        "omitted_probability_mass": frozen["omitted_identity_weight"],
                        "candidates": candidates,
                    },
                }
            )
        shard = {
            "schema": "blind-residual-trajectories/session-v1",
            "diagnostic_only": True,
            "session_id": session_id,
            "source_evidence_digest": digest(evidence_path),
            "tle_digest": digest(tle_path),
            "tle_collected_utc_ns": metadata["tle_collected_ns"],
            "reference_utc_ns": metadata["reference_utc_ns"],
            "episodes": episodes,
        }
        shard["content_digest"] = content_digest(shard)
        name = f"{session_id}.json"
        (args.output / name).write_text(json.dumps(shard, indent=2, allow_nan=False) + "\n")
        session_files.append(
            {"session_id": session_id, "file": name, "digest": digest(args.output / name)}
        )
    manifest = {
        "schema": "blind-residual-trajectories/manifest-v1",
        "diagnostic_only": True,
        "truth_accessed": False,
        "known_position_used": False,
        "site_conditioned_candidates_used": False,
        "refinement_digest": digest(args.refinement),
        "evidence_inventory_digest": digest(args.evidence / "inventory.json"),
        "frozen_location": {
            "latitude_deg": result["latitude_deg"],
            "longitude_deg": result["longitude_deg"],
            "altitude_m": 0.0,
            "selection": "training-selected blind V2 refinement",
        },
        "sessions": session_files,
        "accounting": {
            "candidate_trajectories": total_candidates,
            "trajectory_rows": total_rows,
            "phase_propagation_failures": phase_propagation_failures,
        },
        "limitations": [
            "top-eight support is copied from the frozen refinement; "
            "it is not new identity inference",
            "soft weights are conditional composite weights, not calibrated identity probabilities",
            "phase-rate design uses exact +/-1 second orbital propagation "
            "at fixed receive-time Earth rotation",
        ],
    }
    manifest["content_digest"] = content_digest(manifest)
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refinement", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
