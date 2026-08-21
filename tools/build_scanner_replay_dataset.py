#!/usr/bin/env python3
"""Materialize a bounded scanner replay dataset from recent verified recordings."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from leo.contracts.digests import sha256_digest
from leo.contracts.states import GainMode
from leo.scanner.models import ScannerConfiguration, current_low_band_targets
from leo.scanner.replay import (
    ScannerReferenceLabel,
    ScannerReplayDatasetRecipeV1,
    ScannerReplayFrameRecipeV1,
    ScannerReplayLabelEvidenceV1,
    ScannerReplaySplit,
    ScannerReplaySweepRecipeV1,
    prepare_scanner_replay_dataset,
)
from leo.storage import RecordingScannerReplaySource, RecordingStore, ScannerReplayStore

_DWELL_MS = 80
_SAMPLE_RATE_HZ = 2_500_000
_BANDWIDTH_HZ = 2_500_000
_RECEIVER_IDS = (0, 1)
_GAIN_DB = 30.0
_LABEL_METHOD_ACTIVE = "standard-radio-final-trajectory-v2-silver"
_LABEL_METHOD_QUIET = "standard-radio-final-trajectory-gap-v2-silver"
_QUIET_GUARD_S = 0.2


@dataclass(frozen=True, slots=True)
class _Candidate:
    target_index: int
    session_id: str
    stream_id: str
    sample_start: int
    label: ScannerReferenceLabel
    evidence_digest: str
    evidence_uri: str


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--hours", type=float, default=8.0)
    parser.add_argument("--cutoff-utc-ns", type=int)
    parser.add_argument("--train-sweeps", type=int, default=1)
    parser.add_argument("--validation-sweeps", type=int, default=1)
    parser.add_argument("--test-sweeps", type=int, default=1)
    parser.add_argument(
        "--scenario",
        choices=("all-active", "all-quiet", "single-active"),
        default="all-active",
    )
    parser.add_argument("--active-channel", type=int, choices=(1, 2, 3, 4))
    parser.add_argument("--active-edge", choices=("lower", "upper"))
    return parser.parse_args()


def _load_json(payload: bytes, *, description: str) -> dict[str, Any]:
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError(f"{description} must be one JSON object")
    return value


def _latest_analysis_products(
    bulk_root: Path,
    session_id: str,
    recording_manifest_digest: str,
) -> tuple[dict[str, Any], ...]:
    session_root = bulk_root / "analysis" / session_id
    if not session_root.is_dir():
        return ()
    manifests = sorted(
        session_root.glob("*/manifest.json"),
        key=lambda item: (item.stat().st_mtime_ns, item.as_posix()),
        reverse=True,
    )
    for path in manifests:
        document = _load_json(path.read_bytes(), description="analysis run manifest")
        if document.get("input_manifest_digest") != recording_manifest_digest:
            continue
        products = document.get("products")
        if not isinstance(products, list):
            continue
        selected = tuple(
            item
            for item in products
            if isinstance(item, dict)
            and item.get("kind") == "standard.radio-report"
            and item.get("status") == "complete"
        )
        if selected:
            return selected
    return ()


def _report_candidates(
    recordings: RecordingStore,
    bundle: Any,
    products: tuple[dict[str, Any], ...],
    configuration: ScannerConfiguration,
) -> tuple[_Candidate, ...]:
    by_stream = {stream.stream_id: stream for stream in bundle.manifest.streams}
    target_by_if = {
        target.if_center_hz: index for index, target in enumerate(configuration.targets)
    }
    candidates: list[_Candidate] = []
    for product in products:
        uri = product.get("logical_uri")
        digest = product.get("digest")
        if not isinstance(uri, str) or not isinstance(digest, str):
            continue
        path = recordings.resolve_uri(uri)
        payload = path.read_bytes()
        if sha256_digest(payload) != digest:
            raise ValueError(f"analysis product digest mismatch: {uri}")
        report = _load_json(payload, description="standard radio report")
        if (
            report.get("status") != "complete"
            or report.get("candidate_only") is not True
            or report.get("payload_decoded") is not False
        ):
            continue
        stream_id = report.get("stream_id")
        if not isinstance(stream_id, str) or stream_id not in by_stream:
            continue
        stream = by_stream[stream_id]
        if stream.applied_settings is None:
            continue
        requested = stream.requested_settings
        applied = stream.applied_settings
        if (
            requested.center_frequency_hz not in target_by_if
            or applied.sample_rate_hz != configuration.sample_rate_hz
            or applied.bandwidth_hz != configuration.bandwidth_hz
            or applied.receiver_ids != configuration.receiver_ids
            or applied.gain_mode is not GainMode.MANUAL
            or tuple(gain.gain_db for gain in applied.gains)
            != (_GAIN_DB,) * len(configuration.receiver_ids)
        ):
            continue
        paths = report.get("paths")
        if not isinstance(paths, list) or len(paths) != len(configuration.receiver_ids):
            continue
        intervals: list[tuple[float, float]] = []
        complete = True
        for child in paths:
            if not isinstance(child, dict) or child.get("status") != "complete":
                complete = False
                break
            final = child.get("final_trajectories")
            if not isinstance(final, list):
                complete = False
                break
            for trajectory in final:
                if not isinstance(trajectory, dict):
                    continue
                start_s = trajectory.get("start_s")
                end_s = trajectory.get("end_s")
                if isinstance(start_s, (int, float)) and isinstance(end_s, (int, float)):
                    intervals.append((float(start_s), float(end_s)))
        if not complete:
            continue
        dwell_s = configuration.dwell_ms / 1_000.0
        usable = tuple(interval for interval in intervals if interval[1] - interval[0] >= dwell_s)
        if usable:
            interval = max(usable, key=lambda item: (item[1] - item[0], -item[0]))
            midpoint_s = (interval[0] + interval[1]) / 2.0
            sample_start = round((midpoint_s - dwell_s / 2.0) * configuration.sample_rate_hz)
            candidates.append(
                _candidate(
                    bundle.session_id,
                    stream_id,
                    target_by_if[requested.center_frequency_hz],
                    sample_start,
                    ScannerReferenceLabel.ACTIVE,
                    digest,
                    uri,
                    stream.captured_sample_count,
                    configuration,
                )
            )
        quiet = _largest_quiet_interval(
            intervals,
            stream.captured_sample_count / configuration.sample_rate_hz,
            dwell_s,
        )
        if quiet is not None:
            midpoint_s = (quiet[0] + quiet[1]) / 2.0
            sample_start = round((midpoint_s - dwell_s / 2.0) * configuration.sample_rate_hz)
            candidates.append(
                _candidate(
                    bundle.session_id,
                    stream_id,
                    target_by_if[requested.center_frequency_hz],
                    sample_start,
                    ScannerReferenceLabel.QUIET,
                    digest,
                    uri,
                    stream.captured_sample_count,
                    configuration,
                )
            )
    return tuple(candidates)


def _candidate(
    session_id: str,
    stream_id: str,
    target_index: int,
    sample_start: int,
    label: ScannerReferenceLabel,
    evidence_digest: str,
    evidence_uri: str,
    captured_sample_count: int,
    configuration: ScannerConfiguration,
) -> _Candidate:
    bounded = max(0, min(sample_start, captured_sample_count - configuration.dwell_samples))
    bounded = bounded // configuration.probe_stride_samples * configuration.probe_stride_samples
    return _Candidate(
        target_index=target_index,
        session_id=session_id,
        stream_id=stream_id,
        sample_start=bounded,
        label=label,
        evidence_digest=evidence_digest,
        evidence_uri=evidence_uri,
    )


def _largest_quiet_interval(
    intervals: list[tuple[float, float]],
    duration_s: float,
    dwell_s: float,
) -> tuple[float, float] | None:
    blocked = sorted(
        (
            max(0.0, start_s - _QUIET_GUARD_S),
            min(duration_s, end_s + _QUIET_GUARD_S),
        )
        for start_s, end_s in intervals
        if end_s > start_s and end_s >= 0.0 and start_s <= duration_s
    )
    merged: list[tuple[float, float]] = []
    for start_s, end_s in blocked:
        if not merged or start_s > merged[-1][1]:
            merged.append((start_s, end_s))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end_s))
    gaps: list[tuple[float, float]] = []
    cursor = 0.0
    for start_s, end_s in merged:
        if start_s - cursor >= dwell_s:
            gaps.append((cursor, start_s))
        cursor = max(cursor, end_s)
    if duration_s - cursor >= dwell_s:
        gaps.append((cursor, duration_s))
    return max(gaps, key=lambda item: (item[1] - item[0], -item[0]), default=None)


def _session_splits(
    candidates: tuple[_Candidate, ...],
    dataset_id: str,
    labels_by_target: tuple[ScannerReferenceLabel, ...],
    sweep_counts: dict[ScannerReplaySplit, int],
) -> dict[str, ScannerReplaySplit]:
    counts_by_session: dict[str, Counter[tuple[int, ScannerReferenceLabel]]] = defaultdict(Counter)
    for candidate in candidates:
        counts_by_session[candidate.session_id][(candidate.target_index, candidate.label)] += 1
    assignments: dict[str, ScannerReplaySplit] = {}
    for split in (
        ScannerReplaySplit.TEST,
        ScannerReplaySplit.VALIDATION,
        ScannerReplaySplit.TRAIN,
    ):
        remaining: Counter[tuple[int, ScannerReferenceLabel]] = Counter(
            {
                (target_index, label): sweep_counts[split]
                for target_index, label in enumerate(labels_by_target)
            }
        )
        while any(count > 0 for count in remaining.values()):
            needed = tuple(key for key, count in remaining.items() if count > 0)
            requirement = min(
                needed,
                key=lambda key: sum(
                    counts[key]
                    for session_id, counts in counts_by_session.items()
                    if session_id not in assignments
                ),
            )
            available = tuple(
                session_id
                for session_id, counts in counts_by_session.items()
                if session_id not in assignments and counts[requirement] > 0
            )
            if not available:
                target_index, label = requirement
                raise ValueError(
                    f"cannot assign {split.value} target {target_index} label {label.value} "
                    "without source-session leakage"
                )
            selected = min(
                available,
                key=lambda value: (
                    -sum(min(remaining[key], counts_by_session[value][key]) for key in needed),
                    hashlib.sha256(f"{dataset_id}/{split.value}/{value}".encode()).digest(),
                ),
            )
            assignments[selected] = split
            for key in needed:
                remaining[key] -= min(remaining[key], counts_by_session[selected][key])
    for session_id in sorted({item.session_id for item in candidates}):
        assignments.setdefault(session_id, ScannerReplaySplit.TRAIN)
    return assignments


def _build_recipe(
    dataset_id: str,
    configuration: ScannerConfiguration,
    candidates: tuple[_Candidate, ...],
    sweep_counts: dict[ScannerReplaySplit, int],
    labels_by_target: tuple[ScannerReferenceLabel, ...],
) -> ScannerReplayDatasetRecipeV1:
    assignments = _session_splits(candidates, dataset_id, labels_by_target, sweep_counts)
    pools: dict[tuple[ScannerReplaySplit, int, ScannerReferenceLabel], list[_Candidate]] = (
        defaultdict(list)
    )
    for candidate in candidates:
        pools[(assignments[candidate.session_id], candidate.target_index, candidate.label)].append(
            candidate
        )
    for key, pool in pools.items():
        split, target_index, label = key
        pool.sort(
            key=lambda item: hashlib.sha256(
                f"{dataset_id}/{split.value}/{target_index}/{label.value}/"
                f"{item.session_id}/{item.stream_id}/{item.sample_start}".encode()
            ).digest()
        )
    sweeps: list[ScannerReplaySweepRecipeV1] = []
    for split in ScannerReplaySplit:
        count = sweep_counts[split]
        for sweep_index in range(count):
            frames: list[ScannerReplayFrameRecipeV1] = []
            for target_index, label in enumerate(labels_by_target):
                pool = pools[(split, target_index, label)]
                if len(pool) < count:
                    raise ValueError(
                        f"{split.value} target {target_index} label {label.value} has "
                        f"{len(pool)} candidates, needs {count}"
                    )
                candidate = pool[sweep_index]
                frames.append(
                    ScannerReplayFrameRecipeV1(
                        target_index=target_index,
                        source_session_id=candidate.session_id,
                        source_stream_id=candidate.stream_id,
                        source_sample_start=candidate.sample_start,
                        label=candidate.label,
                        evidence=ScannerReplayLabelEvidenceV1(
                            method=(
                                _LABEL_METHOD_ACTIVE
                                if candidate.label is ScannerReferenceLabel.ACTIVE
                                else _LABEL_METHOD_QUIET
                            ),
                            digest=candidate.evidence_digest,
                            uri=candidate.evidence_uri,
                        ),
                    )
                )
            sweeps.append(
                ScannerReplaySweepRecipeV1(
                    sweep_id=f"{split.value}-{sweep_index + 1:04d}",
                    split=split,
                    frames=tuple(frames),
                )
            )
    return ScannerReplayDatasetRecipeV1(
        dataset_id=dataset_id,
        generator_id="recent-standard-radio-silver-scenarios-v1",
        configuration=configuration,
        sweeps=tuple(sweeps),
    )


def main() -> int:
    arguments = _arguments()
    if arguments.hours <= 0:
        raise ValueError("hours must be positive")
    sweep_counts = {
        ScannerReplaySplit.TRAIN: arguments.train_sweeps,
        ScannerReplaySplit.VALIDATION: arguments.validation_sweeps,
        ScannerReplaySplit.TEST: arguments.test_sweeps,
    }
    if any(count <= 0 for count in sweep_counts.values()):
        raise ValueError("every split must contain at least one sweep")
    configuration = ScannerConfiguration(
        dwell_ms=_DWELL_MS,
        sample_rate_hz=_SAMPLE_RATE_HZ,
        bandwidth_hz=_BANDWIDTH_HZ,
        receiver_ids=_RECEIVER_IDS,
        gain_mode=GainMode.MANUAL,
        gain_db=_GAIN_DB,
        targets=current_low_band_targets(),
    )
    if arguments.scenario == "single-active":
        if arguments.active_channel is None or arguments.active_edge is None:
            raise ValueError("single-active requires --active-channel and --active-edge")
        active_targets = tuple(
            index
            for index, target in enumerate(configuration.targets)
            if target.channel == arguments.active_channel
            and target.edge.value == arguments.active_edge
        )
        if len(active_targets) != 1:
            raise ValueError("active channel and edge do not identify exactly one target")
        active_target_index: int | None = active_targets[0]
        labels_by_target = tuple(
            ScannerReferenceLabel.ACTIVE
            if index == active_target_index
            else ScannerReferenceLabel.QUIET
            for index in range(len(configuration.targets))
        )
    else:
        if arguments.active_channel is not None or arguments.active_edge is not None:
            raise ValueError("--active-channel and --active-edge are only valid for single-active")
        active_target_index = None
        label = (
            ScannerReferenceLabel.ACTIVE
            if arguments.scenario == "all-active"
            else ScannerReferenceLabel.QUIET
        )
        labels_by_target = (label,) * len(configuration.targets)
    recordings = RecordingStore.open_read_only(arguments.bulk_root)
    try:
        cutoff_utc_ns = (
            arguments.cutoff_utc_ns
            if arguments.cutoff_utc_ns is not None
            else time.time_ns() - round(arguments.hours * 3_600 * 1_000_000_000)
        )
        reconciled = recordings.reconcile()
        if reconciled.issues:
            raise ValueError(f"recording store contains {len(reconciled.issues)} inspection issues")
        recent = tuple(
            bundle
            for bundle in reconciled.committed
            if bundle.manifest.created_utc_ns >= cutoff_utc_ns
        )
        candidates: list[_Candidate] = []
        analyzed_sessions = 0
        for bundle in recent:
            products = _latest_analysis_products(
                arguments.bulk_root,
                bundle.session_id,
                bundle.manifest_sha256,
            )
            if not products:
                continue
            analyzed_sessions += 1
            candidates.extend(_report_candidates(recordings, bundle, products, configuration))
        recipe = _build_recipe(
            arguments.dataset_id,
            configuration,
            tuple(candidates),
            sweep_counts,
            labels_by_target,
        )
        prepared = prepare_scanner_replay_dataset(
            recipe,
            RecordingScannerReplaySource(recordings),
        )
        published = ScannerReplayStore(arguments.output_root).publish(prepared)
        label_counts = Counter(item.label.value for item in published.truth.items)
        eligible_label_counts = Counter(item.label.value for item in candidates)
        split_counts = Counter(entry.split.value for entry in published.manifest.entries)
        summary = {
            "dataset_id": published.dataset_id,
            "uri": published.uri,
            "path": str(published.path),
            "scenario": arguments.scenario,
            "active_target_index": active_target_index,
            "cutoff_utc_ns": cutoff_utc_ns,
            "recent_recording_sessions": len(recent),
            "analyzed_recording_sessions": analyzed_sessions,
            "eligible_radio_streams": len(candidates),
            "eligible_labels": dict(sorted(eligible_label_counts.items())),
            "sweeps": dict(sorted(split_counts.items())),
            "frames": len(published.truth.items),
            "labels": dict(sorted(label_counts.items())),
            "manifest_sha256": published.manifest_sha256,
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
    finally:
        recordings.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
