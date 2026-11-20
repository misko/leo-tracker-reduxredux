"""Numerical fixed-owner diagnostics on an authenticated common measurement mask."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from unittest.mock import patch

import numpy as np
from scipy.linalg import cholesky, solve_triangular
from scipy.optimize import lsq_linear

from ..scoring import ARMS
from ..variants import robust_em as lean
from ..variants import robust_orbit_fit as exact
from .joint_orbits_worker import trace
from .robust_orbit_fit_diagnostic import key

CELLS = (
    ("lean_owner_lean_alias", "common", "lean", "lean", "lean"),
    ("lean_owner_v5_alias", "common", "lean", "v5", "lean"),
    ("v5_owner_lean_alias", "common", "v5", "lean", "lean"),
    ("v5_owner_v5_alias", "common", "v5", "v5", "lean"),
    ("v5_full_lean", "full", "v5", "v5", "lean"),
    ("v5_common_clock", "common", "v5", "v5", "clock"),
    ("v5_full_clock", "full", "v5", "v5", "clock"),
    ("v5_full_diagonal", "full", "v5", "v5", "diagonal"),
)
BOUNDARY = "Privileged fixed-owner Doppler diagnostic"


def blind(packet):
    found = {}
    original_valid, refine = exact.grid._valid_states, exact.refine

    def save_bank(*args):
        result = original_valid(*args)
        found["satellites"] = result[0]
        return result

    def save_rows(rows, fit, tile, region, half, arm):
        found["assignments"] = rows
        return refine(rows, fit, tile, region, half, arm)

    with (
        patch.object(exact.grid, "_valid_states", save_bank),
        patch.object(exact, "refine", save_rows),
    ):
        outcome = exact.infer(packet["observation"], packet["offer"], packet["catalogue"])
    assignments = found.get("assignments", [])
    rows = list(trace(packet["observation"], assignments, found.get("satellites", [])))
    for row in rows:
        value = row["cfo_hz"]
        row["lean_lift"] = (
            round((value - lean.fold(value)) / lean.PERIOD) - assignments[row["track"]].alias
        )
    return dict(result=outcome, rows=rows)


def join(owned, picked):
    peers, references = defaultdict(list), defaultdict(list)
    for row in picked:
        peers[key(row["receiver"], row["channel"], row["time_s"], row["cfo_hz"])].append(row)
    for row in owned:
        references[key(row["rx"], row["channel"], row["time_s"], row["folded_hz"])].append(row)
    full, common = [], []
    counts = Counter()
    for k, originals in references.items():
        if len(originals) != 1:
            counts["ambiguous_v5_rows"] += len(originals)
            continue
        (row,) = originals
        if row["role"] != "conditional":
            counts["predictive_rows"] += 1
            continue
        full.append(row)
        matches = peers[k]
        if len(matches) != 1:
            counts["ambiguous_lean_rows" if matches else "v5_only_conditional"] += 1
            continue
        (match,) = matches
        common.append(
            row
            | dict(
                lean_owner=match["norad"],
                lean_track=match["track"],
                lean_lift=match["lean_lift"],
            )
        )
    counts.update(full=len(full), common=len(common), lean_selected=len(picked))
    counts["different_owner"] = sum(r["lean_owner"] != r["v5_owner"] for r in common)
    counts["different_alias"] = sum(r["lean_lift"] != r["v5_lift"] for r in common)
    return dict(full=full, common=common), dict(counts)


def bank(packet):
    found = {}
    validate = exact.grid._valid_states

    def capture(*args):
        result = validate(*args)
        found["satellites"] = result[0]
        return result

    sky = exact.grid.prepare_sky(packet["observation"], packet["catalogue"])
    tile_offer = packet["offer"]
    center = tuple(tile_offer["center"])
    with patch.object(exact.grid, "_valid_states", capture):
        tile = exact.grid.make_tile(sky, center)
    region = exact.Region(tile_offer["id"], center, tile.ecef_center_km, tile.enu_frame)
    return tile, region, {sat.satnum: i for i, sat in enumerate(found["satellites"])}


@dataclass
class Fragment:
    rows: list
    orbit: int
    norad: int
    rf: float
    lane: int
    t: np.ndarray
    y: np.ndarray
    whiten: np.ndarray


def fragments(rows, owner, alias, index):
    collections = defaultdict(list)
    for row in rows:
        collections[
            (row["component"], row.get("lean_track"), row["v5_owner"], row.get("lean_owner"))
        ].append(row)
    result = []
    for points in collections.values():
        points.sort(key=lambda r: r["time_s"])
        first = points[0]
        number = first[owner + "_owner"]
        times = np.array([r["time_s"] for r in points])
        y = np.array([r["folded_hz"] + r[alias + "_lift"] * lean.PERIOD for r in points])
        covariance = lean.CORRELATED_HZ**2 * np.exp(
            -abs(times[:, None] - times) / lean.CORRELATION_S
        )
        covariance.flat[:: len(points) + 1] += lean.WHITE_HZ**2
        white = solve_triangular(cholesky(covariance, lower=True), np.eye(len(points)), lower=True)
        lane = 2 * (first["rx"] - 1) + int(first["channel"] > 4)
        result.append(
            Fragment(points, index[number], number, first["rf_hz"], lane, times, y, white)
        )
    return result


def _least_fit(groups, tile, region, half, arm):
    site = region.site(np.zeros(2))[0]
    tangent = exact._tangent(region, np.zeros(2))
    rows = []
    for g in groups:
        prediction, dp, dt = exact.project(tile, g.orbit, g.t, site, 0, g.rf)
        track = lean.Track(
            g.t, g.y, g.rf, g.lane, False, (g.t - tile.duration_s / 2) / 100, g.whiten
        )
        arc = lean.Arc(
            track,
            np.array([g.orbit]),
            (g.y - prediction)[None],
            (dp @ tangent)[None],
            dt[None],
            np.zeros(1),
            np.zeros(1),
        )
        rows.append(lean.Assignment(arc, 0, 0, 0.0, 0.0))
    start = lean.fit(rows, len(tile.positions_km), half, arm)
    if start is None:
        raise ValueError("the fixed lean mask did not yield a bounded fit")
    fitted, stage = exact.refine(rows, start, tile, region, half, arm)
    state = fitted.state
    rf_terms = [
        state.bias[g.lane]
        + (g.t - tile.duration_s / 2) * state.drift[g.lane] / 100
        + (g.rf / 1e9 - 11.5) * state.c_hz_per_ghz
        for g in groups
    ]
    return state.xy, [state.phase[g.orbit] for g in groups], rf_terms, fitted.score, stage


def clock_basis(times):
    grid = np.arange(301.0)
    centers = np.arange(0.0, 301, 30)
    raw = np.exp(-0.5 * ((times[:, None] - centers) / 20) ** 2)
    standard = np.exp(-0.5 * ((grid[:, None] - centers) / 20) ** 2)
    design = np.column_stack((np.ones(len(grid)), (grid - 150) / 150))
    beta = np.linalg.lstsq(design, standard, rcond=None)[0]
    return raw - np.column_stack((np.ones(len(times)), (times - 150) / 150)) @ beta


def _clock_fit(groups, tile, region, half, arm, priors, prior_model, diagonal):
    fitted = arm == "fitted_c"
    norads = {g.norad: i for i, g in enumerate(dict((g.norad, g) for g in groups).values())}
    components = {
        name: i for i, name in enumerate(sorted({g.rows[0]["component"] for g in groups}))
    }
    radio_width = 30 + int(fitted) + len(components)
    phase_begin = 2 + radio_width
    width = phase_begin + len(norads)
    center = np.zeros(width)
    sigma = np.ones(width)
    sigma[:2] = 1000.0
    for number, idx in norads.items():
        prior = priors.get(str(number))
        mean, sd = prior if prior is not None else (0.0, 2.5)
        center[phase_begin + idx] = mean
        sigma[phase_begin + idx] = sd * prior_model["multiplier"] if prior is not None else sd
    bound = np.r_[[half, half], np.full(radio_width, 8.0), np.full(len(norads), lean.PHASE_BOUND_S)]
    state = np.clip(center, -bound, bound)
    radios, weights, phase_columns = [], [], []
    for g in groups:
        m = np.zeros((len(g.t), radio_width))
        rx = g.lane // 2
        m[:, g.lane] = lean.PERIOD / np.sqrt(12)
        dt = g.t - 150
        m[:, 4 + 2 * rx] = 10 * dt
        m[:, 5 + 2 * rx] = (1 if g.lane % 2 else -1) * 0.5 * dt
        m[:, 8 + 11 * rx : 19 + 11 * rx] = 200 * (g.rf / 11.5e9) * clock_basis(g.t)
        if fitted:
            m[:, 30] = 200000 * (g.rf / 1e9 - 11.5)
        m[:, 30 + int(fitted) + components[g.rows[0]["component"]]] = 1000
        radios.append(m)
        weights.append(
            np.eye(len(g.t)) / 150 if diagonal else g.whiten * np.sqrt(min(1, 40 / len(g.t)))
        )
        phase_columns.append(phase_begin + norads[g.norad])

    def evaluate(x, design=False):
        site = region.site(x[:2])[0]
        tangent = exact._tangent(region, x[:2]) if design else None
        error, matrix = [], []
        for g, m, white, col in zip(groups, radios, weights, phase_columns, strict=True):
            hz, dp, dt = exact.project(tile, g.orbit, g.t, site, x[col], g.rf)
            error.append(white @ (g.y - hz - m @ x[2:phase_begin]))
            if design:
                block = np.zeros((len(g.t), width))
                block[:, :2] = dp @ tangent
                block[:, 2:phase_begin] = m
                block[:, col] = dt
                matrix.append(white @ block)
        residual = np.r_[np.concatenate(error), (center - x) / sigma]
        return residual, np.vstack([*matrix, np.diag(1 / sigma)]) if design else None

    accepted = 0
    for _ in range(8):
        residual, jacobian = evaluate(state, design=True)
        attempt = lsq_linear(
            jacobian,
            residual + jacobian @ state,
            bounds=(-bound, bound),
            method="bvls",
            max_iter=40,
        )
        loss = residual @ residual
        moved = False
        for step in exact.BACKTRACK:
            candidate = state + step * (attempt.x - state)
            r, _ = evaluate(candidate)
            if float(r @ r) + 1e-8 < loss:
                state, moved = candidate, True
                accepted += 1
                break
        if not moved:
            break
    res, _ = evaluate(state)
    return (
        state[:2],
        [state[col] for col in phase_columns],
        [m @ state[2:phase_begin] for m in radios],
        float(res @ res),
        dict(accepted_steps=accepted, archive_phase_priors=sum(str(i) in priors for i in norads)),
    )


def refit(packet, owned, chosen, priors, model):
    masks, counts = join(owned, chosen)
    tile, region, index = bank(packet)
    half = float(packet["offer"].get("width_km", 25)) / 2
    for mask, rows in masks.items():
        use = [
            r
            for r in rows
            if r["v5_owner"] in index and (mask == "full" or r["lean_owner"] in index)
        ]
        counts[mask + "_outside_causal_bank"] = len(rows) - len(use)
        masks[mask] = use
    estimates, residuals = {}, []
    for cell, mask, owner, alias, policy in CELLS:
        rows = masks[mask]
        if not rows:
            continue
        arcs = fragments(rows, owner, alias, index)
        fitted = {}
        for arm in ARMS:
            result = (
                _least_fit(arcs, tile, region, half, arm)
                if policy == "lean"
                else _clock_fit(arcs, tile, region, half, arm, priors, model, policy == "diagonal")
            )
            xy, phases, radio, loss, stage = result
            site, latlon = region.site(xy)
            error = []
            for g, phase, correction in zip(arcs, phases, radio, strict=True):
                physical = exact.project(tile, g.orbit, g.t, site, phase, g.rf)[0]
                residual = g.y - physical - correction
                error.extend(residual)
                for row, measured, frequency, pred, e in zip(
                    g.rows, g.y, physical, physical + correction, residual, strict=True
                ):
                    residuals.append(
                        dict(
                            cell=cell,
                            arm=arm,
                            id=row["id"],
                            component=row["component"],
                            receiver=row["rx"],
                            channel=row["channel"],
                            time_s=row["time_s"],
                            rf_hz=row["rf_hz"],
                            norad=g.norad,
                            phase_s=float(phase),
                            folded_hz=row["folded_hz"],
                            lifted_hz=float(measured),
                            orbit_hz=float(frequency),
                            predicted_hz=float(pred),
                            residual_hz=float(e),
                            archived_v5_residual_hz=row["archived_residual_hz"][arm],
                        )
                    )
            fitted[arm] = dict(
                latlon=None,
                forced_latlon=latlon,
                rf_rms_hz=float(np.sqrt(np.mean(np.square(error)))),
                objective=loss,
                points=len(rows),
                groups=len(arcs),
                phases_s=dict(
                    zip((str(group.norad) for group in arcs), map(float, phases), strict=True)
                ),
                **stage,
            )
        estimates[cell] = dict(
            status="withheld", boundary=BOUNDARY, reason="diagnostic only", metrics={}, arms=fitted
        )
    return dict(estimates=estimates, residuals=residuals, counts=counts)
