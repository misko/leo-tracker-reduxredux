#!/usr/bin/env python3
"""Return overall GLRT and reset-debiased local rates for one raw dwell."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from leo.analysis.starlink.dwell_doppler import (
    DwellDopplerConfig,
    DwellDopplerStatus,
    DwellDopplerTrackInput,
    GlrtProbe,
    analyze_track_doppler,
)
from leo.analysis.starlink.local_doppler import stable_measurement_floats
from leo.analysis.starlink.templates import StarlinkEdge
from leo.contracts.cfo_dealias import DealiasedTrajectoryBankV4
from leo.contracts.digests import canonical_digest
from leo.pipeline import ScopeIdentityV1
from leo.pipeline.contracts import StageOutcome
from leo.storage import PinnedLocalRoot, RecordingStore

DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
DEFAULT_MAXIMUM_TRACK_ATTEMPTS = 4


@dataclass(frozen=True, slots=True)
class RawCandidate:
    observation_id: str
    detection_time_s: float
    detection_sample_start: int
    rank: int
    local_epoch_sample: int
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float


@dataclass(frozen=True, slots=True)
class TrackCandidate:
    analysis_root: Path
    track: DwellDopplerTrackInput
    canonical_observation_count: int
    strong_glrt_window_count: int
    median_glrt_margin: float
    model_mad_scale_hz: float
    source_alias_minimum_hz: float
    source_alias_maximum_hz: float

    @property
    def rank_key(self) -> tuple[object, ...]:
        return (
            -self.strong_glrt_window_count,
            -len(self.track.probes),
            -(self.track.end_s - self.track.start_s),
            -self.median_glrt_margin,
            self.model_mad_scale_hz,
            self.track.stream_id,
            self.track.receiver_id,
            self.track.branch_id,
        )

    def summary(self) -> dict[str, Any]:
        return {
            "branch_id": self.track.branch_id,
            "analysis_root": str(self.analysis_root),
            "stream_id": self.track.stream_id,
            "receiver_id": self.track.receiver_id,
            "edge": self.track.edge.value,
            "start_s": self.track.start_s,
            "end_s": self.track.end_s,
            "canonical_observation_count": self.canonical_observation_count,
            "source_probe_count": len(self.track.probes),
            "strong_glrt_window_count": self.strong_glrt_window_count,
            "median_glrt_margin": self.median_glrt_margin,
            "model_mad_scale_hz": self.model_mad_scale_hz,
            "overall_glrt_rate_hz_s": self.track.overall_glrt_rate_hz_s,
            "overall_glrt_rate_sigma_hz_s": self.track.glrt_rate_sigma_hz_s,
            "source_alias_minimum_hz": self.source_alias_minimum_hz,
            "source_alias_maximum_hz": self.source_alias_maximum_hz,
        }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--maximum-track-attempts",
        type=int,
        default=DEFAULT_MAXIMUM_TRACK_ATTEMPTS,
    )
    parser.add_argument(
        "--omit-frames",
        action="store_true",
        help="persist ramps and diagnostics but omit the large per-frame inventory",
    )
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _glrt_score(candidate: dict[str, Any]) -> dict[str, Any]:
    matches = [item for item in candidate["scores"] if item["method"] == "glrt64"]
    if len(matches) != 1:
        raise ValueError("candidate does not contain exactly one GLRT64 score")
    return matches[0]


def raw_candidates(scan: dict[str, Any]) -> dict[str, RawCandidate]:
    if scan.get("schema_version") != 3:
        raise ValueError("raw dwell Doppler requires pilot-scan V3")
    result = {}
    for detection in scan["detections"]:
        for candidate in detection["candidates"]:
            score = _glrt_score(candidate)
            observation_id = canonical_digest(
                {
                    "sample_start": int(detection["sample_start"]),
                    "candidate_rank": int(candidate["rank"]),
                    "method": "glrt64",
                }
            )
            result[observation_id] = RawCandidate(
                observation_id=observation_id,
                detection_time_s=float(detection["time_s"]),
                detection_sample_start=int(detection["sample_start"]),
                rank=int(candidate["rank"]),
                local_epoch_sample=int(candidate["local_epoch_sample"]),
                tracking_cfo_hz=float(score["tracking_cfo_hz"]),
                exact_score=float(score["exact_score"]),
                control_score=float(score["control_score"]),
                margin=float(score["margin"]),
            )
    return result


def _edge_for_stream(tags: tuple[str, ...], stream_id: str) -> StarlinkEdge:
    prefix = f"tuning:{stream_id}:"
    matches = [item for item in tags if item.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"recording does not declare one tuning tag for {stream_id}")
    return StarlinkEdge(matches[0].rsplit(":", maxsplit=1)[-1])


def _source_probe(
    source_ids: tuple[str, ...],
    sources: dict[str, RawCandidate],
) -> RawCandidate | None:
    available = [sources[source_id] for source_id in source_ids if source_id in sources]
    if not available:
        return None
    return max(
        available,
        key=lambda item: (
            item.margin,
            item.exact_score,
            -item.rank,
            -abs(item.tracking_cfo_hz),
        ),
    )


def _track_candidate(
    *,
    analysis_root: Path,
    stream_id: str,
    receiver_id: int,
    edge: StarlinkEdge,
    scan: dict[str, Any],
    bank: DealiasedTrajectoryBankV4,
    branch_id: str,
) -> TrackCandidate | None:
    branch = next(item for item in bank.branches if item.branch_id == branch_id)
    observations = {item.observation_id: item for item in bank.observations}
    sources = raw_candidates(scan)
    selected_sources = []
    for observation_id in branch.observation_ids:
        observation = observations.get(observation_id)
        if observation is None:
            continue
        source = _source_probe(observation.source_observation_ids, sources)
        if source is not None:
            selected_sources.append(source)
    by_sample = {}
    for item in selected_sources:
        previous = by_sample.get(item.detection_sample_start)
        if previous is None or (item.margin, item.exact_score) > (
            previous.margin,
            previous.exact_score,
        ):
            by_sample[item.detection_sample_start] = item
    ordered = tuple(sorted(by_sample.values(), key=lambda item: (item.detection_time_s, item.rank)))
    if len(ordered) < 3:
        return None
    probes = tuple(
        GlrtProbe(
            probe_index=index,
            detection_time_s=item.detection_time_s,
            detection_sample_start=item.detection_sample_start,
            local_epoch_sample=item.local_epoch_sample,
            source_cfo_hz=item.tracking_cfo_hz,
            exact_score=item.exact_score,
            control_score=item.control_score,
            margin=item.margin,
        )
        for index, item in enumerate(ordered)
    )
    model = branch.model
    canonical_times = np.asarray(
        [
            observations[observation_id].time_s
            for observation_id in branch.observation_ids
            if observation_id in observations
        ],
        dtype=float,
    )
    denominator = float(np.sum((canonical_times - model.reference_time_s) ** 2))
    glrt_sigma = (
        float(model.residual_rms_hz / math.sqrt(denominator)) if denominator > 0.0 else None
    )
    strong = [item for item in probes if item.exact_score >= 0.10 and item.margin > 0.0]
    margins = np.asarray([item.margin for item in strong or probes], dtype=float)
    source_cfo = np.asarray([item.source_cfo_hz for item in probes], dtype=float)
    track = DwellDopplerTrackInput(
        branch_id=branch.branch_id,
        stream_id=stream_id,
        receiver_id=receiver_id,
        edge=edge,
        start_s=branch.start_s,
        end_s=branch.end_s,
        reference_time_s=model.reference_time_s,
        glrt_coefficients_hz=tuple(float(item) for item in model.coefficients_hz),
        glrt_rate_sigma_hz_s=glrt_sigma,
        probe_samples=int(scan["probe_samples"]),
        probes=probes,
    )
    return TrackCandidate(
        analysis_root=analysis_root,
        track=track,
        canonical_observation_count=len(branch.observation_ids),
        strong_glrt_window_count=len(strong),
        median_glrt_margin=float(np.median(margins)),
        model_mad_scale_hz=float(model.mad_scale_hz),
        source_alias_minimum_hz=float(np.min(source_cfo)),
        source_alias_maximum_hz=float(np.max(source_cfo)),
    )


def discover_track_candidates(
    *,
    bulk_root: Path,
    session_id: str,
    run_id: str,
    recording_tags: tuple[str, ...],
) -> tuple[TrackCandidate, ...]:
    run_root = bulk_root / "analysis" / session_id / run_id
    manifest_path = run_root / "manifest.json"
    manifest = _load(manifest_path)
    if manifest.get("session_id") != session_id or manifest.get("run_id") != run_id:
        raise ValueError("analysis manifest identity does not match requested dwell")
    if manifest.get("pipeline_lane") != "standard":
        raise ValueError("raw dwell Doppler requires a Standard analysis run")
    jobs = manifest.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("analysis run contains no terminal jobs")
    successful_outcomes = {outcome.value for outcome in StageOutcome}
    invalid_outcomes = [
        item.get("outcome") for item in jobs if item.get("outcome") not in successful_outcomes
    ]
    if invalid_outcomes:
        raise ValueError(f"analysis run contains non-successful job outcomes {invalid_outcomes!r}")
    output = []
    for stream_id in ("stream-0", "stream-1"):
        edge = _edge_for_stream(recording_tags, stream_id)
        for receiver_id in (0, 1):
            scope = ScopeIdentityV1.receiver_path(
                session_id=session_id,
                stream_id=stream_id,
                receiver_id=receiver_id,
            ).canonical_digest
            analysis_root = run_root / "scientific" / "path-standard" / scope
            scan_path = analysis_root / "standard.pilot-scan.v3.json"
            bank_path = analysis_root / "standard.dealiased-trajectory-bank.v4.json"
            if not scan_path.is_file() or not bank_path.is_file():
                continue
            scan = _load(scan_path)
            bank = DealiasedTrajectoryBankV4.model_validate(_load(bank_path))
            for branch in bank.branches:
                candidate = _track_candidate(
                    analysis_root=analysis_root,
                    stream_id=stream_id,
                    receiver_id=receiver_id,
                    edge=edge,
                    scan=scan,
                    bank=bank,
                    branch_id=branch.branch_id,
                )
                if candidate is not None:
                    output.append(candidate)
    return tuple(sorted(output, key=lambda item: item.rank_key))


def analyze_raw_dwell(
    *,
    bulk_root: Path,
    session_id: str,
    run_id: str,
    maximum_track_attempts: int,
    include_frames: bool = True,
) -> dict[str, Any]:
    if maximum_track_attempts < 1:
        raise ValueError("maximum track attempts must be positive")
    store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
    try:
        bundle = store.inspect(session_id)
        tags = tuple(bundle.manifest.tags)
        candidates = discover_track_candidates(
            bulk_root=bulk_root,
            session_id=session_id,
            run_id=run_id,
            recording_tags=tags,
        )
        attempts = []
        selected_index = None
        seed = int(hashlib.sha256(session_id.encode()).hexdigest()[:8], 16)
        config = replace(DwellDopplerConfig(), bootstrap_seed=seed)
        for candidate_index, candidate in enumerate(candidates[:maximum_track_attempts]):
            attempt_count = min(len(candidates), maximum_track_attempts)
            print(
                f"{session_id}: track {candidate_index + 1}/{attempt_count} "
                f"{candidate.track.stream_id}/RX{candidate.track.receiver_id} "
                f"{candidate.track.branch_id[:18]}",
                flush=True,
            )
            reader = store.reader(bundle, candidate.track.stream_id, verify=True)
            result = analyze_track_doppler(reader, candidate.track, config)
            attempts.append(
                {
                    "rank": candidate_index + 1,
                    "candidate": candidate.summary(),
                    "result": result.document(include_frames=include_frames),
                }
            )
            local_rate = float(result.diagnostics.get("local_corrected_rate_hz_s", math.nan))
            print(
                f"{session_id}: {result.status.value}; "
                f"GLRT={candidate.track.overall_glrt_rate_hz_s / 1_000:+.3f} kHz/s; "
                f"local={local_rate / 1_000:+.3f} kHz/s",
                flush=True,
            )
            if result.status is DwellDopplerStatus.COMPLETE:
                selected_index = candidate_index
                break
        if selected_index is None and attempts:
            selected_index = 0
        selected = None if selected_index is None else attempts[selected_index]
        status = "no_glrt_candidate" if selected is None else str(selected["result"]["status"])
        return stable_measurement_floats(
            {
                "schema": "org.leo.research.raw-dwell-doppler/v1",
                "algorithm": "source-bound-glrt-frame-ramp-rate-v1",
                "session_id": session_id,
                "run_id": run_id,
                "analysis_manifest": str(
                    bulk_root / "analysis" / session_id / run_id / "manifest.json"
                ),
                "analysis_manifest_digest": _digest(
                    bulk_root / "analysis" / session_id / run_id / "manifest.json"
                ),
                "recording_manifest_digest": bundle.manifest_sha256,
                "configuration": asdict(config),
                "candidate_count": len(candidates),
                "maximum_track_attempts": maximum_track_attempts,
                "per_frame_inventory_included": include_frames,
                "attempt_count": len(attempts),
                "selected_attempt_rank": (None if selected is None else selected["rank"]),
                "status": status,
                "selection_policy": (
                    "rank by strong persisted GLRT support without local-rate value; "
                    "try in order until the first fully validated local rate"
                ),
                "candidate_inventory": [item.summary() for item in candidates],
                "attempts": attempts,
                "selected": selected,
                "candidate_only": True,
                "known_pilots_only": True,
                "payload_decoded": False,
            }
        )
    finally:
        store.close()


def main() -> None:
    arguments = _arguments()
    document = analyze_raw_dwell(
        bulk_root=arguments.bulk_root,
        session_id=arguments.session_id,
        run_id=arguments.run_id,
        maximum_track_attempts=arguments.maximum_track_attempts,
        include_frames=not arguments.omit_frames,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(arguments.output)


if __name__ == "__main__":
    main()
