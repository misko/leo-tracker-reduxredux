#!/usr/bin/env python3
"""Export DS7 cached CFO tracks through the public numerical input port; no IQ."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

SEED = 2026092711


def partition(session: str, visit: int) -> bool:
    value = hashlib.sha256(f"{SEED}:visit:{session}:{visit}".encode()).hexdigest()
    return int(value[:8], 16) % 10 < 6


def export(capture: dict, output: Path, bulk_root: Path, tle_root: Path) -> dict:
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    from leo.operations.tle_archive import TleArchiveReader

    started = time.monotonic()
    session = capture["session_id"]
    store = ScannerTrackingInputStore(bulk_root)
    try:
        raw = store.load(session)
        if raw.input_manifest_sha256 != capture["manifest_sha256"]:
            raise ValueError("source manifest mismatch")

        class Inputs:
            def load(self, name):
                if name != session:
                    raise ValueError("unexpected session")
                return raw

        prepared = prepare_adaptive_tle_position_inputs(
            session, inputs=Inputs(), archive=TleArchiveReader(tle_root)
        )
        points = project_scanner_candidates(raw)
        by_id = {p.candidate_id: p for p in points}
        graph = reconstruct_persistent_hop_trajectories(
            points, config=PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6)
        )
        numeric = {t.track_id: t for t in prepared.tracks}
        tracks = []
        for track in graph.tracklets:
            if track.tracklet_id not in numeric:
                continue
            pts = [by_id[p.candidate_id] for p in track.points]
            num = numeric[track.tracklet_id]
            actual_times = [(p.support_center_utc_ns - prepared.start_utc_ns) / 1e9 for p in pts]
            if len(actual_times) != len(num.times_s) or any(
                abs(a - b) > 1e-9 for a, b in zip(actual_times, num.times_s, strict=True)
            ):
                raise ValueError("public trajectory and numerical track differ")
            tracks.append(
                {
                    "track_id": track.tracklet_id,
                    "times_s": num.times_s.tolist(),
                    "measured_hz": num.measured_hz.tolist(),
                    "training_mask": [partition(session, p.visit_index) for p in pts],
                    "receiver_id": pts[0].receiver_id,
                    "channel": pts[0].channel,
                    "rf_hz": pts[0].actual_rf_hz,
                    "visits": [p.visit_index for p in pts],
                }
            )
        if set(numeric) != {t["track_id"] for t in tracks}:
            raise ValueError("incomplete track projection")
        result = {
            "schema": "ds7-baseline-track-export/v1",
            "session_id": session,
            "manifest_sha256": raw.input_manifest_sha256,
            "analysis_manifest_sha256": raw.analysis_manifest_sha256,
            "start_utc_ns": prepared.start_utc_ns,
            "sample_rate_hz": raw.sample_rate_hz,
            "snapshot_sha256": prepared.snapshot_digest,
            "evidence_sha256": prepared.evidence_sha256,
            "partition_seed": SEED,
            "partition_policy": "whole visit; sha256(seed:visit:session:visit) first32 modulo10 <6",
            "track_policy": (
                "public projection; minimum span 3 s and support 6; no geographic filtering"
            ),
            "candidate_policy_state": "not_exported",
            "candidate_policy_reason": (
                "corrected DS6 full-catalogue anchor shortlist and propagated banks "
                "require separate frozen export"
            ),
            "tracks": tracks,
            "elapsed_seconds": time.monotonic() - started,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x") as stream:
            json.dump(result, stream, separators=(",", ":"), allow_nan=False)
        return result
    finally:
        store.close()


def export_banks(
    capture: dict, tracks_path: Path, output: Path, bulk_root: Path, tle_root: Path
) -> dict:
    """Freeze the pinned DS6 five-anchor shortlist and quarter-second banks."""
    import numpy as np
    from leo.analysis.adaptive_tle_prediction import (
        LIGHT_KM_S,
        REFERENCE_RF_HZ,
        propagate_candidate_states,
    )
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from scipy.special import gammaln, logsumexp

    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.frames import geodetic_to_ecef_km
    from leo.sky.propagation import parse_element_set_records, parse_element_sets

    started = time.monotonic()
    session = capture["session_id"]
    document = json.loads(tracks_path.read_text())
    if (
        document["session_id"] != session
        or document["manifest_sha256"] != capture["manifest_sha256"]
    ):
        raise ValueError("track binding mismatch")
    tracks = []
    for row in document["tracks"]:
        mask = np.asarray(row["training_mask"], bool)
        if mask.sum() >= 2 and (~mask).sum() >= 1:
            tracks.append(
                {
                    "id": row["track_id"],
                    "t": np.asarray(row["times_s"]),
                    "y": np.asarray(row["measured_hz"]),
                    "mask": mask,
                    "row": row,
                }
            )
    store = ScannerTrackingInputStore(bulk_root)
    try:
        raw = store.load(session)

        class Inputs:
            def load(self, name):
                if name != session:
                    raise ValueError("unexpected session")
                return raw

        prepared = prepare_adaptive_tle_position_inputs(
            session, inputs=Inputs(), archive=TleArchiveReader(tle_root)
        )
    finally:
        store.close()
    archive = TleArchiveReader(tle_root)
    cutoff = document["start_utc_ns"] - 505_000_000_000
    snapshots = archive.list_snapshots()
    latest = []
    for provider in sorted({s.provider for s in snapshots}):
        eligible = [s for s in snapshots if s.provider == provider and s.collected_utc_ns < cutoff]
        if eligible:
            latest.append(max(eligible, key=lambda s: (s.collected_utc_ns, s.sha256)))
    base = archive.select_latest_before(cutoff)
    if base.digest != prepared.snapshot_digest:
        raise ValueError("baseline causal snapshot changed")

    def read_snapshot(snapshot):
        payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
        parsed = parse_element_sets(payload)
        return list(parse_element_set_records(payload)), parsed.element_epoch_utc_ns()

    base_records, _ = read_snapshot(base)
    choices = {}
    for snapshot in latest:
        records, epochs = read_snapshot(snapshot)
        for record, epoch in zip(records, epochs, strict=True):
            key = (epoch, snapshot.collected_utc_ns, snapshot.digest)
            if record.satellite_number not in choices or key > choices[record.satellite_number][0]:
                choices[record.satellite_number] = (key, record)
    chosen = [choices[r.satellite_number] for r in base_records]
    catalogue = parse_element_sets("".join(record.text for _, record in chosen))
    if catalogue.satellite_numbers != prepared.catalogue.satellite_numbers:
        raise ValueError("freshness selection changed baseline row identities")
    satellite_numbers = np.asarray(catalogue.satellite_numbers)
    nodes = np.arange(
        np.floor(min(t["t"].min() for t in tracks)) - 6,
        np.ceil(max(t["t"].max() for t in tracks)) + 7,
    )
    taus = np.arange(-5.0, 5.001, 0.25)
    positions, velocities, propagated_ids = propagate_candidate_states(
        catalogue,
        np.arange(len(satellite_numbers)),
        document["start_utc_ns"],
        nodes,
        np.array([0.0]),
    )
    positions, velocities = positions[:, 0], velocities[:, 0]

    def robust_score(residual, mask):
        train = residual[..., mask]
        offset = np.median(train, axis=-1)
        for _ in range(12):
            z = (train - offset[..., None]) / 100.0
            weights = 5 / (4 + z * z)
            offset = np.sum(weights * train, axis=-1) / np.sum(weights, axis=-1)
        z = (residual - offset[..., None]) / 100.0
        density = (
            gammaln(2.5)
            - gammaln(2)
            - 0.5 * np.log(4 * np.pi)
            - np.log(100.0)
            - 2.5 * np.log1p(z * z / 4)
        )
        return density[..., mask].sum(axis=-1) - 0.5 * offset**2 / 1e12

    center = [37.856249999999996, -122.484375]
    selected = {t["id"]: set() for t in tracks}
    minimum_mass = 1.0
    for east, north in [(0.0, 0.0), (-12.0, -12.0), (-12.0, 12.0), (12.0, -12.0), (12.0, 12.0)]:
        lat = center[0] + north / 111.195
        lon = center[1] + east / (111.195 * np.cos(np.radians(center[0])))
        a, b = np.radians([lat, lon])
        receiver = geodetic_to_ecef_km(lat, lon, 0)
        up = np.array([np.cos(a) * np.cos(b), np.cos(a) * np.sin(b), np.sin(a)])
        unit = positions - receiver
        unit /= np.linalg.norm(unit, axis=-1)[..., None]
        elevation = unit @ up
        active = np.flatnonzero(np.any(elevation >= 0, axis=1))
        prediction = (
            -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(unit[active] * velocities[active], axis=-1)
        )
        for track in tracks:
            q = track["t"][None, :] + taus[:, None] - nodes[0]
            low = np.floor(q).astype(int)
            weight = q - low
            predicted = prediction[:, low] * (1 - weight) + prediction[:, low + 1] * weight
            visible = np.any(
                (elevation[active][:, low] * (1 - weight) + elevation[active][:, low + 1] * weight)[
                    :, :, track["mask"]
                ]
                >= 0,
                axis=-1,
            )
            score = np.where(
                visible, robust_score(track["y"][None, None, :] - predicted, track["mask"]), -np.inf
            )
            count = min(8, len(active))
            chosen = np.argsort(score, axis=0)[-count:]
            selected[track["id"]].update(propagated_ids[active[chosen.ravel()]].tolist())
            mass = np.exp(
                logsumexp(np.take_along_axis(score, chosen, axis=0), axis=0)
                - logsumexp(score, axis=0)
            )
            minimum_mass = min(minimum_mass, float(np.min(mass)))
    output.mkdir(parents=True, exist_ok=False)
    shortlist = {key: sorted(value) for key, value in selected.items()}
    provider_sources = [
        {
            "provider": s.provider,
            "collected_utc_ns": s.collected_utc_ns,
            "snapshot_sha256": s.digest,
        }
        for s in latest
    ]
    (output / "shortlists.json").write_text(
        json.dumps(
            {
                "schema": "ds7-baseline-shortlists/v1",
                "session_id": session,
                "manifest_sha256": capture["manifest_sha256"],
                "baseline_snapshot_sha256": prepared.snapshot_digest,
                "provider_sources": provider_sources,
                "catalogue_size": len(satellite_numbers),
                "policy": (
                    "corrected DS6 causal newest-per-object among latest provider snapshots; "
                    "five anchors; 41 timing values; training-only top8 union"
                ),
                "minimum_anchor_top8_mass": minimum_mass,
                "shortlists": shortlist,
            },
            separators=(",", ":"),
        )
    )
    arrays = {"timing_grid_s": taus}
    track_meta = []
    for index, track in enumerate(tracks):
        ids = np.asarray(shortlist[track["id"]])
        pos, vel, _ = propagate_candidate_states(
            catalogue, ids, document["start_utc_ns"], track["t"], taus
        )
        arrays[f"candidate_ids_{index}"] = ids
        arrays[f"position_km_{index}"] = pos
        arrays[f"velocity_km_s_{index}"] = vel
        track_meta.append(
            {
                "index": index,
                "track_id": track["id"],
                "candidate_count": len(ids),
                "observation_count": len(track["t"]),
            }
        )
    np.savez_compressed(output / "banks.npz", **arrays)
    result = {
        "schema": "ds7-baseline-bank-export/v1",
        "session_id": session,
        "manifest_sha256": capture["manifest_sha256"],
        "baseline_snapshot_sha256": prepared.snapshot_digest,
        "provider_sources": provider_sources,
        "tracks_sha256": "sha256:" + hashlib.sha256(tracks_path.read_bytes()).hexdigest(),
        "catalogue_size": len(satellite_numbers),
        "tracks": track_meta,
        "elapsed_seconds": time.monotonic() - started,
    }
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tracks", type=Path)
    parser.add_argument("--banks", action="store_true")
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    rows = [r for r in plan["captures"] if r["session_id"] == args.session]
    if len(rows) != 1:
        raise ValueError("session absent or duplicated in plan")
    result = (
        export_banks(rows[0], args.tracks, args.output, args.bulk_root, args.tle_root)
        if args.banks
        else export(rows[0], args.output, args.bulk_root, args.tle_root)
    )
    print(
        json.dumps(
            {
                "session_id": result["session_id"],
                "tracks": len(result["tracks"]),
                "elapsed_seconds": result["elapsed_seconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
