"""Regressions for defects found in review of the sky core.

Each test encodes a specific way the first implementation was wrong, so the
behaviour cannot silently return.
"""

from __future__ import annotations

import numpy as np
import pytest

from leo.contracts.sky import BeamPointingV1, SkyWindowV1
from leo.sky.propagation import ElementSetError, element_line_checksum, parse_element_sets
from leo.sky.sampling import (
    MAX_ANGULAR_RATE_DEG_S,
    achieved_tolerance_deg,
    candidate_margin_deg,
    coarse_grid,
    refinement_grid,
)
from leo.sky.screening import ObservedTracks, eligible_at_each_sample
from tests.sky.test_screening import KNOTS, WINDOW, _screen

KU_BAND_HZ = 11.7e9


def _tracks_from(elevation: list[float], azimuth: list[float] | None = None) -> ObservedTracks:
    elevation_array = np.asarray([elevation], dtype=np.float64)
    azimuth_array = np.asarray([azimuth or [0.0] * len(elevation)], dtype=np.float64)
    knots = elevation_array.shape[1]
    return ObservedTracks(
        azimuth_deg=azimuth_array,
        elevation_deg=elevation_array,
        range_km=np.full((1, knots), 550.0),
        range_rate_km_s=np.zeros((1, knots)),
        altitude_km=np.full((1, knots), 550.0),
        usable=np.asarray([True]),
        anchor_index=knots // 2,
    )


def test_beam_and_mask_eligibility_must_hold_at_the_same_instant() -> None:
    """The object below is inside the cone only while it is below the horizon
    mask, and above the mask only once it has left the cone.  It is never
    observable, and taking the peak elevation and the minimum separation
    independently would have selected it anyway."""

    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0,
        boresight_elevation_deg=8.0,
        half_angle_deg=10.0,
        horizon_mask_deg=10.0,
    )
    tracks = _tracks_from([5.0, 5.0, 5.0, 5.0, 40.0])

    objects, selected, exclusions = _screen(tracks, pointing)

    assert objects == ()
    assert selected == 0
    assert exclusions.outside_beam == 1


def test_simultaneous_eligibility_is_still_selected() -> None:
    """The counterpart: in the cone and above the mask at the same knot."""

    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0,
        boresight_elevation_deg=8.0,
        half_angle_deg=10.0,
        horizon_mask_deg=10.0,
    )
    tracks = _tracks_from([5.0, 5.0, 14.0, 5.0, 40.0])

    objects, selected, _ = _screen(tracks, pointing)

    assert selected == 1
    assert objects[0].minimum_boresight_separation_deg == pytest.approx(6.0, abs=1e-9)


def test_reported_separation_is_the_closest_observable_approach() -> None:
    """A closer pass that happens below the mask must not be reported as the
    closest approach, because the antenna could not have seen it."""

    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0,
        boresight_elevation_deg=8.0,
        half_angle_deg=10.0,
        horizon_mask_deg=10.0,
    )
    # Knot 0 sits exactly on boresight but below the mask; knot 2 is observable.
    tracks = _tracks_from([8.0, 5.0, 14.0, 5.0, 5.0])

    objects, selected, _ = _screen(tracks, pointing)

    assert selected == 1
    assert objects[0].minimum_boresight_separation_deg == pytest.approx(6.0, abs=1e-9)


@pytest.mark.parametrize("half_angle_deg", (0.05, 0.5, 1.0, 3.0, 5.0, 20.0, 90.0))
def test_the_candidate_margin_covers_everything_sampling_can_miss(
    half_angle_deg: float,
) -> None:
    """Sampling cannot decide membership, so the coarse pass must not try.

    Between two samples the look direction moves at most ``rate * spacing``, so
    relaxing the cone by half that cannot exclude an object that was inside it
    in between -- however brief the chord.
    """

    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0,
        boresight_elevation_deg=45.0,
        half_angle_deg=half_angle_deg,
    )
    grid = coarse_grid(WINDOW, pointing)
    margin = candidate_margin_deg(grid)
    assert margin == pytest.approx(MAX_ANGULAR_RATE_DEG_S * grid.spacing_s / 2.0)
    # Worst-case movement between two samples, fully covered by two margins.
    assert 2.0 * margin >= MAX_ANGULAR_RATE_DEG_S * grid.spacing_s - 1e-12


def test_a_grazing_chord_survives_the_coarse_pass() -> None:
    """A pass whose closest approach is 2.99 deg against a 3.00 deg cone is
    inside for about a third of a second.  Sampling steps over it; the margin
    must still keep it as a candidate for the fine pass to decide."""

    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0, boresight_elevation_deg=45.0, half_angle_deg=3.0
    )
    grid = coarse_grid(WINDOW, pointing)
    margin = candidate_margin_deg(grid)
    closest_sampled = 3.0134  # measured worst-case phase for this grid

    assert closest_sampled > pointing.half_angle_deg, "sampling alone misses it"
    assert closest_sampled <= pointing.half_angle_deg + margin, "the margin retains it"


def test_the_refinement_grid_bounds_the_decision_error() -> None:
    """The grid is capped, so the achieved tolerance is reported rather than
    assumed -- but it must still be far below any usable beam width."""

    grid = refinement_grid(WINDOW)
    assert achieved_tolerance_deg(grid) <= 0.05
    assert len(grid) % 2 == 1
    assert grid.utc_ns[grid.anchor_index] == WINDOW.anchor_utc_ns


def test_a_wide_beam_does_not_demand_needless_coarse_resolution() -> None:
    """A wide beam still needs a bounded margin: too coarse a grid inflates the
    cone so far that most of the sky becomes ambiguous and must be refined."""

    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0, boresight_elevation_deg=90.0, half_angle_deg=90.0
    )
    grid = coarse_grid(WINDOW, pointing)
    assert len(grid) <= 51
    assert candidate_margin_deg(grid) <= 4.0


def _valid(line: str) -> str:
    return f"{line[:68]}{element_line_checksum(line)}"


VALID_PAIR = (
    _valid("1 44714U 19074B   26232.62719907  .00001103  00000-0  92799-4 0  9995"),
    _valid("2 44714  53.0537 172.0234 0001334  87.1234 273.0021 15.06393004260123"),
)


def test_the_reference_pair_is_accepted() -> None:
    catalogue = parse_element_sets("\n".join(VALID_PAIR))
    assert len(catalogue) == 1
    assert catalogue.satellite_numbers == (44714,)


def test_a_corrupted_checksum_is_rejected() -> None:
    first, second = VALID_PAIR
    broken = first[:68] + ("0" if first[68] != "0" else "1")
    with pytest.raises(ElementSetError, match="fails its checksum"):
        parse_element_sets("\n".join((broken, second)))


def test_a_short_or_long_line_is_rejected() -> None:
    first, second = VALID_PAIR
    with pytest.raises(ElementSetError, match="characters, expected 69"):
        parse_element_sets("\n".join((first[:60], second)))
    with pytest.raises(ElementSetError, match="characters, expected 69"):
        parse_element_sets("\n".join((first + "0", second)))


def test_lines_naming_different_catalogue_objects_are_rejected() -> None:
    """sgp4's own parser accepts this; the mismatch has to be caught here."""

    first, second = VALID_PAIR
    renumbered = _valid("2 44715" + second[7:])
    assert int(renumbered[68]) == element_line_checksum(renumbered)
    with pytest.raises(ElementSetError, match="different catalogue objects"):
        parse_element_sets("\n".join((first, renumbered)))


def test_a_non_numeric_checksum_is_rejected() -> None:
    first, second = VALID_PAIR
    with pytest.raises(ElementSetError, match="non-numeric checksum"):
        parse_element_sets("\n".join((first[:68] + "X", second)))


def test_an_odd_sample_count_is_required_so_the_anchor_is_always_sampled() -> None:
    window = SkyWindowV1(anchor_utc_ns=KNOTS[len(KNOTS) // 2], sample_count=5)
    assert window.knot_utc_ns()[window.anchor_index] == window.anchor_utc_ns


def test_a_selected_object_never_reports_an_infinite_separation() -> None:
    """An object selected on a fine grid can have no eligible sample on the
    grid it is reported from.  The closest-observable reduction must stay
    finite rather than producing an infinity the contract refuses."""

    from leo.sky.propagation import ElementSetCatalogue
    from leo.sky.screening import build_predictions

    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0, boresight_elevation_deg=45.0, half_angle_deg=3.0
    )
    grid = coarse_grid(WINDOW, pointing)
    samples = len(grid)
    tracks = ObservedTracks(
        azimuth_deg=np.zeros((1, samples)),
        elevation_deg=np.full((1, samples), 70.0),  # far outside the cone at every sample
        range_km=np.full((1, samples), 550.0),
        range_rate_km_s=np.zeros((1, samples)),
        altitude_km=np.full((1, samples), 550.0),
        usable=np.asarray([True]),
        anchor_index=grid.anchor_index,
    )
    assert not eligible_at_each_sample(tracks, pointing).any()

    objects = build_predictions(
        ElementSetCatalogue(("SAT",), (40_000,), ()),
        tracks,
        grid,
        indices=np.asarray([0]),
        pointing=pointing,
        downlink_frequency_hz=KU_BAND_HZ,
        element_epoch_utc_ns=(WINDOW.anchor_utc_ns,),
    )

    assert len(objects) == 1
    assert np.isfinite(objects[0].minimum_boresight_separation_deg)


def test_a_decision_inside_the_resolution_band_is_flagged_not_guessed() -> None:
    """A fine sample landing at 3.00004 deg against a 3 deg cone is not
    evidence the object was outside; the residual error is bounded by the
    achieved tolerance, so the object is retained and marked uncertain."""

    from leo.sky.propagation import ElementSetCatalogue
    from leo.sky.screening import build_predictions

    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0, boresight_elevation_deg=45.0, half_angle_deg=3.0
    )
    grid = refinement_grid(WINDOW)
    tolerance = achieved_tolerance_deg(grid)
    samples = len(grid)
    # Sits just outside the cone by far less than the tolerance.
    tracks = ObservedTracks(
        azimuth_deg=np.zeros((1, samples)),
        elevation_deg=np.full((1, samples), 45.0 + 3.00004),
        range_km=np.full((1, samples), 550.0),
        range_rate_km_s=np.zeros((1, samples)),
        altitude_km=np.full((1, samples), 550.0),
        usable=np.asarray([True]),
        anchor_index=grid.anchor_index,
    )

    assert not eligible_at_each_sample(tracks, pointing).any(), "exact test calls it outside"
    assert eligible_at_each_sample(tracks, pointing, margin_deg=tolerance).any()

    objects = build_predictions(
        ElementSetCatalogue(("SAT",), (40_000,), ()),
        tracks,
        grid,
        indices=np.asarray([0]),
        pointing=pointing,
        downlink_frequency_hz=KU_BAND_HZ,
        element_epoch_utc_ns=(WINDOW.anchor_utc_ns,),
        eligibility_margin_deg=tolerance,
    )
    assert objects[0].boundary_uncertain is True


def test_a_future_element_epoch_is_as_old_as_an_equally_distant_past_one() -> None:
    """Age is a magnitude.  An element set dated after the observation is
    propagated backwards and is no more trustworthy."""

    from leo.sky.propagation import ElementSetCatalogue
    from leo.sky.screening import build_predictions

    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0, boresight_elevation_deg=45.0, half_angle_deg=10.0
    )
    grid = coarse_grid(WINDOW, pointing)
    samples = len(grid)
    tracks = ObservedTracks(
        azimuth_deg=np.zeros((1, samples)),
        elevation_deg=np.full((1, samples), 45.0),
        range_km=np.full((1, samples), 550.0),
        range_rate_km_s=np.zeros((1, samples)),
        altitude_km=np.full((1, samples), 550.0),
        usable=np.asarray([True]),
        anchor_index=grid.anchor_index,
    )
    two_days_ns = 2 * 86_400 * 1_000_000_000

    for epoch in (WINDOW.anchor_utc_ns + two_days_ns, WINDOW.anchor_utc_ns - two_days_ns):
        objects = build_predictions(
            ElementSetCatalogue(("SAT",), (40_000,), ()),
            tracks,
            grid,
            indices=np.asarray([0]),
            pointing=pointing,
            downlink_frequency_hz=KU_BAND_HZ,
            element_epoch_utc_ns=(epoch,),
        )
        assert objects[0].element_age_s == pytest.approx(2 * 86_400.0)
