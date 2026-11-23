"""Saved-only interval pruning and common nominal projection for exact salvage."""

from collections import Counter
from functools import partial
from hashlib import sha256
from pathlib import Path
from time import process_time
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3 import conservative_recovery
from leo.analysis.research import retained_track_likelihood as likelihood
from tools.pipeline_eval.variants import algo08_salvage_bound, v5_tiled_salvage

import lighter_joint_estimator


BYTE_LIMIT = 96 * 2**20
FINE_PINS = {
    v5_tiled_salvage: "a86e62fed9eb7c286747fcf20e246010b3f06774dc9f79843ea7f8610a0fa7b4",
    algo08_salvage_bound: "77db0c8b857242b9e117805158dc129cf5bb45f8fb902c273bd5121ef8bad213",
    likelihood: "73c24d054d5676c7d7051779a6960f8f692ce0d97bc23d292470aa01f6110bcf",
}


def support_feasibility(witness, supports):
    """Mark a support if at least one original phase could clear the radio gate."""
    lo = np.nextafter(witness.raw - witness.limit, -np.inf)
    hi = np.nextafter(witness.raw + witness.limit, np.inf)
    visible = witness.elevation >= 0
    feasible = np.empty(len(supports), bool)
    for reverse in (False, True):
        selected = [(i, len(witness.limit) - a if reverse else b)
                    for i, (a, b) in enumerate(supports) if (a != 0) == reverse]
        if not selected:
            continue
        indices, stops = np.asarray(selected).T
        if reverse:
            lo, hi, visible = lo[:, ::-1], hi[:, ::-1], visible[:, ::-1]
        meets = np.maximum.accumulate(lo, axis=1) <= np.minimum.accumulate(hi, axis=1)
        meets &= np.logical_and.accumulate(visible, axis=1)
        feasible[indices] = meets[:, stops - 1].any(axis=0)
    return feasible


def read_alternative(kernel, scan, j, t, y, noise, rf, f, e, grid, a, b, counts):
    terms = kernel.profile(y[a:b], rf * f[:, a:b], np.diag(1 / noise[a:b]))
    cost = terms["cost"] + grid**2 / 9
    cost[e[:, a:b].min(axis=1) < 0] = np.inf
    best = int(np.argmin(cost))
    residual = terms["residual"][best]
    max_sigma = np.max(abs(residual) / noise[a:b])
    rms, bias = terms["rms"][best], terms["bias"][best]
    if algo08_salvage_bound.defer_noise(residual, t[a:b], rms, bias, cost[best], max_sigma):
        return None
    counts["noise_calls"] += 1
    screen = kernel.batch_noise_screen(residual[None], t[a:b])
    if rms > 450 or abs(bias) > 3000 or not np.isfinite(cost[best]) or not screen["noise_screen_pass"][0] or max_sigma > 6:
        return None
    return dict(start_index=a, stop_index=b, points=b-a, candidate_index=j, norad=int(scan.norads[j]),
                phase_s=float(grid[best]), cost=float(cost[best]), alias=int(terms["alias"][best]),
                rms_hz=float(rms), max_external_radio_sigma=float(max_sigma))


def fine_alternatives(stock, counts, kernel, scan, track, y, noise, rf, shortlist, coordinates):
    t, values = track["times"], track["values"]
    grid = np.linspace(-15, 15, 121)
    supports = [(a, b) for a, b in kernel.selected_supports(len(t))
                if t[b - 1] - t[a] >= 20 and kernel.raw_curvature(dict(times=t[a:b], values=values[a:b]))]
    trials = len(supports) * len(shortlist)
    counts["support_trials"] += trials
    if not supports or not shortlist:
        return [], len(supports)

    def replay():
        counts["fine_replays"] += 1
        return stock(kernel, scan, track, y, noise, rf, shortlist, coordinates)

    tail = len(t)
    if (any(a and b != tail for a, b in supports) or kernel.profile is not likelihood.profile
            or 2 * 8 * grid.size * tail * len(shortlist) > BYTE_LIMIT):
        return replay()
    lengths = sorted({b-a for a, b in supports}, reverse=True)
    by_length = {length: [] for length in lengths}
    states = {}
    start = process_time()
    times, labels = np.tile(t, len(grid)), np.repeat(np.arange(len(grid)), tail)
    for j in sorted(shortlist):
        bank = dict(time_s=scan.sky["time_s"],
                    position_km=np.repeat(scan.sky["position_km"][[j]], len(grid), axis=0),
                    velocity_km_s=np.repeat(scan.sky["velocity_km_s"][[j]], len(grid), axis=0))
        f, e = kernel.paired_phase_frequency(bank, times, labels, grid, *coordinates)
        f, e = f.reshape(len(grid), -1), e.reshape(len(grid), -1)
        witness = algo08_salvage_bound.EndpointWitness.prepare(y, noise, f, e, rf, t)
        if witness is None:
            return replay()
        feasible = support_feasibility(witness, supports)
        if feasible.any():
            states[j] = f, e
        for i in np.flatnonzero(feasible):
            a, b = supports[i]
            by_length[b-a].append((j, a, b))
    counts["fine_proof_cpu_s"] += process_time() - start
    counts["interval_rejected"] += trials - sum(map(len, by_length.values()))

    found = []
    start = process_time()
    for length in lengths:
        rows = by_length[length]
        if len(found) >= 5:
            counts["dominated"] += len(rows)
            continue
        for j, a, b in rows:
            counts["profile_calls"] += 1
            f, e = states[j]
            selected = read_alternative(kernel, scan, j, t, y, noise, rf, f, e, grid, a, b, counts)
            if selected is not None:
                found.append(selected)
    counts["fine_exact_cpu_s"] += process_time() - start
    found.sort(key=lambda row: (-row["points"], row["cost"], row["candidate_index"], row["start_index"], row["stop_index"]))
    return found[:5], len(supports)


class CommonProjection:
    """Share only the immutable nominal projection inside one salvage call."""

    def __init__(self, kernel, scan, keep, counts, byte_limit=BYTE_LIMIT):
        self.kernel, self.scan, self.keep, self.counts = kernel, scan, keep, counts
        self.byte_limit = byte_limit
        self.batch = None
        self.marker = object()
        self.columns = {}

    def __getattr__(self, name):
        return getattr(self.kernel, name)

    def repaired_fit(self, *args, **kwargs):
        fit = self.kernel.repaired_fit(*args, **kwargs)
        p, fitted, _, _ = fit
        missing = [self.scan.tracks[i]["times"] for i, sl in zip(p.members, p.slices, strict=True)
                   if not self.keep[sl].any()]
        if len(missing) < 2 or not all(t.dtype == np.float64 and np.isfinite(t).all() for t in missing):
            return fit
        cells = self.byte_limit // (192 * max(1, len(self.scan.norads)))
        self.coordinates = self.scan.search_region.latlon(fitted["parameters"])
        # Preserve track order.  A batch is allocated only on its first use.
        groups = []
        group, union = [], np.array([], np.float64)
        for t in missing:
            joined = np.union1d(union, t)
            if len(joined) > cells and group:
                groups.append((group, union))
                group, joined = [], np.unique(t)
            group.append(t)
            union = joined
        groups.append((group, union))
        for k, (group, union) in enumerate(groups):
            if len(group) < 2 or len(union) > cells or len(union) == sum(map(len, group)):
                continue
            self.counts["coarse_skipped_duplicate_columns"] += sum(map(len, group)) - len(union)
            for t in group:
                self.columns[id(t)] = k, union, np.searchsorted(union, t)
        return fit

    def prepare_phase_geometry(self, bank, times):
        start = process_time()
        if bank is self.scan.sky and id(times) in self.columns:
            return self.marker, self.columns[id(times)]
        self.counts["coarse_stock_preparations"] += 1
        try:
            return self.kernel.prepare_phase_geometry(bank, times)
        finally:
            self.counts["coarse_projection_cpu_s"] += process_time() - start

    def phase_linear_frequency(self, geometry, *coordinates):
        start = process_time()
        try:
            if not isinstance(geometry, tuple) or geometry[0] is not self.marker:
                return self.kernel.phase_linear_frequency(geometry, *coordinates)
            if tuple(coordinates) != tuple(self.coordinates):
                raise ValueError("Salvage projection coordinate changed within its batch")
            k, union, columns = geometry[1]
            if k != self.batch:
                self.batch = self.planes = None
                base = self.kernel.prepare_phase_geometry(self.scan.sky, union)
                self.planes = self.kernel.phase_linear_frequency(base, *coordinates)
                self.batch = k
                self.counts["coarse_shared_preparations"] += 1
                self.counts["coarse_shared_columns"] += len(union)
            self.counts["coarse_shared_gathers"] += 1
            return tuple(np.ascontiguousarray(plane[:, columns]) for plane in self.planes)
        finally:
            self.counts["coarse_projection_cpu_s"] += process_time() - start


def propose(prepared, region, bound, measured, *, repair, certified, cold_start=None):
    counts = Counter()
    measured["certified_salvage"] = counts
    stock_coarse = conservative_recovery.salvage
    stock_fine = v5_tiled_salvage.fine_alternatives
    supported = (all(sha256(Path(mod.__file__).read_bytes()).hexdigest() == pin for mod, pin in FINE_PINS.items())
                 and isinstance(stock_coarse, partial) and stock_coarse.func is v5_tiled_salvage.salvage
                 and stock_coarse.args[0] is conservative_recovery)
    if not supported:
        counts["unsupported_runtime"] += 1
        return None, "unsupported_certified_salvage_runtime"

    def salvage(scan, node, keep, **kwargs):
        trace = stock_coarse.args[2]
        before = len(trace)
        proxy = CommonProjection(conservative_recovery, scan, keep, counts,
                                 byte_limit=BYTE_LIMIT if certified else 0)
        result = stock_coarse.func(proxy, *stock_coarse.args[1:], scan, node, keep, **kwargs)
        measured["salvage_shortlists"] = trace[before:]
        return result

    fine = partial(fine_alternatives, stock_fine, counts) if certified else stock_fine
    with (patch.object(conservative_recovery, "salvage", salvage),
          patch.object(v5_tiled_salvage, "fine_alternatives", fine)):
        return lighter_joint_estimator.propose(prepared, region, bound, measured, repair=repair, cold_start=cold_start)
