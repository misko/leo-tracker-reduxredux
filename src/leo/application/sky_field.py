"""Compose the archived element sets and the sky science into one report.

This is the seam between infrastructure and pure science.  The archive reader
performs filesystem access and digest verification; :mod:`leo.sky` performs
numerics and knows nothing about where element sets come from.  Neither imports
the other, and this module is the only place they meet.

Screening runs in two passes.  A coarse pass over the whole catalogue splits it
into definitely-in, definitely-out and ambiguous using a margin derived from the
sampling spacing, so no transit can be missed however brief.  A fine pass then
re-evaluates only the ambiguous band, which keeps the cost proportional to the
objects whose membership is genuinely in question.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from leo.contracts.sky import (
    MAXIMUM_FRESH_ELEMENT_AGE_S,
    MAXIMUM_REPORT_OBJECTS,
    BeamPointingV1,
    ObserverSiteV1,
    SkyFieldReportV1,
    SkyObjectPredictionV1,
    SkyWindowV1,
    TleSnapshotRefV1,
)
from leo.operations.tle_archive import TleArchiveError, TleArchiveReader, TleSnapshotRef
from leo.sky.propagation import ElementSetError, parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid, achieved_tolerance_deg, coarse_grid, refinement_grid
from leo.sky.screening import (
    MAXIMUM_REPORTED_OBJECTS,
    ObservedTracks,
    boresight_separation_deg,
    build_predictions,
    classify_coarse,
    eligible_at_each_sample,
    observe_grid,
    summarise_exclusions,
)

# Starlink Ku-band user downlink, lower edge of the channel the capture profiles
# use.  Callers should pass the frequency they actually tuned; this default only
# keeps the CLI usable without one.
DEFAULT_DOWNLINK_FREQUENCY_HZ = 11.7e9

# Ambiguous objects are refined in batches so peak memory stays bounded no
# matter how many of them a wide beam produces.
_REFINEMENT_BATCH = 32


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
        if not 1 <= maximum_objects <= MAXIMUM_REPORT_OBJECTS:
            # The report contract caps its inventory, so a service configured
            # above that bound would build reports that fail validation only at
            # the very end.  Fail at construction instead.
            raise ValueError(f"maximum_objects must be between 1 and {MAXIMUM_REPORT_OBJECTS}")
        self._archive = archive
        self._maximum_objects = maximum_objects

    @staticmethod
    def _closest_first(
        indices: np.ndarray,
        tracks: ObservedTracks,
        grid: SamplingGrid,
        pointing: BeamPointingV1,
    ) -> list[int]:
        """Order selected objects by coarse proximity, so truncation keeps the
        ones the antenna is most nearly pointed at.

        Coarse separation is only an ordering key; every reported number is
        recomputed on the fine grid.
        """

        del grid
        separation = boresight_separation_deg(
            tracks.azimuth_deg, tracks.elevation_deg, pointing
        ).min(axis=1)
        return sorted((int(index) for index in indices), key=lambda i: (float(separation[i]), i))

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

        epochs = catalogue.element_epoch_utc_ns()
        coarse = coarse_grid(window, pointing)
        coarse_tracks = observe_grid(propagate_grid(catalogue, coarse), observer, coarse)
        classification = classify_coarse(coarse_tracks, pointing, coarse)

        fine = refinement_grid(window)
        tolerance = achieved_tolerance_deg(fine)
        selected = classification.definitely_in.copy()
        fine_failures = np.zeros_like(selected)
        ambiguous = classification.needs_refinement
        if ambiguous.size:
            for start in range(0, ambiguous.size, _REFINEMENT_BATCH):
                batch = [int(index) for index in ambiguous[start : start + _REFINEMENT_BATCH]]
                tracks = observe_grid(
                    propagate_grid(catalogue, fine, indices=batch), observer, fine
                )
                # The fine pass is still discrete.  Its residual error is bounded
                # by the achieved tolerance, so a decision inside that band is
                # not knowledge; the object is retained and flagged rather than
                # ruled out by whichever way the sample happened to land.
                eligible = eligible_at_each_sample(tracks, pointing, margin_deg=tolerance).any(
                    axis=1
                )
                for row, index in enumerate(batch):
                    if not tracks.usable[row]:
                        # The orbit could not be computed at this resolution.
                        # That is a propagation failure, not evidence about
                        # where the object was.
                        fine_failures[index] = True
                        selected[index] = False
                        continue
                    selected[index] = bool(eligible[row])

        source_count = int(selected.sum())
        # Report every selected object from the fine grid.  An object selected
        # there may have no eligible coarse sample at all, and reporting it from
        # the coarse track would yield an infinite closest approach.
        chosen = self._closest_first(np.flatnonzero(selected), coarse_tracks, coarse, pointing)[
            : self._maximum_objects
        ]
        objects: tuple[SkyObjectPredictionV1, ...] = ()
        if chosen:
            reported = observe_grid(propagate_grid(catalogue, fine, indices=chosen), observer, fine)
            objects = build_predictions(
                catalogue,
                reported,
                fine,
                indices=np.asarray(chosen),
                pointing=pointing,
                downlink_frequency_hz=downlink_frequency_hz,
                element_epoch_utc_ns=epochs,
                row_of={index: row for row, index in enumerate(chosen)},
                maximum_objects=self._maximum_objects,
                eligibility_margin_deg=tolerance,
            )
        exclusions = summarise_exclusions(
            classification, selected, additional_failures=fine_failures
        )

        anchor_ns = window.anchor_utc_ns
        collection_age_s = abs(anchor_ns - resolved.reference.collected_utc_ns) / 1e9
        # The age that matters is the age of the elements behind the reported
        # objects.  A catalogue-wide maximum would be dominated by whatever the
        # provider's own query window admits and would say nothing about this
        # answer.
        # Absolute in both branches: an element set dated after the observation
        # is no more trustworthy than an equally old one, and a signed age here
        # produced a negative value the contract rightly refuses.
        maximum_element_age_s = (
            max(item.element_age_s for item in objects)
            if objects
            else max(abs(anchor_ns - epoch) / 1e9 for epoch in epochs)
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
            coarse_sample_count=len(coarse),
            refined_object_count=int(ambiguous.size),
            boundary_uncertain_count=sum(1 for item in objects if item.boundary_uncertain),
            screening_angular_tolerance_deg=tolerance,
            collection_age_s=collection_age_s,
            maximum_element_age_s=maximum_element_age_s,
            elements_stale=maximum_element_age_s > MAXIMUM_FRESH_ELEMENT_AGE_S,
        )
