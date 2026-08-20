from __future__ import annotations

import pytest
from pydantic import ValidationError

from leo.contracts.sky import (
    SKY_WINDOW_HALF_WIDTH_S,
    BeamPointingV1,
    ObserverSiteV1,
    SkyWindowV1,
)
from leo.sky.sites import SITE_PRESETS, preset_names, resolve_preset

_NS_PER_S = 1_000_000_000
ANCHOR_NS = 1_787_238_197_000_000_000


def test_the_reviewed_preset_places_spinnaker_on_the_sausalito_waterfront() -> None:
    preset = resolve_preset("spinnaker-sausalito")
    assert preset.label == "Spinnaker, Sausalito"
    # Richardson Bay waterfront; loose bounds so the assertion documents the
    # neighbourhood rather than re-encoding the same digits twice.
    assert 37.85 < preset.latitude_deg < 37.87
    assert -122.49 < preset.longitude_deg < -122.47
    assert preset.provenance.startswith("OpenStreetMap")
    assert preset.position_uncertainty_m <= 100.0


def test_preset_registry_is_stable_and_fails_closed() -> None:
    assert preset_names() == ("spinnaker-sausalito",)
    with pytest.raises(KeyError, match="unknown observer site preset"):
        resolve_preset("no-such-site")
    with pytest.raises(TypeError):
        SITE_PRESETS["spinnaker-sausalito"] = resolve_preset("spinnaker-sausalito")  # type: ignore[index]


def test_presets_are_valid_observer_sites() -> None:
    for name in preset_names():
        preset = resolve_preset(name)
        site = ObserverSiteV1.model_validate(
            {
                "latitude_deg": preset.latitude_deg,
                "longitude_deg": preset.longitude_deg,
                "altitude_m": preset.altitude_m,
                "label": preset.label,
            }
        )
        assert site.label == preset.label


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("latitude_deg", 90.5),
        ("latitude_deg", -91.0),
        ("longitude_deg", 180.5),
        ("longitude_deg", -180.0),
        ("altitude_m", -600.0),
        ("altitude_m", 12_000.0),
    ),
)
def test_observer_site_rejects_out_of_range_coordinates(field: str, value: float) -> None:
    payload = {
        "latitude_deg": 37.858988,
        "longitude_deg": -122.478103,
        "altitude_m": -29.0,
        "label": "test",
        field: value,
    }
    with pytest.raises(ValidationError):
        ObserverSiteV1.model_validate(payload)


def test_observer_site_rejects_non_finite_coordinates() -> None:
    with pytest.raises(ValidationError):
        ObserverSiteV1.model_validate(
            {
                "latitude_deg": float("nan"),
                "longitude_deg": -122.478103,
                "altitude_m": -29.0,
                "label": "test",
            }
        )


def test_observer_site_is_frozen_and_closed() -> None:
    site = ObserverSiteV1(
        latitude_deg=37.858988, longitude_deg=-122.478103, altitude_m=-29.0, label="test"
    )
    with pytest.raises(ValidationError):
        site.latitude_deg = 0.0  # type: ignore[misc]
    with pytest.raises(ValidationError):
        ObserverSiteV1.model_validate(
            {
                "latitude_deg": 37.0,
                "longitude_deg": -122.0,
                "altitude_m": 0.0,
                "label": "test",
                "elevation_ft": 12,
            }
        )


def test_beam_pointing_rejects_a_degenerate_or_oversized_cone() -> None:
    with pytest.raises(ValidationError):
        BeamPointingV1(
            boresight_azimuth_deg=180.0, boresight_elevation_deg=45.0, half_angle_deg=0.0
        )
    with pytest.raises(ValidationError):
        BeamPointingV1(
            boresight_azimuth_deg=180.0, boresight_elevation_deg=45.0, half_angle_deg=90.1
        )
    with pytest.raises(ValidationError):
        BeamPointingV1(
            boresight_azimuth_deg=360.0, boresight_elevation_deg=45.0, half_angle_deg=3.0
        )


def test_default_window_is_the_operator_slider() -> None:
    window = SkyWindowV1(anchor_utc_ns=ANCHOR_NS)
    assert window.half_width_s == SKY_WINDOW_HALF_WIDTH_S
    assert window.end_utc_ns - window.start_utc_ns == 120 * _NS_PER_S

    knots = window.knot_utc_ns()
    assert len(knots) == window.sample_count
    assert knots[0] == window.start_utc_ns
    assert knots[-1] == window.end_utc_ns
    assert knots[len(knots) // 2] == ANCHOR_NS
    spacing = {second - first for first, second in zip(knots[:-1], knots[1:], strict=True)}
    assert spacing == {30 * _NS_PER_S}


def test_window_rejects_knots_that_do_not_divide_the_span_exactly() -> None:
    with pytest.raises(ValidationError, match="divide the span exactly"):
        SkyWindowV1(anchor_utc_ns=ANCHOR_NS, half_width_s=60, sample_count=8)


@pytest.mark.parametrize("sample_count", (2, 3, 5, 11, 121, 241))
def test_supported_sample_counts_produce_exactly_spaced_knots(sample_count: int) -> None:
    window = SkyWindowV1(anchor_utc_ns=ANCHOR_NS, sample_count=sample_count)
    knots = window.knot_utc_ns()
    spacing = {second - first for first, second in zip(knots[:-1], knots[1:], strict=True)}
    assert len(spacing) == 1
