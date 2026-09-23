"""Inventory existing stream-1 GLRT branches without opening recorded IQ."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools import report_glrt_phase_segment_comparison as evidence_reader

ROOT = Path(__file__).resolve().parents[4]
OUTPUT = Path(__file__).with_name("continuous-branch-inventory.json")
BULK_ROOT = Path("/srv/bulk/leo")
SESSION = "cap-20260825T010019-89c2889553e0"
RUN = "capture-34471d9087a94ec1b043951350de3956"
INTERVAL = (31.8, 32.8)
PATHS = {
    0: {
        "scope": "sha256:b6c2f8f86668304044c5c41903004b13a37d94328762172d83577cce4c41170b",
        "selected": "sha256:be34d146cfec9d9fe8b1fd1a73e2dd2c0fa6cc3931eed839f24d8539bcaae69d",
        "secondary": "sha256:799f42467ed5a262172b2bf9c514722ce76de01d3893eed727e82ade6572868e",
    },
    1: {
        "scope": "sha256:deec3913863c3241497d7c81c48d3891a601e7b9dd823a06088b6c3a7210e885",
        "selected": "sha256:5f2716dd54e070caeac4cc1ea76b694bdea81a4694d9b70d25432e84b238e856",
        "secondary": "sha256:3b1281ab14c21bc0c8a468e760d573bc47cfd3cb7c489d6da5d5827d13641438",
    },
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def branch_row(track) -> dict:
    return {
        "branch_id": track.branch_id,
        "representative_trajectory_id": track.representative_trajectory_id,
        "alias_trajectory_ids": list(track.alias_trajectory_ids),
        "start_s": track.start_s,
        "end_s": track.end_s,
        "span_s": track.span_s,
        "observation_count": track.observation_count,
        "evaluated_probe_count": track.evaluated_probe_count,
        "qualified_75ms_window_count": track.qualified_75ms_window_count,
        "glrt_rate_hz_s": track.glrt_rate_hz_s,
        "median_block_corrected_margin": track.median_block_corrected_margin,
        "intersects_fixed_interval": (
            track.end_s >= INTERVAL[0] and track.start_s <= INTERVAL[1]
        ),
    }


def source_ids(track) -> set[str]:
    canonical = {
        row.observation_id: row for row in track.evidence.dealiased_bank.observations
    }
    return {
        source_id
        for observation_id in track.track.observation_ids
        if observation_id in canonical
        for source_id in canonical[observation_id].source_observation_ids
    }


def overlap(left: set[str], right: set[str]) -> dict:
    shared = sorted(left & right)
    return {
        "left_count": len(left),
        "right_count": len(right),
        "shared_count": len(shared),
        "shared_ids": shared,
    }


def build() -> dict:
    manifest, evidence = evidence_reader.load_path_evidence(BULK_ROOT, SESSION, RUN)
    tracks = evidence_reader.deduplicate_glrt_tracks(evidence)
    by_branch = {(track.scope, track.branch_id): track for track in tracks}
    paths = []
    selected_tracks = {}
    for receiver_id, authority in PATHS.items():
        scope = authority["scope"]
        rows = [track for track in tracks if track.scope == scope]
        selected = by_branch[(scope, authority["selected"])]
        secondary = by_branch[(scope, authority["secondary"])]
        selected_tracks[receiver_id, "selected"] = selected
        selected_tracks[receiver_id, "secondary"] = secondary
        paths.append(
            {
                "stream_id": "stream-1",
                "receiver_id": receiver_id,
                "scope": scope,
                "source_product_digests": rows[0].evidence.source_digests,
                "branch_count": len(rows),
                "fixed_interval_branch_count": sum(
                    row.end_s >= INTERVAL[0] and row.start_s <= INTERVAL[1] for row in rows
                ),
                "branches": [branch_row(row) for row in rows],
                "selected_secondary_overlap": {
                    "canonical_observation_ids": overlap(
                        set(selected.track.observation_ids), set(secondary.track.observation_ids)
                    ),
                    "path_local_source_observation_ids": overlap(
                        source_ids(selected), source_ids(secondary)
                    ),
                },
            }
        )
    cross_receiver = []
    for left_role in ("selected", "secondary"):
        for right_role in ("selected", "secondary"):
            left = selected_tracks[0, left_role]
            right = selected_tracks[1, right_role]
            start = max(left.start_s, right.start_s, INTERVAL[0])
            end = min(left.end_s, right.end_s, INTERVAL[1])
            cross_receiver.append(
                {
                    "rx0_role": left_role,
                    "rx0_branch_id": left.branch_id,
                    "rx1_role": right_role,
                    "rx1_branch_id": right.branch_id,
                    "fixed_interval_overlap_start_s": start,
                    "fixed_interval_overlap_end_s": end,
                    "fixed_interval_overlap_s": max(0.0, end - start),
                    "canonical_observation_ids": overlap(
                        set(left.track.observation_ids), set(right.track.observation_ids)
                    ),
                    "local_detection_key_digest_collisions": overlap(
                        source_ids(left), source_ids(right)
                    ),
                }
            )
    helper = Path(evidence_reader.__file__)
    return {
        "schema": "continuous-glrt-branch-inventory/v1",
        "session_id": SESSION,
        "analysis_run_id": RUN,
        "analysis_manifest_sha256": digest(
            BULK_ROOT / "analysis" / SESSION / RUN / "manifest.json"
        ),
        "fixed_interval_s": list(INTERVAL),
        "complete_path_scope_count": len(evidence),
        "deduplicated_branch_count_all_paths": len(tracks),
        "paths": paths,
        "cross_receiver_candidate_overlaps": cross_receiver,
        "identifier_note": (
            "The raw source-observation digest is canonical_digest({sample_start, "
            "candidate_rank, method}) and omits receiver/path identity. Within one path, zero "
            "overlap establishes disjoint archived observation membership but not distinct "
            "physical emitters. Across receivers, equal digests are namespace collisions for "
            "matching local time/rank/method tuples and provide no source-pairing evidence. "
            "Counts use each branch's complete archived support, not only the fixed interval."
        ),
        "interpretation": (
            "Temporal branch overlap establishes candidate material only. Identifier equality "
            "across receivers is not pairing authority. Branch IDs do not prove cross-receiver "
            "source matching, distinct emitters, or phase isolation."
        ),
        "no_iq_read": True,
        "no_phase_reanalysis": True,
        "source_sha256": {
            str(Path(__file__).relative_to(ROOT)): digest(Path(__file__)),
            str(helper.relative_to(ROOT)): digest(helper),
        },
        "run_manifest_identity": {
            "session_id": manifest["session_id"],
            "run_id": manifest["run_id"],
        },
    }


if __name__ == "__main__":
    if OUTPUT.exists():
        raise ValueError("fresh output path required")
    OUTPUT.write_text(json.dumps(build(), indent=2, allow_nan=False) + "\n")
