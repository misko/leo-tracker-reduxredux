"""Lobatto compression of the all-catalogue Doppler shortlist."""

from collections import Counter
from dataclasses import dataclass, replace
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np
from numpy.polynomial.legendre import legvander
from scipy.interpolate import BarycentricInterpolator

from . import joint_orbits as joint
from . import robust_em as lean
from . import robust_orbit_fit as exact

METHODS = ("all_samples", "uniform_samples", "track_quadrature")
BOUNDARY = "Stored original GLRT peaks through Graph and a paired native joint orbit fit"
NODE_COUNT = 8


def lobatto(support, count):
    """Positive endpoint-inclusive quadrature for an empirical measure on [-1, 1]."""
    inner = support[1:-1]
    # Rayleigh-Ritz multiplication by time under (1-x²) times the empirical measure.
    design = np.sqrt(1 - inner**2)[:, None] * legvander(inner, count - 3)
    basis = np.linalg.qr(design, mode="reduced")[0]
    nodes = np.r_[-1.0, np.linalg.eigvalsh(basis.T @ (inner[:, None] * basis)), 1.0]
    moment = legvander(support, count - 1).mean(axis=0)
    mass = np.linalg.solve(legvander(nodes, count - 1).T, moment)
    if np.any(mass <= 0):
        raise ValueError("nonpositive empirical Lobatto mass")
    return nodes, mass


@dataclass(frozen=True)
class CompressedTrack:
    times: np.ndarray
    transform: np.ndarray
    observed: np.ndarray
    noise: float

    def rank(self, frequency, derivative):
        residual = self.observed - (frequency - frequency[:, :1])[:, 1:] @ self.transform
        slope = (derivative - derivative[:, :1])[:, 1:] @ self.transform
        return phase_score(residual, slope, self.noise)


def compress(track, method):
    """Retain the full original GLS metric on the interpolant's column space."""
    half = np.ptp(track.t) / 2
    x = (track.t - track.t[0]) / half - 1
    x[-1] = 1.0
    n = NODE_COUNT
    if method == "track_quadrature":
        nodes, mass = lobatto(x, n)
        times = track.t[0] + half * (1 + nodes)
        times[[0, -1]] = track.t[[0, -1]]
    else:
        take = np.rint(np.linspace(0, len(x) - 1, n)).astype(int)
        nodes, mass, times = x[take], np.full(n, 1 / n), track.t[take]
    # Fix the seed because SciPy permutes multiplication order in barycentric weights.
    basis = BarycentricInterpolator(nodes, np.eye(n), random_state=0)(x)[:, 1:]
    one = track.whiten.sum(axis=1)
    sqrt_mass = np.sqrt(mass[1:])
    columns = lean._unlevel((track.whiten @ (basis / sqrt_mass)).T, one).T
    q, r = np.linalg.qr(columns, mode="reduced")
    y = lean._unlevel(track.whiten @ (track.hz - track.hz[0]), one)
    observed = y @ q
    remainder = y - q @ observed
    return CompressedTrack(times, sqrt_mass[:, None] * r.T, observed, float(remainder @ remainder))


def geometry(tile, times, rf, *, gradients):
    p, v, a = exact.grid._interpolated_states(tile, times)
    d = p - tile.ecef_center_km
    distance = np.linalg.norm(d, axis=-1)
    ray = d / distance[..., None]
    visible = np.flatnonzero((ray @ tile.enu_frame[2] >= -0.035).all(axis=1))
    ray, v, a, distance = (array[visible] for array in (ray, v, a, distance))
    radial = (ray * v).sum(axis=-1)
    transverse = v - radial[..., None] * ray
    scale = rf / exact.grid.LIGHT_SPEED_KM_S
    f = -scale * radial
    fdot = -scale * ((ray * a).sum(axis=-1) + np.sum(transverse**2, axis=-1) / distance)
    xy = scale * (transverse @ tile.enu_frame[:2].T) / distance[..., None] if gradients else None
    return visible, f, fdot, xy


def phase_score(shape, slope, constant=0.0):
    phase = np.clip(
        (shape * slope).sum(axis=1) / (np.sum(slope**2, axis=1) + 1 / lean.PHASE_SD_S**2),
        -lean.PHASE_BOUND_S,
        lean.PHASE_BOUND_S,
    )
    cost = np.sum((shape - phase[:, None] * slope) ** 2, axis=1) + (phase / lean.PHASE_SD_S) ** 2
    return cost + constant, phase


def exact_arc(tile, track, selected=None):
    if selected is not None:
        tile = replace(
            tile,
            positions_km=tile.positions_km[selected],
            velocities_km_s=tile.velocities_km_s[selected],
        )
    rows, f, fdot, xy = geometry(tile, track.t, track.rf, gradients=True)
    if not len(rows):
        return None
    raw = track.hz - f
    one = track.whiten.sum(axis=1)
    cost, phase = phase_score(
        lean._unlevel(raw @ track.whiten.T, one), lean._unlevel(fdot @ track.whiten.T, one)
    )
    keep = np.argsort(cost, kind="stable")[: lean.SHORTLIST]
    rows = selected[rows] if selected is not None else rows
    return lean.Arc(
        track, rows[keep], raw[keep], xy[keep], fdot[keep], cost[keep] / len(track.t), phase[keep]
    )


class Trial:
    def __init__(self, method):
        self.method = method
        self.wall, self.cpu, self.work = Counter(), Counter(), Counter()
        self.shortlists, self.owners, self.held = [], [], []

    def timed(self, stage, operation, *args, **kwargs):
        start, cpu = perf_counter(), process_time()
        out = operation(*args, **kwargs)
        self.wall[stage] += perf_counter() - start
        self.cpu[stage] += process_time() - cpu
        return out

    def screen(self, tile, track):
        n, satellites = len(track.t), len(tile.positions_km)
        self.work["full_possible_cells"] += n * satellites
        self.work["screen_tracks"] += 1
        if self.method == "all_samples" or n <= NODE_COUNT:
            self.work["screen_cells"] += n * satellites
            arc = self.timed("screen", exact_arc, tile, track)
        else:
            self.work["compressed_tracks"] += 1
            packed = self.timed("node_pack", compress, track, self.method)

            def nominate():
                rows, f, fdot, _ = geometry(tile, packed.times, track.rf, gradients=False)
                cost, _ = packed.rank(f, fdot)
                return rows[np.argsort(cost, kind="stable")[: lean.SHORTLIST]]

            self.work["screen_cells"] += len(packed.times) * satellites
            chosen = self.timed("screen", nominate)
            self.work["rescore_cells"] += n * len(chosen)
            arc = (
                self.timed("exact_rescore", exact_arc, tile, track, np.sort(chosen))
                if len(chosen)
                else None
            )
            self.work["screen_visibility_losses"] += len(chosen) - (
                0 if arc is None else len(arc.orbit)
            )
        self.shortlists.append(
            dict(
                t0_s=float(track.t[0]),
                t1_s=float(track.t[-1]),
                rf_hz=track.rf,
                lane=track.lane,
                points=n,
                orbit_rows=[] if arc is None else arc.orbit.tolist(),
            )
        )
        return arc

    @staticmethod
    def assignments(rows):
        return [
            dict(
                t0_s=float(r.arc.track.t[0]),
                t1_s=float(r.arc.track.t[-1]),
                rf_hz=r.arc.track.rf,
                lane=r.arc.track.lane,
                points=len(r.arc.track.t),
                orbit=r.orbit,
                alias=r.alias,
                loss=r.loss,
                margin=float(r.margin) if np.isfinite(r.margin) else None,
            )
            for r in rows
        ]

    def validation(self, arcs, state):
        predicted = self.timed("held_validation", lean.assign, arcs, state, update_phase=False)
        self.held.append(self.assignments(predicted))
        good = [row for row in predicted if row.loss <= joint.OUTLIER_CEILINGS[-1]]
        return dict(
            held_score=float(np.mean([1 / (1 + row.loss) for row in predicted])),
            held_normalized_mean_loss=float(np.mean([row.loss for row in predicted])),
            held_compatible_tracks=len(good),
            held_orbits=len({row.orbit for row in good}),
        )

    def infer(self, document, offer, catalogue):
        refine, project = exact.refine, exact.project

        def final(rows, fit, tile, region, half, arm):
            if not self.owners:
                self.owners = self.assignments(rows)
            self.work["final_fit_calls"] += 1
            return self.timed("final_correction", refine, rows, fit, tile, region, half, arm)

        def projection(tile, orbit, times, site, phase, rf):
            self.work["final_correction_cells"] += len(times)
            return project(tile, orbit, times, site, phase, rf)

        with (
            patch.object(
                lean, "observations", wraps_clock(self, "validate_pack", lean.observations)
            ),
            patch.object(
                exact.grid,
                "prepare_sky",
                wraps_clock(self, "catalogue_init", exact.grid.prepare_sky),
            ),
            patch.object(
                exact.grid,
                "make_tile",
                wraps_clock(self, "regional_propagation", exact.grid.make_tile),
            ),
            patch.object(lean, "shortlist", self.screen),
            patch.object(joint, "solve", wraps_clock(self, "paired_solve", joint.solve)),
            patch.object(joint, "_validation", self.validation),
            patch.object(exact, "refine", final),
            patch.object(exact, "project", projection),
        ):
            result = joint.infer(document, offer, catalogue)
        for clock in (self.wall, self.cpu):
            solve = clock.pop("paired_solve", 0)
            if solve:
                clock["shared_association_and_fit"] = (
                    solve - clock["held_validation"] - clock["final_correction"]
                )
        result["boundary"] = BOUNDARY
        result["metrics"].update(
            stage_wall_s=dict(self.wall),
            stage_cpu_s=dict(self.cpu),
            work=dict(self.work),
            shortlists=self.shortlists,
            owners=self.owners,
            held_by_arm_rows=dict(zip(lean.ARMS, self.held, strict=False)),
        )
        return result


def wraps_clock(trial, name, operation):
    def timed(*args, **kwargs):
        return trial.timed(name, operation, *args, **kwargs)

    return timed
