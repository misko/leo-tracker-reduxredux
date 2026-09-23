"""Freeze the stream-0 raw-candidate population without opening IQ."""

from __future__ import annotations

import hashlib
import itertools
import json
import random
from pathlib import Path
from typing import Any

from leo.storage import RecordingStore
from leo.contracts.standard_pipeline import resolve_manifest_starlink_tuning
from tools import report_glrt_phase_segment_comparison as reader

ROOT = Path(__file__).resolve().parents[4]
OUTPUT = Path(__file__).with_name("stream0-raw-candidate-population.json")
BULK_ROOT = Path("/srv/bulk/leo")
SESSION = "cap-20260825T010019-89c2889553e0"
RUN = "capture-34471d9087a94ec1b043951350de3956"
SCOPES = {
    0: "sha256:7965c386a5103ab9448656c60cdbd394ca5545b42c7f2329b7ce936a95ed444c",
    1: "sha256:9890342cb80f130c53d03d69221102dd00495ba2f0601b29ae347a2656f689bb",
}
SAMPLE_RATE_HZ = 2_500_000.0
FRAME_PERIOD_SAMPLES = SAMPLE_RATE_HZ / 750.0
NATIVE_ALIAS_PERIOD_HZ = 1.0 / 4.4e-6
TIMING_GATE_SAMPLES = 2.0
SPLIT_SEED = 20260926


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wrap(value: float, period: float) -> float:
    return (value + period / 2.0) % period - period / 2.0


def glrt(candidate: dict[str, Any]) -> dict[str, Any]:
    return next(score for score in candidate["scores"] if score["method"] == "glrt64")


def components(rows: list[dict[str, Any]], frequency_gate_hz: float) -> list[list[dict[str, Any]]]:
    """Use the frozen raw-opportunity connected-component policy verbatim."""
    parents = list(range(len(rows)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for right in range(len(rows)):
        for left in range(right):
            epoch_close = abs(
                wrap(
                    rows[right]["local_epoch_sample"] - rows[left]["local_epoch_sample"],
                    FRAME_PERIOD_SAMPLES,
                )
            ) <= TIMING_GATE_SAMPLES
            frequency_close = abs(
                wrap(
                    rows[right]["tracking_cfo_hz"] - rows[left]["tracking_cfo_hz"],
                    NATIVE_ALIAS_PERIOD_HZ,
                )
            ) <= frequency_gate_hz
            if epoch_close and frequency_close:
                parents[find(right)] = find(left)
    grouped: dict[int, list[dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        grouped.setdefault(find(index), []).append(row)
    return [grouped[key] for key in sorted(grouped)]


def timing_matchings(
    left: list[list[dict[str, Any]]], right: list[list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Retain every two-by-two component pairing and its matching members."""
    result = []
    for left_indices in itertools.combinations(range(len(left)), 2):
        for right_indices in itertools.combinations(range(len(right)), 2):
            for permuted_right in itertools.permutations(right_indices):
                member_matches = []
                for left_index, right_index in zip(left_indices, permuted_right, strict=True):
                    pairs = []
                    for left_row in left[left_index]:
                        for right_row in right[right_index]:
                            offset = wrap(
                                right_row["local_epoch_sample"]
                                - left_row["local_epoch_sample"],
                                FRAME_PERIOD_SAMPLES,
                            )
                            if abs(offset) <= TIMING_GATE_SAMPLES:
                                pairs.append(
                                    {
                                        "rx0_candidate_rank": left_row["candidate_rank"],
                                        "rx1_candidate_rank": right_row["candidate_rank"],
                                        "timing_offset_samples": offset,
                                    }
                                )
                    member_matches.append(pairs)
                result.append(
                    {
                        "rx0_component_indices": list(left_indices),
                        "rx1_component_indices": list(permuted_right),
                        "both_pairs_timing_compatible": all(member_matches),
                        "compatible_candidate_members_by_pair": member_matches,
                    }
                )
    return result


def _nominees(matching: dict[str, Any]) -> dict[str, list[int]]:
    """Choose ranks only after exactly one compatible component pairing exists."""
    pairs = matching["compatible_candidate_members_by_pair"]
    selected = [
        min(pair, key=lambda row: (row["rx0_candidate_rank"], row["rx1_candidate_rank"]))
        for pair in pairs
    ]
    return {
        "0": [row["rx0_candidate_rank"] for row in selected],
        "1": [row["rx1_candidate_rank"] for row in selected],
    }


def _timeline_receipt() -> dict[str, Any]:
    """Verify every public refill's coordinates and device-counter succession."""
    store = RecordingStore.open_read_only(BULK_ROOT)
    bundle = store.inspect(SESSION)
    timeline = tuple(store.reader(bundle, "stream-0", verify=True).iter_timeline_metadata())
    if not timeline:
        raise ValueError("stream-0 timeline is empty")
    violations = []
    for previous, current in zip(timeline, timeline[1:], strict=False):
        if current.session_sample_start != previous.session_sample_start + previous.sample_count:
            violations.append("session_sample_start")
        if current.device_sample_counter != previous.device_sample_counter + previous.sample_count:
            violations.append("device_sample_counter")
        if current.source_sequence != previous.source_sequence + 1:
            violations.append("source_sequence")
        if current.missing_samples_before != 0 or current.overflow_observed:
            violations.append("continuity_flags")
    if timeline[0].missing_samples_before != 0 or timeline[0].overflow_observed:
        violations.append("first_refill_flags")
    if violations:
        raise ValueError(f"stream-0 timeline continuity failed: {sorted(set(violations))}")
    profile = bundle.manifest.capture_plan.profile_revision.profile
    tuning = resolve_manifest_starlink_tuning(bundle.manifest)["stream-0"]
    return {
        "verification": "RecordingStore.reader(..., verify=True).iter_timeline_metadata",
        "recording_manifest_digest": bundle.manifest_sha256,
        "refill_count": len(timeline),
        "all_adjacent_session_coordinates_contiguous": True,
        "all_adjacent_device_counters_contiguous": True,
        "all_adjacent_source_sequences_contiguous": True,
        "all_refills_missing_samples_before_zero": True,
        "all_refills_overflow_observed_false": True,
        "first_device_sample_counter": timeline[0].device_sample_counter,
        "last_device_sample_counter_inclusive": (
            timeline[-1].device_sample_counter + timeline[-1].sample_count - 1
        ),
        "receiver_ids": list(timeline[0].receiver_ids),
        "radio_id": timeline[0].radio_id,
        "stream_generation": timeline[0].stream_generation,
        "capture_plan_digest": bundle.manifest.capture_plan.plan_digest,
        "capture_profile_revision_digest": bundle.manifest.capture_plan.profile_revision.revision_digest,
        "capture_profile_name": profile.name,
        "starlink_channel": tuning.channel,
        "template_edge": tuning.edge.value,
        "template_edge_authority": tuning.evidence_source,
        "superseded_profile_edge": profile.starlink_edge.value,
    }


def build() -> dict[str, Any]:
    manifest, evidence = reader.load_path_evidence(BULK_ROOT, SESSION, RUN)
    timeline_continuity = _timeline_receipt()
    by_scope = {row.scope: row for row in evidence}
    products = {(row.get("scope_key"), row.get("kind")): row for row in manifest["products"]}
    rows_by_receiver: dict[int, dict[int, list[list[dict[str, Any]]]]] = {}
    source = {}
    for receiver, scope in SCOPES.items():
        accounting = products[(scope, "standard.trajectory-conditioned-accounting")]
        payload = reader._bulk_uri_path(BULK_ROOT, accounting["logical_uri"]).read_bytes()
        if "sha256:" + hashlib.sha256(payload).hexdigest() != accounting["digest"]:
            raise ValueError("accounting digest mismatch")
        configuration = json.loads(payload)["configuration"]
        passing_by_probe = {}
        for detection in by_scope[scope].pilot_scan["detections"]:
            passing = []
            for candidate in detection["candidates"]:
                score = glrt(candidate)
                if score["margin"] >= float(configuration["positive_margin"]):
                    passing.append(
                        {
                            "candidate_rank": int(candidate["rank"]),
                            "local_epoch_sample": float(candidate["local_epoch_sample"]),
                            "tracking_cfo_hz": float(score["tracking_cfo_hz"]),
                            "exact_score": float(score["exact_score"]),
                            "control_score": float(score["control_score"]),
                            "margin": float(score["margin"]),
                        }
                    )
            passing_by_probe[int(detection["sample_start"])] = components(
                passing, float(configuration["association_gate_hz"])
            )
        rows_by_receiver[receiver] = passing_by_probe
        pilot = products[(scope, "standard.pilot-scan")]
        presentation = products[(scope, "standard.path-presentation")]
        source[str(receiver)] = {
            "scope": scope,
            "stream_id": "stream-0",
            "receiver_id": receiver,
            "pilot_scan_product_digest": pilot["digest"],
            "path_presentation_product_digest": presentation["digest"],
            "accounting_product_digest": accounting["digest"],
            "source_product_digests": by_scope[scope].source_digests,
            "positive_margin": float(configuration["positive_margin"]),
            "association_gate_hz": float(configuration["association_gate_hz"]),
            "template_edge": timeline_continuity["template_edge"],
            "template_edge_status": "bound_by_manifest_tuning_resolver",
        }
    starts = sorted(
        start
        for start in rows_by_receiver[0].keys() & rows_by_receiver[1].keys()
        if len(rows_by_receiver[0][start]) >= 2 and len(rows_by_receiver[1][start]) >= 2
    )
    if len(starts) != 10:
        raise ValueError(f"expected the frozen ten-probe population, got {len(starts)}")
    shuffled = starts.copy()
    random.Random(SPLIT_SEED).shuffle(shuffled)
    partitions = {start: "train" if index < 5 else "held" for index, start in enumerate(shuffled)}
    opportunities = []
    for start in starts:
        matchings = timing_matchings(rows_by_receiver[0][start], rows_by_receiver[1][start])
        compatible = [row for row in matchings if row["both_pairs_timing_compatible"]]
        row: dict[str, Any] = {
            "sample_start": start,
            "time_s": start / SAMPLE_RATE_HZ,
            "partition": partitions[start],
            "receiver_components": {
                "0": rows_by_receiver[0][start],
                "1": rows_by_receiver[1][start],
            },
            "one_to_one_component_matchings": matchings,
        }
        if not compatible:
            row["status"] = "abstain_no_timing_compatible_two_pair_matching"
        elif len(compatible) != 1:
            row["status"] = "abstain_ambiguous_timing_compatible_matching"
        else:
            row["status"] = "eligible"
            row["nominees"] = _nominees(compatible[0])
        opportunities.append(row)
    helper = Path(reader.__file__)
    return {
        "schema": "stream0-raw-candidate-population/v1",
        "session_id": SESSION,
        "analysis_run_id": RUN,
        "stream_id": "stream-0",
        "edge": timeline_continuity["template_edge"],
        "no_iq_read": True,
        "no_phase_refit": True,
        "timeline_continuity": timeline_continuity,
        "screening_policy": {
            "margin_rule": "glrt64 exact_score - control_score >= persisted positive_margin",
            "component_policy": "both epoch <=2 samples modulo frame and CFO <=2500 Hz modulo native alias",
            "frame_period_samples": FRAME_PERIOD_SAMPLES,
            "native_alias_period_hz": NATIVE_ALIAS_PERIOD_HZ,
            "timing_gate_samples": TIMING_GATE_SAMPLES,
            "not_an_archived_candidate_deduplication_contract": True,
        },
        "outer_random_whole_probe_split": {
            "seed": SPLIT_SEED,
            "algorithm": "random.Random(seed).shuffle(sorted(sample_start)); first five train, remainder held",
            "assigned_before_timing_eligibility": True,
            "train_sample_starts_in_draw_order": shuffled[:5],
            "held_sample_starts_in_draw_order": shuffled[5:],
        },
        "sources_by_receiver": source,
        "opportunities": opportunities,
        "source_sha256": {
            str(Path(__file__).relative_to(ROOT)): sha256(Path(__file__)),
            str(helper.relative_to(ROOT)): sha256(helper),
        },
    }


if __name__ == "__main__":
    if OUTPUT.exists():
        raise ValueError("fresh output path required")
    OUTPUT.write_text(json.dumps(build(), indent=2, allow_nan=False) + "\n")
