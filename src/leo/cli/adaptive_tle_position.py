"""Publish blind bounded best-first TLE position-selection evidence."""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.contracts.adaptive_tle_position import (
    AdaptiveTleAccountingV1,
    AdaptiveTleCandidateV1,
    AdaptiveTlePositionDocumentV1,
    AdaptiveTlePriorResultV1,
    AdaptiveTleRegionV1,
)
from leo.contracts.digests import canonical_digest
from leo.presentation.adaptive_tle_position import render_adaptive_tle_position
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStore

PRIORS = {"sacramento": (38.5816, -121.4944), "reno": (39.5296, -119.8138)}
REFERENCE = (37.84903264307456, -122.4856541910174)
_WORKER_TRACKS = None


def configuration():
    return {
        "analysis_id": "scanner-adaptive-tle-position-v1",
        "priors": {name: {"latitude_deg": lat, "longitude_deg": lon, "radius_km": 500}
                   for name, (lat, lon) in PRIORS.items()},
        "tracks": {"minimum_span_s": 3, "minimum_observations": 6, "limit": None},
        "partition": "cf510316-fixed-partition-v1",
        "taus_s": list(range(-5, 6)),
        "search": {"levels_km": [100, 50, 25, 12.5], "budget_points": 400},
        "objective": "duration-weighted-capped-rmse-800hz-v1",
        "identity_selection": "randomized-evaluation-rms-v1",
        "qualifying_threshold_hz": 200,
        "known_position_used_for_inference": False,
    }


def adaptive_tle_position_complete(
    root: Path,
    session_id: str,
    *,
    expected_input=None,
    expected_analysis=None,
):
    store = AdaptiveTlePositionStore(root)
    status = store.status(session_id)
    if status.manifest is None:
        return False
    document = status.manifest.document
    return document.configuration_sha256 == canonical_digest(configuration()) and (
        expected_input is None or document.input_manifest_sha256 == expected_input
    ) and (
        expected_analysis is None or document.analysis_manifest_sha256 == expected_analysis
    ) and store.artifact(session_id) is not None


def _coordinates(latitude_deg, longitude_deg, east_km, north_km):
    angular = np.hypot(east_km, north_km) / 6371.0088
    bearing = np.arctan2(east_km, north_km)
    lat0, lon0 = np.deg2rad([latitude_deg, longitude_deg])
    latitude = np.arcsin(
        np.sin(lat0) * np.cos(angular)
        + np.cos(lat0) * np.sin(angular) * np.cos(bearing)
    )
    longitude = lon0 + np.arctan2(
        np.sin(bearing) * np.sin(angular) * np.cos(lat0),
        np.cos(angular) - np.sin(lat0) * np.sin(latitude),
    )
    return float(np.rad2deg(latitude)), float((np.rad2deg(longitude) + 180) % 360 - 180)


def _point_factory(latitude_deg, longitude_deg):
    from leo.analysis.adaptive_tle_prediction import ReceiverPoint
    from leo.sky.frames import geodetic_to_ecef_km

    def point(east_km, north_km):
        latitude, longitude = _coordinates(
            latitude_deg, longitude_deg, east_km, north_km
        )
        return ReceiverPoint(
            geodetic_to_ecef_km(latitude, longitude, 0),
            np.asarray(
                [
                    np.cos(np.deg2rad(latitude)) * np.cos(np.deg2rad(longitude)),
                    np.cos(np.deg2rad(latitude)) * np.sin(np.deg2rad(longitude)),
                    np.sin(np.deg2rad(latitude)),
                ]
            ),
        )

    return point


def _worker_start(evaluator):
    global _WORKER_TRACKS
    _WORKER_TRACKS = evaluator


def _worker_point(coordinate):
    from leo.analysis.adaptive_tle_position import score_point

    east, north = coordinate
    return score_point(float(east), float(north), _WORKER_TRACKS(float(east), float(north)))


def _candidate(score, spacing, latitude, longitude):
    lat, lon = _coordinates(latitude, longitude, score.east_km, score.north_km)
    weights = [row.weight_s for row in score.tracks if row.heldout_rms_hz is not None]
    values = [row.heldout_rms_hz for row in score.tracks if row.heldout_rms_hz is not None]
    uncapped = None
    if weights:
        uncapped = float(np.sqrt(np.average(np.square(values), weights=weights)))
    lat1, lon1, lat2, lon2 = map(math.radians, (lat, lon, *REFERENCE))
    haversine = (
        math.sin((lat1 - lat2) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon1 - lon2) / 2) ** 2
    )
    return AdaptiveTleCandidateV1(
        latitude_deg=lat,
        longitude_deg=lon,
        east_km=score.east_km,
        north_km=score.north_km,
        spacing_km=spacing,
        capped_weighted_rmse_hz=score.residual_rmse_hz,
        uncapped_weighted_rmse_hz=uncapped,
        matched_track_count=score.matched_track_count,
        unmatched_track_count=score.unmatched_track_count,
        qualifying_observation_count=score.qualifying_observation_count,
        horizontal_error_m=2 * 6_371_008.8 * math.asin(math.sqrt(min(1, haversine))),
    )


def _json_diagnostics(value):
    """Reject non-finite output and normalize dataclass tuples to JSON arrays."""
    return json.loads(json.dumps(value, allow_nan=False))


def run_adaptive_tle_position(root, tle_root, session_id, *, output_root=None, workers=4):
    from leo.analysis.adaptive_tle_position import adaptive_best_first_search
    from leo.analysis.adaptive_tle_prediction import (
        RegionalTrackPredictionEvaluator,
        build_prediction_banks,
    )
    from leo.operations.adaptive_tle_position_inputs import (
        AdaptiveTleInputUnavailable,
        prepare_adaptive_tle_position_inputs,
    )
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    destination = output_root or root
    store = AdaptiveTlePositionStore(destination, read_only=False)
    source_reader = ScannerTrackingInputStore(root)
    try:
        current_source = source_reader.load(session_id)
    finally:
        source_reader.close()
    with store.writer(session_id):
        if adaptive_tle_position_complete(
            destination,
            session_id,
            expected_input=current_source.input_manifest_sha256,
            expected_analysis=current_source.analysis_manifest_sha256,
        ):
            return store.status(session_id).manifest
        if store.status(session_id).manifest is not None:
            raise ValueError("adaptive TLE position publication uses another configuration")
        source_store = ScannerTrackingInputStore(root)
        started = time.monotonic()
        try:
            source = source_store.load(session_id)
            try:
                prepared = prepare_adaptive_tle_position_inputs(
                    session_id, inputs=source_store, archive=TleArchiveReader(tle_root)
                )
            except AdaptiveTleInputUnavailable as error:
                document = AdaptiveTlePositionDocumentV1(
                    session_id=session_id,
                    input_manifest_sha256=source.input_manifest_sha256,
                    analysis_manifest_sha256=source.analysis_manifest_sha256,
                    configuration_sha256=canonical_digest(configuration()),
                    evidence_sha256=canonical_digest(
                        {"session_id": session_id, "reason": str(error)}
                    ),
                    state="insufficient",
                    priors=(),
                    reasons=(str(error),),
                )
                return store.publish(document, render_adaptive_tle_position(document))
        finally:
            source_store.close()
        banks, bank_receipt = build_prediction_banks(
            prepared.catalogue,
            prepared.candidate_indices,
            prepared.start_utc_ns,
            prepared.tracks,
        )
        prior_results, point_inventory, selected_tracks, finest_tracks = [], {}, {}, {}
        traces, frontiers = {}, {}
        context = multiprocessing.get_context("fork")
        for name, (latitude, longitude) in PRIORS.items():
            evaluator = RegionalTrackPredictionEvaluator(
                banks, _point_factory(latitude, longitude)
            )
            with context.Pool(workers, initializer=_worker_start, initargs=(evaluator,)) as pool:
                result = adaptive_best_first_search(
                    lambda points: pool.map(_worker_point, np.asarray(points).tolist())
                )
            spacing = {
                (row["east_km"], row["north_km"]): row["spacing_km"]
                for row in result.trace
                if row["event"] == "evaluate"
            }
            selected = _candidate(
                result.global_incumbent,
                spacing[(result.global_incumbent.east_km, result.global_incumbent.north_km)],
                latitude,
                longitude,
            )
            finest = _candidate(result.finest_incumbent, 12.5, latitude, longitude)
            accounting = AdaptiveTleAccountingV1(
                reconstructed_track_count=prepared.reconstructed_track_count,
                eligible_track_count=prepared.eligible_track_count,
                eligible_observation_count=prepared.eligible_observation_count,
                evaluated_point_count=len(result.all_evaluations),
                finest_evaluated_point_count=len(result.finest_evaluations),
                deferred_cell_count=len(result.deferred_cells),
                runtime_ms=round((time.monotonic() - started) * 1000),
            )
            prior_results.append(
                AdaptiveTlePriorResultV1(
                    name=name,
                    region=AdaptiveTleRegionV1(
                        center_latitude_deg=latitude, center_longitude_deg=longitude
                    ),
                    search_complete=result.complete,
                    stop_reason=result.stop_reason,
                    accounting=accounting,
                    selected=selected,
                    finest=finest,
                )
            )
            point_inventory[name] = [
                {
                    "east_km": row.east_km,
                    "north_km": row.north_km,
                    "capped_weighted_rmse_hz": row.residual_rmse_hz,
                    "qualifying_observation_count": row.qualifying_observation_count,
                    "matched_track_count": row.matched_track_count,
                }
                for row in result.all_evaluations
            ]
            selected_tracks[name] = [asdict(row) for row in result.global_incumbent.tracks]
            finest_tracks[name] = [asdict(row) for row in result.finest_incumbent.tracks]
            traces[name] = list(result.trace)
            frontiers[name] = [asdict(row) for row in result.deferred_cells]
        diagnostics = _json_diagnostics(
            {
                    "evaluated_points": point_inventory,
                    "selected_track_scores": selected_tracks,
                    "finest_track_scores": finest_tracks,
                    "search_trace": traces,
                    "deferred_frontier": frontiers,
                    "track_evidence": list(prepared.track_evidence),
                    "prediction_bank": asdict(bank_receipt),
                    "snapshot_digest": prepared.snapshot_digest,
                    "snapshot_collected_utc_ns": prepared.snapshot_collected_utc_ns,
                    "configuration": configuration(),
                    "reference_evaluation_only": {
                        "latitude_deg": REFERENCE[0],
                        "longitude_deg": REFERENCE[1],
                        "used_for_inference": False,
                    },
            }
        )
        document = AdaptiveTlePositionDocumentV1(
            session_id=session_id,
            input_manifest_sha256=prepared.input_manifest_sha256,
            analysis_manifest_sha256=prepared.analysis_manifest_sha256,
            configuration_sha256=canonical_digest(configuration()),
            evidence_sha256=prepared.evidence_sha256,
            state="diagnostic",
            priors=tuple(prior_results),
            diagnostics=diagnostics,
        )
        return store.publish(document, render_adaptive_tle_position(document))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    manifest = run_adaptive_tle_position(
        args.bulk_root, args.tle_root, args.session_id,
        output_root=args.output_root, workers=args.workers,
    )
    print(json.dumps({"state": "complete", "session_id": args.session_id,
                      "adaptive_tle_position_state": manifest.document.state}))


if __name__ == "__main__":
    main()
