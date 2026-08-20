"""Component tests driving SkyFieldService.field_report through its error paths.

The unit tests around screening exercise the decision logic in isolation with
hand-built tracks.  These drive the whole service against synthetic catalogues
so that failure filtering, exclusion accounting, truncation and backfill are
covered where they actually run -- which is where the last several defects were
found.

Most failing element sets here fail inside sgp4 for a real reason (a decayed
orbit, or a negative semi-latus rectum).  The final-pass-only regression uses a
controlled propagator because an element must succeed at every coarse instant
and fail only at an additional fine instant -- the precise service branch the
real decayed fixtures cannot reach.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

import leo.application.sky_field as sky_field_module
from leo.application.sky_field import SkyFieldService
from leo.contracts.sky import BeamPointingV1, ObserverSiteV1, SkyWindowV1
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import element_line_checksum
from leo.sky.screening import CoarseClassification, ObservedTracks

ANCHOR_NS = 1_787_238_197_000_000_000
EQUATOR = ObserverSiteV1(latitude_deg=0.0, longitude_deg=0.0, altitude_m=0.0, label="equator")
WHOLE_SKY = BeamPointingV1(
    boresight_azimuth_deg=0.0,
    boresight_elevation_deg=90.0,
    half_angle_deg=90.0,
    horizon_mask_deg=0.0,
)


def _seal(line: str) -> str:
    return f"{line[:68]}{element_line_checksum(line)}"


# A near-equatorial 510 km orbit keeps the ground track on the equator, and
# mean anomalies around 130 deg place it over an observer at (0, 0) at the
# anchor instant.  Spreading a few degrees either side gives a handful of
# genuinely visible objects at a range of elevations, which is what the
# selection and ranking paths need to exercise.
_VISIBLE_MEAN_ANOMALY_DEG = 130.0


def _healthy(catalog_number: int, mean_anomaly_offset_deg: float) -> str:
    """A plausible circular low-Earth element set, visible from the equator."""

    mean_anomaly = (_VISIBLE_MEAN_ANOMALY_DEG + mean_anomaly_offset_deg) % 360.0
    return (
        _seal(
            f"1 {catalog_number:05d}U 26232A   26232.50000000  .00000100  00000-0  10000-4 0  9990"
        )
        + "\n"
        + _seal(
            f"2 {catalog_number:05d}   0.5000   0.0000 0001000"
            f"  87.0000 {mean_anomaly:8.4f} 15.20000000260120"
        )
        + "\n"
    )


def _decayed(catalog_number: int) -> str:
    """An element set sgp4 refuses to propagate: the orbit has decayed."""

    return (
        _seal(
            f"1 {catalog_number:05d}U 26232A   26232.50000000  .90000000  00000-0  99999-3 0  9990"
        )
        + "\n"
        + _seal(
            f"2 {catalog_number:05d}  53.0000 172.0000 0001000  87.0000 273.0000 17.90000000260120"
        )
        + "\n"
    )


def _archive(root: Path, payload: str) -> Path:
    directory = root / "archive" / "space-track"
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    (directory / f"{ANCHOR_NS}-{digest}.tle").write_text(payload)
    return root


def _report(root: Path, *, maximum_objects: int = 512):
    service = SkyFieldService(TleArchiveReader(root), maximum_objects=maximum_objects)
    return service.field_report(
        observer=EQUATOR,
        pointing=WHOLE_SKY,
        window=SkyWindowV1(anchor_utc_ns=ANCHOR_NS),
    )


def test_a_catalogue_of_healthy_elements_reports_and_accounts_them(tmp_path: Path) -> None:
    payload = "".join(_healthy(40_000 + index, index * 0.5 - 3.0) for index in range(12))
    report = _report(_archive(tmp_path, payload))

    assert report.snapshot.object_count == 12
    assert report.source_object_count + report.exclusions.total == 12
    assert report.exclusions.propagation_failed == 0


def test_propagation_failures_are_accounted_not_charged_to_the_beam(tmp_path: Path) -> None:
    """The whole point of the four exclusion buckets is that a failure to
    compute is never reported as a fact about where the object was."""

    payload = "".join(_healthy(40_000 + index, index * 0.8 - 2.0) for index in range(6))
    payload += "".join(_decayed(50_000 + index) for index in range(3))
    report = _report(_archive(tmp_path, payload))

    assert report.snapshot.object_count == 9
    assert report.exclusions.propagation_failed == 3
    assert report.source_object_count + report.exclusions.total == 9
    reported_numbers = {item.catalog_number for item in report.objects}
    assert not any(number >= 50_000 for number in reported_numbers)


def test_a_report_full_of_unusable_elements_is_empty_but_complete(tmp_path: Path) -> None:
    payload = "".join(_decayed(50_000 + index) for index in range(5))
    report = _report(_archive(tmp_path, payload))

    assert report.objects == ()
    assert report.returned_object_count == 0
    assert report.exclusions.propagation_failed == 5
    assert report.source_object_count + report.exclusions.total == 5


def test_truncation_backfills_past_a_failure_rather_than_returning_short(
    tmp_path: Path,
) -> None:
    """A failure inside the first N must be replaced from the candidates behind
    it, not silently reduce the returned count below the limit."""

    healthy = "".join(_healthy(40_000 + index, index * 0.6 - 2.0) for index in range(8))
    failing = _decayed(50_000)
    report = _report(_archive(tmp_path, healthy + failing), maximum_objects=4)

    assert report.snapshot.object_count == 9
    assert report.returned_object_count == 4, "the limit is filled despite the failure"
    assert all(item.catalog_number < 50_000 for item in report.objects)
    assert report.truncated is True
    assert report.source_object_count + report.exclusions.total == 9


def test_the_limit_is_filled_when_a_failure_sits_at_the_boundary(tmp_path: Path) -> None:
    """One usable candidate beyond the limit, and one failure inside it: the
    report must still return exactly the limit."""

    payload = "".join(_healthy(40_000 + index, index * 0.7 - 1.5) for index in range(5))
    payload += _decayed(50_000)
    report = _report(_archive(tmp_path, payload), maximum_objects=5)

    usable = 5
    assert report.snapshot.object_count == 6
    assert report.returned_object_count == min(usable, 5)
    assert report.exclusions.propagation_failed == 1
    assert report.source_object_count + report.exclusions.total == 6


def test_final_only_failure_backfills_from_beyond_the_geometry_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fine failure backfill must retain the full ranked candidate queue.

    The sixth object's score is well outside the initial geometry-widened pool.
    It is still the required replacement when the leading object fails only on
    the final grid.
    """

    count = 6
    scores = np.asarray([0.0, 1.0, 2.0, 3.0, 4.0, 20.0])
    pointing = BeamPointingV1(
        boresight_azimuth_deg=0.0,
        boresight_elevation_deg=45.0,
        half_angle_deg=30.0,
        horizon_mask_deg=0.0,
    )

    def fake_propagate(_catalogue, grid, indices=None):  # type: ignore[no-untyped-def]
        return grid, None if indices is None else tuple(indices)

    def fake_observe(propagated, _observer, grid):  # type: ignore[no-untyped-def]
        indices = list(range(count)) if propagated[1] is None else list(propagated[1])
        rows = len(indices)
        samples = len(grid)
        elevation = np.asarray(
            [[45.0 + scores[index]] * samples for index in indices], dtype=np.float64
        )
        # Only catalogue object zero fails, and only on a propagation restricted
        # to candidates -- the final fine pass in this all-definitely-in case.
        usable = np.asarray(
            [not (propagated[1] is not None and index == 0) for index in indices],
            dtype=np.bool_,
        )
        return ObservedTracks(
            azimuth_deg=np.zeros((rows, samples)),
            elevation_deg=elevation,
            range_km=np.full((rows, samples), 550.0),
            range_rate_km_s=np.zeros((rows, samples)),
            altitude_km=np.full((rows, samples), 550.0),
            usable=usable,
            anchor_index=grid.anchor_index,
        )

    def fake_classification(_tracks, _pointing, _grid):  # type: ignore[no-untyped-def]
        yes = np.ones(count, dtype=np.bool_)
        no = np.zeros(count, dtype=np.bool_)
        return CoarseClassification(
            definitely_in=yes,
            ambiguous=no,
            plausible=yes,
            ever_near_mask=yes,
            propagation_ok=yes,
            margin_deg=1.0,
        )

    monkeypatch.setattr(sky_field_module, "propagate_grid", fake_propagate)
    monkeypatch.setattr(sky_field_module, "observe_grid", fake_observe)
    monkeypatch.setattr(sky_field_module, "classify_coarse", fake_classification)

    payload = "".join(_healthy(40_000 + index, 0.0) for index in range(count))
    service = SkyFieldService(TleArchiveReader(_archive(tmp_path, payload)), maximum_objects=5)
    report = service.field_report(
        observer=EQUATOR,
        pointing=pointing,
        window=SkyWindowV1(anchor_utc_ns=ANCHOR_NS),
    )

    assert report.returned_object_count == 5
    assert [item.catalog_number for item in report.objects] == [
        40_001,
        40_002,
        40_003,
        40_004,
        40_005,
    ]
    assert report.exclusions.propagation_failed == 1
    assert report.source_object_count == 5
    assert report.truncated is False
    assert report.source_object_count + report.exclusions.total == count


def test_accounting_closes_for_every_maximum_object_bound(tmp_path: Path) -> None:
    payload = "".join(_healthy(40_000 + index, index * 0.5 - 2.0) for index in range(10))
    payload += "".join(_decayed(50_000 + index) for index in range(2))
    root = _archive(tmp_path, payload)

    for bound in (1, 2, 5, 11, 512):
        report = _report(root, maximum_objects=bound)
        assert report.source_object_count + report.exclusions.total == 12
        assert report.returned_object_count == len(report.objects)
        assert report.returned_object_count <= bound
        assert report.truncated == (report.returned_object_count < report.source_object_count)
        assert report.boundary_uncertain_count == sum(
            1 for item in report.objects if item.boundary_uncertain
        )


def test_every_reported_object_carries_finite_geometry_and_doppler(tmp_path: Path) -> None:
    import math

    payload = "".join(_healthy(40_000 + index, index * 0.9 - 2.0) for index in range(6))
    payload += _decayed(50_000)
    report = _report(_archive(tmp_path, payload))

    assert report.objects
    for item in report.objects:
        assert math.isfinite(item.minimum_boresight_separation_deg)
        assert math.isfinite(item.range_km) and item.range_km > 0.0
        assert math.isfinite(item.doppler.frequency_at_reference_hz)
        assert math.isfinite(item.doppler.residual_rms_hz)
        assert item.element_age_s >= 0.0


@pytest.mark.parametrize("bound", (1, 3))
def test_ranking_is_stable_under_truncation(tmp_path: Path, bound: int) -> None:
    """The objects a smaller limit keeps must be a prefix of what a larger one
    keeps, or truncation is not selecting the closest."""

    payload = "".join(_healthy(40_000 + index, index * 0.6 - 2.0) for index in range(8))
    root = _archive(tmp_path, payload)

    full = [item.catalog_number for item in _report(root, maximum_objects=8).objects]
    limited = [item.catalog_number for item in _report(root, maximum_objects=bound).objects]
    assert limited == full[: len(limited)]
