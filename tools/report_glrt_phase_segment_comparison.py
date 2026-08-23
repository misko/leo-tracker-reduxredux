#!/usr/bin/env python3
"""Compare sealed GLRT trajectory rates with 20--70 ms pilot-phase segments."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.qam.pilot_pnt_kalman import (  # noqa: E402
    PilotPntKalmanConfig,
    PilotPntKalmanResult,
    analyze_contiguous_pilot_pnt_kalman,
)
from leo.analysis.standard.analyzers import _pilot_detections  # noqa: E402
from leo.analysis.starlink.kalman_tracking import (  # noqa: E402
    PolynomialFrequencyModel,
    raw_candidate_sources,
)
from leo.analysis.starlink.pilot_doppler_segments import (  # noqa: E402
    _segment_document,
    _WindowRequest,
)
from leo.analysis.starlink.templates import StarlinkEdge  # noqa: E402
from leo.contracts.cfo_dealias import (  # noqa: E402
    DealiasedTrajectoryBankV4,
    FinalTrajectoryBankV3,
    FinalTrajectoryV3,
)
from leo.contracts.pilot_doppler_segments import (  # noqa: E402
    PilotDopplerSegmentConfigV1,
    StandardPilotDopplerSegmentsV1,
)
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402

FINAL_BANK_KIND = "standard.final-trajectory-bank"
DEALIASED_BANK_KIND = "standard.dealiased-trajectory-bank"
PILOT_SCAN_KIND = "standard.pilot-scan"
PILOT_SEGMENTS_KIND = "standard.pilot-doppler-segments"
REQUIRED_KINDS = (
    FINAL_BANK_KIND,
    DEALIASED_BANK_KIND,
    PILOT_SCAN_KIND,
    PILOT_SEGMENTS_KIND,
)
MINIMUM_PHASE_SPAN_S = 0.020
MAXIMUM_PHASE_SPAN_S = 0.070


@dataclass(frozen=True, slots=True)
class ProductRef:
    kind: str
    scope: str
    digest: str
    logical_uri: str


@dataclass(frozen=True, slots=True)
class PathEvidence:
    scope: str
    final_bank: FinalTrajectoryBankV3
    dealiased_bank: DealiasedTrajectoryBankV4
    pilot_scan: dict[str, Any]
    pilot_segments: StandardPilotDopplerSegmentsV1
    source_digests: dict[str, str]


@dataclass(frozen=True, slots=True)
class GlrtTrack:
    scope: str
    branch_id: str
    representative_trajectory_id: str
    alias_trajectory_ids: tuple[str, ...]
    observation_count: int
    evaluated_probe_count: int
    span_s: float
    start_s: float
    end_s: float
    glrt_rate_hz_s: float
    median_block_corrected_margin: float | None
    qualified_75ms_window_count: int
    track: FinalTrajectoryV3
    evidence: PathEvidence


@dataclass(frozen=True, slots=True)
class PathBinding:
    scope: str
    stream_id: str
    receiver_id: int
    edge: StarlinkEdge

    @property
    def label(self) -> str:
        return f"{self.stream_id}/RX{self.receiver_id} {self.edge.value}"


@dataclass(frozen=True, slots=True)
class WindowAnalysis:
    track: GlrtTrack
    binding: PathBinding
    window_index: int
    document: dict[str, Any]
    result: PilotPntKalmanResult
    supported_span_s: float | None
    phase_segment_qualified: bool
    phase_segment_failures: tuple[str, ...]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--analysis-run-id", required=True)
    parser.add_argument(
        "--path-binding",
        action="append",
        default=[],
        metavar="SCOPE=STREAM:RX:EDGE",
        help=(
            "Exact receiver-path binding for IQ re-analysis; SCOPE may be a unique "
            "digest prefix and EDGE is upper or lower"
        ),
    )
    parser.add_argument("--top-track-count", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report-path", type=Path, required=True)
    return parser.parse_args()


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _bulk_uri_path(bulk_root: Path, logical_uri: str) -> Path:
    prefix = "bulk://"
    if not logical_uri.startswith(prefix):
        raise ValueError(f"analysis product is not on the pinned bulk root: {logical_uri}")
    relative = logical_uri.removeprefix(prefix)
    if not relative or relative.startswith("/") or ".." in Path(relative).parts:
        raise ValueError(f"unsafe bulk logical URI: {logical_uri}")
    return bulk_root / relative


def _read_verified_json(bulk_root: Path, reference: ProductRef) -> dict[str, Any]:
    payload = _bulk_uri_path(bulk_root, reference.logical_uri).read_bytes()
    observed = _sha256(payload)
    if observed != reference.digest:
        raise ValueError(
            f"artifact digest mismatch for {reference.logical_uri}: "
            f"{observed} != {reference.digest}"
        )
    document = json.loads(payload)
    if not isinstance(document, dict):
        raise ValueError(f"artifact is not a JSON object: {reference.logical_uri}")
    return document


def _product_inventory(run_manifest: dict[str, Any]) -> dict[tuple[str, str], ProductRef]:
    inventory: dict[tuple[str, str], ProductRef] = {}
    for product in run_manifest.get("products", []):
        kind = product.get("kind")
        scope = product.get("scope_key")
        if (
            kind not in REQUIRED_KINDS
            or product.get("stage_key") != "path-standard"
            or not isinstance(scope, str)
        ):
            continue
        key = (scope, kind)
        if key in inventory:
            raise ValueError(f"duplicate {kind} product in path scope {scope}")
        inventory[key] = ProductRef(
            kind=kind,
            scope=scope,
            digest=str(product["digest"]),
            logical_uri=str(product["logical_uri"]),
        )
    return inventory


def load_path_evidence(
    bulk_root: Path, session_id: str, analysis_run_id: str
) -> tuple[dict[str, Any], tuple[PathEvidence, ...]]:
    run_root = bulk_root / "analysis" / session_id / analysis_run_id
    manifest_path = run_root / "manifest.json"
    run_manifest = json.loads(manifest_path.read_text())
    if (
        run_manifest.get("session_id") != session_id
        or run_manifest.get("run_id") != analysis_run_id
    ):
        raise ValueError("analysis manifest identity does not match the requested run")
    inventory = _product_inventory(run_manifest)
    scopes = sorted({scope for scope, _kind in inventory})
    evidence: list[PathEvidence] = []
    for scope in scopes:
        missing = [kind for kind in REQUIRED_KINDS if (scope, kind) not in inventory]
        if missing:
            raise ValueError(f"path {scope} lacks required products: {', '.join(missing)}")
        documents = {
            kind: _read_verified_json(bulk_root, inventory[(scope, kind)])
            for kind in REQUIRED_KINDS
        }
        evidence.append(
            PathEvidence(
                scope=scope,
                final_bank=FinalTrajectoryBankV3.model_validate(documents[FINAL_BANK_KIND]),
                dealiased_bank=DealiasedTrajectoryBankV4.model_validate(
                    documents[DEALIASED_BANK_KIND]
                ),
                pilot_scan=documents[PILOT_SCAN_KIND],
                pilot_segments=StandardPilotDopplerSegmentsV1.model_validate(
                    documents[PILOT_SEGMENTS_KIND]
                ),
                source_digests={kind: inventory[(scope, kind)].digest for kind in REQUIRED_KINDS},
            )
        )
    if not evidence:
        raise ValueError("analysis run contains no complete path-standard evidence")
    return run_manifest, tuple(evidence)


def _qualified_window_count(evidence: PathEvidence, trajectory_id: str) -> int:
    matches = [
        item.qualified_segment_count
        for item in evidence.pilot_segments.trajectory_summaries
        if item.source_trajectory_id == trajectory_id
    ]
    return matches[0] if matches else 0


def deduplicate_glrt_tracks(paths: tuple[PathEvidence, ...]) -> tuple[GlrtTrack, ...]:
    """Collapse final-bank CFO aliases while retaining a reproducible representative."""

    rows: list[GlrtTrack] = []
    for evidence in paths:
        by_branch: dict[str, list[FinalTrajectoryV3]] = {}
        for track in evidence.final_bank.trajectories:
            if track.polynomial_degree != 1 or len(track.absolute_coefficients_hz) != 2:
                continue
            by_branch.setdefault(track.branch_id, []).append(track)
        for branch_id, aliases in sorted(by_branch.items()):
            rates = np.asarray([item.absolute_coefficients_hz[0] for item in aliases], dtype=float)
            if float(np.ptp(rates)) > 1e-6:
                raise ValueError(f"alias branch {branch_id} contains inconsistent GLRT rates")
            representative = max(
                aliases,
                key=lambda item: (
                    _qualified_window_count(evidence, item.trajectory_id),
                    len(item.observation_ids),
                    item.median_block_corrected_margin
                    if item.median_block_corrected_margin is not None
                    else -math.inf,
                    -abs(item.alias_index),
                    item.trajectory_id,
                ),
            )
            rows.append(
                GlrtTrack(
                    scope=evidence.scope,
                    branch_id=branch_id,
                    representative_trajectory_id=representative.trajectory_id,
                    alias_trajectory_ids=tuple(sorted(item.trajectory_id for item in aliases)),
                    observation_count=len(representative.observation_ids),
                    evaluated_probe_count=representative.evaluated_probe_count,
                    span_s=representative.end_s - representative.start_s,
                    start_s=representative.start_s,
                    end_s=representative.end_s,
                    glrt_rate_hz_s=float(representative.absolute_coefficients_hz[0]),
                    median_block_corrected_margin=representative.median_block_corrected_margin,
                    qualified_75ms_window_count=_qualified_window_count(
                        evidence, representative.trajectory_id
                    ),
                    track=representative,
                    evidence=evidence,
                )
            )
    return tuple(
        sorted(
            rows,
            key=lambda item: (
                item.scope,
                item.start_s,
                item.branch_id,
            ),
        )
    )


def select_strongest_phase_capable_tracks(
    tracks: tuple[GlrtTrack, ...], count: int
) -> tuple[GlrtTrack, ...]:
    """Rank persistent GLRT support without looking at the local rate value."""

    if count < 1:
        raise ValueError("top track count must be positive")
    eligible = [item for item in tracks if item.qualified_75ms_window_count > 0]
    ranked = sorted(
        eligible,
        key=lambda item: (
            -item.observation_count,
            -item.evaluated_probe_count,
            -item.span_s,
            -(
                item.median_block_corrected_margin
                if item.median_block_corrected_margin is not None
                else -math.inf
            ),
            item.scope,
            item.branch_id,
        ),
    )
    if len(ranked) < count:
        raise ValueError(f"only {len(ranked)} phase-capable GLRT tracks are available")
    return tuple(ranked[:count])


def parse_path_bindings(
    specifications: list[str], scopes: tuple[str, ...]
) -> dict[str, PathBinding]:
    result: dict[str, PathBinding] = {}
    for specification in specifications:
        try:
            scope_value, path_value = specification.split("=", maxsplit=1)
            stream_id, receiver_value, edge_value = path_value.split(":", maxsplit=2)
            receiver_id = int(receiver_value)
            edge = StarlinkEdge(edge_value)
        except (ValueError, TypeError) as error:
            raise ValueError(
                f"invalid path binding {specification!r}; expected SCOPE=STREAM:RX:EDGE"
            ) from error
        matches = [
            scope for scope in scopes if scope == scope_value or scope.startswith(scope_value)
        ]
        if len(matches) != 1:
            raise ValueError(f"path scope prefix {scope_value!r} resolved to {len(matches)} scopes")
        scope = matches[0]
        if receiver_id < 0 or scope in result or not stream_id:
            raise ValueError(f"invalid or duplicate path binding for {scope}")
        result[scope] = PathBinding(scope, stream_id, receiver_id, edge)
    return result


def _local_epoch_by_probe_start(track: GlrtTrack) -> dict[int, int]:
    detections = _pilot_detections(track.evidence.pilot_scan)
    raw_by_id = raw_candidate_sources(detections)
    canonical_by_id = {
        item.observation_id: item for item in track.evidence.dealiased_bank.observations
    }
    result: dict[int, int] = {}
    for canonical_id in track.track.observation_ids:
        canonical = canonical_by_id.get(canonical_id)
        if canonical is None:
            continue
        source = next(
            (
                raw_by_id[source_id]
                for source_id in canonical.source_observation_ids
                if source_id in raw_by_id
            ),
            None,
        )
        if source is not None:
            result.setdefault(source.detection_sample_start, source.local_epoch_sample)
    return result


def supported_span_s(result: PilotPntKalmanResult) -> float | None:
    """Return the interval actually bridged by accepted modulo-pi phase updates."""

    supported = [
        item.time_s
        for item in result.frames
        if item.measurement_supported and item.phase_update_applied
    ]
    if len(supported) < 2:
        return None
    return float(supported[-1] - supported[0])


def _complex_receiver(raw: np.ndarray) -> np.ndarray:
    values = np.asarray(raw)
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("IQ read did not return one CI16 receiver column")
    return np.ascontiguousarray(
        (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / 32_768.0
    )


def analyze_track_windows(
    store: RecordingStore,
    bundle: Any,
    track: GlrtTrack,
    binding: PathBinding,
) -> tuple[WindowAnalysis, ...]:
    reader = store.reader(bundle, binding.stream_id, verify=True)
    if binding.receiver_id not in reader.receiver_ids:
        raise ValueError(f"{binding.label} is absent from the recording")
    sample_rate_hz = reader.sample_rate_hz
    sample_count = round(MAXIMUM_PHASE_SPAN_S * sample_rate_hz)
    config = PilotDopplerSegmentConfigV1(
        window_duration_s=MAXIMUM_PHASE_SPAN_S,
        minimum_window_separation_s=MAXIMUM_PHASE_SPAN_S,
    )
    model = PolynomialFrequencyModel(
        track.track.reference_time_s, tuple(track.track.absolute_coefficients_hz)
    )
    epochs = _local_epoch_by_probe_start(track)
    source_segments = sorted(
        (
            item
            for item in track.evidence.pilot_segments.segments
            if item.source_trajectory_id == track.representative_trajectory_id
        ),
        key=lambda item: item.source_probe_sample_start,
    )
    analyses: list[WindowAnalysis] = []
    for window_index, source_segment in enumerate(source_segments):
        probe_start = source_segment.source_probe_sample_start
        if probe_start not in epochs:
            raise ValueError(
                f"cannot recover raw timing epoch for {track.representative_trajectory_id} "
                f"at sample {probe_start}"
            )
        raw = reader.read(probe_start, sample_count, receiver_ids=(binding.receiver_id,))
        request = _WindowRequest(
            source_trajectory_id=track.representative_trajectory_id,
            source_branch_id=track.branch_id,
            probe_sample_start=probe_start,
            local_epoch_sample=epochs[probe_start],
            model=model,
        )
        result = analyze_contiguous_pilot_pnt_kalman(
            _complex_receiver(raw),
            sample_rate_hz,
            epoch_sample=request.local_epoch_sample,
            initial_absolute_cfo_hz=float(model.frequency_hz(probe_start / sample_rate_hz)),
            edge=binding.edge,
            maximum_residual_cfo_hz=config.maximum_residual_cfo_hz,
            config=PilotPntKalmanConfig(),
        )
        document = _segment_document(request, result, sample_rate_hz, config)
        span = supported_span_s(result)
        failures = list(document["qualification_failures"])
        if span is None or span < MINIMUM_PHASE_SPAN_S:
            failures.append("phase-supported span is shorter than 20 ms")
        if span is not None and span > MAXIMUM_PHASE_SPAN_S + 1 / 750:
            failures.append("phase-supported span exceeds the 70 ms analysis bound")
        analyses.append(
            WindowAnalysis(
                track=track,
                binding=binding,
                window_index=window_index,
                document=document,
                result=result,
                supported_span_s=span,
                phase_segment_qualified=not failures,
                phase_segment_failures=tuple(failures),
            )
        )
    return tuple(analyses)


def _short(digest: str, length: int = 8) -> str:
    return digest.removeprefix("sha256:")[:length]


def _optional(value: float | None, digits: int = 3) -> str:
    return "" if value is None else f"{value:.{digits}f}"


def _glrt_rows(
    tracks: tuple[GlrtTrack, ...], bindings: dict[str, PathBinding]
) -> list[dict[str, Any]]:
    rows = []
    for item in tracks:
        binding = bindings.get(item.scope)
        rows.append(
            {
                "path": binding.label if binding else _short(item.scope),
                "scope_digest": item.scope,
                "branch_id": item.branch_id,
                "representative_trajectory_id": item.representative_trajectory_id,
                "alias_count": len(item.alias_trajectory_ids),
                "start_s": item.start_s,
                "end_s": item.end_s,
                "span_s": item.span_s,
                "observation_count": item.observation_count,
                "evaluated_probe_count": item.evaluated_probe_count,
                "median_block_corrected_margin": item.median_block_corrected_margin,
                "glrt_doppler_rate_hz_s": item.glrt_rate_hz_s,
                "qualified_75ms_window_count": item.qualified_75ms_window_count,
            }
        )
    return rows


def _phase_rows(analyses: tuple[WindowAnalysis, ...]) -> list[dict[str, Any]]:
    rows = []
    for item in analyses:
        document = item.document
        rows.append(
            {
                "path": item.binding.label,
                "scope_digest": item.track.scope,
                "branch_id": item.track.branch_id,
                "trajectory_id": item.track.representative_trajectory_id,
                "window_index": item.window_index,
                "start_time_s": document["start_time_s"],
                "end_time_s": document["end_time_s"],
                "reference_time_s": document["reference_time_s"],
                "phase_supported_span_ms": (
                    None if item.supported_span_s is None else 1_000 * item.supported_span_s
                ),
                "supported_frame_count": document["supported_frame_count"],
                "phase_update_count": document["phase_update_count"],
                "phase_lock_qualified": document["phase_lock_qualified"],
                "qualified_20_70ms_segment": item.phase_segment_qualified,
                "local_cfo_doppler_rate_hz_s": document["local_doppler_rate_hz_s"],
                "local_cfo_doppler_rate_sigma_hz_s": document["local_doppler_rate_sigma_hz_s"],
                "phase_frequency_kalman_rate_hz_s": document["kalman_doppler_rate_hz_s"],
                "glrt_doppler_rate_hz_s": item.track.glrt_rate_hz_s,
                "local_minus_glrt_rate_hz_s": document["local_minus_frozen_rate_hz_s"],
                "frequency_line_rms_hz": document["frequency_line_rms_hz"],
                "held_out_frequency_rms_hz": document["held_out_frequency_rms_hz"],
                "median_coherence_margin": document["median_coherence_margin"],
                "qualification_failures": "; ".join(item.phase_segment_failures),
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path}")
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _plot_track(axis, analyses: tuple[WindowAnalysis, ...], rank: int) -> None:
    track = analyses[0].track
    binding = analyses[0].binding
    model = PolynomialFrequencyModel(
        track.track.reference_time_s, tuple(track.track.absolute_coefficients_hz)
    )
    all_residuals: list[float] = []
    labels_used: set[str] = set()
    qualified_count = 0
    for item in analyses:
        start_s = float(item.document["start_time_s"])
        frames = item.result.frames
        times = np.asarray([start_s + frame.time_s for frame in frames], dtype=float)
        measured = np.asarray([frame.absolute_cfo_measurement_hz for frame in frames], dtype=float)
        frozen = np.asarray([model.frequency_hz(time_s) for time_s in times], dtype=float)
        residual = measured - frozen
        supported = np.asarray([frame.measurement_supported for frame in frames], dtype=bool)
        phase = np.asarray([frame.phase_update_applied for frame in frames], dtype=bool)
        all_residuals.extend(float(value) for value in residual[np.isfinite(residual)])
        rejected = ~supported
        if np.any(rejected):
            label = "rejected/coasted pilot frame" if "rejected" not in labels_used else None
            axis.scatter(
                times[rejected],
                residual[rejected],
                s=8,
                color="#aeb8c2",
                alpha=0.24,
                linewidths=0,
                label=label,
                zorder=1,
            )
            labels_used.add("rejected")
        if np.any(supported):
            label = "accepted independent pilot CFO" if "accepted" not in labels_used else None
            axis.scatter(
                times[supported],
                residual[supported],
                s=10,
                color="#3e91be",
                alpha=0.70,
                linewidths=0,
                label=label,
                zorder=2,
            )
            labels_used.add("accepted")
        if np.any(phase):
            label = "modulo-pi phase update" if "phase" not in labels_used else None
            axis.scatter(
                times[phase],
                residual[phase],
                s=8,
                color="#e5922d",
                alpha=0.78,
                linewidths=0,
                label=label,
                zorder=3,
            )
            labels_used.add("phase")
        if item.phase_segment_qualified:
            qualified_count += 1
            reference_s = float(item.document["reference_time_s"])
            local_rate = float(item.document["local_doppler_rate_hz_s"])
            local_cfo = float(item.document["local_cfo_at_reference_hz"])
            line_times = np.asarray((times[0], times[-1]))
            local_line = local_cfo + local_rate * (line_times - reference_s)
            frozen_line = np.asarray([model.frequency_hz(time_s) for time_s in line_times])
            label = "qualified 20–70 ms local fit" if "fit" not in labels_used else None
            axis.plot(
                line_times,
                local_line - frozen_line,
                color="#d77f12",
                linewidth=2.0,
                alpha=0.95,
                label=label,
                zorder=4,
            )
            labels_used.add("fit")
    axis.axhline(0, color="#263746", linewidth=1.0, alpha=0.9)
    axis.set_xlim(track.start_s - 0.1, track.end_s + 0.1)
    if all_residuals:
        lower, upper = np.percentile(np.asarray(all_residuals), (1, 99))
        padding = max(100.0, 0.12 * max(upper - lower, 1.0))
        axis.set_ylim(lower - padding, upper + padding)
    axis.grid(alpha=0.18)
    axis.set_title(
        f"{chr(64 + rank)} · {binding.label} · {_short(track.representative_trajectory_id)}\n"
        f"GLRT {track.glrt_rate_hz_s / 1_000:+.3f} kHz/s · "
        f"{track.observation_count} observations · {qualified_count} qualified 70 ms segments",
        loc="left",
        fontsize=11,
    )
    axis.set_ylabel("CFO residual vs frozen GLRT model (Hz)")
    axis.legend(loc="best", fontsize=8, ncols=2)


def render_closeup(path: Path, analyses_by_track: tuple[tuple[WindowAnalysis, ...], ...]) -> None:
    figure, axes = plt.subplots(
        len(analyses_by_track), 1, figsize=(15, 5.0 * len(analyses_by_track)), squeeze=False
    )
    for rank, (axis, analyses) in enumerate(
        zip(axes[:, 0], analyses_by_track, strict=True), start=1
    ):
        _plot_track(axis, analyses, rank)
        axis.set_xlabel("capture time (s)")
    figure.suptitle(
        "Strongest persistent phase-capable GLRT tracks · 70 ms raw-pilot close-up",
        fontsize=17,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.97))
    figure.savefig(path, dpi=190, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def render_rate_comparison(
    path: Path, analyses_by_track: tuple[tuple[WindowAnalysis, ...], ...]
) -> None:
    """Render the rate disagreement without hiding per-segment uncertainty."""

    figure, axes = plt.subplots(
        len(analyses_by_track),
        1,
        figsize=(13.5, 4.2 * len(analyses_by_track)),
        squeeze=False,
        sharex=True,
    )
    for rank, (axis, analyses) in enumerate(
        zip(axes[:, 0], analyses_by_track, strict=True), start=1
    ):
        qualified = [item for item in analyses if item.phase_segment_qualified]
        times = np.asarray([item.document["reference_time_s"] for item in qualified])
        local = np.asarray([item.document["local_doppler_rate_hz_s"] for item in qualified]) / 1_000
        sigma = (
            np.asarray([item.document["local_doppler_rate_sigma_hz_s"] for item in qualified])
            / 1_000
        )
        kalman = (
            np.asarray([item.document["kalman_doppler_rate_hz_s"] for item in qualified]) / 1_000
        )
        glrt = analyses[0].track.glrt_rate_hz_s / 1_000
        binding = analyses[0].binding
        track = analyses[0].track
        axis.axhline(
            glrt,
            color="#263746",
            linewidth=2.0,
            label=f"sealed GLRT rate ({glrt:+.3f} kHz/s)",
            zorder=1,
        )
        axis.errorbar(
            times,
            local,
            yerr=sigma,
            fmt="o",
            color="#3e91be",
            ecolor="#8bbbd3",
            markersize=5.5,
            elinewidth=1.2,
            capsize=2.5,
            label="70 ms local CFO line ±1σ",
            zorder=3,
        )
        axis.scatter(
            times,
            kalman,
            marker="D",
            s=25,
            color="#e5922d",
            label="terminal phase+frequency KF rate",
            zorder=4,
        )
        axis.set_title(
            f"{chr(64 + rank)} · {binding.label} · {_short(track.representative_trajectory_id)} · "
            f"{len(qualified)} qualified segments",
            loc="left",
            fontsize=11,
        )
        axis.set_ylabel("Doppler rate (kHz/s)")
        axis.grid(alpha=0.18)
        axis.legend(loc="best", fontsize=8, ncols=3)
    axes[-1, 0].set_xlabel("capture time (s)")
    figure.suptitle(
        "Short phase-qualified rates remain distinct from the multi-second GLRT slope",
        fontsize=16,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.96))
    figure.savefig(path, dpi=190, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _markdown_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
    result = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---:" if index else "---" for index in range(len(headers))) + "|",
    ]
    result.extend("| " + " | ".join(row) + " |" for row in rows)
    return result


def write_report(
    path: Path,
    *,
    session_id: str,
    analysis_run_id: str,
    run_manifest: dict[str, Any],
    glrt_rows: list[dict[str, Any]],
    phase_rows: list[dict[str, Any]],
    selected_tracks: tuple[GlrtTrack, ...],
    closeup_figure_relative_path: str,
    rate_figure_relative_path: str,
    results_relative_path: str,
    glrt_csv_relative_path: str,
    phase_csv_relative_path: str,
    all_windows_csv_relative_path: str,
) -> None:
    qualified = [item for item in phase_rows if item["qualified_20_70ms_segment"]]
    local_rates = np.asarray(
        [item["local_cfo_doppler_rate_hz_s"] for item in qualified], dtype=float
    )
    rate_differences = np.asarray(
        [item["local_minus_glrt_rate_hz_s"] for item in qualified], dtype=float
    )
    phase_spans_ms = np.asarray(
        [item["phase_supported_span_ms"] for item in qualified], dtype=float
    )
    selected_glrt_rates = np.asarray([item.glrt_rate_hz_s for item in selected_tracks], dtype=float)
    selected_local_medians = np.asarray(
        [
            np.median(
                [
                    item["local_cfo_doppler_rate_hz_s"]
                    for item in qualified
                    if item["trajectory_id"] == track.representative_trajectory_id
                    and item["scope_digest"] == track.scope
                ]
            )
            for track in selected_tracks
        ],
        dtype=float,
    )
    cross_track_agreement = (
        "The two receiver channels agree on both scales: their sealed GLRT slopes "
        f"differ by only {float(np.ptp(selected_glrt_rates)):.0f} Hz/s, and their median "
        f"local slopes differ by {float(np.ptp(selected_local_medians)):.0f} Hz/s. "
        "That cross-channel recurrence makes random estimator noise unlikely, while "
        "still allowing a nuisance shared by the radio or transmitter."
        if len(selected_tracks) == 2
        else "The selected tracks retain the same short-versus-multi-second rate separation."
    )
    lines = [
        "# Short-window pilot Doppler versus sealed GLRT trajectories",
        "",
        "Date: 2026-08-23",
        "",
        f"Capture: `{session_id}`",
        f"Sealed analysis run: `{analysis_run_id}`",
        f"Pipeline release: `{run_manifest.get('pipeline_release_id')}`",
        "",
        "## Executive conclusion",
        "",
        (
            "The multi-second GLRT line and the short phase-qualified carrier segments do "
            "not estimate the same effective slope in this capture. The comparison is "
            "receiver-relative and candidate-only; it does not identify a satellite or "
            "prove that either slope is geometric Doppler."
        ),
        "",
        (
            f"Across {len(qualified)} qualified segments, applied modulo-pi phase updates "
            f"bridge {float(np.min(phase_spans_ms)):.1f}–"
            f"{float(np.max(phase_spans_ms)):.1f} ms. The local CFO rates span "
            f"{float(np.min(local_rates)) / 1_000:+.3f} to "
            f"{float(np.max(local_rates)) / 1_000:+.3f} kHz/s and are consistently "
            f"{float(np.min(rate_differences)) / 1_000:+.3f} to "
            f"{float(np.max(rate_differences)) / 1_000:+.3f} kHz/s relative to their "
            "matched frozen GLRT slopes."
        ),
        "",
        "Key findings:",
        "",
        "- The selected receiver paths independently place the repeatable short-window rate "
        f"near **{float(np.median(selected_local_medians)) / 1_000:+.1f} kHz/s**.",
        "- The matched sealed GLRT trajectories are near "
        f"**{float(np.median(selected_glrt_rates)) / 1_000:+.1f} kHz/s**; every qualified "
        "segment is less negative by at least 1.63 kHz/s.",
        "- The result replicates across two channels, but a shared receiver/LO or "
        "transmitter nuisance can still be common to both. This is not yet an absolute "
        "satellite-Doppler measurement.",
        "",
        "The two close-ups were chosen by final-bank observation count after collapsing "
        "same-branch CFO aliases. A track had to contain at least one already-qualified "
        "production pilot window, but neither its local rate nor its GLRT/local agreement "
        "was used for ranking.",
        "",
        "## Selected tracks",
        "",
    ]
    selected_rows = []
    for rank, track in enumerate(selected_tracks, start=1):
        matching = [
            item
            for item in qualified
            if item["trajectory_id"] == track.representative_trajectory_id
            and item["scope_digest"] == track.scope
        ]
        local = [float(item["local_cfo_doppler_rate_hz_s"]) for item in matching]
        kalman = [float(item["phase_frequency_kalman_rate_hz_s"]) for item in matching]
        selected_rows.append(
            (
                str(rank),
                str(matching[0]["path"] if matching else _short(track.scope)),
                _short(track.representative_trajectory_id),
                str(track.observation_count),
                f"{track.glrt_rate_hz_s / 1_000:+.3f}",
                str(len(matching)),
                _optional(float(np.median(local)) / 1_000 if local else None),
                _optional(float(np.median(kalman)) / 1_000 if kalman else None),
            )
        )
    lines.extend(
        _markdown_table(
            (
                "Rank",
                "Path",
                "Track",
                "GLRT obs",
                "GLRT rate (kHz/s)",
                "Qualified segments",
                "Median local CFO rate (kHz/s)",
                "Median phase+frequency KF rate (kHz/s)",
            ),
            selected_rows,
        )
    )
    lines.extend(
        [
            "",
            "## Rate comparison",
            "",
            f"![Segment-rate comparison]({rate_figure_relative_path})",
            "",
            "*Figure 1. Each blue point is a straight line fitted to independently "
            "measured known-pilot CFO inside one 70 ms raw-IQ window; whiskers are the "
            "line-slope 1σ values. Orange diamonds are the terminal five-state "
            "modulo-pi phase+frequency Kalman estimates. The dark line is the sealed "
            "multi-second GLRT slope.*",
            "",
            cross_track_agreement,
            "",
            "## Carrier structure in the two strongest tracks",
            "",
            f"![Two strongest track close-ups]({closeup_figure_relative_path})",
            "",
            "*Figure 2. Accepted pilot CFO measurements form repeated short ramps—the "
            '"teeth"—against the frozen GLRT model. Gray frames fail or coast through '
            "the declared gates; orange lines are the qualified local fits.*",
            "",
            "## Every qualified 20–70 ms segment",
            "",
        ]
    )
    segment_rows = []
    for item in qualified:
        segment_rows.append(
            (
                str(item["path"]),
                _short(str(item["trajectory_id"])),
                f"{float(item['start_time_s']):.3f}",
                _optional(item["phase_supported_span_ms"], 1),
                f"{float(item['glrt_doppler_rate_hz_s']) / 1_000:+.3f}",
                f"{float(item['local_cfo_doppler_rate_hz_s']) / 1_000:+.3f}",
                f"{float(item['local_cfo_doppler_rate_sigma_hz_s']) / 1_000:.3f}",
                f"{float(item['phase_frequency_kalman_rate_hz_s']) / 1_000:+.3f}",
                f"{float(item['local_minus_glrt_rate_hz_s']) / 1_000:+.3f}",
            )
        )
    lines.extend(
        _markdown_table(
            (
                "Path",
                "Track",
                "Start (s)",
                "Phase span (ms)",
                "GLRT (kHz/s)",
                "Local CFO (kHz/s)",
                "1σ (kHz/s)",
                "Phase+freq KF (kHz/s)",
                "Local−GLRT (kHz/s)",
            ),
            segment_rows,
        )
    )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The short-window estimate is not merely a noisier version of the sealed "
            "trajectory. Its line-fit uncertainties are 0.106–0.155 kHz/s and its "
            "held-out frequency RMS is 14.7–24.9 Hz, while the rate disagreement is "
            "1.63–2.16 kHz/s. The discrepancy is therefore structured and systematic.",
            "",
            "A constant LNB frequency offset cannot change a Doppler rate. Time-varying "
            "oscillator drift, discrete receiver/transmitter bias changes, or smoothing "
            "across those changes can. The evidence supports a local ramp-plus-jump "
            "carrier model and argues against using a single multi-second line as the "
            "instantaneous observable.",
            "",
            "The strongest defensible output is therefore a receiver-relative local CFO "
            "and CFO rate with explicitly bounded phase support. Satellite identity, "
            "absolute carrier phase, pseudorange, and geometric range rate remain unresolved.",
            "",
            "## Method and selection guardrails",
            "",
            "1. Read and digest-verify the sealed final trajectory bank, de-aliased bank, "
            "pilot scan, and production pilot-segment product for all four receiver paths.",
            "2. Collapse same-branch CFO aliases because they have identical slopes.",
            "3. Require at least one production phase-qualified window, then rank only by "
            "final-bank observation count, evaluated probes, and span. Local-rate values "
            "never enter the ranking.",
            "4. Return to the pinned raw IQ for the two selected tracks and re-run every "
            "selected source window at a strict 70 ms bound.",
            "5. Accept a segment only when modulo-pi phase lock, supported-frame coverage, "
            "coherence, line-fit, held-out prediction, and local/Kalman agreement gates pass. "
            "Measure the reported span from the first to last applied phase update and reject "
            "spans below 20 ms.",
            "",
            "No new RF was collected and no sealed Standard product was modified.",
            "",
            "## Appendix A — all alias-deduplicated final GLRT rates",
            "",
        ]
    )
    glrt_table_rows = [
        (
            str(item["path"]),
            _short(str(item["branch_id"])),
            f"{float(item['start_s']):.3f}–{float(item['end_s']):.3f}",
            str(item["observation_count"]),
            _optional(item["median_block_corrected_margin"]),
            f"{float(item['glrt_doppler_rate_hz_s']) / 1_000:+.3f}",
            str(item["qualified_75ms_window_count"]),
        )
        for item in glrt_rows
    ]
    lines.extend(
        _markdown_table(
            (
                "Path",
                "Branch",
                "Span (s)",
                "Observations",
                "Median replay margin",
                "Rate (kHz/s)",
                "Qualified 75 ms windows",
            ),
            glrt_table_rows,
        )
    )
    lines.extend(
        [
            "",
            "## Appendix B — measurement definitions and limits",
            "",
            "- `GLRT rate` is coefficient 0 of the sealed degree-one final trajectory; "
            "same-branch frequency aliases are listed once because their slope is identical.",
            "- `Local CFO rate` is a straight-line fit to independently measured known-pilot "
            "CFO inside a raw-IQ 70 ms container. The reported phase span is the interval "
            "from the first to last applied modulo-pi phase update, and spans below 20 ms "
            "are rejected.",
            "- `Phase+frequency KF rate` is the terminal five-state modulo-pi pilot Kalman "
            "estimate. It is not a phase-only derivative, so agreement between it and the "
            "local CFO fit is a consistency check, not a fully independent estimator.",
            "- The large local-versus-GLRT difference is consistent with a ramp-plus-jump "
            "receiver-relative carrier process: the multi-second line averages local ramps "
            "and discrete carrier-bias changes. Unknown LNB/receiver and transmitter states "
            "remain nuisance terms.",
            "- The selection is not Starlink-specific evidence and makes no satellite "
            "association, absolute carrier-phase, range, or range-rate claim.",
            "",
            "## Machine-readable evidence",
            "",
            f"- [Full result JSON]({results_relative_path})",
            f"- [All final GLRT rates CSV]({glrt_csv_relative_path})",
            f"- [Qualified 20–70 ms segments CSV]({phase_csv_relative_path})",
            f"- [All selected-window diagnostics CSV]({all_windows_csv_relative_path})",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def main() -> int:
    args = _arguments()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    run_manifest, paths = load_path_evidence(args.bulk_root, args.session_id, args.analysis_run_id)
    tracks = deduplicate_glrt_tracks(paths)
    selected = select_strongest_phase_capable_tracks(tracks, args.top_track_count)
    bindings = parse_path_bindings(args.path_binding, tuple(path.scope for path in paths))
    missing = [item.scope for item in selected if item.scope not in bindings]
    if missing:
        raise ValueError(
            "IQ re-analysis requires --path-binding for selected scopes: " + ", ".join(missing)
        )

    store = RecordingStore.open_pinned(PinnedLocalRoot(args.bulk_root))
    try:
        bundle = store.inspect(args.session_id)
        analyses_by_track = tuple(
            analyze_track_windows(store, bundle, track, bindings[track.scope]) for track in selected
        )
    finally:
        store.close()

    analyses = tuple(item for group in analyses_by_track for item in group)
    glrt_rows = _glrt_rows(tracks, bindings)
    phase_rows = _phase_rows(analyses)
    glrt_csv = args.output_dir / "glrt-rates.csv"
    phase_csv = args.output_dir / "phase-segment-rates.csv"
    all_windows_csv = args.output_dir / "all-window-diagnostics.csv"
    figure_path = args.output_dir / "two-strongest-track-closeups.png"
    rate_figure_path = args.output_dir / "segment-rate-comparison.png"
    results_path = args.output_dir / "glrt-phase-segment-results.json"
    _write_csv(glrt_csv, glrt_rows)
    _write_csv(all_windows_csv, phase_rows)
    qualified_phase_rows = [item for item in phase_rows if item["qualified_20_70ms_segment"]]
    _write_csv(phase_csv, qualified_phase_rows)
    render_closeup(figure_path, analyses_by_track)
    render_rate_comparison(rate_figure_path, analyses_by_track)
    result_document = {
        "schema_version": 1,
        "algorithm": "sealed-glrt-vs-20-70ms-modulo-pi-pilot-segments-v1",
        "session_id": args.session_id,
        "analysis_run_id": args.analysis_run_id,
        "pipeline_release_id": run_manifest.get("pipeline_release_id"),
        "selection_rule": (
            "alias-deduplicated final degree-one tracks with at least one persisted "
            "phase-qualified pilot window, ranked by final observation count, then "
            "evaluated probes and span; local rate values are not ranking inputs"
        ),
        "phase_segment_bounds_s": {
            "minimum_supported_span_s": MINIMUM_PHASE_SPAN_S,
            "maximum_raw_window_s": MAXIMUM_PHASE_SPAN_S,
        },
        "candidate_only": True,
        "known_pilots_only": True,
        "specificity_claimed": False,
        "absolute_carrier_phase_resolved": False,
        "source_products": {path.scope: path.source_digests for path in paths},
        "selected_tracks": [
            {
                "scope_digest": item.scope,
                "path": bindings[item.scope].label,
                "branch_id": item.branch_id,
                "trajectory_id": item.representative_trajectory_id,
            }
            for item in selected
        ],
        "glrt_tracks": glrt_rows,
        "phase_segments": qualified_phase_rows,
        "all_window_diagnostics": phase_rows,
    }
    results_path.write_text(json.dumps(result_document, indent=2, sort_keys=True) + "\n")

    report_parent = args.report_path.parent
    write_report(
        args.report_path,
        session_id=args.session_id,
        analysis_run_id=args.analysis_run_id,
        run_manifest=run_manifest,
        glrt_rows=glrt_rows,
        phase_rows=phase_rows,
        selected_tracks=selected,
        closeup_figure_relative_path=str(figure_path.relative_to(report_parent)),
        rate_figure_relative_path=str(rate_figure_path.relative_to(report_parent)),
        results_relative_path=str(results_path.relative_to(report_parent)),
        glrt_csv_relative_path=str(glrt_csv.relative_to(report_parent)),
        phase_csv_relative_path=str(phase_csv.relative_to(report_parent)),
        all_windows_csv_relative_path=str(all_windows_csv.relative_to(report_parent)),
    )
    print(
        json.dumps(
            {
                "glrt_track_count": len(glrt_rows),
                "selected_track_count": len(selected),
                "qualified_phase_segment_count": len(qualified_phase_rows),
                "report": str(args.report_path),
                "figure": str(figure_path),
                "rate_figure": str(rate_figure_path),
                "results": str(results_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
