from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.catalogue_prediction import element_pair_digest
from leo.analysis.research.cross_family_injection_protocol import CrossFamilyTruthPair
from leo.analysis.research.cross_family_orbit_truth import (
    CrossFamilyOrbitTruthInputError,
    VerifiedCrossFamilyTruthPair,
    build_verified_cross_family_truth,
)
from leo.contracts.digests import sha256_digest
from leo.contracts.sky import ObserverSiteV1
from leo.sky.propagation import (
    element_line_checksum,
    parse_element_set_records,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import observe_grid

_BASE_LINE_ONE = "1 44714U 19074B   26232.62719907  .00001103  00000-0  92799-4 0  9995"
_BASE_LINE_TWO = "2 44714  53.0537 172.0234 0001334  87.1234 273.0021 15.06393004260123"


def _valid(line: str) -> str:
    return f"{line[:68]}{element_line_checksum(line)}"


def _snapshot() -> str:
    return f"STARLINK-44714\n{_valid(_BASE_LINE_ONE)}\n{_valid(_BASE_LINE_TWO)}\n"


def _site_and_pair() -> tuple[ObserverSiteV1, CrossFamilyTruthPair]:
    snapshot = _snapshot()
    catalogue = parse_element_sets(snapshot)
    records = parse_element_set_records(snapshot)
    centre = catalogue.element_epoch_utc_ns()[0] + 60_000_000_000
    grid = SamplingGrid((centre - 1_000_000_000, centre, centre + 1_000_000_000), 1, 1.0)
    propagated = propagate_grid(catalogue, grid)
    candidates = [
        ObserverSiteV1(latitude_deg=latitude, longitude_deg=longitude, altitude_m=0, label="test")
        for latitude in range(-60, 61, 20)
        for longitude in range(-180, 181, 20)
        if longitude != -180
    ]
    site = max(
        candidates,
        key=lambda item: float(observe_grid(propagated, item, grid).elevation_deg[0, 1]),
    )
    elevation = float(observe_grid(propagated, site, grid).elevation_deg[0, 1])
    assert elevation > 0.0
    span_start = centre - 1_000_000_000
    pair = CrossFamilyTruthPair(
        pair_id="synthetic-background",
        background_session_id="synthetic-background",
        sample_zero_utc_ns=span_start,
        span_start_utc_ns=span_start,
        span_centre_utc_ns=centre,
        seed=1,
        orbit_scenario_id="orbit",
        radio_scenario_id="radio",
        tle_snapshot_path=Path("/unused/snapshot.tle"),
        tle_snapshot_sha256=sha256_digest(snapshot.encode("ascii")),
        tle_collected_utc_ns=span_start - 60_000_000_000,
        tle_object_count=1,
        true_catalog_number=44714,
        true_object_name="STARLINK-44714",
        true_element_digest=element_pair_digest(records[0].first_line, records[0].second_line),
        true_element_epoch_utc_ns=catalogue.element_epoch_utc_ns()[0],
        centre_elevation_deg=elevation,
    )
    return site, pair


def _build(pair: CrossFamilyTruthPair | None = None) -> VerifiedCrossFamilyTruthPair:
    site, default = _site_and_pair()
    return build_verified_cross_family_truth(
        default if pair is None else pair,
        _snapshot(),
        observer_site=site,
        nominal_rf_hz=11_440_312_498.0,
        interpolation_spacing_s=0.001,
        interpolation_maximum_error_hz=0.01,
    )


def test_verified_orbit_and_radio_truth_share_cfo_and_rate_at_center() -> None:
    result = _build()

    assert result.true_catalog_number == 44714
    assert result.visible_starlink_count == 1
    assert result.response_accessed is False
    assert result.candidate_ranking_used_response is False
    assert result.orbit_interpolation_maximum_error_hz <= 0.01
    assert result.truth_digest.startswith("sha256:")
    center = 1.0
    step = 0.001
    assert float(result.radio_trajectory.cfo_hz(center)) == pytest.approx(
        float(result.orbit_trajectory.cfo_hz(center)), abs=1e-12
    )
    orbit_rate = float(
        (
            result.orbit_trajectory.cfo_hz(center + step)
            - result.orbit_trajectory.cfo_hz(center - step)
        )
        / (2 * step)
    )
    radio_rate = float(
        (
            result.radio_trajectory.cfo_hz(center + step)
            - result.radio_trajectory.cfo_hz(center - step)
        )
        / (2 * step)
    )
    assert radio_rate == pytest.approx(orbit_rate, abs=1e-8)


def test_snapshot_or_element_substitution_is_rejected() -> None:
    site, pair = _site_and_pair()
    poisoned = bytearray(_snapshot().encode("ascii"))
    poisoned[-3] = ord("1") if poisoned[-3] != ord("1") else ord("2")

    with pytest.raises(CrossFamilyOrbitTruthInputError, match="snapshot bytes"):
        build_verified_cross_family_truth(
            pair,
            bytes(poisoned),
            observer_site=site,
            nominal_rf_hz=11_440_312_498.0,
            interpolation_spacing_s=0.001,
            interpolation_maximum_error_hz=0.01,
        )


def test_wrong_frozen_catalogue_identity_is_rejected() -> None:
    _, pair = _site_and_pair()

    with pytest.raises(CrossFamilyOrbitTruthInputError, match="not unique"):
        _build(replace(pair, true_catalog_number=1))


def test_frozen_elevation_must_reproduce_exactly() -> None:
    _, pair = _site_and_pair()

    with pytest.raises(CrossFamilyOrbitTruthInputError, match="center elevation"):
        _build(replace(pair, centre_elevation_deg=pair.centre_elevation_deg + 1e-4))


def test_radio_truth_is_linear_while_orbit_truth_retains_curvature() -> None:
    result = _build()
    times = np.asarray((0.5, 1.0, 1.5))
    radio = result.radio_trajectory.cfo_hz(times)
    orbit = result.orbit_trajectory.cfo_hz(times)

    assert radio[0] - 2 * radio[1] + radio[2] == pytest.approx(0.0, abs=1e-9)
    assert abs(float(orbit[0] - 2 * orbit[1] + orbit[2])) > 1.0
