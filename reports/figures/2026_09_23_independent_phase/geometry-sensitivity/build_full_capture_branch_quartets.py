"""Inventory full-capture four-branch co-occurrence from archived metadata."""

from __future__ import annotations

import hashlib
import itertools
import json
from collections import Counter
from pathlib import Path

from leo.analysis.starlink.kalman_tracking import canonical_digest
from tools import report_glrt_phase_segment_comparison as evidence_reader

ROOT = Path(__file__).resolve().parents[4]
OUTPUT = Path(__file__).with_name("full-capture-branch-quartets.json")
BULK_ROOT = Path("/srv/bulk/leo")
SESSION = "cap-20260825T010019-89c2889553e0"
RUN = "capture-34471d9087a94ec1b043951350de3956"
SAMPLE_RATE_HZ = 2_500_000
FRAME_PERIOD_SAMPLES = SAMPLE_RATE_HZ / 750
TIMING_DIAGNOSTIC_SAMPLES = 2.0
SCOPES = {
    0: "sha256:b6c2f8f86668304044c5c41903004b13a37d94328762172d83577cce4c41170b",
    1: "sha256:deec3913863c3241497d7c81c48d3891a601e7b9dd823a06088b6c3a7210e885",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wrap(value: float, period: float) -> float:
    return (value + period / 2) % period - period / 2


def associated_by_probe(track) -> tuple[dict[int, dict], dict]:
    canonical = {
        observation.observation_id: observation
        for observation in track.evidence.dealiased_bank.observations
    }
    source_ids = {
        source_id
        for observation_id in track.track.observation_ids
        for source_id in canonical[observation_id].source_observation_ids
    }
    grouped: dict[int, list[dict]] = {}
    for detection in track.evidence.pilot_scan["detections"]:
        sample = int(detection["sample_start"])
        for candidate in detection["candidates"]:
            local_id = canonical_digest(
                {
                    "sample_start": sample,
                    "candidate_rank": candidate["rank"],
                    "method": "glrt64",
                }
            )
            if local_id not in source_ids:
                continue
            grouped.setdefault(sample, []).append(
                {
                    "candidate_rank": candidate["rank"],
                    "local_epoch_sample": candidate["local_epoch_sample"],
                }
            )
    unique = {sample: rows[0] for sample, rows in grouped.items() if len(rows) == 1}
    return unique, {
        "associated_opportunity_count": sum(len(rows) for rows in grouped.values()),
        "associated_probe_count": len(grouped),
        "unique_association_probe_count": len(unique),
        "ambiguous_association_probe_count": sum(len(rows) > 1 for rows in grouped.values()),
        "ambiguous_probe_starts": sorted(
            sample for sample, rows in grouped.items() if len(rows) > 1
        ),
    }


def timing_offset(left: dict, right: dict) -> float:
    return wrap(
        right["local_epoch_sample"] - left["local_epoch_sample"], FRAME_PERIOD_SAMPLES
    )


def has_glrt64(candidate: dict) -> bool:
    return any(score["method"] == "glrt64" for score in candidate["scores"])


def runs(samples: list[int], cadence: int) -> list[dict]:
    if not samples:
        return []
    result = []
    start = previous = samples[0]
    count = 1
    for sample in samples[1:]:
        if sample - previous == cadence:
            count += 1
        else:
            result.append(
                {
                    "start_s": start / SAMPLE_RATE_HZ,
                    "end_s": previous / SAMPLE_RATE_HZ,
                    "probe_count": count,
                }
            )
            start, count = sample, 1
        previous = sample
    result.append(
        {
            "start_s": start / SAMPLE_RATE_HZ,
            "end_s": previous / SAMPLE_RATE_HZ,
            "probe_count": count,
        }
    )
    return result


def build() -> dict:
    manifest, evidence = evidence_reader.load_path_evidence(BULK_ROOT, SESSION, RUN)
    tracks = evidence_reader.deduplicate_glrt_tracks(evidence)
    scoped = {
        receiver: [row for row in tracks if row.scope == scope]
        for receiver, scope in SCOPES.items()
    }
    raw_multi_probes = {}
    bank_audit = {}
    for receiver, rows in scoped.items():
        evidence_row = rows[0].evidence
        raw_multi_probes[receiver] = {
            int(detection["sample_start"])
            for detection in evidence_row.pilot_scan["detections"]
            if sum(has_glrt64(candidate) for candidate in detection["candidates"]) >= 2
        }
        degree_counts = Counter(
            track.polynomial_degree for track in evidence_row.final_bank.trajectories
        )
        aliases: dict[str, list] = {}
        for track in evidence_row.final_bank.trajectories:
            aliases.setdefault(track.branch_id, []).append(track)
        bank_audit[receiver] = {
            "trajectory_count": len(evidence_row.final_bank.trajectories),
            "polynomial_degree_counts": {
                str(degree): count for degree, count in sorted(degree_counts.items())
            },
            "branch_count": len(aliases),
            "alias_count_by_branch": {
                branch: len(branch_aliases)
                for branch, branch_aliases in sorted(aliases.items())
            },
            "branches_with_different_alias_observation_membership": sum(
                len(
                    {
                        tuple(sorted(alias.observation_ids))
                        for alias in branch_aliases
                    }
                )
                > 1
                for branch_aliases in aliases.values()
            ),
        }
    ledgers, branch_inventory = {}, []
    for receiver, rows in scoped.items():
        for track in rows:
            ledger, accounting = associated_by_probe(track)
            key = (receiver, track.branch_id)
            ledgers[key] = ledger
            branch_inventory.append(
                {
                    "receiver_id": receiver,
                    "scope": track.scope,
                    "branch_id": track.branch_id,
                    "start_s": track.start_s,
                    "end_s": track.end_s,
                    "observation_count": track.observation_count,
                    "evaluated_probe_count": track.evaluated_probe_count,
                    "qualified_75ms_window_count": track.qualified_75ms_window_count,
                    **accounting,
                }
            )
    by_probe: dict[int, dict[int, list[str]]] = {}
    for (receiver, branch), ledger in ledgers.items():
        for sample in ledger:
            by_probe.setdefault(sample, {0: [], 1: []})[receiver].append(branch)
    cadence_counts: dict[int, int] = {}
    ordered_probes = sorted(by_probe)
    for left, right in zip(ordered_probes, ordered_probes[1:], strict=False):
        cadence_counts[right - left] = cadence_counts.get(right - left, 0) + 1
    cadence = max(cadence_counts, key=cadence_counts.get)

    receiver_pairs = []
    for receiver in sorted(SCOPES):
        pair_samples: dict[tuple[str, str], dict[str, list[int]]] = {}
        for sample, receivers in by_probe.items():
            for pair in itertools.combinations(sorted(receivers[receiver]), 2):
                left = ledgers[receiver, pair[0]][sample]
                right = ledgers[receiver, pair[1]][sample]
                kind = (
                    "reused_candidate_rank_probe_starts"
                    if left["candidate_rank"] == right["candidate_rank"]
                    else "distinct_candidate_rank_probe_starts"
                )
                pair_samples.setdefault(
                    pair,
                    {
                        "distinct_candidate_rank_probe_starts": [],
                        "reused_candidate_rank_probe_starts": [],
                    },
                )[kind].append(sample)
        for pair, samples in pair_samples.items():
            distinct = sorted(samples["distinct_candidate_rank_probe_starts"])
            reused = sorted(samples["reused_candidate_rank_probe_starts"])
            receiver_pairs.append(
                {
                    "receiver_id": receiver,
                    "branch_ids": list(pair),
                    "distinct_candidate_rank_probe_count": len(distinct),
                    "distinct_candidate_rank_probe_starts": distinct,
                    "distinct_candidate_rank_runs": runs(distinct, cadence),
                    "reused_candidate_rank_probe_count": len(reused),
                    "reused_candidate_rank_probe_starts": reused,
                }
            )
    receiver_pairs.sort(
        key=lambda row: (
            row["receiver_id"],
            -row["distinct_candidate_rank_probe_count"],
            row["branch_ids"],
        )
    )

    quartets: dict[tuple[str, str, str, str], dict] = {}
    reused_rank_rejections = 0
    for sample, receivers in by_probe.items():
        for rx0_pair in itertools.combinations(sorted(receivers[0]), 2):
            for rx1_pair in itertools.combinations(sorted(receivers[1]), 2):
                a0, b0 = (ledgers[0, branch][sample] for branch in rx0_pair)
                a1, b1 = (ledgers[1, branch][sample] for branch in rx1_pair)
                if a0["candidate_rank"] == b0["candidate_rank"] or a1[
                    "candidate_rank"
                ] == b1["candidate_rank"]:
                    reused_rank_rejections += 1
                    continue
                straight = [timing_offset(a0, a1), timing_offset(b0, b1)]
                crossed = [timing_offset(a0, b1), timing_offset(b0, a1)]
                key = (*rx0_pair, *rx1_pair)
                row = quartets.setdefault(
                    key,
                    {
                        "probe_starts": [],
                        "straight_timing_pass_probe_starts": [],
                        "crossed_timing_pass_probe_starts": [],
                        "both_matchings_pass_probe_starts": [],
                    },
                )
                row["probe_starts"].append(sample)
                straight_pass = all(abs(value) <= TIMING_DIAGNOSTIC_SAMPLES for value in straight)
                crossed_pass = all(abs(value) <= TIMING_DIAGNOSTIC_SAMPLES for value in crossed)
                if straight_pass:
                    row["straight_timing_pass_probe_starts"].append(sample)
                if crossed_pass:
                    row["crossed_timing_pass_probe_starts"].append(sample)
                if straight_pass and crossed_pass:
                    row["both_matchings_pass_probe_starts"].append(sample)
    compact = []
    for key, row in quartets.items():
        for values in row.values():
            values.sort()
        rx0a, rx0b, rx1a, rx1b = key
        compact.append(
            {
                "rx0_branch_ids": [rx0a, rx0b],
                "rx1_branch_ids": [rx1a, rx1b],
                "coincident_probe_count": len(row["probe_starts"]),
                "coincident_probe_starts": row["probe_starts"],
                "coincident_runs": runs(row["probe_starts"], cadence),
                "straight_timing_pass_count": len(row["straight_timing_pass_probe_starts"]),
                "straight_timing_pass_runs": runs(
                    row["straight_timing_pass_probe_starts"], cadence
                ),
                "crossed_timing_pass_count": len(row["crossed_timing_pass_probe_starts"]),
                "crossed_timing_pass_runs": runs(
                    row["crossed_timing_pass_probe_starts"], cadence
                ),
                "both_matchings_pass_count": len(row["both_matchings_pass_probe_starts"]),
            }
        )
    compact.sort(
        key=lambda row: (
            -max(row["straight_timing_pass_count"], row["crossed_timing_pass_count"]),
            -row["coincident_probe_count"],
            row["rx0_branch_ids"],
            row["rx1_branch_ids"],
        )
    )
    helper = Path(evidence_reader.__file__)
    return {
        "schema": "full-capture-glrt-branch-quartets/v1",
        "session_id": SESSION,
        "analysis_run_id": RUN,
        "run_manifest_identity": {
            "session_id": manifest["session_id"],
            "run_id": manifest["run_id"],
        },
        "stream_id": "stream-1",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "scope_by_receiver": {str(key): value for key, value in SCOPES.items()},
        "receiver_branch_counts": {str(key): len(value) for key, value in scoped.items()},
        "dominant_probe_cadence_samples": cadence,
        "existing_timing_diagnostic_samples": TIMING_DIAGNOSTIC_SAMPLES,
        "branch_inventory": branch_inventory,
        "source_product_digests_by_receiver": {
            str(receiver): scoped[receiver][0].evidence.source_digests for receiver in SCOPES
        },
        "raw_pilot_scan_multi_glrt64_candidate_probe_counts": {
            "receiver_0": len(raw_multi_probes[0]),
            "receiver_1": len(raw_multi_probes[1]),
            "both_receivers_exact_probe": len(raw_multi_probes[0] & raw_multi_probes[1]),
        },
        "final_bank_representative_scope_audit": {
            str(receiver): row for receiver, row in bank_audit.items()
        },
        "receiver_branch_pair_count": len(receiver_pairs),
        "receiver_branch_pairs": receiver_pairs,
        "same_candidate_rank_quartet_opportunities_rejected": reused_rank_rejections,
        "quartet_count": len(compact),
        "quartets": compact,
        "interpretation": (
            "Every row requires two uniquely associated branches in each receiver at the same "
            "exact probe start. Timing compatibility is an existing diagnostic, not a source "
            "identity decision. No raw observation digest is joined across receivers."
        ),
        "selection_policy": (
            "Exhaustive full-capture metadata inventory; no quartet or matching is selected by "
            "phase, CFO, timing proximity, or outcome."
        ),
        "no_iq_read": True,
        "no_refit": True,
        "source_sha256": {
            str(Path(__file__).relative_to(ROOT)): digest(Path(__file__)),
            str(helper.relative_to(ROOT)): digest(helper),
        },
    }


if __name__ == "__main__":
    if OUTPUT.exists():
        raise ValueError("fresh output path required")
    OUTPUT.write_text(json.dumps(build(), indent=2, allow_nan=False) + "\n")
