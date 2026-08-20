from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from leo.application.sky_field import SkyFieldService, SkyFieldUnavailableError
from leo.contracts.sky import BeamPointingV1, ObserverSiteV1, SkyFieldReportV1, SkyWindowV1
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.sites import resolve_preset

ANCHOR_NS = 1_787_238_197_000_000_000
KU_BAND_HZ = 11.7e9

# Two real Starlink element sets, retained verbatim so the geometry below is
# reproducible without reaching for the machine's collected archive.
ELEMENT_SETS = (
    "0 STARLINK-1008\n"
    "1 44714U 19074B   26232.62719907  .00001103  00000-0  92799-4 0  9995\n"
    "2 44714  53.0537 172.0234 0001334  87.1234 273.0021 15.06393004260123\n"
    "0 STARLINK-1010\n"
    "1 44716U 19074D   26232.55555556  .00000998  00000-0  85000-4 0  9990\n"
    "2 44716  53.0541  10.4321 0001500  95.0000 265.1234 15.06400000260130\n"
)


def _archive(root: Path, collected_utc_ns: int = ANCHOR_NS, payload: str = ELEMENT_SETS) -> Path:
    directory = root / "archive" / "space-track"
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    (directory / f"{collected_utc_ns}-{digest}.tle").write_text(payload)
    return root


def _service(root: Path, **kwargs: int) -> SkyFieldService:
    return SkyFieldService(TleArchiveReader(root), **kwargs)  # type: ignore[arg-type]


def _whole_sky() -> BeamPointingV1:
    return BeamPointingV1(
        boresight_azimuth_deg=0.0,
        boresight_elevation_deg=90.0,
        half_angle_deg=90.0,
        horizon_mask_deg=0.0,
    )


def test_report_is_reproducible_and_records_its_exact_snapshot(tmp_path: Path) -> None:
    service = _service(_archive(tmp_path))
    site = resolve_preset("spinnaker-sausalito")
    observer = ObserverSiteV1(
        latitude_deg=site.latitude_deg,
        longitude_deg=site.longitude_deg,
        altitude_m=site.altitude_m,
        label=site.label,
    )
    window = SkyWindowV1(anchor_utc_ns=ANCHOR_NS)

    first = service.field_report(observer=observer, pointing=_whole_sky(), window=window)
    second = service.field_report(observer=observer, pointing=_whole_sky(), window=window)

    assert first == second
    assert first.snapshot.provider == "space-track"
    assert first.snapshot.collected_utc_ns == ANCHOR_NS
    assert first.snapshot.object_count == 2
    assert first.snapshot.digest.startswith("sha256:")
    # Every catalogued object is either reported or explained.
    assert first.returned_object_count + first.exclusions.total == first.snapshot.object_count


def test_report_round_trips_through_its_own_contract(tmp_path: Path) -> None:
    service = _service(_archive(tmp_path))
    report = service.field_report(
        observer=ObserverSiteV1(
            latitude_deg=37.858988, longitude_deg=-122.478103, altitude_m=-29.0, label="Spinnaker"
        ),
        pointing=_whole_sky(),
        window=SkyWindowV1(anchor_utc_ns=ANCHOR_NS),
    )

    reloaded = SkyFieldReportV1.model_validate_json(report.model_dump_json())
    assert reloaded == report


def test_a_narrow_beam_pointed_away_returns_an_empty_but_accounted_report(
    tmp_path: Path,
) -> None:
    service = _service(_archive(tmp_path))
    report = service.field_report(
        observer=ObserverSiteV1(
            latitude_deg=37.858988, longitude_deg=-122.478103, altitude_m=-29.0, label="Spinnaker"
        ),
        pointing=BeamPointingV1(
            boresight_azimuth_deg=0.0, boresight_elevation_deg=1.0, half_angle_deg=0.5
        ),
        window=SkyWindowV1(anchor_utc_ns=ANCHOR_NS),
    )

    assert report.objects == ()
    assert report.returned_object_count == 0
    assert report.truncated is False
    assert report.exclusions.total == report.snapshot.object_count


def test_the_reported_inventory_is_bounded_and_flags_truncation(tmp_path: Path) -> None:
    service = _service(_archive(tmp_path), maximum_objects=1)
    report = service.field_report(
        observer=ObserverSiteV1(
            latitude_deg=0.0, longitude_deg=0.0, altitude_m=0.0, label="equator"
        ),
        pointing=_whole_sky(),
        window=SkyWindowV1(anchor_utc_ns=ANCHOR_NS),
    )

    assert report.returned_object_count <= 1
    assert report.truncated == (report.returned_object_count < report.source_object_count)


def test_doppler_is_present_and_physically_scaled(tmp_path: Path) -> None:
    service = _service(_archive(tmp_path))
    report = service.field_report(
        observer=ObserverSiteV1(
            latitude_deg=0.0, longitude_deg=0.0, altitude_m=0.0, label="equator"
        ),
        pointing=_whole_sky(),
        window=SkyWindowV1(anchor_utc_ns=ANCHOR_NS),
        downlink_frequency_hz=KU_BAND_HZ,
    )

    for item in report.objects:
        assert item.doppler.downlink_frequency_hz == KU_BAND_HZ
        assert item.doppler.reference_utc_ns == ANCHOR_NS
        # A LEO pass at Ku band cannot exceed a few hundred kHz of shift.
        assert abs(item.doppler.frequency_at_reference_hz) < 400e3
        assert item.doppler.residual_rms_hz >= 0.0


def test_an_absent_archive_is_unavailable_rather_than_an_empty_sky(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(SkyFieldUnavailableError, match="no TLE snapshot is available"):
        service.field_report(
            observer=ObserverSiteV1(
                latitude_deg=0.0, longitude_deg=0.0, altitude_m=0.0, label="equator"
            ),
            pointing=_whole_sky(),
            window=SkyWindowV1(anchor_utc_ns=ANCHOR_NS),
        )


def test_a_tampered_snapshot_is_unavailable_rather_than_silently_used(tmp_path: Path) -> None:
    root = _archive(tmp_path)
    stored = next((root / "archive" / "space-track").iterdir())
    stored.write_text(ELEMENT_SETS.replace("53.0537", "53.9999"))

    with pytest.raises(SkyFieldUnavailableError, match="does not match its recorded digest"):
        _service(root).resolve_snapshot(ANCHOR_NS)


def test_an_unparsable_snapshot_is_reported_as_unusable(tmp_path: Path) -> None:
    payload = "0 STARLINK-1008\n1 44714U 19074B   26232.62719907  .00001103  00000-0  92799-4 0\n"
    root = _archive(tmp_path, payload=payload)

    with pytest.raises(SkyFieldUnavailableError, match="not usable"):
        _service(root).field_report(
            observer=ObserverSiteV1(
                latitude_deg=0.0, longitude_deg=0.0, altitude_m=0.0, label="equator"
            ),
            pointing=_whole_sky(),
            window=SkyWindowV1(anchor_utc_ns=ANCHOR_NS),
        )


def test_the_snapshot_nearest_the_anchor_is_chosen(tmp_path: Path) -> None:
    one_hour_ns = 3_600_000_000_000
    _archive(tmp_path, collected_utc_ns=ANCHOR_NS - 4 * one_hour_ns)
    _archive(tmp_path, collected_utc_ns=ANCHOR_NS + one_hour_ns, payload=ELEMENT_SETS + "\n")

    resolved = _service(tmp_path).resolve_snapshot(ANCHOR_NS)
    assert resolved.reference.collected_utc_ns == ANCHOR_NS + one_hour_ns
