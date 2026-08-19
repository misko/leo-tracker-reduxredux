"""Closed Standard-v2 product identities and direct scientific dependencies.

The 10-stage production graph keeps trajectory feedback and its table in one
job, but publishes two separately digest-bound products.  These declarations
are infrastructure-blind and are shared by stage adapters and contract tests.
"""

from __future__ import annotations

from leo.contracts.standard_pipeline import (
    STANDARD_NUMERICAL_WATERFALL_KIND,
    STANDARD_PATH_INPUT_BIND_KIND,
    STANDARD_POWER_TIMELINE_KIND,
    STANDARD_PROBE_SCHEDULE_KIND,
)
from leo.pipeline import ProductRequirement, ProductSpec

PATH_INPUT_BIND_PRODUCT = ProductSpec(kind=STANDARD_PATH_INPUT_BIND_KIND, schema_version=2)
QUALITY_PRODUCT = ProductSpec(kind="quality.summary", schema_version=1)
POWER_TIMELINE_PRODUCT = ProductSpec(kind=STANDARD_POWER_TIMELINE_KIND, schema_version=2)
NUMERICAL_WATERFALL_PRODUCT = ProductSpec(
    kind=STANDARD_NUMERICAL_WATERFALL_KIND,
    schema_version=2,
)
PROBE_SCHEDULE_PRODUCT = ProductSpec(kind=STANDARD_PROBE_SCHEDULE_KIND, schema_version=1)
PILOT_SCAN_PRODUCT = ProductSpec(kind="standard.pilot-scan", schema_version=2)
TRAJECTORY_BANK_PRODUCT = ProductSpec(kind="standard.trajectory-bank", schema_version=2)
TRAJECTORY_FEEDBACK_PRODUCT = ProductSpec(
    kind="standard.trajectory-feedback",
    schema_version=2,
)
GLRT64_TRAJECTORY_TABLE_PRODUCT = ProductSpec(
    kind="standard.glrt64-trajectory-table",
    schema_version=2,
)


def _require(product: ProductSpec, producer_stage_key: str) -> ProductRequirement:
    return ProductRequirement(
        kind=product.kind,
        accepted_schema_versions=(product.schema_version,),
        producer_stage_key=producer_stage_key,
        require_available=True,
    )


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
