from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from leo.contracts.sky import (
    BeamPointingV1,
    DopplerPolynomialV1,
    ObserverSiteV1,
    SkyExclusionsV1,
    SkyFieldReportV1,
    SkyObjectPredictionV1,
    SkyWindowV1,
    TleSnapshotRefV1,
)
from leo.sky.propagation import ElementSetCatalogue, PropagatedWindow
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import (
    ObservedTracks,
    boresight_separation_deg,
    boresight_unit_vector,
    build_predictions,
    classify_coarse,
    summarise_exclusions,
)

KU_BAND_HZ = 11.7e9
ANCHOR_NS = 1_787_238_197_000_000_000
WINDOW = SkyWindowV1(anchor_utc_ns=ANCHOR_NS)
KNOTS = WINDOW.knot_utc_ns()
GRID = SamplingGrid(KNOTS, WINDOW.anchor_index, 30.0)
SITE = ObserverSiteV1(
    latitude_deg=37.858988, longitude_deg=-122.478103, altitude_m=-29.0, label="Spinnaker"
)


def _catalogue(count: int) -> ElementSetCatalogue:
    return ElementSetCatalogue(
        names=tuple(f"STARLINK-{index:04d}" for index in range(count)),
        satellite_numbers=tuple(40_000 + index for index in range(count)),
        satellites=(),
    )


def _propagated(count: int) -> PropagatedWindow:
    shape = (count, len(KNOTS), 3)
    return PropagatedWindow(
        utc_ns=KNOTS,
        position_teme_km=np.zeros(shape),
        velocity_teme_km_s=np.zeros(shape),
        error_code=np.zeros((count, len(KNOTS)), dtype=np.int32),
    )


def _tracks(
    azimuth: list[list[float]],
    elevation: list[list[float]],
    *,
    altitude_km: float | list[float] = 550.0,
    usable: list[bool] | None = None,
) -> ObservedTracks:
    azimuth_array = np.asarray(azimuth, dtype=np.float64)
    elevation_array = np.asarray(elevation, dtype=np.float64)
    count, knots = azimuth_array.shape
    if isinstance(altitude_km, list):
        altitude = np.repeat(np.asarray(altitude_km, dtype=np.float64)[:, None], knots, axis=1)
    else:
        altitude = np.full((count, knots), altitude_km)
    return ObservedTracks(
        azimuth_deg=azimuth_array,
        elevation_deg=elevation_array,
        range_km=np.full((count, knots), 550.0),
        range_rate_km_s=np.linspace(-2.0, 2.0, count * knots).reshape(count, knots),
        altitude_km=altitude,
        usable=np.asarray([True] * count if usable is None else usable, dtype=np.bool_),
        anchor_index=len(KNOTS) // 2,
    )


def _screen(tracks: ObservedTracks, pointing: BeamPointingV1, **kwargs: object):
    """Single-pass screening on an exact grid, for unit-level assertions.

    The service runs a coarse pass plus refinement; these tests exercise the
    decision logic directly with a zero-margin grid.
    """

    count = tracks.azimuth_deg.shape[0]
    catalogue = _catalogue(count)
    grid = SamplingGrid(KNOTS, WINDOW.anchor_index, 1e-9)
    classification = classify_coarse(tracks, pointing, grid)
    selected = classification.definitely_in | classification.ambiguous
    objects = build_predictions(
        catalogue,
        tracks,
        grid,
        indices=np.flatnonzero(selected),
        pointing=pointing,
        downlink_frequency_hz=KU_BAND_HZ,
        element_epoch_utc_ns=tuple(WINDOW.anchor_utc_ns for _ in range(count)),
        **kwargs,  # type: ignore[arg-type]
    )
    return objects, int(selected.sum()), summarise_exclusions(classification, selected)


def test_boresight_unit_vector_points_where_the_angles_say() -> None:
    zenith = boresight_unit_vector(
        BeamPointingV1(boresight_azimuth_deg=0.0, boresight_elevation_deg=90.0, half_angle_deg=5.0)
    )
    assert zenith == pytest.approx([0.0, 0.0, 1.0], abs=1e-12)

    east = boresight_unit_vector(
        BeamPointingV1(boresight_azimuth_deg=90.0, boresight_elevation_deg=0.0, half_angle_deg=5.0)
    )
    assert east == pytest.approx([1.0, 0.0, 0.0], abs=1e-12)

    north = boresight_unit_vector(
        BeamPointingV1(boresight_azimuth_deg=0.0, boresight_elevation_deg=0.0, half_angle_deg=5.0)
    )
    assert north == pytest.approx([0.0, 1.0, 0.0], abs=1e-12)


def test_separation_is_zero_on_boresight_and_grows_correctly() -> None:
    pointing = BeamPointingV1(
        boresight_azimuth_deg=120.0, boresight_elevation_deg=40.0, half_angle_deg=5.0
    )
    separation = boresight_separation_deg(
        np.array([120.0, 120.0, 300.0]), np.array([40.0, 50.0, -40.0]), pointing
    )
    assert float(separation[0]) == pytest.approx(0.0, abs=1e-9)
    assert float(separation[1]) == pytest.approx(10.0, abs=1e-9)
    assert float(separation[2]) == pytest.approx(180.0, abs=1e-9)


def test_separation_crosses_the_north_wrap_correctly() -> None:
    """A naive azimuth difference would call this 358 degrees, not 2."""

    pointing = BeamPointingV1(
        boresight_azimuth_deg=1.0, boresight_elevation_deg=0.0, half_angle_deg=5.0
    )
    separation = boresight_separation_deg(np.array([359.0]), np.array([0.0]), pointing)
    assert float(separation[0]) == pytest.approx(2.0, abs=1e-9)


def test_separation_is_correct_near_the_zenith() -> None:
    """Two objects 1 degree from zenith on opposite sides are 2 degrees apart,
    even though their azimuths differ by 180."""

    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0, boresight_elevation_deg=89.0, half_angle_deg=5.0
    )
    separation = boresight_separation_deg(np.array([180.0]), np.array([89.0]), pointing)
    assert float(separation[0]) == pytest.approx(2.0, abs=1e-9)


def test_the_cone_boundary_is_inclusive() -> None:
    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0, boresight_elevation_deg=45.0, half_angle_deg=3.0
    )
    knots = len(KNOTS)
    tracks = _tracks(
        [[0.0] * knots, [0.0] * knots],
        [[48.0] * knots, [48.000001] * knots],
    )

    predictions, count, exclusions = _screen(tracks, pointing)
    assert count == 1
    assert [item.object_name for item in predictions] == ["STARLINK-0000"]
    assert exclusions.outside_beam == 1


def test_an_object_crossing_the_beam_during_the_window_is_reported() -> None:
    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0, boresight_elevation_deg=45.0, half_angle_deg=2.0
    )
    # Enters the cone only at the final knot; never in beam at the anchor.
    tracks = _tracks([[0.0] * 5], [[60.0, 55.0, 50.0, 48.0, 46.0]])

    predictions, count, _ = _screen(tracks, pointing)
    assert count == 1
    assert predictions[0].within_beam_at_anchor is False
    assert predictions[0].elevation_deg == pytest.approx(50.0)
    assert predictions[0].peak_elevation_deg == pytest.approx(60.0)
    assert predictions[0].minimum_boresight_separation_deg == pytest.approx(1.0, abs=1e-9)


def test_the_horizon_mask_excludes_objects_that_never_rise_above_it() -> None:
    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0,
        boresight_elevation_deg=20.0,
        half_angle_deg=90.0,
        horizon_mask_deg=15.0,
    )
    knots = len(KNOTS)
    tracks = _tracks(
        [[0.0] * knots, [0.0] * knots],
        [[20.0] * knots, [10.0] * knots],
    )

    _, count, exclusions = _screen(tracks, pointing)
    assert count == 1
    assert exclusions.below_horizon_mask == 1


def test_implausible_and_failed_element_sets_are_excluded_and_counted() -> None:
    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0, boresight_elevation_deg=45.0, half_angle_deg=90.0
    )
    knots = len(KNOTS)
    tracks = _tracks(
        [[0.0] * knots] * 3,
        [[45.0] * knots] * 3,
        altitude_km=[550.0, 75.8, 550.0],
        usable=[True, True, False],
    )

    _, count, exclusions = _screen(tracks, pointing)
    assert count == 1
    assert exclusions.implausible_altitude == 1
    assert exclusions.propagation_failed == 1
    assert exclusions.below_horizon_mask == 0
    assert exclusions.outside_beam == 0


def test_every_catalogued_object_is_either_reported_or_accounted_for() -> None:
    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0,
        boresight_elevation_deg=45.0,
        half_angle_deg=4.0,
        horizon_mask_deg=10.0,
    )
    knots = len(KNOTS)
    # One object per outcome: in beam, in beam, outside the cone, below the
    # mask, implausible altitude, propagation failure.
    tracks = _tracks(
        [[0.0] * knots] * 6,
        [
            [45.0] * knots,
            [47.0] * knots,
            [80.0] * knots,
            [5.0] * knots,
            [46.0] * knots,
            [45.0] * knots,
        ],
        altitude_km=[550.0, 550.0, 550.0, 550.0, 90.0, 550.0],
        usable=[True, True, True, True, True, False],
    )

    predictions, count, exclusions = _screen(tracks, pointing)
    assert count == len(predictions) == 2
    assert exclusions.outside_beam == 1
    assert exclusions.below_horizon_mask == 1
    assert exclusions.implausible_altitude == 1
    assert exclusions.propagation_failed == 1
    assert count + exclusions.total == 6


def test_predictions_are_ordered_by_proximity_to_boresight() -> None:
    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0, boresight_elevation_deg=45.0, half_angle_deg=10.0
    )
    knots = len(KNOTS)
    tracks = _tracks(
        [[0.0] * knots] * 3,
        [[52.0] * knots, [45.5] * knots, [48.0] * knots],
    )

    predictions, _, _ = _screen(tracks, pointing)
    separations = [item.minimum_boresight_separation_deg for item in predictions]
    assert separations == sorted(separations)
    assert [item.object_name for item in predictions] == [
        "STARLINK-0001",
        "STARLINK-0002",
        "STARLINK-0000",
    ]


def test_the_reported_inventory_is_bounded_and_reports_the_full_count() -> None:
    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0, boresight_elevation_deg=45.0, half_angle_deg=20.0
    )
    knots = len(KNOTS)
    tracks = _tracks(
        [[0.0] * knots] * 6,
        [[45.0 + index] * knots for index in range(6)],
    )

    predictions, count, _ = _screen(tracks, pointing, maximum_objects=2)
    assert len(predictions) == 2
    assert count == 6

    with pytest.raises(ValueError, match="bound must be positive"):
        _screen(tracks, pointing, maximum_objects=0)


def test_an_empty_beam_is_reported_as_empty_not_as_a_failure() -> None:
    pointing = BeamPointingV1(
        boresight_azimuth_deg=180.0, boresight_elevation_deg=10.0, half_angle_deg=1.0
    )
    knots = len(KNOTS)
    tracks = _tracks([[0.0] * knots], [[80.0] * knots])

    predictions, count, exclusions = _screen(tracks, pointing)
    assert predictions == ()
    assert count == 0
    assert exclusions.outside_beam == 1


def test_report_contract_enforces_agreement_between_counts_and_inventory() -> None:
    snapshot = TleSnapshotRefV1(
        provider="space-track",
        collected_utc_ns=ANCHOR_NS,
        digest="sha256:" + "a" * 64,
        object_count=10_956,
    )
    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0, boresight_elevation_deg=45.0, half_angle_deg=5.0
    )
    base = {
        "observer": SITE,
        "pointing": pointing,
        "window": WINDOW,
        "snapshot": snapshot,
        "downlink_frequency_hz": KU_BAND_HZ,
        "objects": (),
        "exclusions": SkyExclusionsV1(outside_beam=10_956),
        "coarse_sample_count": 61,
        "refined_object_count": 0,
        "boundary_uncertain_count": 0,
        "screening_angular_tolerance_deg": 0.01,
        "collection_age_s": 120.0,
        "maximum_element_age_s": 3_600.0,
        "elements_stale": False,
    }

    report = SkyFieldReportV1(
        **base, source_object_count=0, returned_object_count=0, truncated=False
    )
    assert report.returned_object_count == 0

    with pytest.raises(ValidationError, match="disagrees with the object inventory"):
        SkyFieldReportV1(**base, source_object_count=3, returned_object_count=3, truncated=False)
    with pytest.raises(ValidationError, match="truncation flag disagrees"):
        SkyFieldReportV1(**base, source_object_count=3, returned_object_count=0, truncated=False)
    prediction = SkyObjectPredictionV1(
        object_name="STARLINK-0000",
        catalog_number=40_000,
        azimuth_deg=0.0,
        elevation_deg=45.0,
        range_km=550.0,
        range_rate_km_s=-1.0,
        peak_elevation_deg=45.0,
        minimum_boresight_separation_deg=0.0,
        within_beam_at_anchor=True,
        element_epoch_utc_ns=ANCHOR_NS,
        element_age_s=0.0,
        doppler=DopplerPolynomialV1(
            degree=1,
            reference_utc_ns=ANCHOR_NS,
            downlink_frequency_hz=KU_BAND_HZ,
            frequency_at_reference_hz=39.0,
            slope_hz_s=0.0,
            residual_rms_hz=0.0,
        ),
    )
    with pytest.raises(ValidationError, match="more objects were returned"):
        SkyFieldReportV1(
            **{**base, "objects": (prediction,)},
            source_object_count=0,
            returned_object_count=1,
            truncated=False,
        )


def test_report_contract_requires_every_object_to_be_selected_or_excluded() -> None:
    """A snapshot of 100 objects with nothing selected and nothing excluded is
    not a valid report, however internally consistent its other counts are."""

    snapshot = TleSnapshotRefV1(
        provider="space-track",
        collected_utc_ns=ANCHOR_NS,
        digest="sha256:" + "a" * 64,
        object_count=100,
    )
    base = {
        "observer": SITE,
        "pointing": BeamPointingV1(
            boresight_azimuth_deg=0.0, boresight_elevation_deg=45.0, half_angle_deg=5.0
        ),
        "window": WINDOW,
        "snapshot": snapshot,
        "downlink_frequency_hz": KU_BAND_HZ,
        "objects": (),
        "source_object_count": 0,
        "returned_object_count": 0,
        "truncated": False,
        "coarse_sample_count": 61,
        "refined_object_count": 0,
        "boundary_uncertain_count": 0,
        "screening_angular_tolerance_deg": 0.01,
        "collection_age_s": 0.0,
        "maximum_element_age_s": 0.0,
        "elements_stale": False,
    }

    with pytest.raises(ValidationError, match="do not account for the snapshot inventory"):
        SkyFieldReportV1(**base, exclusions=SkyExclusionsV1())

    accounted = SkyFieldReportV1(**base, exclusions=SkyExclusionsV1(below_horizon_mask=100))
    assert accounted.exclusions.total == 100


def test_report_contract_requires_the_stale_flag_to_match_the_age() -> None:
    snapshot = TleSnapshotRefV1(
        provider="space-track",
        collected_utc_ns=ANCHOR_NS,
        digest="sha256:" + "a" * 64,
        object_count=1,
    )
    base = {
        "observer": SITE,
        "pointing": BeamPointingV1(
            boresight_azimuth_deg=0.0, boresight_elevation_deg=45.0, half_angle_deg=5.0
        ),
        "window": WINDOW,
        "snapshot": snapshot,
        "downlink_frequency_hz": KU_BAND_HZ,
        "objects": (),
        "source_object_count": 0,
        "returned_object_count": 0,
        "truncated": False,
        "exclusions": SkyExclusionsV1(below_horizon_mask=1),
        "coarse_sample_count": 61,
        "refined_object_count": 0,
        "boundary_uncertain_count": 0,
        "screening_angular_tolerance_deg": 0.01,
        "collection_age_s": 0.0,
    }

    fresh = SkyFieldReportV1(**base, maximum_element_age_s=3_600.0, elements_stale=False)
    assert fresh.elements_stale is False

    stale = SkyFieldReportV1(**base, maximum_element_age_s=200_000.0, elements_stale=True)
    assert stale.elements_stale is True

    with pytest.raises(ValidationError, match="stale flag disagrees"):
        SkyFieldReportV1(**base, maximum_element_age_s=200_000.0, elements_stale=False)
