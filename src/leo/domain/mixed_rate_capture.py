"""Compile reviewed per-rate profiles into one immutable mixed-rate plan."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from leo.acquisition.starlink_tuning import (
    starlink_channel_if_bounds_hz,
    starlink_edge_if_center_frequency_hz,
    starlink_maximum_coverage_if_center_frequency_hz,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.mixed_rate_capture import CapturePlanV3, MixedRateRadioPlanV1
from leo.contracts.mixed_rate_schedule import ProductionDwellClass
from leo.contracts.profile import CaptureProfileRevisionV2
from leo.contracts.radio import RadioSettingsV1
from leo.contracts.states import SourceType, StarlinkEdge


def compile_mixed_rate_capture_plan_v3(
    *,
    dwell_class: ProductionDwellClass,
    radio_ids: Sequence[str],
    profile_revisions_by_radio: Mapping[str, CaptureProfileRevisionV2],
    starlink_channel: int,
    starlink_edge: StarlinkEdge,
    source_type: SourceType = SourceType.LIVE,
) -> CapturePlanV3:
    """Bind two existing immutable rate profiles to one common RF target."""

    radios = tuple(radio_ids)
    if len(radios) != 2 or len(set(radios)) != 2:
        raise ValueError("mixed-rate capture requires two unique ordered radios")
    if set(profile_revisions_by_radio) != set(radios):
        raise ValueError("mixed-rate profiles must exactly cover selected radios")
    pilot_center_hz = starlink_edge_if_center_frequency_hz(starlink_channel, starlink_edge)
    channel_start_hz, channel_stop_hz = starlink_channel_if_bounds_hz(starlink_channel)
    legs: list[MixedRateRadioPlanV1] = []
    duration_seconds: Decimal | None = None
    for radio_id in radios:
        revision = profile_revisions_by_radio[radio_id]
        profile = revision.profile
        if profile.duration_seconds is None:
            raise ValueError("mixed-rate capture profiles require duration_seconds")
        if duration_seconds is None:
            duration_seconds = profile.duration_seconds
        elif profile.duration_seconds != duration_seconds:
            raise ValueError("mixed-rate capture profiles require one common duration")
        sample_count = int(
            (profile.duration_seconds * profile.sample_rate_hz).to_integral_value(
                rounding=ROUND_HALF_UP
            )
        )
        center_hz = starlink_maximum_coverage_if_center_frequency_hz(
            starlink_channel,
            starlink_edge,
            bandwidth_hz=profile.bandwidth_hz,
        )
        captured_start_hz = center_hz - profile.bandwidth_hz // 2
        captured_stop_hz = center_hz + profile.bandwidth_hz // 2
        legs.append(
            MixedRateRadioPlanV1(
                radio_id=radio_id,
                profile_revision=revision,
                resolved_sample_count=sample_count,
                requested_settings=RadioSettingsV1(
                    center_frequency_hz=center_hz,
                    sample_rate_hz=profile.sample_rate_hz,
                    bandwidth_hz=profile.bandwidth_hz,
                    receiver_ids=profile.receivers,
                    gain_mode=profile.gain_mode,
                    gains=profile.gains,
                ),
                pilot_if_center_frequency_hz=pilot_center_hz,
                channel_if_start_hz=channel_start_hz,
                channel_if_stop_hz=channel_stop_hz,
                captured_if_start_hz=captured_start_hz,
                captured_if_stop_hz=captured_stop_hz,
            )
        )
    values: dict[str, Any] = {
        "schema_version": 3,
        "dwell_class": dwell_class,
        "radio_ids": radios,
        "radio_plans": tuple(legs),
        "source_type": source_type,
        "duration_seconds": duration_seconds,
        "starlink_channel": starlink_channel,
        "starlink_edge": starlink_edge,
        "requested_synchronization_mode": "best_effort",
        "effective_synchronization_mode": "best_effort",
    }
    candidate = CapturePlanV3.model_construct(
        plan_digest="sha256:" + "0" * 64,
        **values,
    )
    document = candidate.model_dump(mode="json", exclude={"plan_digest"})
    return CapturePlanV3.model_validate({**document, "plan_digest": canonical_digest(document)})
