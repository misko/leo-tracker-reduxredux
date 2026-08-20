"""Compose the archived element sets and the sky science into one report.

This is the seam between infrastructure and pure science.  The archive reader
performs filesystem access and digest verification; :mod:`leo.sky` performs
numerics and knows nothing about where element sets come from.  Neither imports
the other, and this module is the only place they meet.
"""

from __future__ import annotations

from dataclasses import dataclass

from leo.contracts.sky import (
    BeamPointingV1,
    ObserverSiteV1,
    SkyFieldReportV1,
    SkyWindowV1,
    TleSnapshotRefV1,
)
from leo.operations.tle_archive import TleArchiveError, TleArchiveReader, TleSnapshotRef
from leo.sky.propagation import ElementSetError, parse_element_sets, propagate_window
from leo.sky.screening import MAXIMUM_REPORTED_OBJECTS, observe_window, screen_field

# Starlink Ku-band user downlink, lower edge of the channel the capture profiles
# use.  Callers should pass the frequency they actually tuned; this default only
# keeps the CLI usable without one.
DEFAULT_DOWNLINK_FREQUENCY_HZ = 11.7e9


class SkyFieldUnavailableError(RuntimeError):
    """No usable element-set snapshot could be resolved for the request."""


@dataclass(frozen=True, slots=True)
class ResolvedSnapshot:
    """One verified snapshot together with its parsed contents."""

    reference: TleSnapshotRef
    text: str


class SkyFieldService:
    """Answer "what is in this beam, and what Doppler will it impose"."""

    def __init__(
        self,
        archive: TleArchiveReader,
        *,
        maximum_objects: int = MAXIMUM_REPORTED_OBJECTS,
    ) -> None:
        self._archive = archive
        self._maximum_objects = maximum_objects

    def resolve_snapshot(
        self, anchor_utc_ns: int, *, provider: str | None = None
    ) -> ResolvedSnapshot:
        """Resolve, verify and read the snapshot nearest the anchor instant."""

        try:
            reference = self._archive.select_nearest(anchor_utc_ns, provider=provider)
            return ResolvedSnapshot(reference, self._archive.read(reference))
        except TleArchiveError as error:
            raise SkyFieldUnavailableError(str(error)) from error

    def field_report(
        self,
        *,
        observer: ObserverSiteV1,
        pointing: BeamPointingV1,
        window: SkyWindowV1,
        downlink_frequency_hz: float = DEFAULT_DOWNLINK_FREQUENCY_HZ,
        provider: str | None = None,
    ) -> SkyFieldReportV1:
        """Build one bounded, candidate-only field report.

        Raises :class:`SkyFieldUnavailableError` when no snapshot verifies.  An
        unavailable sky is never reported as an empty one.
        """

        resolved = self.resolve_snapshot(window.anchor_utc_ns, provider=provider)
        try:
            catalogue = parse_element_sets(resolved.text)
        except ElementSetError as error:
            raise SkyFieldUnavailableError(
                f"snapshot {resolved.reference.path.name} is not usable: {error}"
            ) from error

        propagated = propagate_window(catalogue, window)
        tracks = observe_window(propagated, observer, window)
        objects, source_count, exclusions = screen_field(
            catalogue,
            propagated,
            tracks,
            pointing=pointing,
            window=window,
            downlink_frequency_hz=downlink_frequency_hz,
            maximum_objects=self._maximum_objects,
        )
        return SkyFieldReportV1(
            observer=observer,
            pointing=pointing,
            window=window,
            snapshot=TleSnapshotRefV1(
                provider=resolved.reference.provider,  # type: ignore[arg-type]
                collected_utc_ns=resolved.reference.collected_utc_ns,
                digest=resolved.reference.digest,
                object_count=len(catalogue),
            ),
            downlink_frequency_hz=downlink_frequency_hz,
            objects=objects,
            source_object_count=source_count,
            returned_object_count=len(objects),
            truncated=len(objects) < source_count,
            exclusions=exclusions,
        )
