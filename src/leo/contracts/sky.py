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
