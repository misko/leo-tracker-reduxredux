"""Bounded Standard-stage pilot detection, trajectory fitting, and IQ replay."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from typing import Any, Literal, cast

import numpy as np
from pydantic import JsonValue

from leo.analysis.cfo_lines import CfoPoint, circular_residual_hz
from leo.analysis.residual_hough import (
    ResidualHoughLine,
    ResidualHoughSelectionConfig,
    detect_all_residual_hough_lines,
    hough_config_from_contract,
)
from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
)
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    PilotProbeDetection,
    conditioned_glrt64_score,
    detect_pilot_method_candidates,
    detect_pilot_methods,
)
from leo.analysis.starlink.templates import StarlinkEdge
from leo.analysis.starlink.trajectories import (
    PolynomialTrajectory,
    TrajectoryBankResult,
    TrajectoryFamily,
    TrajectoryObservation,
    correct_polynomial_cfo,
    default_trajectory_bank_config,
    fit_trajectory_bank,
)
from leo.analysis.starlink.trajectory_accounting import associate_trajectory_baseline
from leo.contracts.alternate_cfo_tracks import ResidualHoughSegmentationConfigV2
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_pipeline import StandardPathInputBindV3
from leo.pipeline import (
    AnalysisContext,
    IqReader,
    OutputSink,
    ProductReader,
    StageOutcome,
    StageResult,
    StageSpec,
)
from leo.pipeline.scopes import ScopeKind


@dataclass(frozen=True, slots=True)
class TrajectoryFeedbackConfig:
    """Frozen, bounded sampling and replay policy for Standard analysis."""

    coarse_window_samples_per_second: int = 1
    subwindow_ms: int = 50
    probe_ms: int = 20
    probe_offsets_ms: tuple[int, ...] = (0, 25)
    maximum_outer_windows: int = 120
    maximum_replayed_families: int = 16
    maximum_scored_candidates_per_probe: int = 4
    maximum_segmentation_candidates_per_probe: int | None = None
    maximum_workers: int = 4
    cfo_acquisition_mode: Literal["independent_wide_per_probe"] = "independent_wide_per_probe"
    cfo_search_min_hz: float = -400_000.0
    cfo_search_max_hz: float = 400_000.0
    coarse_cfo_step_hz: float = 80_000.0
    fine_cfo_radius_hz: float = 80_000.0
    fine_cfo_step_hz: float = 500.0
    conditioned_cfo_radius_hz: float = 2_000.0
    conditioned_cfo_step_hz: float = 100.0
    retained_candidate_count: int = 8
    candidate_epoch_separation_samples: int = 20
    candidate_cfo_separation_hz: float = 80_000.0
    glrt_size: int = 512


def validate_maximum_replayed_families(maximum: int) -> int:
    """Return one valid replay-family bound, rejecting bool and nonpositive values."""

    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0:
        raise ValueError("maximum_replayed_families must be a positive integer")
    return maximum


def validate_trajectory_feedback_config(config: TrajectoryFeedbackConfig) -> None:
    """Validate the complete shared policy at every public computation boundary."""

    coarse = config.coarse_window_samples_per_second
    if isinstance(coarse, bool) or not isinstance(coarse, int) or coarse != 1:
        raise ValueError("only exact one-second coarse windows are supported")
    integers = (
        config.subwindow_ms,
        config.probe_ms,
        config.maximum_outer_windows,
        config.maximum_scored_candidates_per_probe,
        config.maximum_workers,
        config.retained_candidate_count,
        config.candidate_epoch_separation_samples,
        config.glrt_size,
    )
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in integers
    ):
        raise ValueError("trajectory feedback bounds must be positive integers")
    if not config.probe_ms <= config.subwindow_ms <= 1_000:
        raise ValueError("trajectory feedback window geometry is invalid")
    if 1_000 % config.subwindow_ms:
        raise ValueError("subwindow_ms must divide one second exactly")
    if (
        not config.probe_offsets_ms
        or config.probe_offsets_ms != tuple(sorted(set(config.probe_offsets_ms)))
        or any(
            isinstance(offset, bool) or not isinstance(offset, int)
            for offset in config.probe_offsets_ms
        )
        or any(
            offset < 0 or offset + config.probe_ms > config.subwindow_ms
            for offset in config.probe_offsets_ms
        )
    ):
        raise ValueError("probe offsets must be unique, ordered, and contained in each subwindow")
    if (
        config.cfo_acquisition_mode != "independent_wide_per_probe"
        or config.cfo_search_min_hz != -400_000.0
        or config.cfo_search_max_hz != 400_000.0
    ):
        raise ValueError("pilot acquisition must use an independent -400/+400 kHz search")
    acquisition_values = (
        config.coarse_cfo_step_hz,
        config.fine_cfo_radius_hz,
        config.fine_cfo_step_hz,
        config.conditioned_cfo_radius_hz,
        config.conditioned_cfo_step_hz,
        config.candidate_cfo_separation_hz,
    )
    if not all(math.isfinite(value) and value > 0 for value in acquisition_values):
        raise ValueError("pilot acquisition CFO steps, radii, and separation must be positive")
    if config.maximum_scored_candidates_per_probe > config.retained_candidate_count:
        raise ValueError("scored pilot candidates cannot exceed retained acquisition basins")
    if config.maximum_segmentation_candidates_per_probe is not None and (
        isinstance(config.maximum_segmentation_candidates_per_probe, bool)
        or not isinstance(config.maximum_segmentation_candidates_per_probe, int)
        or config.maximum_segmentation_candidates_per_probe < 1
        or config.maximum_segmentation_candidates_per_probe
        > config.maximum_scored_candidates_per_probe
    ):
        raise ValueError("segmentation candidate bound must be positive and no larger than scored")
    if config.glrt_size < 2 or config.glrt_size & (config.glrt_size - 1):
        raise ValueError("pilot GLRT size must be a power of two of at least two")
    validate_maximum_replayed_families(config.maximum_replayed_families)


class TrajectoryFeedbackAnalyzer:
    """Run every pilot method, fit d1/d2/d3 tracks, then dechirp and replay."""

    def __init__(
        self,
        spec: StageSpec,
        config: TrajectoryFeedbackConfig | None = None,
    ) -> None:
        config = config or TrajectoryFeedbackConfig()
        validate_trajectory_feedback_config(config)
        self.spec = spec
        self._config = config

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        binding = StandardPathInputBindV3.model_validate(products.read_subject_binding())
        _require_exact_path_binding(context, binding, iq)
        if len(iq.receiver_ids) != 1:
            return self._empty(context, outputs, "trajectory feedback requires one receiver scope")
        geometry = _geometry(iq.sample_rate_hz, self._config)
        if iq.sample_count < geometry.probe_samples:
            return self._empty(context, outputs, "recording is shorter than one pilot probe")
        edge = binding.starlink_edge
        detections = scan_legacy_pilot_detections(iq, self._config, edge=edge)
        bank, representatives = fit_legacy_pilot_trajectories(detections, self._config)
        replay = replay_pilot_trajectories(iq, detections, representatives, self._config, edge=edge)
        documents = _documents(
            context,
            detections,
            bank,
            representatives,
            replay,
            geometry,
        )
        published = tuple(
            outputs.publish_json(product, documents[product.kind])
            for product in self.spec.output_products
        )
        outcome = StageOutcome.COMPLETE if detections else StageOutcome.INSUFFICIENT_DATA
        return StageResult(
            outcome=outcome,
            products=published,
            summary={
                "probe_count": len(detections),
                "trajectory_count": len(bank.trajectories),
                "trajectory_family_count": len(bank.families),
                "replayed_family_count": len(representatives),
                "candidate_only": True,
            },
            message=(
                "candidate-only all-method polynomial trajectory feedback; no payload decoded"
                if detections
                else "no complete pilot probes"
            ),
        )

    def _empty(self, context: AnalysisContext, outputs: OutputSink, reason: str) -> StageResult:
        documents: dict[str, dict[str, JsonValue]] = {
            product.kind: {
                "schema_version": 1,
                "run_id": context.run_id,
                "candidate_only": True,
                "status": "insufficient",
                "reason": reason,
                "items": [],
            }
            for product in self.spec.output_products
        }
        published = tuple(
            outputs.publish_json(product, documents[product.kind])
            for product in self.spec.output_products
        )
        return StageResult(
            outcome=StageOutcome.INSUFFICIENT_DATA,
            products=published,
            summary={"probe_count": 0, "candidate_only": True},
            message=reason,
        )


def _require_exact_path_binding(
    context: AnalysisContext,
    binding: StandardPathInputBindV3,
    iq: IqReader,
) -> None:
    scope = context.scope
    if (
        scope is None
        or scope.kind is not ScopeKind.RECEIVER_PATH
        or (scope.session_id, scope.stream_id, scope.receiver_id)
        != (binding.session_id, binding.stream_id, binding.receiver_id)
    ):
        raise ValueError("path input binding does not match the exact analyzer scope")
    if (iq.receiver_ids, iq.sample_rate_hz, iq.sample_count, iq.center_frequency_hz) != (
        (binding.receiver_id,),
        binding.sample_rate_hz,
        binding.declared_sample_count,
        binding.tuned_center_frequency_hz,
    ):
        raise ValueError("IQ reader does not match the exact path input binding")


@dataclass(frozen=True, slots=True)
class _Geometry:
    outer_samples: int
    subwindow_samples: int
    probe_samples: int
    probe_offset_samples: tuple[int, ...]


def scan_pilot_detections(
    iq: IqReader,
    config: TrajectoryFeedbackConfig,
    *,
    edge: StarlinkEdge,
) -> tuple[PilotProbeDetection, ...]:
    """Read scheduled probes and emit deterministic bounded multi-basin certificates."""

    validate_trajectory_feedback_config(config)
    if len(iq.receiver_ids) != 1:
        raise ValueError("pilot scan requires one receiver scope")
    geometry = _geometry(iq.sample_rate_hz, config)
    calibration = _baseband_prior(iq.receiver_ids[0])
    acquisition = _independent_wide_acquisition(config, geometry.probe_samples)
    detection_batches = _bounded_parallel_batches(
        _iter_probe_batches(iq, geometry, config.maximum_outer_windows),
        lambda batch: _detect_batch(
            batch,
            iq.sample_rate_hz,
            calibration,
            acquisition,
            config.maximum_scored_candidates_per_probe,
            config.glrt_size,
            edge,
        ),
        config.maximum_workers,
    )
    return tuple(
        sorted(
            (item for batch in detection_batches for item in batch),
            key=lambda item: item.sample_start,
        )
    )


def scan_legacy_pilot_detections(
    iq: IqReader,
    config: TrajectoryFeedbackConfig,
    *,
    edge: StarlinkEdge,
) -> tuple[PilotProbeDetection, ...]:
    """Preserve the published v1 winner-only detector behavior."""

    validate_trajectory_feedback_config(config)
    if len(iq.receiver_ids) != 1:
        raise ValueError("pilot scan requires one receiver scope")
    geometry = _geometry(iq.sample_rate_hz, config)
    calibration = _baseband_prior(iq.receiver_ids[0])
    acquisition = _independent_wide_acquisition(config, geometry.probe_samples)
    batches = _bounded_parallel_batches(
        _iter_probe_batches(iq, geometry, config.maximum_outer_windows),
        lambda batch: _detect_batch(
            batch,
            iq.sample_rate_hz,
            calibration,
            acquisition,
            None,
            config.glrt_size,
            edge,
        ),
        config.maximum_workers,
    )
    return tuple(
        sorted(
            (item for batch in batches for item in batch),
            key=lambda item: item.sample_start,
        )
    )


def fit_pilot_trajectories(
    detections: tuple[PilotProbeDetection, ...],
    config: TrajectoryFeedbackConfig,
) -> tuple[TrajectoryBankResult, tuple[tuple[str, PolynomialTrajectory], ...]]:
    """Fit degree-1/2/3 candidate families without IQ access."""

    validate_trajectory_feedback_config(config)
    observations = trajectory_observations(detections)
    bank = fit_trajectory_bank(observations, default_trajectory_bank_config())
    return bank, select_trajectory_representatives(bank, config.maximum_replayed_families)


def fit_residual_hough_pilot_trajectories(
    detections: tuple[PilotProbeDetection, ...],
    config: TrajectoryFeedbackConfig,
    segmentation: ResidualHoughSegmentationConfigV2,
) -> tuple[TrajectoryBankResult, tuple[tuple[str, PolynomialTrajectory], ...]]:
    """Fit bounded, overlapping degree-one segments and select replay seeds."""

    validate_trajectory_feedback_config(config)
    source_observations = trajectory_observations(detections)
    observations = segmentation_trajectory_observations(detections, config)
    if len(observations) > segmentation.maximum_input_points:
        raise ValueError("pilot point inventory exceeds residual-Hough segmentation bound")
    by_id = {item.observation_id: item for item in observations}
    points = tuple(
        CfoPoint(
            point_id=item.observation_id,
            time_s=item.time_s,
            frequency_hz=item.tracking_cfo_hz,
            exact_score=item.score,
            control_score=0.0 if item.control_score is None else item.control_score,
            margin=item.margin,
        )
        for item in observations
    )
    hough = hough_config_from_contract(segmentation.initial_hough)
    selection_config = ResidualHoughSelectionConfig(
        minimum_split_gain=segmentation.minimum_split_gain,
        maximum_proposals=segmentation.maximum_proposals_per_parent,
        maximum_parent_support=segmentation.maximum_parent_support,
    )
    _, refined = detect_all_residual_hough_lines(
        points=points,
        hough_config=hough,
        selection_config=selection_config,
    )
    ranked: list[PolynomialTrajectory] = []
    for _parent, selection in refined:
        parent_trajectories = [
            _residual_line_trajectory(
                line,
                by_id=by_id,
                alias_spacing_hz=segmentation.initial_hough.alias_spacing_hz,
            )
            for line in selection.lines
        ]
        parent_trajectories.sort(
            key=lambda item: (
                -sum(_observation_weight(by_id[point_id]) for point_id in item.observation_ids),
                -(item.end_s - item.start_s),
                -item.point_count,
                item.residual_rms_hz,
                item.trajectory_id,
            )
        )
        ranked.extend(parent_trajectories)
    maximum = segmentation.initial_hough.maximum_published_tracks
    retained = tuple(
        sorted(
            ranked[:maximum],
            key=lambda item: (
                item.start_s,
                item.end_s,
                item.method.value,
                item.polynomial_degree,
                item.trajectory_id,
            ),
        )
    )
    families = tuple(
        sorted(
            (
                TrajectoryFamily(
                    canonical_digest({"members": (item.trajectory_id,)}),
                    item.trajectory_id,
                    (item.trajectory_id,),
                    item.start_s,
                    item.end_s,
                )
                for item in retained
            ),
            key=lambda item: (item.start_s, item.end_s, item.family_id),
        )
    )
    bank = TrajectoryBankResult(
        config_digest=canonical_digest(segmentation.model_dump(mode="json")),
        trajectories=retained,
        families=families,
        observation_count=len(source_observations),
        truncated_trajectory_count=max(0, len(ranked) - len(retained)),
    )
    return bank, select_trajectory_representatives(bank, config.maximum_replayed_families)


def _observation_weight(observation: TrajectoryObservation) -> float:
    control = 0.0 if observation.control_score is None else observation.control_score
    return min(max(observation.margin, 0.0) / max(control, 0.02), 16.0)


def _residual_line_trajectory(
    line: ResidualHoughLine,
    *,
    by_id: dict[str, TrajectoryObservation],
    alias_spacing_hz: float,
) -> PolynomialTrajectory:
    support = tuple(by_id[point_id] for point_id in line.point_ids)
    times = np.asarray([item.time_s for item in support], dtype=float)
    frequencies = np.asarray([item.tracking_cfo_hz for item in support], dtype=float)
    residual = circular_residual_hz(
        frequencies,
        line.mapped_slope_hz_per_s * times + line.mapped_intercept_hz,
        alias_spacing_hz,
    )
    reference_time_s = line.start_s
    coefficients = (
        line.mapped_slope_hz_per_s,
        line.mapped_slope_hz_per_s * reference_time_s + line.mapped_intercept_hz,
    )
    identity = {
        "method": PilotMethod.GLRT64.value,
        "degree": 1,
        "reference_time_s": round(reference_time_s, 12),
        "coefficients_hz": [round(float(value), 12) for value in coefficients],
        "observation_ids": list(line.point_ids),
    }
    sse = max(float(np.sum(residual**2)), np.finfo(float).tiny)
    count = len(support)
    bic = count * math.log(sse / count) + 2.0 * math.log(count)
    return PolynomialTrajectory(
        trajectory_id=canonical_digest(identity),
        method=PilotMethod.GLRT64,
        polynomial_degree=1,
        reference_time_s=reference_time_s,
        coefficients_hz=coefficients,
        start_s=line.start_s,
        end_s=line.end_s,
        observation_ids=line.point_ids,
        point_count=count,
        residual_rms_hz=float(np.sqrt(np.mean(residual**2))),
        bic=bic,
        high_gate=0.0,
        em_iterations=0,
    )


def fit_legacy_pilot_trajectories(
    detections: tuple[PilotProbeDetection, ...],
    config: TrajectoryFeedbackConfig,
) -> tuple[TrajectoryBankResult, tuple[tuple[str, PolynomialTrajectory], ...]]:
    validate_trajectory_feedback_config(config)
    observations = legacy_trajectory_observations(detections)
    bank = fit_trajectory_bank(observations, default_trajectory_bank_config())
    return bank, select_trajectory_representatives(bank, config.maximum_replayed_families)


def replay_pilot_trajectories(
    iq: IqReader,
    detections: tuple[PilotProbeDetection, ...],
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    config: TrajectoryFeedbackConfig,
    *,
    edge: StarlinkEdge,
    alias_indices: Mapping[str, int] | None = None,
    alias_spacing_hz: float | None = None,
) -> tuple[dict[str, JsonValue], ...]:
    """Read exact probes, apply any resolved alias lifts, and rerun detectors."""

    validate_trajectory_feedback_config(config)
    if (alias_indices is None) != (alias_spacing_hz is None):
        raise ValueError("replay alias indices and spacing must be supplied together")
    offsets: dict[str, float] = {}
    if alias_indices is not None and alias_spacing_hz is not None:
        if not math.isfinite(alias_spacing_hz) or alias_spacing_hz <= 0:
            raise ValueError("replay alias spacing must be finite and positive")
        trajectory_ids = {trajectory.trajectory_id for _, trajectory in representatives}
        if set(alias_indices) != trajectory_ids:
            raise ValueError("replay alias indices must exactly cover the representatives")
        if any(
            isinstance(index, bool) or not isinstance(index, int)
            for index in alias_indices.values()
        ):
            raise ValueError("replay alias indices must be integers")
        offsets = {
            trajectory_id: alias_indices[trajectory_id] * alias_spacing_hz
            for trajectory_id in trajectory_ids
        }
    geometry = _geometry(iq.sample_rate_hz, config)
    return _replay(
        iq,
        list(detections),
        representatives,
        geometry,
        config.maximum_outer_windows,
        config.maximum_workers,
        edge,
        offsets,
        conditioned_association_gate_hz=None,
        conditioned_glrt_size=config.glrt_size,
    )


def replay_pilot_trajectories_with_conditioned_scores(
    iq: IqReader,
    detections: tuple[PilotProbeDetection, ...],
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    config: TrajectoryFeedbackConfig,
    *,
    edge: StarlinkEdge,
    alias_indices: Mapping[str, int],
    alias_spacing_hz: float,
    association_gate_hz: float,
) -> tuple[dict[str, JsonValue], ...]:
    """Replay trajectories and pair GLRT with the associated baseline epoch."""

    validate_trajectory_feedback_config(config)
    if not math.isfinite(alias_spacing_hz) or alias_spacing_hz <= 0:
        raise ValueError("replay alias spacing must be finite and positive")
    if not math.isfinite(association_gate_hz) or association_gate_hz <= 0:
        raise ValueError("conditioned association gate must be finite and positive")
    trajectory_ids = {trajectory.trajectory_id for _, trajectory in representatives}
    if set(alias_indices) != trajectory_ids:
        raise ValueError("replay alias indices must exactly cover the representatives")
    if any(
        isinstance(index, bool) or not isinstance(index, int) for index in alias_indices.values()
    ):
        raise ValueError("replay alias indices must be integers")
    offsets = {
        trajectory_id: alias_indices[trajectory_id] * alias_spacing_hz
        for trajectory_id in trajectory_ids
    }
    geometry = _geometry(iq.sample_rate_hz, config)
    return _replay(
        iq,
        list(detections),
        representatives,
        geometry,
        config.maximum_outer_windows,
        config.maximum_workers,
        edge,
        offsets,
        conditioned_association_gate_hz=association_gate_hz,
        conditioned_glrt_size=config.glrt_size,
    )


def legacy_trajectory_replay_rows(
    rows: tuple[dict[str, JsonValue], ...],
) -> tuple[dict[str, JsonValue], ...]:
    """Project enriched internal replay rows onto the immutable V3 contract."""

    keys = (
        "family_id",
        "trajectory_id",
        "trajectory_method",
        "polynomial_degree",
        "sample_start",
        "time_s",
        "detector_method",
        "baseline_margin",
        "corrected_margin",
        "margin_delta",
        "corrected_residual_cfo_hz",
    )
    return tuple({key: row[key] for key in keys} for row in rows)


def infer_hough_replay_alias_indices(
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    observations: tuple[TrajectoryObservation, ...],
    *,
    alias_spacing_hz: float,
) -> dict[str, int]:
    """Resolve one constant lift per Hough segment from its own support.

    Hough geometry is intentionally modulo the pilot alias spacing.  Its
    supporting observations retain absolute acquisition coordinates, so their
    robust confidence-weighted integer mode identifies the physical lift used
    only for IQ replay.  Overlapping representatives are resolved separately.
    """

    if not math.isfinite(alias_spacing_hz) or alias_spacing_hz <= 0:
        raise ValueError("Hough replay alias spacing must be finite and positive")
    by_id = {item.observation_id: item for item in observations}
    if len(by_id) != len(observations):
        raise ValueError("Hough replay observations must have unique identities")
    result: dict[str, int] = {}
    for _, trajectory in representatives:
        if trajectory.trajectory_id in result:
            raise ValueError("Hough replay representatives must be unique")
        scores: dict[int, tuple[float, int]] = {}
        for observation_id in trajectory.observation_ids:
            observation = by_id.get(observation_id)
            if observation is None:
                raise ValueError("Hough replay representative has missing support")
            delta_hz = observation.tracking_cfo_hz - float(
                trajectory.frequency_hz(observation.time_s)
            )
            alias_index = round(delta_hz / alias_spacing_hz)
            weight, count = scores.get(alias_index, (0.0, 0))
            scores[alias_index] = (weight + _observation_weight(observation), count + 1)
        if not scores:
            raise ValueError("Hough replay representative has no support")
        result[trajectory.trajectory_id] = max(
            sorted(scores),
            key=lambda index: (
                scores[index][0],
                scores[index][1],
                -abs(index),
                -index,
            ),
        )
    return result


def _geometry(sample_rate_hz: int, config: TrajectoryFeedbackConfig) -> _Geometry:
    validate_trajectory_feedback_config(config)
    if sample_rate_hz <= 0:
        raise ValueError("sample rate must be positive")
    subwindow = sample_rate_hz * config.subwindow_ms
    probe = sample_rate_hz * config.probe_ms
    if subwindow % 1_000 or probe % 1_000:
        raise ValueError("window durations do not map to integral samples")
    offsets = tuple(sample_rate_hz * offset for offset in config.probe_offsets_ms)
    if any(offset % 1_000 for offset in offsets):
        raise ValueError("probe offsets do not map to integral samples")
    return _Geometry(
        sample_rate_hz,
        subwindow // 1_000,
        probe // 1_000,
        tuple(offset // 1_000 for offset in offsets),
    )


def _independent_wide_acquisition(
    config: TrajectoryFeedbackConfig, probe_samples: int
) -> SymbolwiseAcquisitionConfig:
    validate_trajectory_feedback_config(config)
    return SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=config.cfo_search_min_hz,
        residual_cfo_max_hz=config.cfo_search_max_hz,
        coarse_cfo_step_hz=config.coarse_cfo_step_hz,
        fine_cfo_radius_hz=config.fine_cfo_radius_hz,
        fine_cfo_step_hz=config.fine_cfo_step_hz,
        conditioned_cfo_radius_hz=config.conditioned_cfo_radius_hz,
        conditioned_cfo_step_hz=config.conditioned_cfo_step_hz,
        retained_candidate_count=config.retained_candidate_count,
        candidate_epoch_separation_samples=config.candidate_epoch_separation_samples,
        candidate_cfo_separation_hz=config.candidate_cfo_separation_hz,
        maximum_probe_samples=probe_samples,
    )


def _iter_probe_batches(
    iq: IqReader,
    geometry: _Geometry,
    maximum_outer_windows: int,
):
    """Yield one bounded task containing all scheduled probes in a coarse second."""

    receiver_index = 0
    pending = np.empty(0, dtype=np.complex128)
    pending_start = 0
    expected_start = 0
    outer_count = 0
    # Typed recording readers deliberately cap individual requests at 2**20
    # samples.  A one-second coarse window at the production 2.5 MHz rate is
    # assembled below, so the transport read size must remain independently
    # bounded.
    for block in iq.iter_blocks(block_samples=min(geometry.outer_samples, 2**20)):
        if block.metadata.session_sample_start != expected_start:
            raise ValueError("trajectory feedback requires contiguous IQ coverage")
        expected_start += block.metadata.sample_count
        values = (
            block.samples[:, receiver_index, 0].astype(np.float64)
            + 1j * block.samples[:, receiver_index, 1].astype(np.float64)
        ) / 32_768.0
        pending = np.concatenate((pending, values))
        while len(pending) >= geometry.outer_samples and outer_count < maximum_outer_windows:
            outer = pending[: geometry.outer_samples]
            yield tuple(
                (
                    pending_start + subwindow_start + probe_offset,
                    np.ascontiguousarray(
                        outer[
                            subwindow_start + probe_offset : subwindow_start
                            + probe_offset
                            + geometry.probe_samples
                        ]
                    ),
                )
                for subwindow_start in range(0, geometry.outer_samples, geometry.subwindow_samples)
                for probe_offset in geometry.probe_offset_samples
            )
            pending = pending[geometry.outer_samples :]
            pending_start += geometry.outer_samples
            outer_count += 1
        if outer_count >= maximum_outer_windows:
            return


def _detect_batch(
    batch: tuple[tuple[int, np.ndarray], ...],
    sample_rate_hz: int,
    calibration: ReceiverFrequencyCalibration,
    acquisition: SymbolwiseAcquisitionConfig,
    maximum_scored_candidates: int | None,
    glrt_size: int,
    edge: StarlinkEdge,
) -> tuple[PilotProbeDetection, ...]:
    result = []
    for sample_start, samples in batch:
        if maximum_scored_candidates is None:
            detected = detect_pilot_methods(
                samples,
                sample_rate_hz,
                sample_start=sample_start,
                calibration=calibration,
                acquisition_config=acquisition,
                edge=edge,
            )
        else:
            detected = detect_pilot_method_candidates(
                samples,
                sample_rate_hz,
                sample_start=sample_start,
                calibration=calibration,
                acquisition_config=acquisition,
                edge=edge,
                maximum_scored_candidates=maximum_scored_candidates,
                glrt_size=glrt_size,
            )
        result.append(detected)
    return tuple(result)


def _bounded_parallel_batches[BatchInput, BatchOutput](
    batches: Iterable[BatchInput],
    function: Callable[[BatchInput], BatchOutput],
    maximum_workers: int,
) -> tuple[BatchOutput, ...]:
    """Run coarse windows concurrently without retaining the whole dwell."""

    completed: dict[int, BatchOutput] = {}
    pending: dict[Future[BatchOutput], int] = {}
    with ThreadPoolExecutor(max_workers=maximum_workers) as executor:
        for index, batch in enumerate(batches):
            pending[executor.submit(function, batch)] = index
            if len(pending) >= maximum_workers * 2:
                finished, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in finished:
                    completed[pending.pop(future)] = future.result()
        while pending:
            finished, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in finished:
                completed[pending.pop(future)] = future.result()
    return tuple(completed[index] for index in sorted(completed))


def trajectory_observations(
    detections: tuple[PilotProbeDetection, ...],
) -> tuple[TrajectoryObservation, ...]:
    values = []
    for detection in detections:
        candidates = detection.candidates
        candidate_scores = (
            tuple((candidate.rank, candidate.scores) for candidate in candidates)
            if candidates
            else ((0, detection.scores),)
        )
        for candidate_rank, scores in candidate_scores:
            for score in scores:
                if score.method is not PilotMethod.GLRT64:
                    continue
                values.append(
                    TrajectoryObservation(
                        canonical_digest(
                            {
                                "sample_start": detection.sample_start,
                                "candidate_rank": candidate_rank,
                                "method": score.method.value,
                            }
                        ),
                        score.method,
                        detection.sample_start,
                        detection.time_s,
                        score.tracking_cfo_hz,
                        score.exact_score,
                        score.control_score,
                        score.margin,
                    )
                )
    return tuple(values)


def segmentation_trajectory_observations(
    detections: tuple[PilotProbeDetection, ...],
    config: TrajectoryFeedbackConfig,
) -> tuple[TrajectoryObservation, ...]:
    """Return the explicitly bounded candidate prefix used by residual Hough.

    Dense acquisition evidence remains intact in the persisted pilot scan.  This
    selector bounds only the downstream line fit and is deterministic because
    candidate ranks are stable within each independently scored probe.
    """

    limit = config.maximum_segmentation_candidates_per_probe
    if limit is None:
        return trajectory_observations(detections)
    selected = tuple(
        detection
        if not detection.candidates
        else PilotProbeDetection(
            status=detection.status,
            sample_start=detection.sample_start,
            time_s=detection.time_s,
            local_epoch_sample=detection.local_epoch_sample,
            acquired_cfo_hz=detection.acquired_cfo_hz,
            scores=detection.scores,
            qam_accuracy=detection.qam_accuracy,
            qam_evm=detection.qam_evm,
            reason=detection.reason,
            source_candidate_count=detection.source_candidate_count,
            truncated_candidate_count=detection.truncated_candidate_count,
            candidates=tuple(
                candidate for candidate in detection.candidates if candidate.rank < limit
            ),
        )
        for detection in detections
    )
    return trajectory_observations(selected)


def legacy_trajectory_observations(
    detections: tuple[PilotProbeDetection, ...],
) -> tuple[TrajectoryObservation, ...]:
    """Exact v1 winner-only observation IDs and values."""

    return tuple(
        TrajectoryObservation(
            canonical_digest(
                {"sample_start": detection.sample_start, "method": score.method.value}
            ),
            score.method,
            detection.sample_start,
            detection.time_s,
            score.tracking_cfo_hz,
            score.exact_score,
            score.control_score,
            score.margin,
        )
        for detection in detections
        for score in detection.scores
    )


def select_trajectory_representatives(
    bank: Any, maximum: int
) -> tuple[tuple[str, PolynomialTrajectory], ...]:
    maximum = validate_maximum_replayed_families(maximum)
    by_id = {item.trajectory_id: item for item in bank.trajectories}
    result = []
    for family in bank.families[:maximum]:
        members = tuple(by_id[item] for item in family.member_trajectory_ids)
        glrt64 = tuple(item for item in members if item.method is PilotMethod.GLRT64)
        if not glrt64:
            continue
        representative = min(
            glrt64,
            key=lambda item: (
                -float(item.end_s - item.start_s),
                item.bic / max(item.point_count, 1),
                item.polynomial_degree,
            ),
        )
        result.append((family.family_id, representative))
    return tuple(result)


def _replay(
    iq: IqReader,
    detections: list[PilotProbeDetection],
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    geometry: _Geometry,
    maximum_outer_windows: int,
    maximum_workers: int,
    edge: StarlinkEdge,
    frequency_offsets_hz: Mapping[str, float],
    *,
    conditioned_association_gate_hz: float | None,
    conditioned_glrt_size: int,
) -> tuple[dict[str, JsonValue], ...]:
    baseline = {item.sample_start: item for item in detections}
    result: list[dict[str, JsonValue]] = []
    replay_config = SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=-20_000.0,
        residual_cfo_max_hz=20_000.0,
        coarse_cfo_step_hz=10_000.0,
        fine_cfo_radius_hz=20_000.0,
        retained_candidate_count=2,
        maximum_probe_samples=geometry.probe_samples,
    )
    calibrations = {
        trajectory.trajectory_id: ReceiverFrequencyCalibration(
            "trajectory-corrected",
            0.0,
            canonical_digest({"trajectory_id": trajectory.trajectory_id}).removeprefix("sha256:"),
        )
        for _, trajectory in representatives
    }
    replayed = _bounded_parallel_batches(
        _iter_probe_batches(iq, geometry, maximum_outer_windows),
        lambda batch: _replay_batch(
            batch,
            iq.sample_rate_hz,
            representatives,
            baseline,
            calibrations,
            replay_config,
            edge,
            frequency_offsets_hz,
            conditioned_association_gate_hz,
            conditioned_glrt_size,
        ),
        maximum_workers,
    )
    result.extend(item for batch in replayed for item in batch)
    return tuple(
        sorted(
            result,
            key=lambda item: (
                str(item["family_id"]),
                cast(int, item["sample_start"]),
                str(item["detector_method"]),
            ),
        )
    )


def _replay_batch(
    batch: tuple[tuple[int, np.ndarray], ...],
    sample_rate_hz: int,
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    baseline: dict[int, PilotProbeDetection],
    calibrations: dict[str, ReceiverFrequencyCalibration],
    replay_config: SymbolwiseAcquisitionConfig,
    edge: StarlinkEdge,
    frequency_offsets_hz: Mapping[str, float],
    conditioned_association_gate_hz: float | None = None,
    conditioned_glrt_size: int = 512,
) -> tuple[dict[str, JsonValue], ...]:
    result: list[dict[str, JsonValue]] = []
    for sample_start, samples in batch:
        time_s = sample_start / sample_rate_hz
        for family_id, trajectory in representatives:
            if not trajectory.start_s <= time_s <= trajectory.end_s:
                continue
            corrected = correct_polynomial_cfo(
                samples,
                sample_rate_hz,
                sample_start,
                trajectory,
                frequency_offset_hz=frequency_offsets_hz.get(trajectory.trajectory_id, 0.0),
            )
            detected = detect_pilot_methods(
                corrected,
                sample_rate_hz,
                sample_start=sample_start,
                calibration=calibrations[trajectory.trajectory_id],
                acquisition_config=replay_config,
                edge=edge,
            )
            match = (
                None
                if conditioned_association_gate_hz is None
                else associate_trajectory_baseline(
                    baseline[sample_start],
                    trajectory,
                    frequency_offset_hz=frequency_offsets_hz.get(trajectory.trajectory_id, 0.0),
                    association_gate_hz=conditioned_association_gate_hz,
                )
            )
            conditioned_score = None
            conditioned_seed_cfo_hz = None
            if match is not None:
                lifted_trajectory_hz = float(trajectory.frequency_hz(time_s)) + (
                    frequency_offsets_hz.get(trajectory.trajectory_id, 0.0)
                )
                conditioned_seed_cfo_hz = match.trajectory_tracking_cfo_hz - lifted_trajectory_hz
                conditioned_score = conditioned_glrt64_score(
                    corrected,
                    sample_rate_hz,
                    epoch_sample=match.candidate_epoch_sample,
                    acquired_cfo_hz=conditioned_seed_cfo_hz,
                    edge=edge,
                    glrt_size=conditioned_glrt_size,
                )
            original = {score.method: score for score in baseline[sample_start].scores}
            for score in detected.scores:
                before = original.get(score.method)
                if before is None:
                    continue
                row = cast(
                    dict[str, JsonValue],
                    {
                        "family_id": family_id,
                        "trajectory_id": trajectory.trajectory_id,
                        "trajectory_method": trajectory.method.value,
                        "polynomial_degree": trajectory.polynomial_degree,
                        "sample_start": sample_start,
                        "time_s": time_s,
                        "detector_method": score.method.value,
                        "baseline_margin": before.margin,
                        "corrected_margin": score.margin,
                        "margin_delta": score.margin - before.margin,
                        "corrected_residual_cfo_hz": score.tracking_cfo_hz,
                    },
                )
                if score.method is PilotMethod.GLRT64 and match is not None:
                    assert conditioned_score is not None
                    assert conditioned_seed_cfo_hz is not None
                    row.update(
                        {
                            "conditioned_corrected_margin": conditioned_score.margin,
                            "conditioned_tracking_cfo_hz": conditioned_score.tracking_cfo_hz,
                            "conditioned_epoch_sample": match.candidate_epoch_sample,
                            "conditioned_seed_cfo_hz": conditioned_seed_cfo_hz,
                        }
                    )
                result.append(
                    cast(
                        dict[str, JsonValue],
                        row,
                    )
                )
    return tuple(result)


def _documents(context, detections, bank, representatives, replay, geometry):
    common = {
        "schema_version": 1,
        "run_id": context.run_id,
        "scope_key": context.scope_key,
        "candidate_only": True,
        "payload_decoded": False,
    }
    return {
        "starlink.pilot-method-detections": cast(
            dict[str, JsonValue],
            {
                **common,
                "coarse_window_samples": geometry.outer_samples,
                "subwindow_samples": geometry.subwindow_samples,
                "probe_samples": geometry.probe_samples,
                "methods": [method.value for method in PilotMethod],
                "detections": [_legacy_detection_document(item) for item in detections],
            },
        ),
        "starlink.polynomial-trajectories": cast(
            dict[str, JsonValue],
            {
                **common,
                "config_digest": bank.config_digest,
                "observation_count": bank.observation_count,
                "truncated_trajectory_count": bank.truncated_trajectory_count,
                "trajectories": [asdict(item) for item in bank.trajectories],
                "families": [asdict(item) for item in bank.families],
                "replayed_representatives": [
                    {"family_id": family_id, **asdict(trajectory)}
                    for family_id, trajectory in representatives
                ],
            },
        ),
        "starlink.trajectory-redetection": cast(
            dict[str, JsonValue],
            {**common, "results": list(replay)},
        ),
        "starlink.glrt64-trajectory-table": cast(
            dict[str, JsonValue],
            {
                **common,
                "frequency_model": "cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)",
                "coefficient_order": "highest_polynomial_power_first",
                "fit_gate_hz": 2_500.0,
                "trajectories": build_glrt64_trajectory_table(bank, representatives, replay),
            },
        ),
    }


def _legacy_detection_document(item: PilotProbeDetection) -> dict[str, Any]:
    """Keep the published v1 document closed despite richer internal evidence."""

    return {
        "status": item.status,
        "sample_start": item.sample_start,
        "time_s": item.time_s,
        "local_epoch_sample": item.local_epoch_sample,
        "acquired_cfo_hz": item.acquired_cfo_hz,
        "scores": [asdict(score) for score in item.scores],
        "qam_accuracy": item.qam_accuracy,
        "qam_evm": item.qam_evm,
        "reason": item.reason,
    }


def _baseband_prior(receiver_id: int) -> ReceiverFrequencyCalibration:
    """Internal numerical coordinate only; never persisted as calibration authority."""

    return ReceiverFrequencyCalibration(
        receiver_id=str(receiver_id),
        center_hz=0.0,
        calibration_sha256=canonical_digest(
            {
                "receiver_id": receiver_id,
                "frequency_reference": "uncalibrated_prior",
                "coordinate": "baseband_cfo_hz",
            }
        ).removeprefix("sha256:"),
    )


def build_glrt64_trajectory_table(
    bank: Any,
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    replay: tuple[dict[str, JsonValue], ...],
) -> list[dict[str, JsonValue]]:
    family_by_member = {
        trajectory_id: family.family_id
        for family in bank.families
        for trajectory_id in family.member_trajectory_ids
    }
    replayed = {trajectory.trajectory_id for _, trajectory in representatives}
    result = []
    for trajectory in bank.trajectories:
        if trajectory.method is not PilotMethod.GLRT64:
            continue
        family_id = family_by_member.get(trajectory.trajectory_id)
        delta_values: list[float] = []
        for item in replay:
            if (
                item["trajectory_id"] != trajectory.trajectory_id
                or item["detector_method"] != "glrt64"
            ):
                continue
            value = item["margin_delta"]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("GLRT-64 replay margin delta must be numeric")
            delta_values.append(float(value))
        deltas = np.asarray(delta_values, dtype=np.float64)
        result.append(
            cast(
                dict[str, JsonValue],
                {
                    "trajectory_id": trajectory.trajectory_id,
                    "family_id": family_id,
                    "model": {1: "linear", 2: "quadratic", 3: "cubic"}[
                        trajectory.polynomial_degree
                    ],
                    "polynomial_degree": trajectory.polynomial_degree,
                    "reference_time_s": trajectory.reference_time_s,
                    "coefficients_hz": list(trajectory.coefficients_hz),
                    "start_s": trajectory.start_s,
                    "end_s": trajectory.end_s,
                    "duration_s": trajectory.end_s - trajectory.start_s,
                    "point_count": trajectory.point_count,
                    "residual_rms_hz": trajectory.residual_rms_hz,
                    "bic": trajectory.bic,
                    "high_gate": trajectory.high_gate,
                    "em_iterations": trajectory.em_iterations,
                    "fit_matches_well": trajectory.residual_rms_hz <= 2_500.0,
                    "selected_for_correction": trajectory.trajectory_id in replayed,
                    "corrected_glrt64_probe_count": int(deltas.size),
                    "median_glrt64_margin_delta": (
                        float(np.median(deltas)) if deltas.size else None
                    ),
                },
            )
        )
    return result
