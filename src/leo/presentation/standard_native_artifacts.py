"""Closed browser artifact inventory for promoted Standard-native runs.

This additive read-model contract does not create a catalog product and does
not widen the published Standard-native presentation V3 contracts.  Every row
points at an immutable, run-registered PNG that was produced before sealing.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self, cast
from urllib.parse import quote

from pydantic import Field, StringConstraints, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.presentation.standard_pipeline import StandardSubjectKindV2

Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=192, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
BoundedText = Annotated[str, StringConstraints(min_length=1, max_length=256)]
ApiHref = Annotated[str, StringConstraints(min_length=1, max_length=768)]

StandardNativePngArtifactNameV4 = Literal[
    "waterfall",
    "pilot-methods",
    "cfo-raw",
    "cfo-dealiased",
    "cfo-final",
    "cfo-alternate",
    "trajectory-accounting",
    "full-capture-glrt20ms",
    "pilot-doppler",
    "pilot-carrier-tracking",
    "pilot-segment-rates",
]

STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V4: tuple[StandardNativePngArtifactNameV4, ...] = (
    "waterfall",
    "pilot-methods",
    "cfo-raw",
    "cfo-dealiased",
    "cfo-final",
)
STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V4: tuple[StandardNativePngArtifactNameV4, ...] = (
    *STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V4,
    "cfo-alternate",
    "trajectory-accounting",
    "full-capture-glrt20ms",
    "pilot-doppler",
    "pilot-carrier-tracking",
    "pilot-segment-rates",
)

# name -> (label, description, catalog kind, schema, view name or None)
STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V4: dict[
    StandardNativePngArtifactNameV4,
    tuple[str, str, str, int, str | None],
] = {
    "waterfall": (
        "Waterfall — frequency × time",
        "Fixed global device-time axis; missing support is blank",
        "standard.waterfall-png",
        2,
        "waterfall",
    ),
    "pilot-methods": (
        "Pilot detector comparison — GLRT64, Symbolwise, Anchor-8",
        "Wholly-valid probes with hard continuity resets",
        "standard.pilot-methods-png",
        2,
        "glrt64",
    ),
    "cfo-raw": (
        "CFO trajectories — Hough-seeded robust linear segments",
        "Reset-local raw trajectory geometry on the global time axis",
        "standard.cfo-trajectories-png",
        2,
        "cfo_trajectory",
    ),
    "cfo-dealiased": (
        "De-aliased CFO trajectories",
        "Canonical modulo-alias branches before absolute-lift replay",
        "standard.cfo-trajectories-dealiased-png",
        2,
        None,
    ),
    "cfo-final": (
        "Final replay-classified CFO candidates",
        "Correction-eligible and display-only reset-local tracks",
        "standard.cfo-trajectories-final-png",
        2,
        None,
    ),
    "cfo-alternate": (
        "Alternate Hough CFO candidates",
        "Independent reset-local alternate Hough geometry",
        "standard.alternate-cfo-tracks-png",
        3,
        None,
    ),
    "trajectory-accounting": (
        "Trajectory-conditioned replay accounting",
        "Per-segment transition and support accounting",
        "standard.trajectory-conditioned-accounting-png",
        3,
        None,
    ),
    "full-capture-glrt20ms": (
        "Independent 20 ms GLRT and local Doppler rate",
        "Globally scheduled valid windows with segment-local fits",
        "standard.full-capture-glrt20ms-png",
        2,
        None,
    ),
    "pilot-doppler": (
        "Pilot Doppler qualification overview",
        "Segment-local qualification and reacquisition evidence",
        "standard.pilot-doppler-segments-png",
        3,
        None,
    ),
    "pilot-carrier-tracking": (
        "Frame CFO and carrier-rate tracking",
        "Frame-level state with visible continuity resets",
        "standard.pilot-carrier-tracking-png",
        3,
        None,
    ),
    "pilot-segment-rates": (
        "Doppler rates across 50–75 ms segment regions",
        "Direct local rates remain separate across continuity segments",
        "standard.pilot-segment-rates-png",
        3,
        None,
    ),
}

# Additive identity for the held-out V3 phase views.  V4 is a published public
# read contract and must continue to describe the schema-3 plots from older
# sealed runs exactly.
STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V7 = {
    **STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V4,
    "pilot-doppler": (
        "Pilot Doppler qualification overview",
        "Independent local Doppler and held-out adjacent phase evidence",
        "standard.pilot-doppler-segments-png",
        4,
        None,
    ),
    "pilot-carrier-tracking": (
        "Held-out adjacent carrier-phase trackability",
        "Prefix-trained modulo-pi nuisance and later one-step innovations",
        "standard.pilot-carrier-tracking-png",
        4,
        None,
    ),
    "pilot-segment-rates": (
        "Doppler rates across 50–75 ms segment regions",
        "Independent direct rates remain separate across continuity segments",
        "standard.pilot-segment-rates-png",
        4,
        None,
    ),
}

StandardNativePngArtifactNameV8 = Literal[
    "waterfall",
    "doppler-waterfall",
    "pilot-methods",
    "cfo-raw",
    "cfo-dealiased",
    "cfo-final",
    "cfo-alternate",
    "trajectory-accounting",
    "full-capture-glrt20ms",
    "pilot-doppler",
    "pilot-carrier-tracking",
    "pilot-segment-rates",
]

STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V8: tuple[StandardNativePngArtifactNameV8, ...] = (
    "waterfall",
    "doppler-waterfall",
    "pilot-methods",
    "cfo-raw",
    "cfo-dealiased",
    "cfo-final",
)
STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V8: tuple[StandardNativePngArtifactNameV8, ...] = (
    *STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V8,
    "cfo-alternate",
    "trajectory-accounting",
    "full-capture-glrt20ms",
    "pilot-doppler",
    "pilot-carrier-tracking",
    "pilot-segment-rates",
)
STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V8: dict[
    StandardNativePngArtifactNameV8,
    tuple[str, str, str, int, str | None],
] = {
    **{name: values for name, values in STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V7.items()},
    "doppler-waterfall": (
        "Doppler diagnostic — target-band waterfall and GLRT fits",
        "Rate-normalized common-frequency crop with segment-local candidate tracks and resets",
        "standard.doppler-waterfall-png",
        1,
        None,
    ),
}


class StandardNativePngArtifactV4(ContractModel):
    """One immutable PNG available for the selected native subject."""

    schema_version: Literal[4] = 4
    name: StandardNativePngArtifactNameV4
    label: BoundedText
    description: BoundedText
    href: ApiHref
    catalog_kind: Identifier
    product_schema_version: Annotated[int, Field(gt=0)]
    digest: Sha256Digest
    byte_size: Annotated[int, Field(gt=0, le=64 * 1024 * 1024)]
    media_type: Literal["image/png"] = "image/png"


class StandardNativePngArtifactInventoryV4(ContractModel):
    """Exact ordered 11/5/5 PNG inventory bound to one Current native run."""

    schema_version: Literal[4] = 4
    session_id: Identifier
    subject_id: Identifier
    subject_kind: StandardSubjectKindV2
    run_id: Identifier
    run_manifest_digest: Sha256Digest
    sample_rate_hz: Literal[2_500_000, 3_000_000, 5_000_000, 10_000_000]
    coverage_status: Literal["complete", "partial_coverage", "insufficient_data"]
    artifacts: tuple[StandardNativePngArtifactV4, ...] = Field(min_length=5, max_length=11)
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _inventory_is_exact(self) -> Self:
        expected_names = (
            STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V4
            if self.subject_kind is StandardSubjectKindV2.RECEIVER_PATH
            else STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V4
        )
        if tuple(item.name for item in self.artifacts) != expected_names:
            raise ValueError("native PNG artifact inventory is not the exact ordered scope set")
        base = (
            f"/api/v2/recordings/{quote(self.session_id, safe='')}/standard-subjects/"
            f"{quote(self.subject_id, safe='')}"
        )
        for item in self.artifacts:
            label, description, kind, schema_version, view_name = (
                STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V4[item.name]
            )
            expected_href = (
                f"{base}/views/{view_name}.png"
                if view_name is not None
                else f"{base}/artifacts/{item.name}.png"
            )
            if (
                item.label != label
                or item.description != description
                or item.catalog_kind != kind
                or item.product_schema_version != schema_version
                or item.href != expected_href
            ):
                raise ValueError("native PNG artifact descriptor differs from its closed identity")
        values = {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "subject_id": self.subject_id,
            "subject_kind": self.subject_kind.value,
            "run_id": self.run_id,
            "run_manifest_digest": self.run_manifest_digest,
            "sample_rate_hz": self.sample_rate_hz,
            "coverage_status": self.coverage_status,
            "artifacts": tuple(item.model_dump(mode="json") for item in self.artifacts),
        }
        if self.content_digest != canonical_digest(values):
            raise ValueError("native PNG artifact inventory digest does not match")
        return self


class StandardNativePngArtifactInventoryV5(ContractModel):
    """Exact PNG inventory for one subject in an unequal-rate Current run."""

    schema_version: Literal[5] = 5
    session_id: Identifier
    subject_id: Identifier
    subject_kind: StandardSubjectKindV2
    run_id: Identifier
    run_manifest_digest: Sha256Digest
    sample_rates_hz: tuple[Literal[2_500_000, 5_000_000, 10_000_000], ...] = Field(
        min_length=1,
        max_length=2,
    )
    coverage_status: Literal["complete", "partial_coverage", "insufficient_data"]
    artifacts: tuple[StandardNativePngArtifactV4, ...] = Field(min_length=5, max_length=11)
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _inventory_is_exact(self) -> Self:
        if self.sample_rates_hz != tuple(sorted(set(self.sample_rates_hz))):
            raise ValueError("mixed native PNG rates must be unique and ordered")
        expected_names = (
            STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V4
            if self.subject_kind is StandardSubjectKindV2.RECEIVER_PATH
            else STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V4
        )
        if tuple(item.name for item in self.artifacts) != expected_names:
            raise ValueError("mixed native PNG artifact inventory is not the exact scope set")
        base = (
            f"/api/v2/recordings/{quote(self.session_id, safe='')}/standard-subjects/"
            f"{quote(self.subject_id, safe='')}"
        )
        for item in self.artifacts:
            label, description, kind, schema_version, view_name = (
                STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V4[item.name]
            )
            expected_href = (
                f"{base}/views/{view_name}.png"
                if view_name is not None
                else f"{base}/artifacts/{item.name}.png"
            )
            if (
                item.label != label
                or item.description != description
                or item.catalog_kind != kind
                or item.product_schema_version != schema_version
                or item.href != expected_href
            ):
                raise ValueError("mixed native PNG descriptor differs from its closed identity")
        values = {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "subject_id": self.subject_id,
            "subject_kind": self.subject_kind.value,
            "run_id": self.run_id,
            "run_manifest_digest": self.run_manifest_digest,
            "sample_rates_hz": self.sample_rates_hz,
            "coverage_status": self.coverage_status,
            "artifacts": tuple(item.model_dump(mode="json") for item in self.artifacts),
        }
        if self.content_digest != canonical_digest(values):
            raise ValueError("mixed native PNG artifact inventory digest does not match")
        return self


class StandardNativePngArtifactInventoryV6(StandardNativePngArtifactInventoryV5):
    """Exact PNG inventory for a production-policy Current run."""

    schema_version: Literal[6] = 6  # type: ignore[assignment]
    sample_rates_hz: tuple[
        Literal[2_500_000, 5_000_000, 10_000_000, 15_000_000, 20_000_000], ...
    ] = Field(min_length=1, max_length=2)  # type: ignore[assignment]


class StandardNativePngArtifactInventoryV7(ContractModel):
    """Additive inventory for held-out phase views; V4--V6 remain readable."""

    schema_version: Literal[7] = 7
    session_id: Identifier
    subject_id: Identifier
    subject_kind: StandardSubjectKindV2
    run_id: Identifier
    run_manifest_digest: Sha256Digest
    sample_rates_hz: tuple[
        Literal[2_500_000, 3_000_000, 5_000_000, 10_000_000, 15_000_000, 20_000_000],
        ...,
    ] = Field(min_length=1, max_length=2)
    coverage_status: Literal["complete", "partial_coverage", "insufficient_data"]
    artifacts: tuple[StandardNativePngArtifactV4, ...] = Field(min_length=5, max_length=11)
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _inventory_is_exact(self) -> Self:
        if self.sample_rates_hz != tuple(sorted(set(self.sample_rates_hz))):
            raise ValueError("V7 native PNG rates must be unique and ordered")
        expected_names = (
            STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V4
            if self.subject_kind is StandardSubjectKindV2.RECEIVER_PATH
            else STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V4
        )
        if tuple(item.name for item in self.artifacts) != expected_names:
            raise ValueError("V7 native PNG artifact inventory is not the exact scope set")
        base = (
            f"/api/v2/recordings/{quote(self.session_id, safe='')}/standard-subjects/"
            f"{quote(self.subject_id, safe='')}"
        )
        for item in self.artifacts:
            label, description, kind, schema_version, view_name = (
                STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V7[item.name]
            )
            expected_href = (
                f"{base}/views/{view_name}.png"
                if view_name is not None
                else f"{base}/artifacts/{item.name}.png"
            )
            if (
                item.label != label
                or item.description != description
                or item.catalog_kind != kind
                or item.product_schema_version != schema_version
                or item.href != expected_href
            ):
                raise ValueError("V7 native PNG descriptor differs from its closed identity")
        values = {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "subject_id": self.subject_id,
            "subject_kind": self.subject_kind.value,
            "run_id": self.run_id,
            "run_manifest_digest": self.run_manifest_digest,
            "sample_rates_hz": self.sample_rates_hz,
            "coverage_status": self.coverage_status,
            "artifacts": tuple(item.model_dump(mode="json") for item in self.artifacts),
        }
        if self.content_digest != canonical_digest(values):
            raise ValueError("V7 native PNG artifact inventory digest does not match")
        return self


class StandardNativePngArtifactV8(ContractModel):
    """One immutable PNG descriptor in the additive Doppler inventory."""

    schema_version: Literal[8] = 8
    name: StandardNativePngArtifactNameV8
    label: BoundedText
    description: BoundedText
    href: ApiHref
    catalog_kind: Identifier
    product_schema_version: Annotated[int, Field(gt=0)]
    digest: Sha256Digest
    byte_size: Annotated[int, Field(gt=0, le=64 * 1024 * 1024)]
    media_type: Literal["image/png"] = "image/png"


class StandardNativePngArtifactInventoryV8(ContractModel):
    """Additive inventory containing the rate-normalized Doppler diagnostic."""

    schema_version: Literal[8] = 8
    session_id: Identifier
    subject_id: Identifier
    subject_kind: StandardSubjectKindV2
    run_id: Identifier
    run_manifest_digest: Sha256Digest
    sample_rates_hz: tuple[
        Literal[2_500_000, 3_000_000, 5_000_000, 10_000_000, 15_000_000, 20_000_000],
        ...,
    ] = Field(min_length=1, max_length=2)
    coverage_status: Literal["complete", "partial_coverage", "insufficient_data"]
    artifacts: tuple[StandardNativePngArtifactV8, ...] = Field(min_length=6, max_length=12)
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _inventory_is_exact(self) -> Self:
        if self.sample_rates_hz != tuple(sorted(set(self.sample_rates_hz))):
            raise ValueError("V8 native PNG rates must be unique and ordered")
        expected_names = (
            STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V8
            if self.subject_kind is StandardSubjectKindV2.RECEIVER_PATH
            else STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V8
        )
        if tuple(item.name for item in self.artifacts) != expected_names:
            raise ValueError("V8 native PNG artifact inventory is not the exact scope set")
        base = (
            f"/api/v2/recordings/{quote(self.session_id, safe='')}/standard-subjects/"
            f"{quote(self.subject_id, safe='')}"
        )
        for item in self.artifacts:
            label, description, kind, schema_version, view_name = (
                STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V8[item.name]
            )
            expected_href = (
                f"{base}/views/{view_name}.png"
                if view_name is not None
                else f"{base}/artifacts/{item.name}.png"
            )
            if (
                item.label != label
                or item.description != description
                or item.catalog_kind != kind
                or item.product_schema_version != schema_version
                or item.href != expected_href
            ):
                raise ValueError("V8 native PNG descriptor differs from its closed identity")
        values = {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "subject_id": self.subject_id,
            "subject_kind": self.subject_kind.value,
            "run_id": self.run_id,
            "run_manifest_digest": self.run_manifest_digest,
            "sample_rates_hz": self.sample_rates_hz,
            "coverage_status": self.coverage_status,
            "artifacts": tuple(item.model_dump(mode="json") for item in self.artifacts),
        }
        if self.content_digest != canonical_digest(values):
            raise ValueError("V8 native PNG artifact inventory digest does not match")
        return self


class StandardNativePngArtifactInventoryV9(StandardNativePngArtifactInventoryV8):
    """Additive direct-async PNG inventory supporting native 25 MS/s paths."""

    schema_version: Literal[9] = 9  # type: ignore[assignment]
    sample_rates_hz: tuple[Literal[2_500_000, 10_000_000, 15_000_000, 25_000_000], ...] = Field(
        min_length=1, max_length=2
    )  # type: ignore[assignment]


StandardNativePngArtifactNameV10 = Literal[
    "waterfall",
    "doppler-waterfall",
    "pilot-methods",
    "cfo-raw",
    "cfo-dealiased",
    "cfo-final",
    "cfo-alternate",
    "trajectory-accounting",
    "full-capture-glrt20ms",
    "glrt-epoch-timing",
    "glrt-epoch-rate",
    "pilot-doppler",
    "pilot-carrier-tracking",
    "pilot-segment-rates",
]

STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V10: tuple[StandardNativePngArtifactNameV10, ...] = (
    "waterfall",
    "doppler-waterfall",
    "pilot-methods",
    "cfo-raw",
    "cfo-dealiased",
    "cfo-final",
    "cfo-alternate",
    "trajectory-accounting",
    "full-capture-glrt20ms",
    "glrt-epoch-timing",
    "glrt-epoch-rate",
    "pilot-doppler",
    "pilot-carrier-tracking",
    "pilot-segment-rates",
)
STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V10 = cast(
    dict[StandardNativePngArtifactNameV10, tuple[str, str, str, int, str | None]],
    {
        **STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V8,
        "glrt-epoch-timing": (
            "GLRT frame-epoch timing fits",
            "CFO-selected, continuity-local linear and quadratic timing residuals",
            "standard.glrt-epoch-timing-png",
            1,
            None,
        ),
        "glrt-epoch-rate": (
            "GLRT epoch/CFO Doppler-rate consistency",
            "Physical-minus-sign epoch curvature versus canonical GLRT CFO derivatives",
            "standard.glrt-epoch-rate-png",
            1,
            None,
        ),
    },
)


class StandardNativePngArtifactV10(ContractModel):
    """One immutable PNG descriptor in the additive epoch inventory."""

    schema_version: Literal[10] = 10
    name: StandardNativePngArtifactNameV10
    label: BoundedText
    description: BoundedText
    href: ApiHref
    catalog_kind: Identifier
    product_schema_version: Annotated[int, Field(gt=0)]
    digest: Sha256Digest
    byte_size: Annotated[int, Field(gt=0, le=64 * 1024 * 1024)]
    media_type: Literal["image/png"] = "image/png"


class StandardNativePngArtifactInventoryV10(ContractModel):
    """Additive path inventory containing GLRT epoch timing and rate diagnostics."""

    schema_version: Literal[10] = 10
    session_id: Identifier
    subject_id: Identifier
    subject_kind: Literal[StandardSubjectKindV2.RECEIVER_PATH]
    run_id: Identifier
    run_manifest_digest: Sha256Digest
    sample_rates_hz: tuple[
        Literal[
            2_500_000,
            3_000_000,
            5_000_000,
            10_000_000,
            15_000_000,
            20_000_000,
            25_000_000,
        ],
        ...,
    ] = Field(min_length=1, max_length=1)
    coverage_status: Literal["complete", "partial_coverage", "insufficient_data"]
    artifacts: tuple[StandardNativePngArtifactV10, ...] = Field(min_length=14, max_length=14)
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _inventory_is_exact(self) -> Self:
        if self.sample_rates_hz != tuple(sorted(set(self.sample_rates_hz))):
            raise ValueError("V10 native PNG rates must be unique and ordered")
        if tuple(item.name for item in self.artifacts) != STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V10:
            raise ValueError("V10 native PNG artifact inventory is not the exact path set")
        base = (
            f"/api/v2/recordings/{quote(self.session_id, safe='')}/standard-subjects/"
            f"{quote(self.subject_id, safe='')}"
        )
        for item in self.artifacts:
            label, description, kind, schema_version, view_name = (
                STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V10[item.name]
            )
            expected_href = (
                f"{base}/views/{view_name}.png"
                if view_name is not None
                else f"{base}/artifacts/{item.name}.png"
            )
            if (
                item.label != label
                or item.description != description
                or item.catalog_kind != kind
                or item.product_schema_version != schema_version
                or item.href != expected_href
            ):
                raise ValueError("V10 native PNG descriptor differs from its closed identity")
        values = {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "subject_id": self.subject_id,
            "subject_kind": self.subject_kind.value,
            "run_id": self.run_id,
            "run_manifest_digest": self.run_manifest_digest,
            "sample_rates_hz": self.sample_rates_hz,
            "coverage_status": self.coverage_status,
            "artifacts": tuple(item.model_dump(mode="json") for item in self.artifacts),
        }
        if self.content_digest != canonical_digest(values):
            raise ValueError("V10 native PNG artifact inventory digest does not match")
        return self
