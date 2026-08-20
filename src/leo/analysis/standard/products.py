"""Closed Standard-v2 product identities and direct scientific dependencies.

The 10-stage production graph keeps trajectory feedback and its table in one
job, but publishes two separately digest-bound products.  These declarations
are infrastructure-blind and are shared by stage adapters and contract tests.
"""

from __future__ import annotations

from leo.analysis.standard.source_bindings import STANDARD_SOURCE_BINDING_SPECS
from leo.contracts.standard_pipeline import (
    STANDARD_NUMERICAL_WATERFALL_KIND,
    STANDARD_PATH_INPUT_BIND_KIND,
    STANDARD_POWER_TIMELINE_KIND,
    STANDARD_PROBE_SCHEDULE_KIND,
)
from leo.pipeline import ProductRequirement, ProductRole, ProductSpec

PATH_INPUT_BIND_PRODUCT = ProductSpec(kind=STANDARD_PATH_INPUT_BIND_KIND, schema_version=3)
QUALITY_PRODUCT = ProductSpec(kind="quality.summary", schema_version=1)
POWER_TIMELINE_PRODUCT = ProductSpec(kind=STANDARD_POWER_TIMELINE_KIND, schema_version=2)
NUMERICAL_WATERFALL_PRODUCT = ProductSpec(
    kind=STANDARD_NUMERICAL_WATERFALL_KIND,
    schema_version=2,
)
PROBE_SCHEDULE_PRODUCT = ProductSpec(kind=STANDARD_PROBE_SCHEDULE_KIND, schema_version=2)
PILOT_SCAN_PRODUCT = ProductSpec(kind="standard.pilot-scan", schema_version=3)
TRAJECTORY_BANK_PRODUCT = ProductSpec(kind="standard.trajectory-bank", schema_version=2)
TRAJECTORY_FEEDBACK_PRODUCT = ProductSpec(
    kind="standard.trajectory-feedback",
    schema_version=2,
)
GLRT64_TRAJECTORY_TABLE_PRODUCT = ProductSpec(
    kind="standard.glrt64-trajectory-table",
    schema_version=2,
)
CFO_ALIAS_MAP_PRODUCT = ProductSpec(kind="standard.cfo-alias-map", schema_version=2)
DEALIASED_TRAJECTORY_BANK_V1_PRODUCT = ProductSpec(
    kind="standard.dealiased-trajectory-bank", schema_version=1
)
DEALIASED_TRAJECTORY_BANK_PRODUCT = ProductSpec(
    kind="standard.dealiased-trajectory-bank", schema_version=2
)
CFO_LIFT_REPLAY_PRODUCT = ProductSpec(kind="standard.cfo-lift-replay", schema_version=1)
FINAL_TRAJECTORY_BANK_PRODUCT = ProductSpec(kind="standard.final-trajectory-bank", schema_version=1)
GLRT64_FINAL_TRAJECTORY_TABLE_PRODUCT = ProductSpec(
    kind="standard.glrt64-final-trajectory-table", schema_version=1
)
PATH_REPORT_V1_PRODUCT = ProductSpec(kind="standard.path-report", schema_version=1)
PATH_REPORT_PRODUCT = ProductSpec(kind="standard.path-report", schema_version=2)
PATH_PRESENTATION_PRODUCT = ProductSpec(
    kind="standard.path-presentation",
    schema_version=3,
    role=ProductRole.PRESENTATION,
)
WATERFALL_PNG_PRODUCT = ProductSpec(
    kind="standard.waterfall-png",
    schema_version=1,
    role=ProductRole.PRESENTATION,
    media_type="image/png",
)
PILOT_METHODS_PNG_PRODUCT = ProductSpec(
    kind="standard.pilot-methods-png",
    schema_version=1,
    role=ProductRole.PRESENTATION,
    media_type="image/png",
)
CFO_TRAJECTORIES_PNG_PRODUCT = ProductSpec(
    kind="standard.cfo-trajectories-png",
    schema_version=1,
    role=ProductRole.PRESENTATION,
    media_type="image/png",
)
DEALIASED_CFO_TRAJECTORIES_PNG_PRODUCT = ProductSpec(
    kind="standard.cfo-trajectories-dealiased-png",
    schema_version=1,
    role=ProductRole.PRESENTATION,
    media_type="image/png",
)
FINAL_CFO_TRAJECTORIES_PNG_PRODUCT = ProductSpec(
    kind="standard.cfo-trajectories-final-png",
    schema_version=1,
    role=ProductRole.PRESENTATION,
    media_type="image/png",
)
STANDARD_PNG_PRODUCTS = (
    WATERFALL_PNG_PRODUCT,
    PILOT_METHODS_PNG_PRODUCT,
    CFO_TRAJECTORIES_PNG_PRODUCT,
    DEALIASED_CFO_TRAJECTORIES_PNG_PRODUCT,
    FINAL_CFO_TRAJECTORIES_PNG_PRODUCT,
)
RADIO_REPORT_V1_PRODUCT = ProductSpec(kind="standard.radio-report", schema_version=1)
RADIO_REPORT_PRODUCT = ProductSpec(kind="standard.radio-report", schema_version=2)
PAIRED_REPORT_V1_PRODUCT = ProductSpec(kind="standard.paired-report", schema_version=1)
PAIRED_REPORT_PRODUCT = ProductSpec(kind="standard.paired-report", schema_version=2)
QUALITY_OUTPUTS = (QUALITY_PRODUCT,)
POWER_OUTPUTS = (POWER_TIMELINE_PRODUCT,)
WATERFALL_OUTPUTS = (NUMERICAL_WATERFALL_PRODUCT,)
PROBE_SCHEDULE_OUTPUTS = (PROBE_SCHEDULE_PRODUCT,)
PILOT_SCAN_OUTPUTS = (PILOT_SCAN_PRODUCT,)
TRAJECTORY_BANK_OUTPUTS = (TRAJECTORY_BANK_PRODUCT,)


def _require(product: ProductSpec, producer_stage_key: str) -> ProductRequirement:
    return ProductRequirement(
        kind=product.kind,
        accepted_schema_versions=(product.schema_version,),
        producer_stage_key=producer_stage_key,
        require_available=True,
    )


QUALITY_INPUTS = (_require(PATH_INPUT_BIND_PRODUCT, "path-input-bind"),)
PROBE_SCHEDULE_INPUTS = (_require(PATH_INPUT_BIND_PRODUCT, "path-input-bind"),)
POWER_INPUTS = (_require(QUALITY_PRODUCT, "path-quality"),)
WATERFALL_INPUTS = (_require(POWER_TIMELINE_PRODUCT, "path-power"),)
PILOT_SCAN_INPUTS = (_require(PROBE_SCHEDULE_PRODUCT, "path-probe-schedule"),)
TRAJECTORY_BANK_INPUTS = (_require(PILOT_SCAN_PRODUCT, "path-pilot-scan"),)
TRAJECTORY_FEEDBACK_INPUTS = (
    _require(PILOT_SCAN_PRODUCT, "path-pilot-scan"),
    _require(TRAJECTORY_BANK_PRODUCT, "path-trajectory-bank"),
)
TRAJECTORY_FEEDBACK_OUTPUTS = (
    TRAJECTORY_FEEDBACK_PRODUCT,
    GLRT64_TRAJECTORY_TABLE_PRODUCT,
)
PATH_REPORT_INPUTS = (
    _require(PATH_INPUT_BIND_PRODUCT, "path-input-bind"),
    _require(PROBE_SCHEDULE_PRODUCT, "path-probe-schedule"),
    _require(QUALITY_PRODUCT, "path-quality"),
    _require(POWER_TIMELINE_PRODUCT, "path-power"),
    _require(NUMERICAL_WATERFALL_PRODUCT, "path-waterfall"),
    _require(PILOT_SCAN_PRODUCT, "path-pilot-scan"),
    _require(TRAJECTORY_BANK_PRODUCT, "path-trajectory-bank"),
    _require(TRAJECTORY_FEEDBACK_PRODUCT, "path-trajectory-feedback"),
    _require(GLRT64_TRAJECTORY_TABLE_PRODUCT, "path-trajectory-feedback"),
)
PATH_PRESENTATION_INPUTS = (
    _require(POWER_TIMELINE_PRODUCT, "path-power"),
    _require(NUMERICAL_WATERFALL_PRODUCT, "path-waterfall"),
    _require(PILOT_SCAN_PRODUCT, "path-pilot-scan"),
    _require(TRAJECTORY_BANK_PRODUCT, "path-trajectory-bank"),
    _require(TRAJECTORY_FEEDBACK_PRODUCT, "path-trajectory-feedback"),
    _require(GLRT64_TRAJECTORY_TABLE_PRODUCT, "path-trajectory-feedback"),
    _require(PATH_REPORT_PRODUCT, "path-scientific-report"),
)
RADIO_REPORT_INPUT = _require(PATH_REPORT_PRODUCT, "path-scientific-report")
PAIRED_REPORT_INPUT = _require(RADIO_REPORT_PRODUCT, "radio-scientific-report")

# These are the frozen durable outputs. Source-binding wrappers are derivation
# metadata around these products, never additional scientific products in the
# expanded run inventory for the two-radio/four-path topology.
STANDARD_SOURCE_BOUND_STAGE_OUTPUTS = {
    "path-quality": QUALITY_OUTPUTS,
    "path-power": POWER_OUTPUTS,
    "path-waterfall": WATERFALL_OUTPUTS,
    "path-probe-schedule": PROBE_SCHEDULE_OUTPUTS,
    "path-pilot-scan": PILOT_SCAN_OUTPUTS,
    "path-trajectory-bank": TRAJECTORY_BANK_OUTPUTS,
    "path-trajectory-feedback": TRAJECTORY_FEEDBACK_OUTPUTS,
}

_declared_source_bound_outputs = {
    (stage_key, product.kind, product.schema_version)
    for stage_key, products in STANDARD_SOURCE_BOUND_STAGE_OUTPUTS.items()
    for product in products
}
_source_binding_specs = {
    (spec.stage_key, spec.product_kind, spec.product_schema_version)
    for spec in STANDARD_SOURCE_BINDING_SPECS
}
if _source_binding_specs != _declared_source_bound_outputs:
    raise RuntimeError("Standard source-binding metadata disagrees with durable stage outputs")
