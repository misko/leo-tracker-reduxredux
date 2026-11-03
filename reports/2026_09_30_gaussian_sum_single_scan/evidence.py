#!/usr/bin/env python3
"""Freeze and replay pre-association completed-track evidence for DS9--DS11.

This adapter deliberately does not expose pose files, fitted satellite labels, or
the response-selected candidate shortlists shipped beside older exports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
AUTHORITIES = {
    "DS9": ROOT / "reports/2026_09_28_ds9_post_ds8/manifest.json",
    "DS10": ROOT / "reports/2026_09_29_ds10_post_ds9/local/manifest.json",
    "DS11": ROOT / "reports/2026_09_30_ds11_post_ds10/local/manifest.json",
}
DS10_PLAN = ROOT / "reports/2026_09_30_ds10_single10/plan.json"
DS11_PLAN = ROOT / "reports/2026_09_30_ds11_single10/export-plan.json"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def freeze_selection() -> dict[str, Any]:
    manifests = {name: _read(path) for name, path in AUTHORITIES.items()}
    ds9 = sorted(
        manifests["DS9"]["captures"],
        key=lambda row: (row["capture_start_utc_ns"], row["session_id"]),
    )
    indices = [math.floor(i * (len(ds9) - 1) / 7) for i in range(8)]
    ds10_plan = _read(DS10_PLAN)
    ds11_plan = _read(DS11_PLAN)
    selected = {
        "DS9": [ds9[index] | {"selection_index": index, "unit_id": f"DS9-F{index + 1:03d}"} for index in indices],
        "DS10": [row | {"unit_id": Path(row["artifacts"][0]["path"]).parent.name} for row in ds10_plan["inputs"]],
        "DS11": ds11_plan["captures"],
    }
    return {
        "schema": "gaussian-sum-scan-selection/v1",
        "method": {
            "DS9": "chronological floor(i*(N-1)/7), i=0..7; tie by session_id",
            "DS10": "exact inputs from existing DS10 single-scan plan",
            "DS11": "exact captures from existing DS11 export plan",
        },
        "authorities": {
            name: {"path": str(path), "sha256": digest(path)}
            for name, path in AUTHORITIES.items()
        }
        | {
            "DS10_plan": {"path": str(DS10_PLAN), "sha256": digest(DS10_PLAN)},
            "DS11_plan": {"path": str(DS11_PLAN), "sha256": digest(DS11_PLAN)},
        },
        "counts": {name: len(rows) for name, rows in selected.items()},
        "selected": selected,
    }


def _find_exports(session_id: str) -> list[Path]:
    return sorted(ROOT.glob(f"reports/*/exports/*/observations.json")) if False else sorted(
        path
        for path in ROOT.glob("reports/*/exports/*/observations.json")
        if f'"session_id":"{session_id}"' in path.read_text(encoding="utf-8")[:500]
        or f'"session_id": "{session_id}"' in path.read_text(encoding="utf-8")[:500]
    )


def load_observation_export(path: Path, expected: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate one public, pre-association track export and return causal ordering."""
    doc = _read(path)
    if doc.get("schema") != "ds7-baseline-track-export/v1":
        raise ValueError("unsupported observation export schema")
    if expected is not None:
        for key in ("session_id", "manifest_sha256"):
            if expected.get(key) != doc.get(key):
                raise ValueError(f"observation {key} binding mismatch")
        declared = [item for item in expected.get("artifacts", []) if item.get("kind") == "observations"]
        matching = [item for item in declared if Path(item["path"]).resolve() == path.resolve()]
        if matching and matching[0].get("sha256") != digest(path):
            raise ValueError("observation artifact digest mismatch")
    start = int(doc["start_utc_ns"])
    seen: set[str] = set()
    tracks = []
    for row in doc["tracks"]:
        track_id = str(row["track_id"])
        if track_id in seen:
            raise ValueError("duplicate track_id")
        seen.add(track_id)
        times = [float(value) for value in row["times_s"]]
        measured = [float(value) for value in row["measured_hz"]]
        visits = [int(value) for value in row["visits"]]
        if not times or len(times) != len(measured) or len(times) != len(visits):
            raise ValueError(f"invalid observation vectors for {track_id}")
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError(f"non-increasing times for {track_id}")
        rx = int(row["receiver_id"])
        observation_ids = [
            f"{doc['session_id']}:rx{rx}:channel{int(row['channel'])}:visit{visit}"
            for visit in visits
        ]
        tracks.append(
            {
                "track_id": track_id,
                "receiver_id": rx,
                "channel": int(row["channel"]),
                "rf_hz": float(row["rf_hz"]),
                "support_start_utc_ns": start + round(times[0] * 1e9),
                "support_end_utc_ns": start + round(times[-1] * 1e9),
                "times_utc_ns": [start + round(value * 1e9) for value in times],
                "measured_hz": measured,
                "physical_observation_ids": observation_ids,
                "visits": visits,
                "uncertainty": {
                    "covariance_hz2": None,
                    "status": "unavailable; must be supplied by frozen development-only rule",
                },
                "aliases": [],
                "discontinuities": [],
            }
        )
    tracks.sort(key=lambda row: (row["support_end_utc_ns"], row["support_start_utc_ns"], row["track_id"]))
    owners: dict[str, list[str]] = {}
    for row in tracks:
        for item in row["physical_observation_ids"]:
            owners.setdefault(item, []).append(row["track_id"])
    collisions = {key: value for key, value in owners.items() if len(value) > 1}
    return {
        "schema": "gaussian-sum-scan-evidence/v1",
        "session_id": doc["session_id"],
        "manifest_sha256": doc["manifest_sha256"],
        "source": {"path": str(path.resolve()), "sha256": digest(path)},
        "source_analysis_manifest_sha256": doc["analysis_manifest_sha256"],
        "source_snapshot_sha256": doc["snapshot_sha256"],
        "source_evidence_sha256": doc["evidence_sha256"],
        "sample_rate_hz": doc["sample_rate_hz"],
        "replay_semantics": "completed-track retrospective; chronological by support end then start then ID",
        "candidate_bank": None,
        "candidate_bank_status": "required response-free regional bank unavailable",
        "observation_id_collisions": collisions,
        "overlap_policy": "IDs are detector atoms independent of track hypothesis; colliding same-RX tracks must not both be assimilated",
        "tracks": tracks,
    }


def build_inventory(selection: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for dataset, captures in selection["selected"].items():
        for capture in captures:
            paths = _find_exports(capture["session_id"])
            exports = []
            for path in paths:
                try:
                    evidence = load_observation_export(path, capture)
                    exports.append(
                        {
                            "path": str(path.resolve()),
                            "sha256": evidence["source"]["sha256"],
                            "track_count": len(evidence["tracks"]),
                            "observation_count": sum(len(t["measured_hz"]) for t in evidence["tracks"]),
                        }
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    exports.append({"path": str(path.resolve()), "rejected": str(exc)})
            rows.append({"dataset": dataset, "unit_id": capture["unit_id"], "session_id": capture["session_id"], "exports": exports})
    return {
        "schema": "gaussian-sum-evidence-inventory/v1",
        "selection_sha256": "sha256:" + hashlib.sha256(
            json.dumps(selection, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "rows": rows,
        "audit": {
            "observation_source": "public ds7 baseline projection; pre-association and no geographic filtering",
            "candidate_bank": {
                "status": "rejected_for_regional_inference",
                "reason": "archived banks are residual-response top-8 unions evaluated at the old site center and four +/-12 km corners",
                "catalogue_vs_shortlist": "catalogue manifests report about 11130 rows, while per-track banks commonly retain only 9--19 response-selected candidates",
                "required_replacement": "causal archived catalogue propagated inside the callback for every prior-supported location, with location-dependent visibility/opportunity priors",
            },
            "covariance": "not present in observation exports; no independent-noise claim is justified",
            "source_overlap": "RX tracks and temporally overlapping tracks remain separate; runner must model shared visit/source error and must not multiply aliases as independent evidence",
            "causality": "observations are completed-track retrospective; TLE digest is recorded but acquisition timestamps and orbit-error model are absent from the observation export",
            "truth_isolation": "adapter does not read pose files, fitted labels, shortlisted identities, or reference coordinates",
            "frequency": "measured_hz is the public projected CFO and rf_hz is the physical RF; sign convention requires callback verification against public predictor",
            "historical_prediction_frequency": {
                "reference_rf_hz": 11200000000.0,
                "finding": "the archived public predictor uses a fixed 11.2 GHz Doppler reference; per-track rf_hz ranges by channel and is not the historical prediction scale",
                "source": "reports/2026_09_28_full_manifest_inputs/runtime-sources/leo.analysis.adaptive_tle_prediction.py",
                "integration_rule": "freeze the physical likelihood frequency convention explicitly; do not silently substitute 11.325 GHz or track rf_hz",
            },
        },
    }


def export_orbit_states(
    observation_path: Path, tle_path: Path, output: Path, *, step_s: float = 5.0
) -> dict[str, Any]:
    """Export a response-free causal catalogue state table without reading RF response."""
    import numpy as np
    from leo.sky.frames import greenwich_mean_sidereal_time_rad, julian_day_from_utc_ns, teme_to_ecef
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets, propagate_grid
    from leo.sky.sampling import SamplingGrid

    def propagate_candidate_states(catalogue, candidate_indices, start_utc_ns, times_s, taus_s):
        orbit_ns = np.asarray([start_utc_ns + round(float(t + tau) * 1e9)
                               for tau in taus_s for t in times_s], dtype=np.int64)
        grid = SamplingGrid(tuple(int(value) for value in orbit_ns), 0, 1.0)
        state = propagate_grid(catalogue, grid, candidate_indices)
        jd, fraction = julian_day_from_utc_ns(orbit_ns)
        position, velocity = teme_to_ecef(state.position_teme_km, state.velocity_teme_km_s,
                                           greenwich_mean_sidereal_time_rad(jd, fraction))
        shape = (len(candidate_indices), len(taus_s), len(times_s), 3)
        position, velocity = position.reshape(shape), velocity.reshape(shape)
        valid_mask = np.all(state.error_code == 0, axis=1)
        valid_mask &= np.all(np.isfinite(position), axis=(1, 2, 3))
        valid_mask &= np.all(np.isfinite(velocity), axis=(1, 2, 3))
        valid_mask &= np.min(np.linalg.norm(position, axis=-1), axis=(1, 2)) > 6498.137
        selected = np.asarray(candidate_indices)[valid_mask]
        return position[valid_mask], velocity[valid_mask], selected

    observations = _read(observation_path)
    archive = TleArchiveReader(tle_path.parents[2])
    refs = [item for item in archive.list_snapshots(tle_path.parent.name) if item.path == tle_path]
    if len(refs) != 1:
        raise ValueError("TLE path is not one canonical public-reader snapshot")
    payload = archive.read(refs[0])
    catalogue = parse_element_sets(payload)
    indices = np.arange(len(catalogue.satellite_numbers), dtype=int)
    all_times = [float(t) for row in observations["tracks"] for t in row["times_s"]]
    start_s = math.floor((min(all_times) - 10.0) / step_s) * step_s
    stop_s = math.ceil((max(all_times) + 10.0) / step_s) * step_s
    knots = np.arange(start_s, stop_s + step_s / 2, step_s)
    positions, velocities, valid = propagate_candidate_states(
        catalogue, indices, int(observations["start_utc_ns"]), knots, np.array([0.0])
    )
    rejected = sorted(set(indices.tolist()) - set(valid.tolist()))
    rejected_norad = [int(catalogue.satellite_numbers[index]) for index in rejected]
    midpoints = knots[:-1] + step_s / 2
    mid_pos, mid_vel, mid_valid = propagate_candidate_states(
        catalogue, valid, int(observations["start_utc_ns"]), midpoints, np.array([0.0])
    )
    if not np.array_equal(mid_valid, valid):
        failed = sorted(set(valid.tolist()) - set(mid_valid.tolist()))
        raise ValueError(f"catalogue objects failed midpoint propagation: {failed[:20]}")
    linear_pos = (positions[:, 0, :-1] + positions[:, 0, 1:]) / 2
    linear_vel = (velocities[:, 0, :-1] + velocities[:, 0, 1:]) / 2
    pos_error = np.linalg.norm(mid_pos[:, 0] - linear_pos, axis=-1)
    vel_error = np.linalg.norm(mid_vel[:, 0] - linear_vel, axis=-1)
    hermite_pos = linear_pos + step_s / 8 * (velocities[:, 0, :-1] - velocities[:, 0, 1:])
    hermite_vel = 1.5 / step_s * (positions[:, 0, 1:] - positions[:, 0, :-1]) - 0.25 * (
        velocities[:, 0, :-1] + velocities[:, 0, 1:]
    )
    hermite_pos_error = np.linalg.norm(mid_pos[:, 0] - hermite_pos, axis=-1)
    hermite_vel_error = np.linalg.norm(mid_vel[:, 0] - hermite_vel, axis=-1)
    cubic_velocity = (
        -velocities[:, 0, :-3]
        + 9 * velocities[:, 0, 1:-2]
        + 9 * velocities[:, 0, 2:-1]
        - velocities[:, 0, 3:]
    ) / 16
    cubic_velocity_error = np.linalg.norm(mid_vel[:, 0, 1:-1] - cubic_velocity, axis=-1)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        output,
        satellite_ids=np.asarray(catalogue.satellite_numbers, dtype=np.int64)[valid],
        knot_times_s=knots,
        positions_ecef_km=positions[:, 0],
        velocities_ecef_km_s=velocities[:, 0],
    )
    snapshot_collected = int(tle_path.name.split("-", 1)[0]) if "-" in tle_path.name else None
    return {
        "schema": "gaussian-sum-response-free-orbits/v1",
        "session_id": observations["session_id"],
        "observation_sha256": digest(observation_path),
        "tle": {
            "path": str(tle_path.resolve()), "sha256": digest(tle_path),
            "snapshot_collected_utc_ns": snapshot_collected,
            "causal": snapshot_collected is not None and snapshot_collected < observations["start_utc_ns"],
            "age_at_capture_start_s": None if snapshot_collected is None else (observations["start_utc_ns"] - snapshot_collected) / 1e9,
        },
        "policy": "all catalogue objects; no measured response, pose, horizon, label exclusion, or old-site shortlist used",
        "catalogue_count": len(indices),
        "propagated_count": len(valid),
        "propagation_rejected_count": len(rejected),
        "propagation_rejected_catalogue_indices": rejected,
        "propagation_rejected_norad_ids": rejected_norad,
        "catalogue_gap": bool(rejected),
        "state_file": str(output.resolve()),
        "state_sha256": digest(output),
        "state_frame": "ECEF km and ECEF km/s from public TEME propagation",
        "knot_start_s": float(knots[0]), "knot_stop_s": float(knots[-1]), "knot_step_s": step_s,
        "midpoint_linear_interpolation": {
            "checked_midpoints": len(midpoints),
            "maximum_position_error_km": float(pos_error.max()),
            "p99_position_error_km": float(np.quantile(pos_error, 0.99)),
            "maximum_velocity_error_km_s": float(vel_error.max()),
            "p99_velocity_error_km_s": float(np.quantile(vel_error, 0.99)),
        },
        "midpoint_cubic_hermite_interpolation": {
            "uses_endpoint_position_and_velocity": True,
            "maximum_position_error_km": float(hermite_pos_error.max()),
            "p99_position_error_km": float(np.quantile(hermite_pos_error, 0.99)),
            "maximum_velocity_error_km_s": float(hermite_vel_error.max()),
            "p99_velocity_error_km_s": float(np.quantile(hermite_vel_error, 0.99)),
        },
        "midpoint_four_knot_cubic_velocity_interpolation": {
            "interior_midpoints_only": True,
            "weights": [-0.0625, 0.5625, 0.5625, -0.0625],
            "maximum_velocity_error_km_s": float(cubic_velocity_error.max()),
            "p99_velocity_error_km_s": float(np.quantile(cubic_velocity_error, 0.99)),
        },
        "orbit_error_model": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("freeze")
    inventory = sub.add_parser("inventory")
    inventory.add_argument("--selection", type=Path, default=HERE / "selection.json")
    export = sub.add_parser("export")
    export.add_argument("source", type=Path)
    export.add_argument("output", type=Path)
    orbit = sub.add_parser("orbit-export")
    orbit.add_argument("observations", type=Path)
    orbit.add_argument("tle", type=Path)
    orbit.add_argument("output", type=Path)
    orbit.add_argument("metadata", type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        result, output = freeze_selection(), HERE / "selection.json"
    elif args.command == "inventory":
        result, output = build_inventory(_read(args.selection)), HERE / "inventory.json"
    elif args.command == "export":
        result, output = load_observation_export(args.source), args.output
    else:
        result, output = export_orbit_states(args.observations, args.tle, args.output), args.metadata
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "sha256": digest(output)}, separators=(",", ":")))


if __name__ == "__main__":
    main()
