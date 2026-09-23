"""Read-only public-port inputs for the fast coverage research benchmark."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

from leo.contracts.catalogue_association import CataloguePredictionSupportV1
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

KERNEL_PATH = Path(__file__).with_name("map_randomized_tle_coverage.py")


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def reference_kernel():
    spec = importlib.util.spec_from_file_location("fast_coverage_reference", KERNEL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("reference coverage kernel unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def catalogue_authority(
    session: str, evidence_dir: Path, tle_root: Path, start_ns: int
) -> tuple[object, np.ndarray, dict]:
    """Use the saved evidence only for catalogue authority, never its old split."""
    evidence_path = evidence_dir / "evidence" / f"{session}.json"
    authority = json.loads(evidence_path.read_text())["inventory"]
    if authority["session_id"] != session or authority["reference_utc_ns"] != start_ns:
        raise ValueError("catalogue evidence does not match the current recording")
    if authority.get("known_position_used") is not False or authority.get("fixed_candidates"):
        raise ValueError("blind search requires position-free, unrestricted catalogue evidence")
    tle_path = evidence_dir / "evidence" / authority["tle_file"]
    cutoff = start_ns - 505_000_000_000
    if file_digest(tle_path) != authority["tle_digest"] or authority["tle_collected_ns"] >= cutoff:
        raise ValueError("catalogue digest or causal cutoff mismatch")
    snapshot = TleArchiveReader(tle_root).select_latest_before(cutoff)
    if (
        snapshot.digest != authority["tle_digest"]
        or snapshot.collected_utc_ns != authority["tle_collected_ns"]
    ):
        raise ValueError("saved catalogue is not the exact latest causal snapshot")
    catalogue = parse_element_sets(tle_path.read_text())
    indices = np.asarray([
        i for i, name in enumerate(catalogue.names)
        if name.startswith("STARLINK") and not name.upper().endswith(" DEB")
    ], dtype=int)
    if not len(indices):
        raise ValueError("causal catalogue has no eligible Starlink entries")
    return catalogue, indices, {
        "snapshot_digest": snapshot.digest,
        "snapshot_collected_utc_ns": snapshot.collected_utc_ns,
        "evidence_digest": file_digest(evidence_path),
        "catalogue_cutoff_utc_ns": cutoff,
        "catalogue_candidate_count": len(indices),
        "archived_evidence_partition_not_used": authority.get("partition"),
    }


def load(
    session: str,
    evidence_dir: Path,
    bulk_root: Path = Path("/srv/bulk/leo"),
    tle_root: Path = Path("/var/lib/leo/tle"),
    *,
    track_count: int = 10,
) -> dict:
    """Load standard longest tracks via the existing read-only public source port."""
    if track_count < 1:
        raise ValueError("positive track count required")
    kernel = reference_kernel()
    before = file_digest(KERNEL_PATH)
    start, config, selected, eligible, reconstructed = kernel._tracks(
        session, bulk_root, track_count
    )
    catalogue, indices, provenance = catalogue_authority(session, evidence_dir, tle_root, start)
    tracks, observed_ids = [], set()
    for rank, (tracklet_id, graph, rows, times, span) in enumerate(selected, 1):
        ids = tuple(row.observation_id for row in rows)
        if len(set(ids)) != len(ids) or observed_ids.intersection(ids):
            raise ValueError("overlapping observation IDs require union-aware coverage scoring")
        observed_ids.update(ids)
        measured = np.asarray([row.measured_cfo_hz for row in rows], dtype=float)
        times = np.asarray(times, dtype=float)
        if not np.all(np.isfinite(measured)) or not np.all(np.isfinite(times)):
            raise ValueError("nonfinite trajectory evidence")
        measured.setflags(write=False)
        times.setflags(write=False)
        tracks.append({
            "rank": rank,
            "tracklet_id": tracklet_id,
            "support_digest": CataloguePredictionSupportV1.from_graph(graph).content_digest,
            "observation_ids": ids,
            "times_s": times,
            "measured_hz": measured,
            "span_s": float(span),
            "observation_count": len(ids),
        })
    if len(tracks) != track_count:
        raise ValueError("recording has fewer eligible tracks than requested")
    if file_digest(KERNEL_PATH) != before:
        raise ValueError("reference source changed while loading evidence")
    provenance.update({
        "session_id": session,
        "truth_accessed": False,
        "fixed_satellite_identities_used": False,
        "source_port": "ScannerTrackingInputStore via standard longest-track selection",
        "reference_kernel_digest": before,
        "loader_digest": file_digest(Path(__file__)),
        "reconstructed_track_count": reconstructed,
        "eligible_track_count": eligible,
        "selected_track_count": len(tracks),
        "unique_observation_count": len(observed_ids),
        "observation_ids_disjoint": True,
    })
    return {
        "start_ns": start,
        "catalogue": catalogue,
        "indices": indices,
        "trajectory_digest": config.digest,
        "tracks": tracks,
        "provenance": provenance,
    }
