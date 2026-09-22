#!/usr/bin/env python3
"""Research-only uncapped RF track export for the pending 12-hour study.

This program reads public scanner inputs, reconstructs trajectories directly
from saved fractional GLRT candidates, and writes one JSON shard per session.
It does not read tracking reviews, known receiver coordinates, satellite
shortlists, or truth.  It references and inventories a causal full catalogue
snapshot but deliberately does not propagate it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Protocol

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig,
    persistent_hop_tracklet_graph,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.scanner_trajectory import (
    project_scanner_candidates,
    timing_is_qualified_for_tle,
)
from leo.contracts.digests import canonical_digest
from leo.sky.propagation import parse_element_set_records

ALGORITHM = "research-uncapped-glrt-track-export-v1"
CAUSAL_GUARD_NS = 505_000_000_000


class ScannerInputs(Protocol):
    def load(self, session_id: str): ...


class TleArchive(Protocol):
    def select_latest_before(self, utc_ns: int): ...
    def read(self, snapshot) -> str: ...


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _contract_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"unsupported contract value {type(value).__name__}")


def _write_create_only(path: Path, payload: bytes) -> None:
    """Create atomically; an exact existing retry is accepted."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == payload:
            return
        raise FileExistsError(f"existing shard differs: {path}")
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


def _source_contracts() -> dict[str, str]:
    # Record the exact exporter and public adapters used for every sealed shard.
    modules = {
        "exporter": Path(__file__).resolve(),
        "scanner_tracking_source": Path(
            sys.modules["leo.storage.scanner_tracking_source"].__file__
        ),
        "scanner_trajectory": Path(sys.modules["leo.application.scanner_trajectory"].__file__),
        "persistent_hop_trajectory": Path(
            sys.modules["leo.analysis.persistent_hop_trajectory"].__file__
        ),
        "tle_archive": Path(sys.modules["leo.operations.tle_archive"].__file__),
    }
    return {name: _sha256(path) for name, path in sorted(modules.items())}


def _row_document(row, selected_source) -> dict[str, Any]:
    return {
        "observation_id": row.observation_id,
        "source_group_id": row.source_group_id,
        "support_start_utc_ns": row.support_start_utc_ns,
        "support_center_utc_ns": row.support_center_utc_ns,
        "support_end_utc_ns": row.support_end_utc_ns,
        "measured_cfo_hz": row.measured_cfo_hz,
        "standard_uncertainty_hz": row.standard_uncertainty_hz,
        "fractional_candidate_rank": selected_source.candidate_rank,
        "fractional_exact_score": selected_source.exact_score,
        "fractional_control_score": selected_source.control_score,
        "fractional_margin": selected_source.margin,
        "source_sample_start": row.source_sample_start,
        "source_sample_end": row.source_sample_end,
    }


def _catalogue_reference(archive: TleArchive, cutoff_utc_ns: int) -> dict[str, Any]:
    snapshot = archive.select_latest_before(cutoff_utc_ns)
    if snapshot.collected_utc_ns >= cutoff_utc_ns:
        raise ValueError("archive returned a non-causal snapshot")
    raw = archive.read(snapshot)
    retained, debris = exclude_labelled_starlink_debris(raw)
    records = parse_element_set_records(retained)
    starlink = tuple(record for record in records if record.name.upper().startswith("STARLINK"))
    return {
        "digest": snapshot.digest,
        "collected_utc_ns": snapshot.collected_utc_ns,
        "provider": snapshot.provider,
        "byte_size": snapshot.byte_size,
        "causal_cutoff_utc_ns": cutoff_utc_ns,
        "raw_object_count": len(records) + len(debris),
        "labelled_debris_exclusion_count": len(debris),
        "full_retained_object_count": len(records),
        "full_retained_starlink_count": len(starlink),
        "catalogue_membership_digest": canonical_digest(
            [
                {
                    "catalog_number": record.satellite_number,
                    "name": record.name,
                    "element_text_digest": "sha256:"
                    + hashlib.sha256(record.text.encode()).hexdigest(),
                }
                for record in starlink
            ]
        ),
        "states_propagated": False,
        "site_conditioned": False,
    }


def _select_disjoint_tracklets(candidates):
    """Greedily retain the preordered RF graphs without reusing a source group."""
    accepted = []
    rejected_overlap = []
    owned_source_groups: set[str] = set()
    for tracklet, rows in candidates:
        source_groups = {row.source_group_id for row in rows}
        overlap = sorted(source_groups & owned_source_groups)
        if overlap:
            rejected_overlap.append(
                {
                    "tracklet_id": tracklet.tracklet_id,
                    "observation_count": len(rows),
                    "overlapping_source_group_count": len(overlap),
                    "overlapping_source_group_digest": canonical_digest(overlap),
                }
            )
            continue
        owned_source_groups.update(source_groups)
        accepted.append((tracklet, rows))
    return accepted, rejected_overlap


def export_session(
    session_id: str, *, inputs: ScannerInputs, archive: TleArchive, output: Path
) -> dict[str, Any]:
    source = inputs.load(session_id)
    if not timing_is_qualified_for_tle(source.timing):
        raise ValueError(f"{session_id}: UTC is unqualified")
    projected = project_scanner_candidates(source)
    projected_by_id = {candidate.candidate_id: candidate for candidate in projected}
    config = PersistentHopTrajectoryConfig()
    trajectory = reconstruct_persistent_hop_trajectories(projected, config=config)
    tracklets = {tracklet.tracklet_id: tracklet for tracklet in trajectory.tracklets}

    # A tracklet can appear in several hypotheses.  Bind each distinct graph and
    # reject any tracklet whose graph differs between hypotheses.
    graphs: dict[str, Any | None] = {}
    hypothesis_inventory = []
    for rank, hypothesis in enumerate(trajectory.hypotheses):
        hypothesis_inventory.append(
            {
                "rank": rank,
                "hypothesis_id": hypothesis.hypothesis_id,
                "tracklet_ids": list(hypothesis.tracklet_ids),
                "aggregate_weighted_support": hypothesis.aggregate_weighted_support,
                "source_group_count": hypothesis.source_group_count,
            }
        )
        for tracklet_id in hypothesis.tracklet_ids:
            graph = persistent_hop_tracklet_graph(hypothesis, tracklet_id)
            previous = graphs.get(tracklet_id)
            signature = tuple(row.observation_id for row in graph.observations)
            if previous is None and tracklet_id not in graphs:
                graphs[tracklet_id] = graph
            elif previous is not None and signature != tuple(
                row.observation_id for row in previous.observations
            ):
                graphs[tracklet_id] = None

    ambiguous = sorted(tracklet_id for tracklet_id, graph in graphs.items() if graph is None)
    candidates = []
    for tracklet_id, graph in graphs.items():
        if graph is None:
            continue
        rows = tuple(
            sorted(
                graph.observations, key=lambda row: (row.support_center_utc_ns, row.observation_id)
            )
        )
        tracklet = tracklets[tracklet_id]
        candidates.append((tracklet, graph, rows))
    candidates.sort(
        key=lambda item: (
            -item[0].weighted_support,
            -len(item[2]),
            item[0].start_utc_ns,
            item[0].tracklet_id,
        )
    )

    accepted, rejected_overlap = _select_disjoint_tracklets(
        [(tracklet, rows) for tracklet, _graph, rows in candidates]
    )

    tracks = []
    all_observation_ids: set[str] = set()
    for tracklet, rows in sorted(
        accepted, key=lambda item: (item[0].start_utc_ns, item[0].tracklet_id)
    ):
        selected_by_group = {
            projected_by_id[point.candidate_id].source_group_id: projected_by_id[point.candidate_id]
            for point in tracklet.points
        }
        if set(selected_by_group) != {row.source_group_id for row in rows}:
            raise ValueError("tracklet points do not bind exported RF observations")
        observation_ids = {row.observation_id for row in rows}
        if len(observation_ids) != len(rows) or observation_ids & all_observation_ids:
            raise ValueError("deterministic ownership produced duplicate observations")
        all_observation_ids.update(observation_ids)
        lane = tracklet.lane_key
        document = {
            "tracklet_id": tracklet.tracklet_id,
            "lane": {
                "channel": lane[0],
                "edge": lane[1].value,
                "receiver_id": lane[2],
                "actual_rf_hz": lane[3],
                "canonical_rf_hz": trajectory.canonical_rf_hz,
            },
            "start_utc_ns": tracklet.start_utc_ns,
            "end_utc_ns": tracklet.end_utc_ns,
            "weighted_support": tracklet.weighted_support,
            "normalized_rate_hz_per_s": tracklet.normalized_rate_hz_per_s,
            "observation_count": len(rows),
            "observations": [
                _row_document(row, selected_by_group[row.source_group_id]) for row in rows
            ],
        }
        document["support_digest"] = canonical_digest(document)
        tracks.append(document)

    if not tracks:
        raise ValueError(f"{session_id}: reconstruction produced no unique RF tracklets")
    earliest = min(row["support_start_utc_ns"] for track in tracks for row in track["observations"])
    catalogue = _catalogue_reference(archive, earliest - CAUSAL_GUARD_NS)
    saved_candidate_count = sum(len(probe.candidates) for probe in source.probes)
    passing_candidate_count = sum(
        candidate.passed_fractional_margin_gate
        for probe in source.probes
        for candidate in probe.candidates
    )
    accounting = {
        "saved_probe_count": len(source.probes),
        "saved_fractional_candidate_count": saved_candidate_count,
        "margin_passing_candidate_count": passing_candidate_count,
        "projected_candidate_count": len(projected),
        "reconstructed_hypothesis_count": len(trajectory.hypotheses),
        "reconstructed_tracklet_count": len(trajectory.tracklets),
        "distinct_tracklet_graph_count": len(graphs),
        "ambiguous_tracklet_graph_count": len(ambiguous),
        "overlap_rejected_tracklet_count": len(rejected_overlap),
        "exported_tracklet_count": len(tracks),
        "exported_observation_count": len(all_observation_ids),
    }
    source_contracts = _source_contracts()
    configuration = {
        "algorithm": ALGORITHM,
        "trajectory_configuration_digest": config.digest,
        "population": "all-qualified-saved-fractional-glrt-observations-v1",
        "ownership": "weighted-support-source-disjoint-greedy-v1",
        "causal_guard_ns": CAUSAL_GUARD_NS,
        "minimum_track_observations": None,
        "minimum_track_span_s": None,
        "maximum_tracks": None,
        "maximum_observations_per_track": None,
        "known_position_used": False,
        "saved_site_conditioned_reviews_used": False,
    }
    shard = {
        "schema": "position-research-rf-shard-v1",
        "session": {
            "session_id": session_id,
            "capture_mode": source.capture_mode,
            "capture_start_utc_ns": source.capture_start_utc_ns,
            "capture_end_utc_ns": source.capture_end_utc_ns,
            "sample_rate_hz": source.sample_rate_hz,
            "radio_id": source.radio_id,
            "stream_generation": source.stream_generation,
            "input_manifest_sha256": source.input_manifest_sha256,
            "analysis_manifest_sha256": source.analysis_manifest_sha256,
            "raw_recording_authority_digest": source.raw_recording_authority_digest,
            "timing_authority_digest": canonical_digest(_contract_value(source.timing)),
        },
        "configuration": configuration,
        "configuration_digest": canonical_digest(configuration),
        "source_contracts": source_contracts,
        "source_contracts_digest": canonical_digest(source_contracts),
        "catalogue_snapshot": catalogue,
        "accounting": accounting,
        "hypotheses": hypothesis_inventory,
        "ambiguous_tracklet_ids": ambiguous,
        "overlap_rejections": rejected_overlap,
        "tracks": tracks,
    }
    shard["content_digest"] = canonical_digest(shard)
    path = output / f"{session_id}.json"
    payload = _json_bytes(shard)
    _write_create_only(path, payload)
    return {
        "session_id": session_id,
        "path": str(path),
        "file_digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "content_digest": shard["content_digest"],
        "accounting": accounting,
        "catalogue_snapshot_digest": catalogue["digest"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="public scanner store root")
    parser.add_argument("--tle-root", type=Path, required=True, help="read-only TLE archive root")
    parser.add_argument("--output", type=Path, required=True, help="new or retry shard directory")
    parser.add_argument("--session", action="append", required=True, help="session ID; repeatable")
    args = parser.parse_args()

    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    inputs = ScannerTrackingInputStore(args.root)
    archive = TleArchiveReader(args.tle_root)
    try:
        results = [
            export_session(session_id, inputs=inputs, archive=archive, output=args.output)
            for session_id in args.session
        ]
    finally:
        inputs.close()
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
