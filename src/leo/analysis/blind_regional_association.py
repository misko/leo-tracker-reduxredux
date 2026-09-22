"""Location-blind joint regional position and catalogue association numerics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from leo.analysis.research.regional_doppler import (
    LIGHT_KM_S,
    REFERENCE_RF_HZ,
    ObservationArc,
    Region,
    ScoreConfig,
    centered_errors,
    score_states,
)
from leo.analysis.sparse_scan_position import DEFAULT_REGION


@dataclass(frozen=True, slots=True)
class BlindRegionalTrack:
    track_id: str
    observation_id: tuple[str, ...]
    utc_ns: np.ndarray
    measured_hz: np.ndarray
    training: np.ndarray
    catalog_number: np.ndarray
    position_ecef_km: np.ndarray
    velocity_ecef_km_s: np.ndarray
    full_catalogue_size: int
    catalogue_universe_digest: str
    source_support_digest: str


@dataclass(frozen=True, slots=True)
class BlindRegionalConfig:
    coarse_spacing_km: float = 1000.0
    maximum_tracks: int = 64
    coarse_track_limit: int = 8
    search_observation_limit: int = 64
    alternative_mode_limit: int = 8
    mode_separation_km: float = 1000.0
    refinement_mode_limit: int = 2
    refinement_grid_side: int = 9
    refinement_half_width_km: tuple[float, ...] = (500.0, 100.0)
    continuous_max_iterations: int = 80
    continuous_xatol_km: float = 0.05
    score: ScoreConfig = ScoreConfig()

    def __post_init__(self) -> None:
        if (
            self.coarse_spacing_km <= 0
            or not 1 <= self.coarse_track_limit <= self.maximum_tracks <= 64
            or not 4 <= self.search_observation_limit <= 64
            or not 1 <= self.alternative_mode_limit <= 16
            or not 1 <= self.refinement_mode_limit <= self.alternative_mode_limit
            or self.refinement_grid_side < 5
            or self.refinement_grid_side % 2 == 0
            or any(value <= 0 for value in self.refinement_half_width_km)
            or not 1 <= self.continuous_max_iterations <= 80
            or not 0 < self.continuous_xatol_km <= 1
        ):
            raise ValueError("blind regional configuration violates work bounds")


@dataclass(frozen=True, slots=True)
class BlindRegionalMode:
    latitude_deg: float
    longitude_deg: float
    east_km: float
    north_km: float
    training_log_evidence: float
    heldout_log_evidence: float
    refined: bool
    track_associations: tuple[BlindTrackAssociation, ...]


@dataclass(frozen=True, slots=True)
class BlindTrackAssociation:
    track_id: str
    association_state: str
    top_candidates: tuple[BlindCandidateWeight, ...]
    other_catalogue_weight: float
    null_weight: float
    time_s: tuple[float, ...]
    measured_hz: tuple[float, ...]
    prediction_hz: tuple[float, ...]
    training: tuple[bool, ...]
    probability_note: str = "uncalibrated diagnostic mixture weight"


@dataclass(frozen=True, slots=True)
class BlindCandidateWeight:
    catalog_number: int
    weight: float
    training_log_score: float
    heldout_log_score: float
    training_rms_hz: float
    heldout_rms_hz: float


@dataclass(frozen=True, slots=True)
class BlindRegionalResult:
    state: str
    reasons: tuple[str, ...]
    blind_positioning: bool
    site_conditioned: bool
    selected_track_count: int
    coarse_track_count: int
    omitted_coarse_track_count: int
    full_observation_count: int
    search_observation_count: int
    omitted_search_observation_count: int
    coarse_point_count: int
    refined_mode_count: int
    continuous_refinement_evaluation_count: int
    map_east_km: tuple[float, ...]
    map_north_km: tuple[float, ...]
    map_training_log_evidence: tuple[float, ...]
    modes: tuple[BlindRegionalMode, ...]


def solve_blind_regional_association(
    tracks: tuple[BlindRegionalTrack, ...],
    *,
    region: Region = DEFAULT_REGION,
    config: BlindRegionalConfig | None = None,
) -> BlindRegionalResult:
    """Search position and identities without a known-site candidate shortlist."""
    selected = config or BlindRegionalConfig()
    ordered = _validate(tracks, selected)
    if not ordered:
        return _empty("no-eligible-tracks")
    coarse_tracks = tuple(
        sorted(ordered, key=lambda row: (-_span(row), -len(row.utc_ns), row.track_id))[
            : selected.coarse_track_limit
        ]
    )
    search = {row.track_id: _subset(row, selected.search_observation_limit) for row in ordered}
    coarse = region.grid(selected.coarse_spacing_km)
    coarse_score, _heldout, _identities, _weights = _score(
        coarse_tracks, search, coarse, selected.score
    )
    modes = _separated_modes(coarse, coarse_score, selected)
    refined = []
    continuous_evaluations = 0
    for coarse_index in modes[: selected.refinement_mode_limit]:
        east, north = float(coarse.east_km[coarse_index]), float(coarse.north_km[coarse_index])
        for half in selected.refinement_half_width_km:
            xs = np.linspace(
                max(-region.width_km / 2, east - half),
                min(region.width_km / 2, east + half),
                selected.refinement_grid_side,
            )
            ys = np.linspace(
                max(-region.height_km / 2, north - half),
                min(region.height_km / 2, north + half),
                selected.refinement_grid_side,
            )
            xx, yy = np.meshgrid(xs, ys)
            grid = region.points(xx.ravel(), yy.ravel())
            score, _test, _ids, _weight = _score(ordered, search, grid, selected.score)
            best = int(np.argmax(score))
            east, north = float(grid.east_km[best]), float(grid.north_km[best])

        def objective(x):
            nonlocal continuous_evaluations
            continuous_evaluations += 1
            point = region.points([float(x[0])], [float(x[1])])
            score, _test, _ids, _weight = _score(ordered, search, point, selected.score)
            return -float(score[0])

        polished = minimize(
            objective,
            np.asarray([east, north]),
            method="Nelder-Mead",
            bounds=(
                (-region.width_km / 2, region.width_km / 2),
                (-region.height_km / 2, region.height_km / 2),
            ),
            options={
                "maxiter": selected.continuous_max_iterations,
                "xatol": selected.continuous_xatol_km,
                "fatol": 1e-6,
            },
        )
        east, north = map(float, polished.x)
        point = region.points([east], [north])
        train, heldout, _identities, _weights = _score(ordered, None, point, selected.score)
        refined.append(
            BlindRegionalMode(
                float(point.latitude_deg[0]),
                float(point.longitude_deg[0]),
                east,
                north,
                float(train[0]),
                float(heldout[0]),
                True,
                tuple(_track_association(row, point, selected.score) for row in ordered),
            )
        )
    # Preserve unrefined alternatives as explicitly coarse branches.
    for index in modes[len(refined) :]:
        point = region.points([coarse.east_km[index]], [coarse.north_km[index]])
        train, heldout, _identities, _weights = _score(ordered, None, point, selected.score)
        refined.append(
            BlindRegionalMode(
                float(point.latitude_deg[0]),
                float(point.longitude_deg[0]),
                float(point.east_km[0]),
                float(point.north_km[0]),
                float(train[0]),
                float(heldout[0]),
                False,
                tuple(_track_association(row, point, selected.score) for row in ordered),
            )
        )
    refined.sort(key=lambda mode: (-mode.training_log_evidence, mode.east_km, mode.north_km))
    reasons = [
        "bounded-search-not-global-optimum",
        "association-weights-uncalibrated",
        "single-scan-identifiability-not-established",
    ]
    if refined and not refined[0].refined:
        reasons.append("full-observation-leader-was-not-refined")
    full_count = sum(len(row.utc_ns) for row in ordered)
    search_count = sum(len(search[row.track_id]) for row in ordered)
    return BlindRegionalResult(
        "diagnostic",
        tuple(reasons),
        True,
        False,
        len(ordered),
        len(coarse_tracks),
        len(ordered) - len(coarse_tracks),
        full_count,
        search_count,
        full_count - search_count,
        len(coarse),
        min(len(modes), selected.refinement_mode_limit),
        continuous_evaluations,
        tuple(map(float, coarse.east_km)),
        tuple(map(float, coarse.north_km)),
        tuple(map(float, coarse_score)),
        tuple(refined),
    )


def _validate(tracks, config):
    if len(tracks) > config.maximum_tracks or len({row.track_id for row in tracks}) != len(tracks):
        raise ValueError("blind regional track bound or identity violated")
    universe = {row.catalogue_universe_digest for row in tracks}
    for row in tracks:
        n, c = len(row.utc_ns), len(row.catalog_number)
        if (
            not 4 <= n <= 512
            or len(row.observation_id) != n
            or len(set(row.observation_id)) != n
            or any(not value for value in row.observation_id)
            or row.utc_ns.shape != (n,)
            or not np.issubdtype(row.utc_ns.dtype, np.integer)
            or np.any(row.utc_ns <= 0)
            or np.any(np.diff(row.utc_ns) <= 0)
            or row.measured_hz.shape != (n,)
            or not np.all(np.isfinite(row.measured_hz))
            or row.training.shape != (n,)
        ):
            raise ValueError("blind regional observation arrays are invalid")
        if row.training.dtype != bool or min(np.sum(row.training), np.sum(~row.training)) < 2:
            raise ValueError("blind regional tracks require train and heldout support")
        if row.position_ecef_km.shape != (c, n, 3) or row.velocity_ecef_km_s.shape != (c, n, 3):
            raise ValueError("blind regional state arrays are invalid")
        if not np.all(np.isfinite(row.position_ecef_km)) or not np.all(
            np.isfinite(row.velocity_ecef_km_s)
        ):
            raise ValueError("blind regional state arrays are non-finite")
        if (
            c != row.full_catalogue_size
            or c == 0
            or row.catalog_number.shape != (c,)
            or len(set(map(int, row.catalog_number))) != c
            or np.any(row.catalog_number <= 0)
            or not row.track_id
            or not _digest(row.catalogue_universe_digest)
            or not _digest(row.source_support_digest)
        ):
            raise ValueError("blind regional catalogue accounting is invalid")
    if len(universe) > 1:
        raise ValueError("blind regional tracks use different catalogue universes")
    return tuple(sorted(tracks, key=lambda row: row.track_id))


def _span(row):
    return int(np.max(row.utc_ns) - np.min(row.utc_ns))


def _subset(row, limit):
    if len(row.utc_ns) <= limit:
        return np.arange(len(row.utc_ns))
    training, heldout = np.flatnonzero(row.training), np.flatnonzero(~row.training)
    training_count = min(len(training), max(2, round(limit * len(training) / len(row.utc_ns))))
    heldout_count = min(len(heldout), limit - training_count)
    if heldout_count < 2:
        heldout_count = 2
        training_count = limit - heldout_count
    chosen = tuple(
        training[np.rint(np.linspace(0, len(training) - 1, training_count)).astype(int)]
    ) + tuple(heldout[np.rint(np.linspace(0, len(heldout) - 1, heldout_count)).astype(int)])
    return np.asarray(sorted(chosen))


def _score(tracks, subsets, grid, score_config):
    total = np.zeros(len(grid))
    heldout = np.zeros(len(grid))
    identities = [[] for _ in range(len(grid))]
    weights = [[] for _ in range(len(grid))]
    for row in tracks:
        index = np.arange(len(row.utc_ns)) if subsets is None else subsets[row.track_id]
        arc = ObservationArc(
            (row.utc_ns[index] - row.utc_ns[index][0]).astype(float) / 1e9,
            row.measured_hz[index],
            np.zeros(len(index), dtype=int),
            row.training[index],
            partition="randomized",
        )
        result = score_states(
            arc,
            row.position_ecef_km[:, index],
            row.velocity_ecef_km_s[:, index],
            grid,
            row.full_catalogue_size,
            score_config,
        )
        total += result["train_logbf"]
        heldout += result["heldout_logbf"]
        for point, candidate in enumerate(result["best_index"]):
            identities[point].append(None if candidate < 0 else int(row.catalog_number[candidate]))
            weights[point].append(float(result["signal_weight"][point]))
    return total, heldout, identities, weights


def _separated_modes(grid, score, config):
    output = []
    for index in np.argsort(score)[::-1]:
        if all(
            np.hypot(
                grid.east_km[index] - grid.east_km[old], grid.north_km[index] - grid.north_km[old]
            )
            >= config.mode_separation_km
            for old in output
        ):
            output.append(int(index))
        if len(output) == config.alternative_mode_limit:
            break
    return output


def _track_association(row, grid, config):
    receiver, up = grid.ecef_km[0], grid.up[0]
    delta = row.position_ecef_km - receiver
    distance = np.linalg.norm(delta, axis=-1)
    prediction = (
        -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * row.velocity_ecef_km_s, axis=-1) / distance
    )
    elevation = np.sum(delta * up, axis=-1) / distance
    visible = np.min(elevation[:, row.training], axis=1) >= np.sin(
        np.deg2rad(config.minimum_elevation_deg)
    )
    if not np.any(visible):
        return BlindTrackAssociation(
            row.track_id,
            "unassigned",
            (),
            0.0,
            1.0,
            (),
            (),
            (),
            (),
        )
    arc = ObservationArc(
        (row.utc_ns - row.utc_ns[0]).astype(float) / 1e9,
        row.measured_hz,
        np.zeros(len(row.utc_ns), dtype=int),
        row.training,
        partition="randomized",
    )
    mse, test_mse = centered_errors(arc, prediction)
    null_mse, _ = centered_errors(arc, np.zeros(len(row.utc_ns)))
    n = config.effective_count
    candidate = (
        -0.5 * n * mse / config.signal_sigma_hz**2
        - n * np.log(config.signal_sigma_hz)
        + np.log(config.signal_prior / row.full_catalogue_size)
    )
    candidate = np.where(visible, candidate, -np.inf)
    null = (
        -0.5 * n * null_mse / config.null_sigma_hz**2
        - n * np.log(config.null_sigma_hz)
        + np.log1p(-config.signal_prior)
    )
    maximum = max(float(np.max(candidate)), float(null))
    raw = np.exp(candidate - maximum)
    null_raw = float(np.exp(null - maximum))
    denominator = float(np.sum(raw) + null_raw)
    weights = raw / denominator
    order = np.argsort(weights)[::-1]
    top = tuple(
        BlindCandidateWeight(
            int(row.catalog_number[index]),
            float(weights[index]),
            float(
                -0.5 * n * mse[index] / config.signal_sigma_hz**2
                - n * np.log(config.signal_sigma_hz)
            ),
            float(
                -0.5 * n * test_mse[index] / config.signal_sigma_hz**2
                - n * np.log(config.signal_sigma_hz)
            ),
            float(np.sqrt(mse[index])),
            float(np.sqrt(test_mse[index])),
        )
        for index in order[:5]
    )
    leader = int(order[0])
    fitted = prediction[leader].copy()
    fitted += float(np.mean(row.measured_hz[row.training] - fitted[row.training]))
    return BlindTrackAssociation(
        row.track_id,
        "associated" if weights[leader] >= 0.5 else "unresolved",
        top,
        float(np.sum(weights[order[5:]])),
        null_raw / denominator,
        tuple(map(float, arc.time_s)),
        tuple(map(float, row.measured_hz)),
        tuple(map(float, fitted)),
        tuple(map(bool, row.training)),
    )


def _empty(reason):
    return BlindRegionalResult(
        "insufficient", (reason,), True, False, 0, 0, 0, 0, 0, 0, 0, 0, 0, (), (), (), ()
    )


def _digest(value):
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )
