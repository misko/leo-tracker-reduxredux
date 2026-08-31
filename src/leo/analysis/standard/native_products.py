"""Closed additive product identities for Standard-native-v1."""

from __future__ import annotations

from leo.contracts.standard_pipeline import (
    STANDARD_NUMERICAL_WATERFALL_KIND,
    STANDARD_PATH_INPUT_BIND_KIND,
    STANDARD_POWER_TIMELINE_KIND,
    STANDARD_PROBE_SCHEDULE_KIND,
)
from leo.pipeline import ProductRole, ProductSpec

PATH_INPUT_BIND_V4_PRODUCT = ProductSpec(kind=STANDARD_PATH_INPUT_BIND_KIND, schema_version=4)
PATH_INPUT_BIND_V5_PRODUCT = ProductSpec(kind=STANDARD_PATH_INPUT_BIND_KIND, schema_version=5)
QUALITY_V2_PRODUCT = ProductSpec(kind="quality.summary", schema_version=2)
QUALITY_V3_PRODUCT = ProductSpec(kind="quality.summary", schema_version=3)
POWER_TIMELINE_V3_PRODUCT = ProductSpec(kind=STANDARD_POWER_TIMELINE_KIND, schema_version=3)
POWER_TIMELINE_V4_PRODUCT = ProductSpec(kind=STANDARD_POWER_TIMELINE_KIND, schema_version=4)
NUMERICAL_WATERFALL_V3_PRODUCT = ProductSpec(
    kind=STANDARD_NUMERICAL_WATERFALL_KIND,
    schema_version=3,
)
NUMERICAL_WATERFALL_V4_PRODUCT = ProductSpec(
    kind=STANDARD_NUMERICAL_WATERFALL_KIND,
    schema_version=4,
)
PROBE_SCHEDULE_V3_PRODUCT = ProductSpec(kind=STANDARD_PROBE_SCHEDULE_KIND, schema_version=3)
PROBE_SCHEDULE_V4_PRODUCT = ProductSpec(kind=STANDARD_PROBE_SCHEDULE_KIND, schema_version=4)
STATEFUL_PATH_V1_PRODUCT = ProductSpec(kind="standard.native-stateful-path", schema_version=1)
STATEFUL_PATH_V2_PRODUCT = ProductSpec(kind="standard.native-stateful-path", schema_version=2)
STATEFUL_PATH_V3_PRODUCT = ProductSpec(kind="standard.native-stateful-path", schema_version=3)
PILOT_SCAN_V4_PRODUCT = ProductSpec(kind="standard.pilot-scan", schema_version=4)
TRAJECTORY_BANK_V4_PRODUCT = ProductSpec(kind="standard.trajectory-bank", schema_version=4)
TRAJECTORY_FEEDBACK_V4_PRODUCT = ProductSpec(kind="standard.trajectory-feedback", schema_version=4)
TRAJECTORY_CONDITIONED_ACCOUNTING_V3_PRODUCT = ProductSpec(
    kind="standard.trajectory-conditioned-accounting",
    schema_version=3,
)
GLRT64_TRAJECTORY_TABLE_V4_PRODUCT = ProductSpec(
    kind="standard.glrt64-trajectory-table", schema_version=4
)
CFO_ALIAS_MAP_V3_PRODUCT = ProductSpec(kind="standard.cfo-alias-map", schema_version=3)
DEALIASED_TRAJECTORY_BANK_V5_PRODUCT = ProductSpec(
    kind="standard.dealiased-trajectory-bank", schema_version=5
)
CFO_LIFT_REPLAY_V5_PRODUCT = ProductSpec(kind="standard.cfo-lift-replay", schema_version=5)
FINAL_TRAJECTORY_BANK_V4_PRODUCT = ProductSpec(
    kind="standard.final-trajectory-bank", schema_version=4
)
GLRT64_FINAL_TRAJECTORY_TABLE_V4_PRODUCT = ProductSpec(
    kind="standard.glrt64-final-trajectory-table", schema_version=4
)
KALMAN_TRACKING_V2_PRODUCT = ProductSpec(kind="standard.kalman-tracking", schema_version=2)
PILOT_DOPPLER_SEGMENTS_V3_PRODUCT = ProductSpec(
    kind="standard.pilot-doppler-segments", schema_version=3
)
PILOT_DOPPLER_SEGMENTS_V4_PRODUCT = ProductSpec(
    kind="standard.pilot-doppler-segments", schema_version=4
)
FULL_CAPTURE_GLRT20MS_V1_PRODUCT = ProductSpec(
    kind="standard.full-capture-glrt20ms", schema_version=1
)
FULL_CAPTURE_GLRT20MS_V2_PRODUCT = ProductSpec(
    kind="standard.full-capture-glrt20ms", schema_version=2
)
PATH_REPORT_V3_PRODUCT = ProductSpec(kind="standard.path-report", schema_version=3)
PATH_REPORT_V4_PRODUCT = ProductSpec(kind="standard.path-report", schema_version=4)
PATH_PRESENTATION_V5_PRODUCT = ProductSpec(
    kind="standard.path-presentation",
    schema_version=5,
    role=ProductRole.PRESENTATION,
)


def _png(kind: str, version: int) -> ProductSpec:
    return ProductSpec(
        kind=kind,
        schema_version=version,
        role=ProductRole.PRESENTATION,
        media_type="image/png",
    )


WATERFALL_PNG_V2_PRODUCT = _png("standard.waterfall-png", 2)
DOPPLER_WATERFALL_PNG_V1_PRODUCT = _png("standard.doppler-waterfall-png", 1)
PILOT_METHODS_PNG_V2_PRODUCT = _png("standard.pilot-methods-png", 2)
CFO_TRAJECTORIES_PNG_V2_PRODUCT = _png("standard.cfo-trajectories-png", 2)
DEALIASED_CFO_TRAJECTORIES_PNG_V2_PRODUCT = _png("standard.cfo-trajectories-dealiased-png", 2)
FINAL_CFO_TRAJECTORIES_PNG_V2_PRODUCT = _png("standard.cfo-trajectories-final-png", 2)
TRAJECTORY_CONDITIONED_ACCOUNTING_PNG_V3_PRODUCT = _png(
    "standard.trajectory-conditioned-accounting-png", 3
)
PILOT_DOPPLER_SEGMENTS_PNG_V3_PRODUCT = _png("standard.pilot-doppler-segments-png", 3)
PILOT_CARRIER_TRACKING_PNG_V3_PRODUCT = _png("standard.pilot-carrier-tracking-png", 3)
PILOT_SEGMENT_RATES_PNG_V3_PRODUCT = _png("standard.pilot-segment-rates-png", 3)
PILOT_DOPPLER_SEGMENTS_PNG_V4_PRODUCT = _png("standard.pilot-doppler-segments-png", 4)
PILOT_CARRIER_TRACKING_PNG_V4_PRODUCT = _png("standard.pilot-carrier-tracking-png", 4)
PILOT_SEGMENT_RATES_PNG_V4_PRODUCT = _png("standard.pilot-segment-rates-png", 4)
FULL_CAPTURE_GLRT20MS_PNG_V2_PRODUCT = _png("standard.full-capture-glrt20ms-png", 2)

STANDARD_NATIVE_PNG_PRODUCTS = (
    WATERFALL_PNG_V2_PRODUCT,
    DOPPLER_WATERFALL_PNG_V1_PRODUCT,
    PILOT_METHODS_PNG_V2_PRODUCT,
    CFO_TRAJECTORIES_PNG_V2_PRODUCT,
    DEALIASED_CFO_TRAJECTORIES_PNG_V2_PRODUCT,
    FINAL_CFO_TRAJECTORIES_PNG_V2_PRODUCT,
)

PATH_STANDARD_NATIVE_OUTPUTS = (
    QUALITY_V3_PRODUCT,
    POWER_TIMELINE_V4_PRODUCT,
    NUMERICAL_WATERFALL_V4_PRODUCT,
    PROBE_SCHEDULE_V4_PRODUCT,
    STATEFUL_PATH_V3_PRODUCT,
    PILOT_DOPPLER_SEGMENTS_V4_PRODUCT,
    FULL_CAPTURE_GLRT20MS_V2_PRODUCT,
    PATH_REPORT_V4_PRODUCT,
)

ALTERNATE_CFO_TRACK_BANK_V4_PRODUCT = ProductSpec(
    kind="standard.alternate-cfo-track-bank", schema_version=4
)
ALTERNATE_CFO_TRACK_BANK_V5_PRODUCT = ProductSpec(
    kind="standard.alternate-cfo-track-bank", schema_version=5
)
TRAJECTORY_CONDITIONED_ACCOUNTING_V4_PRODUCT = ProductSpec(
    kind="standard.trajectory-conditioned-accounting", schema_version=4
)
ALTERNATE_CFO_TRACKS_PNG_V3_PRODUCT = _png("standard.alternate-cfo-tracks-png", 3)
PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS = (
    ALTERNATE_CFO_TRACK_BANK_V5_PRODUCT,
    TRAJECTORY_CONDITIONED_ACCOUNTING_V4_PRODUCT,
    *STANDARD_NATIVE_PNG_PRODUCTS,
    ALTERNATE_CFO_TRACKS_PNG_V3_PRODUCT,
    TRAJECTORY_CONDITIONED_ACCOUNTING_PNG_V3_PRODUCT,
    FULL_CAPTURE_GLRT20MS_PNG_V2_PRODUCT,
    PILOT_DOPPLER_SEGMENTS_PNG_V4_PRODUCT,
    PILOT_CARRIER_TRACKING_PNG_V4_PRODUCT,
    PILOT_SEGMENT_RATES_PNG_V4_PRODUCT,
)

RADIO_REPORT_V3_PRODUCT = ProductSpec(kind="standard.radio-report", schema_version=3)
RADIO_REPORT_V4_PRODUCT = ProductSpec(kind="standard.radio-report", schema_version=4)
RADIO_REPORT_V5_PRODUCT = ProductSpec(kind="standard.radio-report", schema_version=5)
RADIO_REPORT_V6_PRODUCT = ProductSpec(kind="standard.radio-report", schema_version=6)
RADIO_SCIENTIFIC_NATIVE_OUTPUTS = (RADIO_REPORT_V6_PRODUCT, *STANDARD_NATIVE_PNG_PRODUCTS)
PAIRED_REPORT_V3_PRODUCT = ProductSpec(kind="standard.paired-report", schema_version=3)
PAIRED_REPORT_V4_PRODUCT = ProductSpec(kind="standard.paired-report", schema_version=4)
PAIRED_REPORT_V5_PRODUCT = ProductSpec(kind="standard.paired-report", schema_version=5)
PAIRED_REPORT_V6_PRODUCT = ProductSpec(kind="standard.paired-report", schema_version=6)
PAIRED_REPORT_V7_PRODUCT = ProductSpec(kind="standard.paired-report", schema_version=7)
PAIRED_SCIENTIFIC_NATIVE_OUTPUTS = (PAIRED_REPORT_V7_PRODUCT,)
PAIRED_PRESENTATION_NATIVE_OUTPUTS = STANDARD_NATIVE_PNG_PRODUCTS

STANDARD_NATIVE_REGISTRY_OUTPUT_COUNT = sum(
    len(outputs)
    for outputs in (
        PATH_STANDARD_NATIVE_OUTPUTS,
        PATH_ALTERNATE_TRACKS_NATIVE_OUTPUTS,
        RADIO_SCIENTIFIC_NATIVE_OUTPUTS,
        PAIRED_SCIENTIFIC_NATIVE_OUTPUTS,
        PAIRED_PRESENTATION_NATIVE_OUTPUTS,
    )
)
if STANDARD_NATIVE_REGISTRY_OUTPUT_COUNT != 36:
    raise RuntimeError("Standard-native-v1 output inventory changed")
