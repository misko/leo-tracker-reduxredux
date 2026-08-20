"""Executable adapters for the bounded whole-dwell numerical pipeline.

The numerical functions remain infrastructure blind.  These adapters give the
processing service concrete stage implementations and publish bounded JSON
products.  A shared run/scope coordinator computes the bounded bundle once per
worker process; after a worker restart it deterministically recomputes from the
immutable IQ input instead of depending on process-local state.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass
from threading import RLock
from typing import Any, ClassVar, cast

import numpy as np
from pydantic import JsonValue

from leo.analysis.controls import (
    ControlConfig,
    ScientificSummary,
    build_scientific_summary,
    evaluate_candidate_controls,
)
from leo.analysis.doppler import (
    DopplerFitConfig,
    LockedFrame,
    LockedIntegrationConfig,
    LockedIntegrationResult,
    associate_tle_candidate,
    dedoppler_locked_integration,
    fit_doppler,
)
from leo.analysis.graphs import (
    ComputeTier,
    long_dwell_budget,
    long_dwell_stage_specs,
    validated_long_dwell_registry,
)
from leo.analysis.power import PowerAnalyzer
from leo.analysis.presentation import (
    WholeDwellPresentationAnalyzer,
    WholeDwellPresentationBundle,
    whole_dwell_presentation_documents,
)
from leo.analysis.quality import QualityAnalyzer
from leo.analysis.standard.analyzers import (
    production_standard_v2_configuration as _production_standard_v2_configuration,
)
from leo.analysis.standard.analyzers import (
    production_standard_v2_registry as _production_standard_v2_registry,
)
from leo.analysis.starlink import NumericalStatus, ReceiverFrequencyCalibration
from leo.analysis.starlink.glrt64_presentation import Glrt64TrajectoryPresentationAnalyzer
from leo.analysis.starlink.long_dwell import (
    ActivityTrackingConfig,
    CandidateCloudConfig,
    DenseRefinementConfig,
    DenseRefinementResult,
    DenseRefinementWindow,
    RawValidationResult,
    SparseSurveyConfig,
    build_candidate_cloud,
    dense_refine_candidates,
    qam_handoff,
    sparse_whole_dwell_survey,
    track_candidate_activity,
    validate_raw_iq,
)
from leo.analysis.starlink.trajectory_feedback import TrajectoryFeedbackAnalyzer
from leo.analysis.waterfall import WaterfallConfig, bounded_waterfall
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_pipeline import StandardPathInputBindV3
from leo.contracts.states import StarlinkEdge
from leo.pipeline import (
    AnalysisContext,
    AnalyzerRegistry,
    IqReader,
    OutputSink,
    ProductReader,
    StageOutcome,
    StageResult,
    StageSpec,
)


@dataclass(frozen=True, slots=True)
class ComputedLongDwell:
    raw: RawValidationResult
    dense_windows: tuple[DenseRefinementWindow, ...]
    refined: DenseRefinementResult
    locked: LockedIntegrationResult
    bundle: WholeDwellPresentationBundle


class LongDwellCoordinator:
    """Bounded deterministic computation shared by concrete stage adapters."""

    def __init__(
        self,
        tier: ComputeTier | str,
        *,
        configurations: dict[str, dict[str, JsonValue]] | None = None,
        maximum_cached_scopes: int = 2,
    ) -> None:
        if maximum_cached_scopes < 1:
            raise ValueError("maximum_cached_scopes must be positive")
        self.tier = ComputeTier(tier)
        self.budget = long_dwell_budget(self.tier)
        self._configurations = configurations or {}
        self._maximum_cached_scopes = maximum_cached_scopes
        self._cache: OrderedDict[tuple[str, str], ComputedLongDwell] = OrderedDict()
        self._lock = RLock()

    @property
    def pipeline_configuration(self) -> dict[str, dict[str, JsonValue]]:
        return {
            item.stage_key: {
                **item.config_dict(),
                **self._configurations.get(item.stage_key, {}),
            }
            for item in self.budget.stages
            if item.enabled
        }

    def compute(
        self, context: AnalysisContext, iq: IqReader, *, edge: StarlinkEdge
    ) -> ComputedLongDwell:
        identity = (context.run_id, f"{context.scope_key}.{edge.value}")
        with self._lock:
            cached = self._cache.get(identity)
            if cached is not None:
                self._cache.move_to_end(identity)
        if cached is not None:
            return cached
        computed = self._compute(context, iq, edge=edge)
        with self._lock:
            cached = self._cache.setdefault(identity, computed)
            self._cache.move_to_end(identity)
            while len(self._cache) > self._maximum_cached_scopes:
                self._cache.popitem(last=False)
            return cached

    @property
    def cached_scope_count(self) -> int:
        with self._lock:
            return len(self._cache)

    def release(self, context: AnalysisContext, *, edge: StarlinkEdge) -> None:
        """Release one completed run/scope after its final presentation stage."""

        with self._lock:
            self._cache.pop((context.run_id, f"{context.scope_key}.{edge.value}"), None)

    def _compute(
        self, context: AnalysisContext, iq: IqReader, *, edge: StarlinkEdge
    ) -> ComputedLongDwell:
        raw_config = self._config("raw-validate")
        raw = validate_raw_iq(iq, block_samples=_int(raw_config, "block_samples", 262_144))

        waterfall_config = self._config("waterfall")
        waterfall = bounded_waterfall(
            iq,
            WaterfallConfig(
                fft_samples=_int(waterfall_config, "fft_samples", 1024),
                frequency_bins=_int(waterfall_config, "frequency_bins", 128),
                maximum_time_bins=_int(
                    waterfall_config,
                    "maximum_time_bins",
                    256,
                ),
                block_samples=_int(waterfall_config, "block_samples", 262_144),
            ),
        )
        calibrations = _receiver_calibrations(iq)
        survey_config_values = self._config("starlink-survey")
        survey = sparse_whole_dwell_survey(
            iq,
            calibrations,
            SparseSurveyConfig(
                probe_samples=_int(survey_config_values, "probe_samples", 14_000),
                maximum_windows=_int(survey_config_values, "maximum_windows", 24),
                block_samples=_int(survey_config_values, "block_samples", 262_144),
                maximum_buffered_samples=_int(
                    survey_config_values,
                    "maximum_buffered_samples",
                    500_000,
                ),
                residual_cfo_min_hz=_float(
                    survey_config_values,
                    "residual_cfo_min_hz",
                    -400_000.0,
                ),
                residual_cfo_max_hz=_float(
                    survey_config_values,
                    "residual_cfo_max_hz",
                    400_000.0,
                ),
                coarse_cfo_step_hz=_float(
                    survey_config_values,
                    "coarse_cfo_step_hz",
                    80_000.0,
                ),
                retained_candidates_per_search=_int(
                    survey_config_values,
                    "retained_candidates_per_search",
                    8,
                ),
            ),
            edge=edge,
        )
        cloud_values = self._config("candidate-cloud")
        cloud = build_candidate_cloud(
            survey,
            CandidateCloudConfig(
                maximum_candidates=_int(cloud_values, "maximum_candidates", 64),
                minimum_margin=_float(cloud_values, "minimum_margin", 0.0),
                epoch_basin_separation_samples=_int(
                    cloud_values,
                    "epoch_basin_separation_samples",
                    20,
                ),
                cfo_basin_separation_hz=_float(
                    cloud_values,
                    "cfo_basin_separation_hz",
                    20_000.0,
                ),
            ),
        )
        track_values = self._config("activity-track")
        tracks = track_candidate_activity(
            cloud,
            ActivityTrackingConfig(
                maximum_window_gap=_int(track_values, "maximum_window_gap", 2),
                maximum_cfo_step_hz=_float(
                    track_values,
                    "maximum_cfo_step_hz",
                    30_000.0,
                ),
                minimum_observations=_int(track_values, "minimum_observations", 2),
            ),
        )
        dense_values = self._config("dense-refine")
        maximum_dense_windows = _int(dense_values, "maximum_windows", 32)
        maximum_probe_samples = _int(
            dense_values,
            "maximum_probe_samples",
            50_000,
        )
        dense_windows = _candidate_windows(
            iq,
            cloud.candidates[:maximum_dense_windows],
            calibrations,
            maximum_probe_samples=maximum_probe_samples,
            block_samples=_int(raw_config, "block_samples", 262_144),
        )
        refined = dense_refine_candidates(
            dense_windows,
            iq.sample_rate_hz,
            DenseRefinementConfig(
                residual_cfo_radius_hz=_float(
                    dense_values,
                    "residual_cfo_radius_hz",
                    2_000.0,
                ),
                conditioned_cfo_step_hz=_float(
                    dense_values,
                    "conditioned_cfo_step_hz",
                    10.0,
                ),
                maximum_windows=maximum_dense_windows,
                maximum_probe_samples=maximum_probe_samples,
            ),
            edge=edge,
        )
        doppler_values = self._config("doppler")
        polynomial_order = _int(doppler_values, "polynomial_order", 2)
        doppler = fit_doppler(
            refined.refined,
            iq.sample_rate_hz,
            DopplerFitConfig(
                polynomial_order=polynomial_order,
                minimum_points=_int(
                    doppler_values,
                    "minimum_points",
                    polynomial_order + 2,
                ),
                maximum_points=_int(doppler_values, "maximum_points", 2048),
                stationary_slope_limit_hz_s=_float(
                    doppler_values,
                    "stationary_slope_limit_hz_s",
                    5.0,
                ),
                stationary_excursion_limit_hz=_float(
                    doppler_values,
                    "stationary_excursion_limit_hz",
                    100.0,
                ),
                maximum_residual_rms_hz=_float(
                    doppler_values,
                    "maximum_residual_rms_hz",
                    5_000.0,
                ),
            ),
        )
        locked_values = self._config("locked-integrate")
        locked_config = LockedIntegrationConfig(
            maximum_frames=_int(locked_values, "maximum_frames", 256),
            maximum_frame_samples=_int(
                locked_values,
                "maximum_frame_samples",
                maximum_probe_samples,
            ),
            minimum_frames=_int(locked_values, "minimum_frames", 2),
        )
        frames = _locked_frames(
            dense_windows,
            refined,
            maximum_frames=locked_config.maximum_frames,
        )
        locked = dedoppler_locked_integration(
            frames,
            iq.sample_rate_hz,
            doppler,
            locked_config,
        )
        qam = qam_handoff(dense_windows, refined, iq.sample_rate_hz, edge=edge)
        control_values = self._config("controls")
        controls = evaluate_candidate_controls(
            dense_windows,
            refined,
            qam,
            doppler,
            iq.sample_rate_hz,
            ControlConfig(
                surrogate_symbol_rolls=_surrogate_rolls(control_values),
                minimum_held_out_margin=_float(
                    control_values,
                    "minimum_held_out_margin",
                    0.05,
                ),
                minimum_surrogate_margin=_float(
                    control_values,
                    "minimum_surrogate_margin",
                    0.03,
                ),
                minimum_qam_accuracy=_float(
                    control_values,
                    "minimum_qam_accuracy",
                    0.6,
                ),
                maximum_qam_evm=_float(control_values, "maximum_qam_evm", 1.25),
                thresholds_calibrated=_bool(
                    control_values,
                    "thresholds_calibrated",
                    False,
                ),
            ),
            edge=edge,
        )
        tle_values = self._config("tle-associate")
        tle = associate_tle_candidate(
            doppler,
            None,
            maximum_frequency_residual_hz=_float(
                tle_values,
                "maximum_frequency_residual_hz",
                25_000.0,
            ),
            maximum_slope_residual_hz_s=_float(
                tle_values,
                "maximum_slope_residual_hz_s",
                500.0,
            ),
        )
        summary = build_scientific_summary(
            sample_rate_hz=iq.sample_rate_hz,
            waterfall=waterfall,
            cloud=cloud,
            tracks=tracks,
            doppler=doppler,
            qam=qam,
            controls=controls,
            tle=tle,
        )
        identity_digest = canonical_digest(
            {
                "session_id": context.session_id,
                "scope_key": context.scope_key,
                "sample_rate_hz": iq.sample_rate_hz,
                "sample_count": iq.sample_count,
                "receiver_ids": iq.receiver_ids,
            }
        )
        configuration_digest = canonical_digest(
            {
                "compute_tier": self.tier.value,
                "stages": self.pipeline_configuration,
            }
        )
        bundle = WholeDwellPresentationBundle(
            compute_tier=self.tier,
            recording_digest=identity_digest,
            pipeline_config_digest=configuration_digest,
            receiver_tuned_center_hz=float(iq.center_frequency_hz),
            waterfall=waterfall,
            survey=survey,
            cloud=cloud,
            tracks=tracks,
            doppler=doppler,
            qam=qam,
            controls=controls,
            tle=tle,
            summary=summary,
        )
        return ComputedLongDwell(raw, dense_windows, refined, locked, bundle)

    def _config(self, stage_key: str) -> dict[str, JsonValue]:
        return self.pipeline_configuration.get(stage_key, {})


class _RawValidationAnalyzer:
    def __init__(self, coordinator: LongDwellCoordinator, spec: StageSpec) -> None:
        self._coordinator = coordinator
        self.spec = spec

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        config = self._coordinator.pipeline_configuration[self.spec.key]
        result = validate_raw_iq(
            iq,
            block_samples=_int(config, "block_samples", 262_144),
        )
        document = {"schema_version": 1, "run_id": context.run_id, **asdict(result)}
        published = outputs.publish_json(self.spec.output_products[0], cast(Any, document))
        outcome = _coverage_outcome(result.observed_samples, result.coverage_fraction)
        return StageResult(
            outcome=outcome,
            products=(published,),
            summary={"coverage_fraction": result.coverage_fraction},
            message=None if outcome is StageOutcome.COMPLETE else result.reason,
        )


class _DelegatingAnalyzer:
    """Attach canonical graph dependencies to an existing pure analyzer."""

    def __init__(self, delegate: QualityAnalyzer | PowerAnalyzer, spec: StageSpec) -> None:
        self._delegate = delegate
        self.spec = spec

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        return self._delegate.analyze(context, iq, products, outputs)


class _ComputedStageAnalyzer:
    _PRESENTATION_KEYS: ClassVar[dict[str, str]] = {
        "waterfall.presentation": "waterfall.presentation",
        "detection.presentation": "detection.presentation",
        "qam.presentation": "qam.presentation",
        "doppler.presentation": "doppler.presentation",
        "controls.presentation": "controls.presentation",
        "overlays.presentation": "overlays.presentation",
        "provenance.presentation": "provenance.presentation",
        "carrier-timing.presentation": "carrier-timing.presentation",
        "qam-timeline.presentation": "qam-timeline.presentation",
        "analysis-stage-timeline.presentation": "analysis-stage-timeline.presentation",
    }

    def __init__(self, coordinator: LongDwellCoordinator, spec: StageSpec) -> None:
        self._coordinator = coordinator
        self.spec = spec

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        binding = StandardPathInputBindV3.model_validate(products.read_subject_binding())
        computed = self._coordinator.compute(context, iq, edge=binding.starlink_edge)
        documents = _stage_documents(context.run_id, self.spec.key, computed)
        published = tuple(
            outputs.publish_json(product, documents[product.kind])
            for product in self.spec.output_products
        )
        outcome, message = _computed_outcome(self.spec.key, computed)
        bundle = computed.bundle
        result = StageResult(
            outcome=outcome,
            products=published,
            summary={
                "coverage_fraction": bundle.waterfall.coverage.observed_fraction,
                "candidate_count": len(bundle.cloud.candidates),
                "best_qam_accuracy": bundle.summary.best_qam_accuracy,
                "best_cfo_hz": (
                    bundle.cloud.candidates[0].observation.absolute_cfo_hz
                    if bundle.cloud.candidates
                    else None
                ),
                "doppler_slope_hz_s": bundle.doppler.slope_hz_s,
                "compute_tier": bundle.compute_tier.value,
                "scientific_confidence": bundle.controls.confidence.value,
            },
            message=message,
        )
        if self.spec.key == "presentation-overlays":
            self._coordinator.release(context, edge=binding.starlink_edge)
        return result


def production_long_dwell_registry(
    tier: ComputeTier | str = ComputeTier.STANDARD,
    *,
    configurations: dict[str, dict[str, JsonValue]] | None = None,
) -> AnalyzerRegistry:
    """Return concrete analyzers whose specs exactly match the canonical DAG."""

    selected = ComputeTier(tier)
    coordinator = LongDwellCoordinator(selected, configurations=configurations)
    analyzers: list[Any] = []
    for spec in long_dwell_stage_specs(selected):
        analyzer: Any
        if spec.key == "raw-validate":
            analyzer = _RawValidationAnalyzer(coordinator, spec)
        elif spec.key == "quality":
            analyzer = _DelegatingAnalyzer(QualityAnalyzer(), spec)
        elif spec.key == "power":
            analyzer = _DelegatingAnalyzer(PowerAnalyzer(), spec)
        elif spec.key == "trajectory-feedback":
            analyzer = TrajectoryFeedbackAnalyzer(spec)
        elif spec.key == "glrt64-trajectory-presentation":
            analyzer = Glrt64TrajectoryPresentationAnalyzer(spec)
        else:
            analyzer = _ComputedStageAnalyzer(coordinator, spec)
        analyzers.append(analyzer)
    return validated_long_dwell_registry(cast(tuple[Any, ...], tuple(analyzers)), selected)


def production_standard_v2_registry() -> AnalyzerRegistry:
    """Return the typed production registry for expanded Standard-v2 runs."""

    return _production_standard_v2_registry()


def production_standard_v2_configuration() -> dict[str, dict[str, JsonValue]]:
    """Return the closed default configuration for the typed Standard-v2 graph."""

    return _production_standard_v2_configuration()


def production_long_dwell_configuration(
    tier: ComputeTier | str = ComputeTier.STANDARD,
) -> dict[str, dict[str, JsonValue]]:
    """Configuration document to pin into a pipeline release."""

    coordinator = LongDwellCoordinator(tier)
    return coordinator.pipeline_configuration


def _receiver_calibrations(iq: IqReader) -> dict[int, ReceiverFrequencyCalibration]:
    # ``IqReader.center_frequency_hz`` is the hardware tuning center recorded in
    # the capture manifest.  It is not a baseband CFO calibration and must never
    # be fed into IQ derotation.  No explicit per-receiver frequency calibration
    # is present in recording.v1, so the honest calibrated baseband reference is
    # zero.  This is an explicitly uncalibrated research prior for the Standard
    # exploratory graph only; it is not a ReceiverFrequencyCalibrationV1 and is
    # categorically ineligible for WP11/scientific acceptance.  WP11 resolves an
    # immutable calibration by exact hardware path and full dwell interval.
    calibration_center_hz = 0.0
    return {
        receiver_id: ReceiverFrequencyCalibration(
            receiver_id=str(receiver_id),
            center_hz=calibration_center_hz,
            calibration_sha256=canonical_digest(
                {
                    "receiver_id": receiver_id,
                    "baseband_calibration_center_hz": calibration_center_hz,
                    "source": "no-explicit-baseband-frequency-calibration",
                }
            ).removeprefix("sha256:"),
        )
        for receiver_id in iq.receiver_ids
    }


def _candidate_windows(
    iq: IqReader,
    candidates: tuple[Any, ...],
    calibrations: dict[int, ReceiverFrequencyCalibration],
    *,
    maximum_probe_samples: int,
    block_samples: int,
) -> tuple[DenseRefinementWindow, ...]:
    requests = []
    for candidate in candidates:
        observation = candidate.observation
        start = observation.window_sample_start
        count = min(maximum_probe_samples, max(0, iq.sample_count - start))
        if count:
            requests.append((candidate, start, count))
    buffers = [np.zeros(count, dtype=np.complex128) for _, _, count in requests]
    observed = [np.zeros(count, dtype=bool) for _, _, count in requests]
    receiver_index = {receiver_id: index for index, receiver_id in enumerate(iq.receiver_ids)}
    for block in iq.iter_blocks(block_samples=block_samples):
        block_start = block.metadata.session_sample_start
        block_stop = block_start + block.metadata.sample_count
        for index, (candidate, start, count) in enumerate(requests):
            stop = start + count
            overlap_start = max(start, block_start)
            overlap_stop = min(stop, block_stop)
            if overlap_start >= overlap_stop:
                continue
            source_start = overlap_start - block_start
            source_stop = overlap_stop - block_start
            target_start = overlap_start - start
            target_stop = overlap_stop - start
            channel = receiver_index[candidate.observation.receiver_id]
            values = block.samples[source_start:source_stop, channel]
            buffers[index][target_start:target_stop] = (
                values[:, 0].astype(np.float64) + 1j * values[:, 1].astype(np.float64)
            ) / 32_768.0
            observed[index][target_start:target_stop] = True
    return tuple(
        DenseRefinementWindow(
            candidate.candidate_id,
            candidate.observation.receiver_id,
            start,
            values,
            calibrations[candidate.observation.receiver_id],
            candidate.observation.residual_cfo_hz,
        )
        for (candidate, start, _), values, coverage in zip(
            requests,
            buffers,
            observed,
            strict=True,
        )
        if bool(np.all(coverage))
    )


def _locked_frames(
    windows: tuple[DenseRefinementWindow, ...],
    refined: DenseRefinementResult,
    *,
    maximum_frames: int,
) -> tuple[LockedFrame, ...]:
    refined_ids = {item.candidate_id for item in refined.refined}
    selected = tuple(item for item in windows if item.candidate_id in refined_ids)[:maximum_frames]
    if not selected:
        return ()
    common_samples = min(len(item.samples) for item in selected)
    return tuple(
        LockedFrame(
            item.candidate_id,
            item.sample_start,
            np.ascontiguousarray(item.samples[:common_samples]),
        )
        for item in selected
    )


def _stage_documents(
    run_id: str,
    stage_key: str,
    computed: ComputedLongDwell,
) -> dict[str, dict[str, JsonValue]]:
    bundle = computed.bundle
    presentation = whole_dwell_presentation_documents(run_id, bundle)
    if stage_key == "presentation-overlays":
        return presentation
    products_by_stage: dict[str, dict[str, JsonValue]] = {
        "waterfall": presentation[WholeDwellPresentationAnalyzer.WATERFALL.kind],
        "starlink-survey": {
            "schema_version": 1,
            "run_id": run_id,
            "status": bundle.survey.status.value,
            "reason": bundle.survey.reason,
            "coverage": cast(JsonValue, asdict(bundle.survey.coverage)),
            "candidate_count": len(bundle.survey.candidates),
            "config_digest": bundle.survey.config_digest,
        },
        "candidate-cloud": presentation[WholeDwellPresentationAnalyzer.DETECTION.kind],
        "activity-track": {
            "schema_version": 1,
            "run_id": run_id,
            "status": bundle.tracks.status.value,
            "tracks": cast(JsonValue, [asdict(item) for item in bundle.tracks.tracks]),
            "orphan_candidate_count": bundle.tracks.orphan_candidate_count,
            "config_digest": bundle.tracks.config_digest,
        },
        "dense-refine": {
            "schema_version": 1,
            "run_id": run_id,
            "status": computed.refined.status.value,
            "refined": cast(JsonValue, [asdict(item) for item in computed.refined.refined]),
            "attempted_window_count": computed.refined.attempted_window_count,
            "config_digest": computed.refined.config_digest,
        },
        "doppler": presentation[WholeDwellPresentationAnalyzer.DOPPLER.kind],
        "locked-integrate": {
            "schema_version": 1,
            "run_id": run_id,
            "status": computed.locked.status.value,
            "frame_count": computed.locked.frame_count,
            "coherent_power": computed.locked.coherent_power,
            "incoherent_power": computed.locked.incoherent_power,
            "coherent_gain_db": computed.locked.coherent_gain_db,
            "source_ids": list(computed.locked.source_ids),
            "config_digest": computed.locked.config_digest,
            "reason": computed.locked.reason,
        },
        "qam": presentation[WholeDwellPresentationAnalyzer.QAM.kind],
        "controls": presentation[WholeDwellPresentationAnalyzer.CONTROLS.kind],
        "tle-associate": cast(
            dict[str, JsonValue],
            {
                "schema_version": 1,
                "run_id": run_id,
                **asdict(bundle.tle),
            },
        ),
        "scientific-summary": _summary_document(run_id, bundle.summary),
    }
    product = products_by_stage[stage_key]
    stage_spec = long_dwell_stage_specs(bundle.compute_tier)[_stage_index(stage_key)]
    return {stage_spec.output_products[0].kind: product}


def _summary_document(run_id: str, summary: ScientificSummary) -> dict[str, JsonValue]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "confidence": summary.confidence.value,
        "candidate_count": summary.candidate_count,
        "track_count": summary.track_count,
        "best_qam_accuracy": summary.best_qam_accuracy,
        "best_qam_evm": summary.best_qam_evm,
        "doppler_slope_hz_s": summary.doppler_slope_hz_s,
        "doppler_residual_rms_hz": summary.doppler_residual_rms_hz,
        "tle_candidate": summary.tle_candidate,
        "waterfall_time_bins": summary.waterfall_time_bins,
        "waterfall_frequency_bins": summary.waterfall_frequency_bins,
        "coverage_fraction": summary.coverage_fraction,
        "lineage_config_digests": list(summary.lineage_config_digests),
        "notes": list(summary.notes),
    }


def _stage_index(stage_key: str) -> int:
    return next(
        index
        for index, spec in enumerate(long_dwell_stage_specs(ComputeTier.STANDARD))
        if spec.key == stage_key
    )


def _computed_outcome(
    stage_key: str,
    computed: ComputedLongDwell,
) -> tuple[StageOutcome, str | None]:
    bundle = computed.bundle
    values: dict[str, tuple[NumericalStatus, str]] = {
        "starlink-survey": (bundle.survey.status, bundle.survey.reason),
        "candidate-cloud": (bundle.cloud.status, "candidate cloud is empty"),
        "activity-track": (bundle.tracks.status, "no continuous activity track"),
        "dense-refine": (computed.refined.status, "no dense candidate refinement"),
        "doppler": (bundle.doppler.status, bundle.doppler.reason),
        "locked-integrate": (computed.locked.status, computed.locked.reason),
        "qam": (bundle.qam.status, bundle.qam.reason),
        "controls": (bundle.controls.status, bundle.controls.reason),
    }
    if stage_key == "waterfall":
        return (
            _coverage_outcome(
                bundle.waterfall.coverage.observed_samples,
                bundle.waterfall.coverage.observed_fraction,
            ),
            None,
        )
    if stage_key in {"tle-associate", "scientific-summary", "presentation-overlays"}:
        status, reason = bundle.controls.status, bundle.controls.reason
    else:
        status, reason = values[stage_key]
    if status is NumericalStatus.INSUFFICIENT:
        return StageOutcome.INSUFFICIENT_DATA, reason
    if status is NumericalStatus.NO_RESULT:
        return StageOutcome.NO_RESULT, reason
    if bundle.waterfall.coverage.observed_fraction < 1.0:
        return StageOutcome.PARTIAL_COVERAGE, "whole-dwell input coverage is partial"
    return StageOutcome.COMPLETE, None


def _coverage_outcome(observed: int, fraction: float) -> StageOutcome:
    if observed == 0:
        return StageOutcome.INSUFFICIENT_DATA
    if fraction < 1.0:
        return StageOutcome.PARTIAL_COVERAGE
    return StageOutcome.COMPLETE


def _int(values: dict[str, JsonValue], key: str, default: int) -> int:
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _float(values: dict[str, JsonValue], key: str, default: float) -> float:
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def _bool(values: dict[str, JsonValue], key: str, default: bool) -> bool:
    value = values.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be boolean")
    return value


def _surrogate_rolls(values: dict[str, JsonValue]) -> tuple[int, ...]:
    explicit = values.get("surrogate_symbol_rolls")
    if explicit is not None:
        if not isinstance(explicit, list) or any(
            isinstance(value, bool) or not isinstance(value, int) for value in explicit
        ):
            raise ValueError("surrogate_symbol_rolls must be an integer list")
        return tuple(cast(int, value) for value in explicit)
    count = _int(values, "surrogate_count", 3)
    defaults = (17, 53, 101, 149, 197, 251, 307, 359, 419)
    if not 1 <= count <= len(defaults):
        raise ValueError("surrogate_count exceeds the committed roll inventory")
    return defaults[:count]
