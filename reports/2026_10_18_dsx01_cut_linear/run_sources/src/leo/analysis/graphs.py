"""One semantic long-dwell DAG with explicit Quick/Standard/Research budgets."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import JsonValue

from leo.pipeline import (
    Analyzer,
    AnalyzerRegistry,
    PipelineGraph,
    ProductRequirement,
    ProductRole,
    ProductSpec,
    ResourceClass,
    StageSpec,
)


class ComputeTier(StrEnum):
    """A resource policy, never a statement of scientific confidence."""

    QUICK = "quick"
    STANDARD = "standard"
    RESEARCH = "research"


@dataclass(frozen=True, slots=True)
class StageBudget:
    stage_key: str
    enabled: bool
    maximum_memory_bytes: int
    maximum_output_points: int
    configuration: tuple[tuple[str, JsonValue], ...]

    def config_dict(self) -> dict[str, JsonValue]:
        return dict(self.configuration)


@dataclass(frozen=True, slots=True)
class LongDwellBudget:
    tier: ComputeTier
    maximum_parallel_heavy_stages: int
    stages: tuple[StageBudget, ...]

    def stage(self, key: str) -> StageBudget:
        try:
            return next(item for item in self.stages if item.stage_key == key)
        except StopIteration as exc:
            raise KeyError(key) from exc

    @property
    def enabled_stage_keys(self) -> tuple[str, ...]:
        return tuple(item.stage_key for item in self.stages if item.enabled)


def _product(kind: str, *, presentation: bool = False) -> ProductSpec:
    return ProductSpec(
        kind=kind,
        role=ProductRole.PRESENTATION if presentation else ProductRole.SCIENTIFIC,
    )


RAW = _product("raw.validation")
QUALITY = _product("quality.summary")
POWER = _product("power.summary")
WATERFALL = _product("waterfall.tiles")
SURVEY = _product("starlink.survey")
CLOUD = _product("starlink.candidates")
TRACKS = _product("starlink.tracks")
REFINED = _product("starlink.refined")
DOPPLER = _product("doppler.fit")
LOCKED = _product("starlink.locked")
QAM = _product("starlink.qam")
PILOT_METHOD_DETECTIONS = _product("starlink.pilot-method-detections")
POLYNOMIAL_TRAJECTORIES = _product("starlink.polynomial-trajectories")
TRAJECTORY_REDETECTION = _product("starlink.trajectory-redetection")
GLRT64_TRAJECTORY_TABLE = _product("starlink.glrt64-trajectory-table")
GLRT64_TRAJECTORY_PNG = ProductSpec(
    kind="starlink.glrt64-trajectory-plot",
    role=ProductRole.PRESENTATION,
    media_type="image/png",
)
CONTROLS = _product("starlink.controls")
TLE = _product("starlink.tle-association")
SUMMARY = _product("starlink.summary")
WATERFALL_PRESENTATION = _product("waterfall.presentation", presentation=True)
DETECTION_PRESENTATION = _product("detection.presentation", presentation=True)
QAM_PRESENTATION = _product("qam.presentation", presentation=True)
DOPPLER_PRESENTATION = _product("doppler.presentation", presentation=True)
CONTROLS_PRESENTATION = _product("controls.presentation", presentation=True)
OVERLAYS_PRESENTATION = _product("overlays.presentation", presentation=True)
PROVENANCE_PRESENTATION = _product("provenance.presentation", presentation=True)
CARRIER_TIMING_PRESENTATION = _product("carrier-timing.presentation", presentation=True)
QAM_TIMELINE_PRESENTATION = _product("qam-timeline.presentation", presentation=True)
ANALYSIS_STAGE_TIMELINE_PRESENTATION = _product(
    "analysis-stage-timeline.presentation", presentation=True
)


LONG_DWELL_STAGE_SPECS = (
    StageSpec(
        key="raw-validate",
        algorithm_version="1.0.0",
        configuration_schema="raw-validation.v1",
        output_products=(RAW,),
        resource_class=ResourceClass.STREAMING,
    ),
    StageSpec(
        key="quality",
        algorithm_version="1.0.0",
        configuration_schema="quality.v1",
        dependencies=("raw-validate",),
        input_products=(ProductRequirement(kind=RAW.kind),),
        output_products=(QUALITY,),
        resource_class=ResourceClass.STREAMING,
    ),
    StageSpec(
        key="power",
        algorithm_version="1.0.0",
        configuration_schema="power.v1",
        dependencies=("quality",),
        input_products=(ProductRequirement(kind=QUALITY.kind),),
        output_products=(POWER,),
        resource_class=ResourceClass.STREAMING,
    ),
    StageSpec(
        key="waterfall",
        algorithm_version="1.0.0",
        configuration_schema="waterfall.v1",
        dependencies=("power",),
        input_products=(ProductRequirement(kind=POWER.kind),),
        output_products=(WATERFALL,),
        resource_class=ResourceClass.HEAVY,
    ),
    StageSpec(
        key="starlink-survey",
        algorithm_version="1.0.0",
        configuration_schema="starlink-survey.v1",
        dependencies=("waterfall",),
        input_products=(ProductRequirement(kind=WATERFALL.kind),),
        output_products=(SURVEY,),
        resource_class=ResourceClass.CPU,
    ),
    StageSpec(
        key="candidate-cloud",
        algorithm_version="1.0.0",
        configuration_schema="candidate-cloud.v1",
        dependencies=("starlink-survey",),
        input_products=(ProductRequirement(kind=SURVEY.kind),),
        output_products=(CLOUD,),
        resource_class=ResourceClass.MEMORY,
    ),
    StageSpec(
        key="activity-track",
        algorithm_version="1.0.0",
        configuration_schema="activity-track.v1",
        dependencies=("candidate-cloud",),
        input_products=(ProductRequirement(kind=CLOUD.kind),),
        output_products=(TRACKS,),
        resource_class=ResourceClass.CPU,
    ),
    StageSpec(
        key="dense-refine",
        algorithm_version="1.0.0",
        configuration_schema="dense-refine.v1",
        dependencies=("activity-track",),
        input_products=(ProductRequirement(kind=TRACKS.kind),),
        output_products=(REFINED,),
        resource_class=ResourceClass.HEAVY,
    ),
    StageSpec(
        key="doppler",
        algorithm_version="1.0.0",
        configuration_schema="doppler.v1",
        dependencies=("dense-refine",),
        input_products=(ProductRequirement(kind=REFINED.kind),),
        output_products=(DOPPLER,),
        resource_class=ResourceClass.CPU,
    ),
    StageSpec(
        key="locked-integrate",
        algorithm_version="1.0.0",
        configuration_schema="locked-integration.v1",
        dependencies=("dense-refine", "doppler"),
        input_products=(
            ProductRequirement(kind=REFINED.kind),
            ProductRequirement(kind=DOPPLER.kind),
        ),
        output_products=(LOCKED,),
        resource_class=ResourceClass.HEAVY,
    ),
    StageSpec(
        key="qam",
        algorithm_version="1.0.0",
        configuration_schema="known-pilot-qam.v1",
        dependencies=("dense-refine", "locked-integrate"),
        input_products=(
            ProductRequirement(kind=REFINED.kind),
            ProductRequirement(kind=LOCKED.kind),
        ),
        output_products=(QAM,),
        resource_class=ResourceClass.CPU,
    ),
    StageSpec(
        key="trajectory-feedback",
        algorithm_version="1.0.0",
        configuration_schema="trajectory-feedback.v1",
        dependencies=("qam",),
        input_products=(ProductRequirement(kind=QAM.kind),),
        output_products=(
            PILOT_METHOD_DETECTIONS,
            POLYNOMIAL_TRAJECTORIES,
            TRAJECTORY_REDETECTION,
            GLRT64_TRAJECTORY_TABLE,
        ),
        resource_class=ResourceClass.HEAVY,
    ),
    StageSpec(
        key="controls",
        algorithm_version="1.0.0",
        configuration_schema="candidate-controls.v1",
        dependencies=("dense-refine", "doppler", "qam", "trajectory-feedback"),
        input_products=(
            ProductRequirement(kind=QAM.kind),
            ProductRequirement(kind=REFINED.kind),
            ProductRequirement(kind=DOPPLER.kind),
            ProductRequirement(kind=TRAJECTORY_REDETECTION.kind),
            ProductRequirement(kind=GLRT64_TRAJECTORY_TABLE.kind),
        ),
        output_products=(CONTROLS,),
        resource_class=ResourceClass.CPU,
    ),
    StageSpec(
        key="tle-associate",
        algorithm_version="1.0.0",
        configuration_schema="tle-association.v1",
        dependencies=("doppler", "controls"),
        input_products=(
            ProductRequirement(kind=DOPPLER.kind),
            ProductRequirement(kind=CONTROLS.kind),
        ),
        output_products=(TLE,),
        resource_class=ResourceClass.CPU,
    ),
    StageSpec(
        key="scientific-summary",
        algorithm_version="1.0.0",
        configuration_schema="scientific-summary.v1",
        dependencies=(
            "waterfall",
            "candidate-cloud",
            "activity-track",
            "doppler",
            "qam",
            "trajectory-feedback",
            "controls",
            "tle-associate",
        ),
        input_products=(
            ProductRequirement(kind=WATERFALL.kind),
            ProductRequirement(kind=CLOUD.kind),
            ProductRequirement(kind=TRACKS.kind),
            ProductRequirement(kind=DOPPLER.kind),
            ProductRequirement(kind=QAM.kind),
            ProductRequirement(kind=PILOT_METHOD_DETECTIONS.kind),
            ProductRequirement(kind=POLYNOMIAL_TRAJECTORIES.kind),
            ProductRequirement(kind=TRAJECTORY_REDETECTION.kind),
            ProductRequirement(kind=GLRT64_TRAJECTORY_TABLE.kind),
            ProductRequirement(kind=CONTROLS.kind),
            ProductRequirement(kind=TLE.kind),
        ),
        output_products=(SUMMARY,),
        resource_class=ResourceClass.CPU,
    ),
    StageSpec(
        key="glrt64-trajectory-presentation",
        algorithm_version="1.0.0",
        configuration_schema="glrt64-trajectory-presentation.v1",
        dependencies=("scientific-summary", "trajectory-feedback"),
        input_products=(
            ProductRequirement(kind=PILOT_METHOD_DETECTIONS.kind),
            ProductRequirement(kind=POLYNOMIAL_TRAJECTORIES.kind),
            ProductRequirement(kind=TRAJECTORY_REDETECTION.kind),
            ProductRequirement(kind=GLRT64_TRAJECTORY_TABLE.kind),
        ),
        output_products=(GLRT64_TRAJECTORY_PNG,),
        resource_class=ResourceClass.CPU,
    ),
    StageSpec(
        key="presentation-overlays",
        algorithm_version="1.0.0",
        configuration_schema="presentation-overlays.v1",
        dependencies=("scientific-summary", "glrt64-trajectory-presentation"),
        input_products=(ProductRequirement(kind=SUMMARY.kind),),
        output_products=(
            WATERFALL_PRESENTATION,
            DETECTION_PRESENTATION,
            QAM_PRESENTATION,
            DOPPLER_PRESENTATION,
            CONTROLS_PRESENTATION,
            OVERLAYS_PRESENTATION,
            PROVENANCE_PRESENTATION,
            CARRIER_TIMING_PRESENTATION,
            QAM_TIMELINE_PRESENTATION,
            ANALYSIS_STAGE_TIMELINE_PRESENTATION,
        ),
        resource_class=ResourceClass.CPU,
    ),
)


_QUICK_LAST_STAGE = "candidate-cloud"


def long_dwell_stage_specs(tier: ComputeTier | str) -> tuple[StageSpec, ...]:
    """Return a dependency-closed prefix of the one canonical semantic graph."""

    selected = ComputeTier(tier)
    if selected is not ComputeTier.QUICK:
        return LONG_DWELL_STAGE_SPECS
    result = []
    for spec in LONG_DWELL_STAGE_SPECS:
        result.append(spec)
        if spec.key == _QUICK_LAST_STAGE:
            break
    return tuple(result)


def long_dwell_graph(tier: ComputeTier | str) -> PipelineGraph:
    """Build and validate the dependency-closed graph for one compute budget."""

    return PipelineGraph(long_dwell_stage_specs(tier))


def long_dwell_budget(tier: ComputeTier | str) -> LongDwellBudget:
    selected = ComputeTier(tier)
    if selected is ComputeTier.QUICK:
        values = _budget_values(128, 128, 24, 64, 0, 0, 256 * 1024**2)
        parallel = 1
    elif selected is ComputeTier.STANDARD:
        values = _budget_values(512, 256, 120, 256, 64, 3, 1024 * 1024**2)
        parallel = 1
    else:
        values = _budget_values(1024, 512, 600, 1024, 256, 9, 4 * 1024**3)
        parallel = 2
    enabled = {item.key for item in long_dwell_stage_specs(selected)}
    stages = tuple(
        StageBudget(key, key in enabled, memory, points, tuple(config.items()))
        for key, memory, points, config in values
    )
    return LongDwellBudget(selected, parallel, stages)


def validated_long_dwell_registry(
    analyzers: tuple[Analyzer, ...], tier: ComputeTier | str
) -> AnalyzerRegistry:
    """Bind concrete pure analyzers only when their contracts match the DAG exactly."""

    expected = {item.key: item for item in long_dwell_stage_specs(tier)}
    registry = AnalyzerRegistry(analyzers)
    if set(registry.keys) != set(expected):
        missing = sorted(set(expected) - set(registry.keys))
        extra = sorted(set(registry.keys) - set(expected))
        raise ValueError(f"long-dwell registry mismatch; missing={missing}, extra={extra}")
    for key, spec in expected.items():
        if registry.get(key).spec != spec:
            raise ValueError(f"analyzer StageSpec differs from canonical graph: {key}")
    registry.graph()
    return registry


def _budget_values(
    waterfall_time_bins: int,
    waterfall_frequency_bins: int,
    survey_windows: int,
    cloud_candidates: int,
    dense_windows: int,
    surrogate_count: int,
    maximum_memory: int,
) -> tuple[tuple[str, int, int, dict[str, JsonValue]], ...]:
    common = ("block_samples", 262_144)
    return (
        ("raw-validate", 8 * 1024**2, 1, dict([common])),
        ("quality", 16 * 1024**2, 4, dict([common])),
        ("power", 16 * 1024**2, 4, dict([common])),
        (
            "waterfall",
            min(maximum_memory, 256 * 1024**2),
            waterfall_time_bins * waterfall_frequency_bins,
            {
                "maximum_time_bins": waterfall_time_bins,
                "frequency_bins": waterfall_frequency_bins,
                "fft_samples": 1024,
                "block_samples": 262_144,
            },
        ),
        (
            "starlink-survey",
            min(maximum_memory, survey_windows * 14_000 * 8 + 64 * 1024**2),
            survey_windows * 8,
            {
                "maximum_windows": survey_windows,
                "probe_samples": 14_000,
                "maximum_buffered_samples": survey_windows * 14_000,
            },
        ),
        (
            "candidate-cloud",
            min(maximum_memory, 64 * 1024**2),
            cloud_candidates,
            {"maximum_candidates": cloud_candidates},
        ),
        (
            "activity-track",
            min(maximum_memory, 64 * 1024**2),
            cloud_candidates,
            {"maximum_window_gap": 2, "minimum_observations": 2},
        ),
        (
            "dense-refine",
            min(maximum_memory, max(dense_windows, 1) * 50_000 * 16),
            dense_windows * 8,
            {"maximum_windows": dense_windows or 1, "maximum_probe_samples": 50_000},
        ),
        (
            "doppler",
            min(maximum_memory, 64 * 1024**2),
            max(dense_windows, 1),
            {"maximum_points": max(dense_windows, 3), "polynomial_order": 2},
        ),
        (
            "locked-integrate",
            min(maximum_memory, max(dense_windows, 1) * 50_000 * 16),
            max(dense_windows, 1),
            {"maximum_frames": max(dense_windows, 2), "maximum_frame_samples": 50_000},
        ),
        ("qam", min(maximum_memory, 512 * 1024**2), 4800, {}),
        (
            "trajectory-feedback",
            min(maximum_memory, 768 * 1024**2),
            320_000,
            {
                "coarse_window_ms": 1_000,
                "subwindow_ms": 50,
                "probe_ms": 20,
                "probe_offsets_ms": [0, 25],
                "polynomial_degrees": [1, 2, 3],
                "maximum_replayed_families": 16,
                "maximum_workers": 4,
            },
        ),
        (
            "controls",
            min(maximum_memory, 256 * 1024**2),
            max(1, surrogate_count * max(dense_windows, 1)),
            {
                "surrogate_count": surrogate_count,
                "thresholds_calibrated": False,
            },
        ),
        ("tle-associate", 32 * 1024**2, 32, {"optional": True}),
        ("scientific-summary", 32 * 1024**2, 4096, {}),
        ("glrt64-trajectory-presentation", 256 * 1024**2, 1, {}),
        ("presentation-overlays", 32 * 1024**2, 4096, {}),
    )
