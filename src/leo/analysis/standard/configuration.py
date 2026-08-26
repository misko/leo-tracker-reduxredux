"""Shared pure construction of the production receiver Standard configuration."""

from __future__ import annotations

from dataclasses import fields, replace
from typing import Any, cast

from pydantic import JsonValue

from leo.analysis.standard.alternate_tracks import default_alternate_cfo_config
from leo.analysis.standard.full_capture_glrt20ms import FullCaptureGlrt20msConfig
from leo.analysis.standard.runner import ReceiverStandardConfig
from leo.analysis.starlink.cfo_dealias import (
    default_linear_cfo_dealias_config,
    default_replay_gate_v4,
)
from leo.analysis.starlink.multi_target import default_multi_target_association_config
from leo.analysis.starlink.trajectory_feedback import (
    TrajectoryFeedbackConfig,
    validate_trajectory_feedback_config,
)
from leo.analysis.waterfall import WaterfallConfig
from leo.contracts.alternate_cfo_tracks import ResidualHoughSegmentationConfigV2
from leo.contracts.cfo_dealias import (
    CfoDealiasConfigV2,
    HuberLinearRefinementConfigV1,
    ReplayGateConfigV4,
    SeededAliasEmConfigV1,
)
from leo.contracts.kalman_tracking import KalmanTrackingConfigV1
from leo.contracts.multi_target import MultiTargetAssociationConfigV1
from leo.contracts.pilot_doppler_segments import PilotDopplerSegmentConfigV2
from leo.contracts.trajectory_accounting import TrajectoryAccountingConfigV2

PRODUCTION_RECEIVER_STANDARD_SAMPLE_RATE_HZ = 2_500_000
RECEIVER_STANDARD_RATE_DERIVED_FIELDS = ("replay_gate.sample_rate_hz",)


def production_receiver_standard_stage_configuration() -> dict[str, JsonValue]:
    """Return a fresh copy of the reviewed production ``path-standard`` policy."""

    return {
        "waterfall": {
            "fft_samples": 1024,
            "frequency_bins": 256,
            "maximum_time_bins": 512,
        },
        "feedback": {
            "maximum_workers": 4,
            "maximum_scored_candidates_per_probe": 10,
            "probe_offsets_ms": [0, 25],
            "cfo_acquisition_mode": "independent_wide_per_probe",
            "cfo_search_min_hz": -400_000.0,
            "cfo_search_max_hz": 400_000.0,
            "coarse_cfo_step_hz": 80_000.0,
            "fine_cfo_radius_hz": 80_000.0,
            "fine_cfo_step_hz": 500.0,
            "conditioned_cfo_radius_hz": 2_000.0,
            "conditioned_cfo_step_hz": 100.0,
            "retained_candidate_count": 10,
            "candidate_epoch_separation_samples": 5,
            "candidate_cfo_separation_hz": 10_000.0,
            "glrt_size": 512,
        },
        "segmentation": default_alternate_cfo_config().model_dump(mode="json"),
        "dealias": default_linear_cfo_dealias_config().model_dump(mode="json"),
        "huber_linear": HuberLinearRefinementConfigV1().model_dump(mode="json"),
        "replay_gate": default_replay_gate_v4().model_dump(mode="json"),
        "trajectory_accounting": TrajectoryAccountingConfigV2().model_dump(mode="json"),
        "kalman": KalmanTrackingConfigV1().model_dump(mode="json"),
        "pilot_doppler_segments": PilotDopplerSegmentConfigV2().model_dump(mode="json"),
        "full_capture_glrt20ms": {
            "enabled": True,
            "window_ms": 20,
            "stride_ms": 10,
            "margin_gate": 0.025,
            "maximum_workers": 4,
            "line_rms_reference_hz": 75.0,
        },
    }


def parse_receiver_standard_config(values: dict[str, JsonValue]) -> ReceiverStandardConfig:
    """Parse one closed stage policy without applying implicit runtime overrides."""

    allowed = {item.name for item in fields(ReceiverStandardConfig)}
    if set(values) - allowed:
        raise ValueError("unknown fused receiver Standard configuration fields")
    nested_fields = {
        "waterfall",
        "feedback",
        "segmentation",
        "dealias",
        "seeded_alias_em",
        "huber_linear",
        "replay_gate",
        "association",
        "trajectory_accounting",
        "kalman",
        "pilot_doppler_segments",
        "full_capture_glrt20ms",
    }
    scalar_values = {key: value for key, value in values.items() if key not in nested_fields}
    waterfall_values = values.get("waterfall", {})
    feedback_values = values.get("feedback", {})
    segmentation_values = values.get(
        "segmentation", default_alternate_cfo_config().model_dump(mode="json")
    )
    dealias_values = values.get("dealias")
    seeded_alias_em_values = values.get("seeded_alias_em", {})
    huber_linear_values = values.get("huber_linear", {})
    replay_gate_values = values.get("replay_gate")
    association_values = values.get("association", {})
    trajectory_accounting_values = values.get("trajectory_accounting", {})
    kalman_values = values.get("kalman", {})
    pilot_doppler_segment_values = values.get("pilot_doppler_segments", {})
    full_capture_glrt20ms_values = values.get("full_capture_glrt20ms", {})
    nested_values = (
        waterfall_values,
        feedback_values,
        segmentation_values,
        dealias_values,
        seeded_alias_em_values,
        huber_linear_values,
        replay_gate_values,
        association_values,
        trajectory_accounting_values,
        kalman_values,
        pilot_doppler_segment_values,
        full_capture_glrt20ms_values,
    )
    if any(not isinstance(item, dict) for item in nested_values):
        raise ValueError("fused receiver nested configuration must be objects")
    return ReceiverStandardConfig(
        **cast(dict[str, Any], scalar_values),
        waterfall=_dataclass_config(
            WaterfallConfig,
            cast(dict[str, JsonValue], waterfall_values),
        ),
        feedback=_feedback_config(cast(dict[str, JsonValue], feedback_values)),
        segmentation=ResidualHoughSegmentationConfigV2.model_validate(segmentation_values),
        dealias=CfoDealiasConfigV2.model_validate(dealias_values),
        seeded_alias_em=SeededAliasEmConfigV1.model_validate(seeded_alias_em_values),
        huber_linear=HuberLinearRefinementConfigV1.model_validate(huber_linear_values),
        replay_gate=ReplayGateConfigV4.model_validate(replay_gate_values),
        association=(
            MultiTargetAssociationConfigV1.model_validate(association_values)
            if association_values
            else default_multi_target_association_config()
        ),
        trajectory_accounting=TrajectoryAccountingConfigV2.model_validate(
            trajectory_accounting_values
        ),
        kalman=KalmanTrackingConfigV1.model_validate(kalman_values),
        pilot_doppler_segments=PilotDopplerSegmentConfigV2.model_validate(
            pilot_doppler_segment_values
        ),
        full_capture_glrt20ms=_dataclass_config(
            FullCaptureGlrt20msConfig,
            cast(dict[str, JsonValue], full_capture_glrt20ms_values),
        ),
    )


def resolve_receiver_standard_sample_rate(
    config: ReceiverStandardConfig,
    *,
    sample_rate_hz: int,
) -> ReceiverStandardConfig:
    """Return a configuration whose explicit rate-derived fields match the source."""

    _validate_sample_rate(sample_rate_hz)
    if config.replay_gate.sample_rate_hz == sample_rate_hz:
        return config
    return replace(
        config,
        replay_gate=config.replay_gate.model_copy(update={"sample_rate_hz": sample_rate_hz}),
    )


def require_receiver_standard_sample_rate(
    config: ReceiverStandardConfig,
    *,
    sample_rate_hz: int,
) -> ReceiverStandardConfig:
    """Fail closed unless every explicit rate-derived field is already resolved."""

    _validate_sample_rate(sample_rate_hz)
    if config.replay_gate.sample_rate_hz != sample_rate_hz:
        raise ValueError(
            "receiver Standard configuration is not resolved for the input sample rate"
        )
    return config


def production_receiver_standard_config(
    *,
    sample_rate_hz: int = PRODUCTION_RECEIVER_STANDARD_SAMPLE_RATE_HZ,
) -> ReceiverStandardConfig:
    """Build the production policy and resolve it before callers compute its digest."""

    return resolve_receiver_standard_sample_rate(
        parse_receiver_standard_config(production_receiver_standard_stage_configuration()),
        sample_rate_hz=sample_rate_hz,
    )


def _feedback_config(values: dict[str, JsonValue]) -> TrajectoryFeedbackConfig:
    allowed = {item.name for item in fields(TrajectoryFeedbackConfig)}
    if set(values) - allowed:
        raise ValueError("unknown trajectory feedback configuration fields")
    raw_offsets = values.get("probe_offsets_ms", [0, 25])
    if not isinstance(raw_offsets, (list, tuple)) or any(
        isinstance(value, bool) or not isinstance(value, int) for value in raw_offsets
    ):
        raise ValueError("probe_offsets_ms must be an array of integers")
    config_values: dict[str, Any] = dict(values)
    config_values["probe_offsets_ms"] = tuple(raw_offsets)
    config = TrajectoryFeedbackConfig(**cast(dict[str, Any], config_values))
    validate_trajectory_feedback_config(config)
    return config


def _dataclass_config(cls, values: dict[str, JsonValue]):
    allowed = {item.name for item in fields(cls)}
    if set(values) - allowed:
        raise ValueError(f"unknown {cls.__name__} configuration fields")
    return cls(**values)


def _validate_sample_rate(sample_rate_hz: int) -> None:
    if isinstance(sample_rate_hz, bool) or not isinstance(sample_rate_hz, int):
        raise TypeError("sample_rate_hz must be an integer")
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive")
