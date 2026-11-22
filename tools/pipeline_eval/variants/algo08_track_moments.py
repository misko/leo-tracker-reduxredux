"""Project local Doppler polynomials during broad regional proposals."""

from copy import copy
from dataclasses import dataclass
from time import process_time
from unittest.mock import patch

import numpy as np
from scipy.linalg import block_diag

from leo.analysis.localization_v3 import discovery, scan as scan_module
from leo.analysis.research.retained_track_likelihood import BIAS, NOISE, PERIOD
from tools.pipeline_eval.variants import v5_core


BIN_SECONDS = 20.0


@dataclass(frozen=True)
class TrackMoments:
    nodes: np.ndarray
    basis: np.ndarray
    transfer: np.ndarray
    ones: np.ndarray
    time: np.ndarray

    def project_observations(self, values):
        """Retain the observed moments and all energy outside the local basis."""
        moments = self.basis.T @ values
        remainder = values - self.basis @ moments
        return moments, float(remainder @ remainder)

    def center(self, moments):
        mean = (moments @ self.ones) / len(self.basis)
        return mean, moments - mean[:, None] * self.ones


def track_moments(times):
    """Represent each nonempty time bin with up to three interpolation nodes."""
    bins = np.flatnonzero(np.diff(np.floor((times - times[0]) / BIN_SECONDS))) + 1
    nodes, bases, transfers = [], [], []
    for piece in np.split(times, bins):
        if len(piece) <= 3:
            nodes.append(piece)
            bases.append(np.eye(len(piece)))
            transfers.append(bases[-1])
            continue
        coordinate = (piece - piece[0]) / (piece[-1] - piece[0])
        middle = 1 + int(np.argmin(abs(coordinate[1:-1] - 0.5)))
        selected = [0, middle, len(piece) - 1]
        polynomial = np.polynomial.polynomial.polyvander(coordinate, 2)
        basis, triangular = np.linalg.qr(polynomial)
        transfer = np.linalg.solve(polynomial[selected].T, triangular.T).T
        nodes.append(piece[selected])
        bases.append(basis)
        transfers.append(transfer)
    basis = block_diag(*bases)
    return TrackMoments(np.concatenate(nodes), basis, block_diag(*transfers),
                        basis.sum(axis=0), basis.T @ ((times - times.mean()) / 150))


def profile(moments, observed, predicted):
    """Stock white profile for a Doppler curve interpolated at the moment nodes."""
    data, remainder = moments.project_observations(observed)
    mean, centered = moments.center(data - predicted @ moments.transfer.T)
    count = len(observed)
    alias = np.rint(-mean / PERIOD)
    folded = mean + alias * PERIOD
    bias = folded * (count / (count + NOISE**2 / BIAS**2))
    energy = np.einsum("ij,ij->i", centered, centered) + remainder + count * (folded - bias)**2
    rms = np.sqrt(energy / count)
    cost = energy / NOISE**2 + (bias / BIAS)**2 + np.log1p(BIAS**2 * count / NOISE**2)
    return dict(rms=rms, cost=cost, bias=bias)


class MomentDiscovery:
    """Restrict time interpolation to broad proposals, keeping the full track context."""

    def __init__(self, scan, detail):
        self.full = scan
        for key in (
            "previous_shape_cache", "causal_uncertainty_modes", "reference_motion_derivatives"
        ):
            scan.__dict__.setdefault(key, {})
        self.scan = copy(scan)
        self.detail = detail
        self.moments = {scan.tracks[i]["key"]: track_moments(scan.tracks[i]["times"])
                        for i in scan.curved}
        compact = self.scan
        compact.times = np.unique(np.concatenate([m.nodes for m in self.moments.values()]))
        compact.geometry = scan_module.prepare_phase_geometry(scan.sky, compact.times)
        self.indices = {key: np.searchsorted(compact.times, m.nodes)
                        for key, m in self.moments.items()}
        detail.update(
            catalogue=len(scan.norads),
            full_curved_points=sum(len(m.basis) for m in self.moments.values()),
            moment_nodes=sum(len(m.nodes) for m in self.moments.values()),
            full_unique_times=len(scan.times), moment_unique_times=len(compact.times),
            association_candidates=0, association_cells=0, counterfactual_association_cells=0,
        )

    def statistics(self, groups, bank, corrections, height=0):
        """Build the release phase-seed statistics using projected residuals."""
        result = {name: [] for name in ("n", "mx", "xx", "g", "q", "mean", "xz", "rss",
                                        "visible")}
        fragments, centered = [], []
        for key, (track,) in groups:
            moments, indexes = self.moments[key], self.indices[key]
            times = track["times"]
            q = track["rf_hz"] / discovery.REFERENCE_RF
            values = track["values"] - corrections[str(track["channel"])]
            data, remainder = moments.project_observations(values)
            f = q * bank[f"doppler_{height}"][:, indexes]
            mean, residual = moments.center(data - f @ moments.transfer.T)
            row = dict(n=len(times), mx=((times - 150) / 150).mean(),
                       xx=moments.time @ moments.time, g=scan_module.group(track), q=q, mean=mean,
                       xz=residual @ moments.time, rss=np.einsum("ij,ij->i", residual, residual)
                       + remainder, visible=np.all(bank["elevation_deg"][:, indexes] >= 0, axis=1))
            for name, value in row.items():
                result[name].append(value)
            fragments.append(track)
            centered.append(residual)
        result = {name: np.asarray(values) for name, values in result.items()}
        order = np.arange(len(fragments))
        shape = np.maximum(0, result["rss"] - result["xz"]**2
                           / np.maximum(result["xx"][:, None], 1e-12))
        return dict(
            result, starts=order, ci=order, count=result["n"], fragments=fragments,
            active=np.ones(len(order), dtype=bool), fragment_active=np.ones(len(order), dtype=bool),
            shape_rms=np.sqrt(shape / result["n"][:, None]),
            component_visible=result["visible"], centered=centered,
        )

    def phase_statistics(self, stats, _times, _frequency, derivative):
        terms = {name: [] for name in ("hm", "hh", "xh", "zh")}
        for track, q, residual in zip(stats["fragments"], stats["q"], stats.pop("centered"),
                                      strict=True):
            key = track["key"]
            moments, indexes = self.moments[key], self.indices[key]
            mean, h = moments.center((q * derivative[:, indexes]) @ moments.transfer.T)
            terms["hm"].append(mean)
            terms["hh"].append(np.einsum("ij,ij->i", h, h))
            terms["xh"].append(h @ moments.time)
            terms["zh"].append(np.einsum("ij,ij->i", h, residual))
        return dict(stats, **{name: np.asarray(values) for name, values in terms.items()})

    def associate(self, state, base, point, method):
        f, elevation, derivative = self.scan.predictions(state, base, point, method)
        rows, nominations = [], {}
        for i in self.scan.curved:
            track = self.full.tracks[i]
            key = track["key"]
            moments, indexes = self.moments[key], self.indices[key]
            observed = track["values"] - self.scan.hardware(track, state["beta"])
            q = track["rf_hz"] / discovery.REFERENCE_RF
            if method == "receiver_smooth":
                observed -= q * self.full.rx_basis[i] @ state["smooth"][track["receiver"] - 1]
            terms = profile(moments, observed, q * f[:, indexes])
            visible = np.all(elevation[:, indexes] >= 0, axis=1)
            j = int(np.argmin(np.where(visible, terms["cost"], np.inf)))
            # Only the ungated lowest-cost nomination enters discovery. The
            # published acceptance gate is run on the exact full-data winner.
            terms.update(parts=np.ones(len(f), dtype=int), split_at=np.full(len(f), -1),
                         passing=np.zeros(len(f), dtype=bool))
            rows.append(dict(component=key, points=len(observed), active_curvature=True,
                             times_s=track["times"]))
            nominations[i] = dict(j=j, terms=terms)
            self.detail["association_candidates"] += len(f)
            self.detail["association_cells"] += len(f) * len(indexes)
            self.detail["counterfactual_association_cells"] += len(f) * len(observed)
        return None, rows, nominations, (f, elevation, derivative)

    def rank(self):
        # The stock policy still learns centre and corner proposals, then ranks
        # unique assignments with the full NormalPosition design and likelihood.
        with (
            patch.object(discovery, "statistics", self.statistics),
            patch.object(discovery, "augment_phase_statistics", self.phase_statistics),
            patch.object(self.scan, "association", self.associate),
        ):
            return v5_core.ranked_initial_nodes(self.scan)


def select(scan, detail):
    started = process_time()
    proposals = MomentDiscovery(scan, detail)
    detail["moment_setup_cpu_s"] = process_time() - started
    start = process_time()
    nodes = proposals.rank()
    detail.update(broad_and_exact_cold_rank_cpu_s=process_time() - start,
                  ranked_signatures=[discovery.signature(node) for node in nodes])
    start = process_time()
    answer, branches = v5_core.fit_initial_nodes(scan, nodes[:3])
    detail["exact_refreshed_fit_cpu_s"] = process_time() - start
    if answer["choices"][0]["arms"]["c0"]["metrics"]["accepted_points"] == 0:
        detail["fallback"] = "empty_full_data_gate"
        if scan.geometry is None:
            scan.geometry = scan_module.prepare_phase_geometry(scan.sky, scan.times)
        return v5_core.initial_selection(scan)
    return answer, branches


def prepare_context(create, prepared, region, noise, bound, previous):
    """Defer the full sky-time matrix for the initial proposal context only."""
    if previous != "previous":
        return create(prepared, region, noise, bound, previous)
    with patch.object(scan_module, "prepare_phase_geometry", return_value=None):
        return create(prepared, region, noise, bound, previous)
