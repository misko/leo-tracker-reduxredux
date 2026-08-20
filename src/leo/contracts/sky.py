"""Immutable observer, pointing and window contracts for the sky interface.

These contracts carry no catalog, storage, HTTP or CLI identity.  They describe
where an observer stands, where an antenna looks, and over which bounded UTC
window a prediction is requested.  Nothing here reads a clock: every instant is
supplied by the caller so that a prediction is reproducible.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest

SiteName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9-]*$"),
]
SiteLabel = Annotated[str, StringConstraints(min_length=1, max_length=128)]

# The slider the operator sees spans 120 s centred on the anchor instant.
SKY_WINDOW_HALF_WIDTH_S = 60
_NS_PER_S = 1_000_000_000


class ObserverSiteV1(ContractModel):
    """One WGS84 ground position.

    ``altitude_m`` is height above the WGS84 *ellipsoid*, not mean sea level.
    The distinction is stated because the geodetic-to-ECEF conversion consumes
    ellipsoidal height directly; around San Francisco Bay the two differ by
    roughly 32 m, which is immaterial for pointing but must not be ambiguous in
    a persisted contract.
    """

    schema_version: Literal[1] = 1
    latitude_deg: Annotated[float, Field(ge=-90.0, le=90.0)]
    longitude_deg: Annotated[float, Field(gt=-180.0, le=180.0)]
    altitude_m: Annotated[float, Field(ge=-500.0, le=9_000.0)]
    label: SiteLabel

    @model_validator(mode="after")
    def _coordinates_are_finite(self) -> Self:
        for value in (self.latitude_deg, self.longitude_deg, self.altitude_m):
            if not math.isfinite(value):
                raise ValueError("observer site coordinates must be finite")
        return self


class BeamPointingV1(ContractModel):
    """A circular antenna acceptance cone plus a horizon mask.

    ``half_angle_deg`` is measured from boresight, so the full acceptance width
    is twice this value.  A wide half angle combined with the mask degenerates
    to "everything above the mask", which is the whole-sky browsing case.
    """

    schema_version: Literal[1] = 1
    boresight_azimuth_deg: Annotated[float, Field(ge=0.0, lt=360.0)]
    boresight_elevation_deg: Annotated[float, Field(ge=-90.0, le=90.0)]
    half_angle_deg: Annotated[float, Field(gt=0.0, le=90.0)]
    horizon_mask_deg: Annotated[float, Field(ge=0.0, le=90.0)] = 0.0

    @model_validator(mode="after")
    def _angles_are_finite(self) -> Self:
        for value in (
            self.boresight_azimuth_deg,
            self.boresight_elevation_deg,
            self.half_angle_deg,
            self.horizon_mask_deg,
        ):
            if not math.isfinite(value):
                raise ValueError("beam pointing angles must be finite")
        return self


class SkyWindowV1(ContractModel):
    """A bounded UTC window sampled at a fixed number of knots.

    The window is closed on both ends and always symmetric about the anchor, so
    ``sample_count`` knots span ``anchor - half_width`` to ``anchor + half_width``
    inclusive.  An odd count therefore places one knot exactly on the anchor.
    """

    schema_version: Literal[1] = 1
    anchor_utc_ns: Annotated[int, Field(gt=0)]
    half_width_s: Annotated[int, Field(ge=1, le=3_600)] = SKY_WINDOW_HALF_WIDTH_S
    sample_count: Annotated[int, Field(ge=2, le=241)] = 5

    @property
    def start_utc_ns(self) -> int:
        return self.anchor_utc_ns - self.half_width_s * _NS_PER_S

    @property
    def end_utc_ns(self) -> int:
        return self.anchor_utc_ns + self.half_width_s * _NS_PER_S

    def knot_utc_ns(self) -> tuple[int, ...]:
        """Return every knot instant, exactly reproducible from the contract."""

        span_ns = 2 * self.half_width_s * _NS_PER_S
        divisor = self.sample_count - 1
        return tuple(
            self.start_utc_ns + (span_ns * index) // divisor for index in range(self.sample_count)
        )

    @model_validator(mode="after")
    def _knots_are_exactly_spaced(self) -> Self:
        span_ns = 2 * self.half_width_s * _NS_PER_S
        if span_ns % (self.sample_count - 1):
            raise ValueError("sky window knots must divide the span exactly")
        return self


class TleSnapshotRefV1(ContractModel):
    """The exact archived element-set snapshot a prediction was computed from."""

    schema_version: Literal[1] = 1
    provider: Literal["space-track", "huggingface"]
    collected_utc_ns: Annotated[int, Field(gt=0)]
    digest: Sha256Digest
    object_count: Annotated[int, Field(ge=1, le=100_000)]


class DopplerPolynomialV1(ContractModel):
    """A predicted Doppler shift expressed as derivatives at a reference instant.

    Coefficients are the derivatives of the *shift* at ``reference_utc_ns``, so
    the shift at offset ``t`` seconds is::

        shift(t) = frequency_at_reference_hz
                 + slope_hz_s * t
                 + acceleration_hz_s2 * t**2 / 2
                 + jerk_hz_s3 * t**3 / 6

    The first three fields deliberately match the names the analysis pipeline's
    ``TlePrediction`` already uses, so a prediction can be handed to the
    existing association stage without reshaping.
    """

    schema_version: Literal[1] = 1
    degree: Literal[1, 2, 3]
    reference_utc_ns: Annotated[int, Field(gt=0)]
    downlink_frequency_hz: Annotated[float, Field(gt=0.0)]
    frequency_at_reference_hz: float
    slope_hz_s: float
    acceleration_hz_s2: float = 0.0
    jerk_hz_s3: float = 0.0
    residual_rms_hz: Annotated[float, Field(ge=0.0)]

    @model_validator(mode="after")
    def _coefficients_match_the_declared_degree(self) -> Self:
        for value in (
            self.frequency_at_reference_hz,
            self.slope_hz_s,
            self.acceleration_hz_s2,
            self.jerk_hz_s3,
            self.residual_rms_hz,
        ):
            if not math.isfinite(value):
                raise ValueError("Doppler polynomial coefficients must be finite")
        if self.degree < 3 and self.jerk_hz_s3 != 0.0:
            raise ValueError("jerk requires a degree-3 polynomial")
        if self.degree < 2 and self.acceleration_hz_s2 != 0.0:
            raise ValueError("acceleration requires at least a degree-2 polynomial")
        return self


class SkyObjectPredictionV1(ContractModel):
    """One catalogued object's geometry and predicted Doppler over the window."""

    schema_version: Literal[1] = 1
    object_name: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    catalog_number: Annotated[int, Field(ge=1)]
    azimuth_deg: Annotated[float, Field(ge=0.0, lt=360.0)]
    elevation_deg: Annotated[float, Field(ge=-90.0, le=90.0)]
    range_km: Annotated[float, Field(gt=0.0)]
    range_rate_km_s: float
    peak_elevation_deg: Annotated[float, Field(ge=-90.0, le=90.0)]
    minimum_boresight_separation_deg: Annotated[float, Field(ge=0.0, le=180.0)]
    within_beam_at_anchor: bool
    doppler: DopplerPolynomialV1

    @model_validator(mode="after")
    def _peak_elevation_cannot_be_below_the_anchor_elevation(self) -> Self:
        if self.peak_elevation_deg < self.elevation_deg - 1e-9:
            raise ValueError("peak elevation cannot be below the anchor elevation")
        return self


class SkyExclusionsV1(ContractModel):
    """Why catalogued objects were left out, reported rather than hidden."""

    schema_version: Literal[1] = 1
    propagation_failed: Annotated[int, Field(ge=0)] = 0
    implausible_altitude: Annotated[int, Field(ge=0)] = 0
    below_horizon_mask: Annotated[int, Field(ge=0)] = 0
    outside_beam: Annotated[int, Field(ge=0)] = 0

    @property
    def total(self) -> int:
        return (
            self.propagation_failed
            + self.implausible_altitude
            + self.below_horizon_mask
            + self.outside_beam
        )


class SkyFieldReportV1(ContractModel):
    """Which catalogued objects fall in one beam, and what Doppler they imply.

    Evidence is predictive only.  Presence in this report says a published
    element set places an object in the beam; it makes no claim that anything
    was received, detected or identified.
    """

    schema_version: Literal[1] = 1
    observer: ObserverSiteV1
    pointing: BeamPointingV1
    window: SkyWindowV1
    snapshot: TleSnapshotRefV1
    downlink_frequency_hz: Annotated[float, Field(gt=0.0)]
    objects: Annotated[tuple[SkyObjectPredictionV1, ...], Field(max_length=512)]
    source_object_count: Annotated[int, Field(ge=0)]
    returned_object_count: Annotated[int, Field(ge=0)]
    truncated: bool
    exclusions: SkyExclusionsV1

    @model_validator(mode="after")
    def _counts_agree_with_the_returned_inventory(self) -> Self:
        if self.returned_object_count != len(self.objects):
            raise ValueError("returned object count disagrees with the object inventory")
        if self.returned_object_count > self.source_object_count:
            raise ValueError("more objects were returned than were selected")
        if self.truncated != (self.returned_object_count < self.source_object_count):
            raise ValueError("truncation flag disagrees with the returned inventory")
        return self
