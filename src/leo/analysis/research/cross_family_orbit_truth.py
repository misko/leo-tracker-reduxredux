"""Response-free SGP4 and matched-radio truth for paired Qin injection."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np

from leo.analysis.catalogue_prediction import element_pair_digest
from leo.analysis.research.cross_family_injection_protocol import CrossFamilyTruthPair
from leo.analysis.research.trajectory_qin_injection import PiecewiseLinearCfoTrajectory
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.sky import ObserverSiteV1
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import (
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    ElementSetError,
    parse_element_set_records,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import observe_grid

_NS_PER_S = 1_000_000_000
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class CrossFamilyOrbitTruthInputError(ValueError):
    """The frozen TLE truth authority is incomplete or inconsistent."""


class CrossFamilyOrbitTruthNumericalError(ValueError):
    """The selected TLE cannot supply the declared trajectory accuracy."""


@dataclass(frozen=True, slots=True)
class VerifiedCrossFamilyTruthPair:
    """Authenticated orbit truth plus a center-matched linear radio truth."""

    pair_id: str
    true_catalog_number: int
    true_object_name: str
    starlink_object_count: int
    visible_starlink_count: int
    selected_centre_elevation_deg: float
    orbit_trajectory: PiecewiseLinearCfoTrajectory
    radio_trajectory: PiecewiseLinearCfoTrajectory
    orbit_interpolation_maximum_error_hz: float
    truth_digest: str
    response_accessed: Literal[False] = field(default=False, init=False)
    candidate_ranking_used_response: Literal[False] = field(default=False, init=False)
    sample_clock_offset_ppm: float = field(default=0.0, init=False)
    orbit_tau_s: float = field(default=0.0, init=False)
    algorithm_version: Literal["paired-sgp4-and-centre-matched-radio-truth-v1"] = field(
        default="paired-sgp4-and-centre-matched-radio-truth-v1", init=False
    )


def build_verified_cross_family_truth(
    pair: CrossFamilyTruthPair,
    snapshot_payload: bytes | str,
    *,
    observer_site: ObserverSiteV1,
    nominal_rf_hz: float,
    interpolation_spacing_s: float,
    interpolation_maximum_error_hz: float,
) -> VerifiedCrossFamilyTruthPair:
    """Authenticate, reproduce selection, and build both frozen truth curves."""

    pair = _revalidate_pair(pair)
    observer_site = ObserverSiteV1.model_validate(observer_site.model_dump(mode="json"))
    if not math.isfinite(nominal_rf_hz) or nominal_rf_hz <= 0.0:
        raise CrossFamilyOrbitTruthInputError("nominal RF must be finite and positive")
    if interpolation_spacing_s != 0.001 or interpolation_maximum_error_hz != 0.01:
        raise CrossFamilyOrbitTruthInputError("truth interpolation policy differs from v1")
    raw_bytes = (
        snapshot_payload.encode("ascii")
        if isinstance(snapshot_payload, str)
        else bytes(snapshot_payload)
    )
    if sha256_digest(raw_bytes) != pair.tle_snapshot_sha256:
        raise CrossFamilyOrbitTruthInputError("TLE snapshot bytes do not match the frozen digest")
    try:
        text = raw_bytes.decode("ascii")
        records = parse_element_set_records(text)
        catalogue = parse_element_sets(text)
    except (UnicodeDecodeError, ElementSetError) as error:
        raise CrossFamilyOrbitTruthInputError(
            "authenticated TLE snapshot is not parseable"
        ) from error
    if not (
        len(records) == len(catalogue) == pair.tle_object_count == len(catalogue.satellite_numbers)
    ):
        raise CrossFamilyOrbitTruthInputError("TLE object inventories do not close")
    selected_rows = [
        index
        for index, number in enumerate(catalogue.satellite_numbers)
        if number == pair.true_catalog_number
    ]
    if len(selected_rows) != 1:
        raise CrossFamilyOrbitTruthInputError("true catalogue number is not unique in the snapshot")
    selected_index = selected_rows[0]
    if records[selected_index].name != pair.true_object_name:
        raise CrossFamilyOrbitTruthInputError("true object name differs from the snapshot")
    if (
        element_pair_digest(records[selected_index].first_line, records[selected_index].second_line)
        != pair.true_element_digest
    ):
        raise CrossFamilyOrbitTruthInputError("true element bytes differ from the frozen digest")
    if catalogue.element_epoch_utc_ns()[selected_index] != pair.true_element_epoch_utc_ns:
        raise CrossFamilyOrbitTruthInputError("true element epoch differs from the snapshot")

    centre_grid = SamplingGrid(
        utc_ns=(
            pair.span_centre_utc_ns - _NS_PER_S,
            pair.span_centre_utc_ns,
            pair.span_centre_utc_ns + _NS_PER_S,
        ),
        anchor_index=1,
        spacing_s=1.0,
    )
    centre_tracks = observe_grid(propagate_grid(catalogue, centre_grid), observer_site, centre_grid)
    starlink_indices = np.asarray(
        [
            index
            for index, record in enumerate(records)
            if record.name.upper().startswith("STARLINK-")
        ],
        dtype=np.int64,
    )
    plausible = centre_tracks.usable & (
        np.min(centre_tracks.altitude_km, axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM
    )
    visible = starlink_indices[
        plausible[starlink_indices] & (centre_tracks.elevation_deg[starlink_indices, 1] >= 0.0)
    ]
    if visible.size == 0:
        raise CrossFamilyOrbitTruthNumericalError("snapshot has no visible plausible Starlink")
    winner = min(
        (int(index) for index in visible),
        key=lambda index: (
            -float(centre_tracks.elevation_deg[index, 1]),
            catalogue.satellite_numbers[index],
        ),
    )
    if winner != selected_index:
        raise CrossFamilyOrbitTruthInputError(
            "frozen orbit truth is not the response-free highest-elevation Starlink"
        )
    selected_elevation = float(centre_tracks.elevation_deg[winner, 1])
    if not math.isclose(selected_elevation, pair.centre_elevation_deg, rel_tol=0.0, abs_tol=1e-10):
        raise CrossFamilyOrbitTruthInputError("frozen center elevation differs from propagation")

    duration_ns = 2 * _NS_PER_S
    step_ns = round(interpolation_spacing_s * _NS_PER_S)
    if step_ns <= 0 or duration_ns % step_ns != 0:
        raise CrossFamilyOrbitTruthInputError("interpolation spacing must divide the 2 s span")
    knot_utc_ns = tuple(
        range(pair.span_start_utc_ns, pair.span_start_utc_ns + duration_ns + 1, step_ns)
    )
    knot_grid = SamplingGrid(
        utc_ns=knot_utc_ns,
        anchor_index=len(knot_utc_ns) // 2,
        spacing_s=interpolation_spacing_s,
    )
    knot_tracks = observe_grid(
        propagate_grid(catalogue, knot_grid, indices=[selected_index]),
        observer_site,
        knot_grid,
    )
    if not bool(knot_tracks.usable[0]):
        raise CrossFamilyOrbitTruthNumericalError("selected element failed on orbit truth knots")
    knot_cfo = doppler_shift_hz(nominal_rf_hz, knot_tracks.range_rate_km_s[0])
    knot_times_s = tuple((value - pair.span_start_utc_ns) / _NS_PER_S for value in knot_utc_ns)
    orbit_trajectory = PiecewiseLinearCfoTrajectory(
        trajectory_id=pair.orbit_scenario_id,
        knot_times_s=knot_times_s,
        knot_cfo_hz=tuple(float(value) for value in knot_cfo),
    )

    midpoint_utc_ns = tuple(value + step_ns // 2 for value in knot_utc_ns[:-1])
    midpoint_grid = SamplingGrid(
        utc_ns=midpoint_utc_ns,
        anchor_index=len(midpoint_utc_ns) // 2,
        spacing_s=interpolation_spacing_s,
    )
    midpoint_tracks = observe_grid(
        propagate_grid(catalogue, midpoint_grid, indices=[selected_index]),
        observer_site,
        midpoint_grid,
    )
    if not bool(midpoint_tracks.usable[0]):
        raise CrossFamilyOrbitTruthNumericalError("selected element failed on validation knots")
    midpoint_truth = doppler_shift_hz(nominal_rf_hz, midpoint_tracks.range_rate_km_s[0])
    midpoint_times_s = np.asarray(
        [(value - pair.span_start_utc_ns) / _NS_PER_S for value in midpoint_utc_ns],
        dtype=float,
    )
    maximum_error = float(
        np.max(np.abs(orbit_trajectory.cfo_hz(midpoint_times_s) - midpoint_truth))
    )
    if maximum_error > interpolation_maximum_error_hz:
        raise CrossFamilyOrbitTruthNumericalError(
            "piecewise-linear orbit truth exceeds the frozen interpolation error"
        )

    centre_s = 1.0
    centre_cfo = float(orbit_trajectory.cfo_hz(centre_s))
    centre_rate = float(
        (
            orbit_trajectory.cfo_hz(centre_s + interpolation_spacing_s)
            - orbit_trajectory.cfo_hz(centre_s - interpolation_spacing_s)
        )
        / (2.0 * interpolation_spacing_s)
    )
    radio_cfo = tuple(centre_cfo + centre_rate * (time_s - centre_s) for time_s in knot_times_s)
    radio_trajectory = PiecewiseLinearCfoTrajectory(
        trajectory_id=pair.radio_scenario_id,
        knot_times_s=knot_times_s,
        knot_cfo_hz=radio_cfo,
    )
    payload = {
        "algorithm_version": "paired-sgp4-and-centre-matched-radio-truth-v1",
        "pair_id": pair.pair_id,
        "snapshot_digest": pair.tle_snapshot_sha256,
        "true_catalog_number": pair.true_catalog_number,
        "true_object_name": pair.true_object_name,
        "true_element_digest": pair.true_element_digest,
        "true_element_epoch_utc_ns": pair.true_element_epoch_utc_ns,
        "observer_site": observer_site.model_dump(mode="json"),
        "nominal_rf_hz": nominal_rf_hz,
        "starlink_object_count": int(starlink_indices.size),
        "visible_starlink_count": int(visible.size),
        "selected_centre_elevation_deg": selected_elevation,
        "orbit_trajectory": {
            "trajectory_id": orbit_trajectory.trajectory_id,
            "knot_times_s": orbit_trajectory.knot_times_s,
            "knot_cfo_hz": orbit_trajectory.knot_cfo_hz,
        },
        "radio_trajectory": {
            "trajectory_id": radio_trajectory.trajectory_id,
            "knot_times_s": radio_trajectory.knot_times_s,
            "knot_cfo_hz": radio_trajectory.knot_cfo_hz,
        },
        "orbit_interpolation_maximum_error_hz": maximum_error,
        "response_accessed": False,
        "candidate_ranking_used_response": False,
        "sample_clock_offset_ppm": 0.0,
        "orbit_tau_s": 0.0,
    }
    return VerifiedCrossFamilyTruthPair(
        pair_id=pair.pair_id,
        true_catalog_number=pair.true_catalog_number,
        true_object_name=pair.true_object_name,
        starlink_object_count=int(starlink_indices.size),
        visible_starlink_count=int(visible.size),
        selected_centre_elevation_deg=selected_elevation,
        orbit_trajectory=orbit_trajectory,
        radio_trajectory=radio_trajectory,
        orbit_interpolation_maximum_error_hz=maximum_error,
        truth_digest=canonical_digest(payload),
    )


def _revalidate_pair(pair: CrossFamilyTruthPair) -> CrossFamilyTruthPair:
    if not isinstance(pair, CrossFamilyTruthPair):
        raise CrossFamilyOrbitTruthInputError("cross-family pair is invalid")
    for text_value, label in (
        (pair.pair_id, "pair identity"),
        (pair.background_session_id, "background identity"),
        (pair.orbit_scenario_id, "orbit scenario identity"),
        (pair.radio_scenario_id, "radio scenario identity"),
        (pair.true_object_name, "true object name"),
    ):
        if not isinstance(text_value, str) or not text_value.strip():
            raise CrossFamilyOrbitTruthInputError(f"{label} is invalid")
    for numeric_value, label in (
        (pair.sample_zero_utc_ns, "sample-zero UTC"),
        (pair.span_start_utc_ns, "span-start UTC"),
        (pair.span_centre_utc_ns, "span-centre UTC"),
        (pair.tle_collected_utc_ns, "TLE collection UTC"),
        (pair.tle_object_count, "TLE object count"),
        (pair.true_catalog_number, "true catalogue number"),
        (pair.true_element_epoch_utc_ns, "true element epoch"),
    ):
        if (
            not isinstance(numeric_value, int)
            or isinstance(numeric_value, bool)
            or numeric_value <= 0
        ):
            raise CrossFamilyOrbitTruthInputError(f"{label} is invalid")
    if not isinstance(pair.seed, int) or isinstance(pair.seed, bool) or pair.seed < 0:
        raise CrossFamilyOrbitTruthInputError("seed is invalid")
    if not isinstance(pair.tle_snapshot_path, Path):
        raise CrossFamilyOrbitTruthInputError("TLE snapshot path is invalid")
    if (
        _SHA256_RE.fullmatch(pair.tle_snapshot_sha256) is None
        or _SHA256_RE.fullmatch(pair.true_element_digest) is None
    ):
        raise CrossFamilyOrbitTruthInputError("TLE digests are invalid")
    if pair.span_centre_utc_ns - pair.span_start_utc_ns != _NS_PER_S:
        raise CrossFamilyOrbitTruthInputError("pair must retain an exact two-second span")
    if pair.tle_collected_utc_ns >= pair.span_start_utc_ns:
        raise CrossFamilyOrbitTruthInputError("TLE snapshot is not causal")
    if not math.isfinite(pair.centre_elevation_deg) or not 0.0 <= pair.centre_elevation_deg <= 90.0:
        raise CrossFamilyOrbitTruthInputError("center elevation is invalid")
    return CrossFamilyTruthPair(
        pair_id=pair.pair_id,
        background_session_id=pair.background_session_id,
        sample_zero_utc_ns=pair.sample_zero_utc_ns,
        span_start_utc_ns=pair.span_start_utc_ns,
        span_centre_utc_ns=pair.span_centre_utc_ns,
        seed=pair.seed,
        orbit_scenario_id=pair.orbit_scenario_id,
        radio_scenario_id=pair.radio_scenario_id,
        tle_snapshot_path=pair.tle_snapshot_path,
        tle_snapshot_sha256=pair.tle_snapshot_sha256,
        tle_collected_utc_ns=pair.tle_collected_utc_ns,
        tle_object_count=pair.tle_object_count,
        true_catalog_number=pair.true_catalog_number,
        true_object_name=pair.true_object_name,
        true_element_digest=pair.true_element_digest,
        true_element_epoch_utc_ns=pair.true_element_epoch_utc_ns,
        centre_elevation_deg=pair.centre_elevation_deg,
    )
