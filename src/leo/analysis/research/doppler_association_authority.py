"""Immutable UTC, RF, site, and causal-TLE authorities for holdout association.

These contracts describe inputs only.  They contain no satellite propagation,
catalog ranking, radio response, or estimator outcome.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from leo.contracts.digests import Sha256Digest, canonical_digest

AUTHORITY_BUNDLE_SCHEMA = "org.leo.research.doppler-association-authority-bundle/v1"

Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
RelativeArchivePath = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=2048,
        pattern=r"^archive/space-track/[0-9]+-[0-9a-f]{64}\.tle$",
    ),
]
LogicalUri = Annotated[str, StringConstraints(min_length=1, max_length=2048)]
RepositoryPath = Annotated[str, StringConstraints(min_length=1, max_length=2048)]
ResolverRole = Literal[
    "recording_manifest",
    "analysis_manifest",
    "utc_timing",
    "nominal_rf",
    "observer_site",
    "tle_archive",
]
_REQUIRED_RESOLVER_ROLES: tuple[ResolverRole, ...] = (
    "recording_manifest",
    "analysis_manifest",
    "utc_timing",
    "nominal_rf",
    "observer_site",
    "tle_archive",
)


class _AuthorityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)


class StreamUtcAuthorityV1(_AuthorityModel):
    session_id: Identifier
    stream_id: Identifier
    timing_method: Literal["device_counter_anchored"]
    sample_rate_hz: Annotated[int, Field(gt=0)]
    first_sample_earliest_utc_ns: Annotated[int, Field(gt=0)]
    first_sample_estimate_utc_ns: Annotated[int, Field(gt=0)]
    first_sample_latest_utc_ns: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def _bounds_are_ordered(self) -> Self:
        if not (
            self.first_sample_earliest_utc_ns
            <= self.first_sample_estimate_utc_ns
            <= self.first_sample_latest_utc_ns
        ):
            raise ValueError("first-sample UTC bounds are not ordered")
        return self

    def sample_utc_ns(
        self,
        reference_sample: float,
        *,
        bound: Literal["earliest", "estimate", "latest"] = "estimate",
    ) -> int:
        """Convert a device-relative sample coordinate using one frozen UTC bound."""

        if not math.isfinite(reference_sample) or reference_sample < 0:
            raise ValueError("reference sample must be finite and non-negative")
        origin = {
            "earliest": self.first_sample_earliest_utc_ns,
            "estimate": self.first_sample_estimate_utc_ns,
            "latest": self.first_sample_latest_utc_ns,
        }[bound]
        return origin + round(reference_sample * 1_000_000_000 / self.sample_rate_hz)


class NominalRfAuthorityV1(_AuthorityModel):
    session_id: Identifier
    stream_id: Identifier
    radio_id: Identifier
    receiver_id: Annotated[int, Field(ge=0, le=255)]
    edge: Literal["lower", "upper"]
    applied_if_center_hz: Annotated[int, Field(gt=0)]
    nominal_lnb_lo_hz: Annotated[int, Field(gt=0)]
    nominal_sky_frequency_hz: Annotated[int, Field(gt=0)]
    rf_rule: Literal["applied-if-center-plus-nominal-lnb-lo"]
    random_tuning_applied_settings_authoritative: Literal[True]
    receiver_frequency_reference_calibrated: Literal[False]
    lnb_offset_or_drift_measured: Literal[False]

    @model_validator(mode="after")
    def _nominal_frequency_is_arithmetic_only(self) -> Self:
        if self.nominal_sky_frequency_hz != self.applied_if_center_hz + self.nominal_lnb_lo_hz:
            raise ValueError("nominal RF disagrees with applied IF plus nominal LO")
        return self


class ObserverSiteAuthorityV1(_AuthorityModel):
    name: Identifier
    latitude_deg: Annotated[float, Field(ge=-90, le=90)]
    longitude_deg: Annotated[float, Field(ge=-180, le=180)]
    altitude_m: float
    position_uncertainty_m: Annotated[float, Field(gt=0)]
    provenance: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    source_sha256: Sha256Digest
    authority_level: Literal["reviewed-preset-not-capture-bound"]
    capture_bound_position: Literal[False]
    capture_bound_boresight: Literal[False]
    absolute_secure_norad_permitted: Literal[False]

    @model_validator(mode="after")
    def _site_values_are_finite(self) -> Self:
        values = (
            self.latitude_deg,
            self.longitude_deg,
            self.altitude_m,
            self.position_uncertainty_m,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("site authority values must be finite")
        return self


class CaptureArtifactAuthorityV1(_AuthorityModel):
    """Exact frozen manifests and selector identities for one capture."""

    session_id: Identifier
    recording_manifest_uri: LogicalUri
    recording_manifest_sha256: Sha256Digest
    analysis_run_id: Identifier
    analysis_manifest_uri: LogicalUri
    analysis_manifest_sha256: Sha256Digest
    raw_integrity_attestation_id: Identifier
    episode_id: Sha256Digest
    scope_key: Sha256Digest
    target_mask_digest: Sha256Digest


class AuthorityResolverV1(_AuthorityModel):
    """Digest-pinned implementation path, separate from the artifact it resolves."""

    role: ResolverRole
    implementation_path: RepositoryPath
    implementation_sha256: Sha256Digest

    @model_validator(mode="after")
    def _path_is_repository_relative(self) -> Self:
        parts = self.implementation_path.split("/")
        if (
            self.implementation_path.startswith("/")
            or "\\" in self.implementation_path
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ValueError("resolver implementation path must be repository-relative")
        return self


class ImmutableStarlinkTleSnapshotV1(_AuthorityModel):
    source: Literal["space-track"]
    scope: Literal["starlink"]
    collected_utc_ns: Annotated[int, Field(gt=0)]
    archive_relative_path: RelativeArchivePath
    snapshot_sha256: Sha256Digest
    byte_size: Annotated[int, Field(gt=0, le=16 * 1024 * 1024)]
    satellite_count: Annotated[int, Field(gt=0)]
    tle_epoch_min: AwareDatetime
    tle_epoch_max: AwareDatetime
    mutable_index_is_authority: Literal[False]

    @model_validator(mode="after")
    def _snapshot_is_immutable_and_ordered(self) -> Self:
        digest_hex = self.snapshot_sha256.removeprefix("sha256:")
        expected_path = f"archive/space-track/{self.collected_utc_ns}-{digest_hex}.tle"
        if self.archive_relative_path != expected_path:
            raise ValueError("TLE archive path disagrees with collection time or digest")
        if self.tle_epoch_min > self.tle_epoch_max:
            raise ValueError("TLE epoch interval is reversed")
        return self


class CaptureTleAuthorityV1(_AuthorityModel):
    session_id: Identifier
    target_earliest_utc_ns: Annotated[int, Field(gt=0)]
    target_latest_utc_ns: Annotated[int, Field(gt=0)]
    snapshot: ImmutableStarlinkTleSnapshotV1
    selection_rule: Literal["latest-immutable-starlink-snapshot-collected-before-target"]

    @model_validator(mode="after")
    def _snapshot_is_causal(self) -> Self:
        if self.target_latest_utc_ns < self.target_earliest_utc_ns:
            raise ValueError("target UTC interval is reversed")
        if self.snapshot.collected_utc_ns >= self.target_earliest_utc_ns:
            raise ValueError("TLE snapshot was not collected strictly before the target")
        return self


class DopplerAssociationAuthorityBundleV1(_AuthorityModel):
    schema: Literal[  # type: ignore[assignment]
        "org.leo.research.doppler-association-authority-bundle/v1"
    ]
    phase: Literal["pre_response_authority_freeze"]
    dataset_policy_sha256: Sha256Digest
    selector_v2_file_sha256: Sha256Digest
    selector_v2_manifest_digest: Sha256Digest
    captures: tuple[CaptureArtifactAuthorityV1, ...]
    resolvers: tuple[AuthorityResolverV1, ...]
    site: ObserverSiteAuthorityV1
    utc: tuple[StreamUtcAuthorityV1, ...]
    rf: tuple[NominalRfAuthorityV1, ...]
    tle: tuple[CaptureTleAuthorityV1, ...]
    iq_accessed: Literal[False]
    response_accessed: Literal[False]
    satellites_propagated_or_ranked: Literal[False]
    authority_digest: Sha256Digest

    @model_validator(mode="after")
    def _bundle_is_closed(self) -> Self:
        capture_ids = tuple(item.session_id for item in self.captures)
        utc_ids = tuple(item.session_id for item in self.utc)
        rf_ids = tuple(item.session_id for item in self.rf)
        tle_ids = tuple(item.session_id for item in self.tle)
        inventories = (capture_ids, utc_ids, rf_ids, tle_ids)
        if not capture_ids or any(len(set(items)) != len(items) for items in inventories):
            raise ValueError("capture authority inventories must be nonempty and unique")
        if any(set(items) != set(capture_ids) for items in inventories[1:]):
            raise ValueError("artifact, UTC, RF, and TLE capture inventories disagree")
        stream_by_session = {item.session_id: item.stream_id for item in self.utc}
        if any(stream_by_session[item.session_id] != item.stream_id for item in self.rf):
            raise ValueError("UTC and RF selected-stream authorities disagree")
        resolver_roles = tuple(item.role for item in self.resolvers)
        if resolver_roles != _REQUIRED_RESOLVER_ROLES:
            raise ValueError("resolver roles or order drifted")
        content = self.model_dump(mode="json", exclude={"authority_digest"})
        if self.authority_digest != canonical_digest(content):
            raise ValueError("association authority digest disagrees")
        return self


def seal_association_authority_bundle(
    *,
    dataset_policy_sha256: str,
    selector_v2_file_sha256: str,
    selector_v2_manifest_digest: str,
    captures: tuple[CaptureArtifactAuthorityV1, ...],
    resolvers: tuple[AuthorityResolverV1, ...],
    site: ObserverSiteAuthorityV1,
    utc: tuple[StreamUtcAuthorityV1, ...],
    rf: tuple[NominalRfAuthorityV1, ...],
    tle: tuple[CaptureTleAuthorityV1, ...],
) -> DopplerAssociationAuthorityBundleV1:
    """Seal input authorities without touching responses or propagating TLEs."""

    document = {
        "schema": AUTHORITY_BUNDLE_SCHEMA,
        "phase": "pre_response_authority_freeze",
        "dataset_policy_sha256": dataset_policy_sha256,
        "selector_v2_file_sha256": selector_v2_file_sha256,
        "selector_v2_manifest_digest": selector_v2_manifest_digest,
        "captures": [item.model_dump(mode="json") for item in captures],
        "resolvers": [item.model_dump(mode="json") for item in resolvers],
        "site": site.model_dump(mode="json"),
        "utc": [item.model_dump(mode="json") for item in utc],
        "rf": [item.model_dump(mode="json") for item in rf],
        "tle": [item.model_dump(mode="json") for item in tle],
        "iq_accessed": False,
        "response_accessed": False,
        "satellites_propagated_or_ranked": False,
    }
    return DopplerAssociationAuthorityBundleV1.model_validate(
        {**document, "authority_digest": canonical_digest(document)}
    )
