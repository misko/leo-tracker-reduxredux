"""Offer-blind stereo partial matching of offset-invariant Doppler contrasts."""

from dataclasses import dataclass
from time import perf_counter_ns, process_time_ns

import numpy as np
from scipy.optimize import linear_sum_assignment


UNMATCHED = 27.


@dataclass(frozen=True)
class Arc:
    key: str
    receiver: int
    channel: int
    rf_hz: float
    times: np.ndarray
    sample_times: np.ndarray
    values: np.ndarray
    noise: np.ndarray


def sample_arcs(tracks, noise, active):
    use_point_noise = noise["extra_parameter_BIC_gain"] > 0
    result = []
    for track in tracks:
        times = np.asarray(track["times"])
        values = np.asarray(track["values"])
        if len(times) < 6 or not active(dict(track, times=times, values=values)):
            continue
        index = np.rint(np.linspace(0, len(times) - 1, 6)).astype(int)
        fixed_noise = (
            np.array([noise["per_observation_noise_sigma_hz"][oid]
                      for oid in track["observation_ids"]])[index]
            if use_point_noise else np.full(6, noise["constant_radio_sigma_hz"])
        )
        result.append(Arc(
            track["key"], track["receiver"], track["channel"], track["rf_hz"],
            times, times[index], values[index], fixed_noise,
        ))
    return result


def eligible_pairs(arcs):
    return [(i, j) for i, a in enumerate(arcs) for j, b in enumerate(arcs)
            if a.receiver == 1 and b.receiver == 2
            and (a.channel, a.rf_hz) == (b.channel, b.rf_hz)
            and np.intersect1d(a.times, b.times, assume_unique=True).size >= 2]


@dataclass(frozen=True)
class Terms:
    energy: np.ndarray
    cross: np.ndarray
    information: np.ndarray
    visible: np.ndarray
    mean_residual: np.ndarray
    mean_tangent: np.ndarray

    def cost(self, phase):
        cost = self.energy - 2 * phase * self.cross + phase**2 * self.information
        return np.where(self.visible, np.maximum(0., cost), np.inf)


def terms(arc, frequency, elevation, derivative, index):
    rf_scale = arc.rf_hz / 11.5e9
    residual = arc.values - rf_scale * frequency[:, index]
    tangent = rf_scale * derivative[:, index]
    noise = np.hypot(arc.noise[:3], arc.noise[3:][::-1])
    change = (residual[:, 3:][:, ::-1] - residual[:, :3]) / noise
    slope = (tangent[:, 3:][:, ::-1] - tangent[:, :3]) / noise
    return Terms(
        np.sum(change**2, axis=1), np.sum(change * slope, axis=1), np.sum(slope**2, axis=1),
        np.all(elevation[:, index] >= 0, axis=1), residual.mean(axis=1), tangent.mean(axis=1),
    )


def readout(arc, term, j, phase, labels, period):
    phase_s = float(phase[j])
    alias = int(np.rint(-(term.mean_residual[j] - phase_s * term.mean_tangent[j]) / period))
    return dict(track=arc.key, norad=int(labels[j]), phase_s=phase_s, alias=alias)


def independent(arcs, rows, prior, labels, period):
    charge = 2 * np.log(len(labels))
    costs, selected = [], []
    for arc, row in zip(arcs, rows, strict=True):
        phase = np.clip(row.cross / (row.information + prior), -15., 15.)
        objective = row.cost(phase) + prior * phase**2 + charge
        j = int(np.argmin(objective))
        if objective[j] < UNMATCHED:
            costs.append(float(objective[j]))
            selected.append(readout(arc, row, j, phase, labels, period))
        else:
            costs.append(UNMATCHED)
            selected.append(None)
    return costs, selected


def match(edges):
    """Return disjoint savings edges, allowing every row its own zero-cost dummy."""
    if not edges:
        return []
    left = sorted({i for i, _ in edges})
    right = sorted({j for _, j in edges})
    matrix = np.zeros((len(left), len(right) + len(left)))
    for row, i in enumerate(left):
        for column, j in enumerate(right):
            matrix[row, column] = edges.get((i, j), 0)
    rows, columns = linear_sum_assignment(matrix)
    return [(left[r], right[c]) for r, c in zip(rows, columns, strict=True)
            if c < len(right) and matrix[r, c] < 0]


def joint(arcs, rows, pairs, prior, labels, period, costs, original):
    charge = 2 * np.log(len(labels))
    improvements, selected = {}, {}
    for i, j in pairs:
        a, b = rows[i], rows[j]
        phase = np.clip((a.cross + b.cross) / (a.information + b.information + prior), -15., 15.)
        first, second = a.cost(phase), b.cost(phase)
        objective = np.where((first < UNMATCHED) & (second < UNMATCHED),
                             first + second + prior * phase**2 + charge, np.inf)
        k = int(np.argmin(objective))
        gain = float(objective[k]) - costs[i] - costs[j]
        if gain < 0:
            improvements[i, j] = gain
            selected[i, j] = [readout(arcs[t], rows[t], k, phase, labels, period) for t in (i, j)]
    assignments = original.copy()
    paired = match(improvements)
    for i, j in paired:
        assignments[i], assignments[j] = selected[i, j]
    return -sum(improvements[pair] for pair in paired), assignments, paired


def stencil(region):
    from tools.pipeline_eval.variants.experimental.regional_reassignment import probes

    yield dict(side="inside", xy_km=[0., 0.], latlon=region.center)
    near = (1 / 2 - 1 / 256, 1 / 2 + 1 / 256)
    for point in probes(region):
        e, n = point["xy_km"]
        radius = max(abs(e), abs(n)) / region.width_km
        if any(abs(radius - face) < 1e-12 for face in near) or (
                (e == 0 or n == 0) and radius in (1 / 4, 5 / 2)):
            yield point


def prediction(prepared, region):
    from leo.analysis.localization_v3.tracks import active_curvature
    from leo.analysis.research.phase_linear_geometry import (
        phase_linear_frequency,
        prepare_phase_geometry,
    )
    from leo.analysis.research.retained_track_likelihood import PERIOD

    start, wall = process_time_ns(), perf_counter_ns()
    tracks = prepared["tracks"]["tracks"]
    arcs = sample_arcs(tracks, prepared["noise"], active_curvature)
    if not arcs:
        raise ValueError("Expected active curved tracks on the frozen development packet")
    pairs = eligible_pairs(arcs)
    times = np.unique(np.concatenate([arc.sample_times for arc in arcs]))
    index = [np.searchsorted(times, arc.sample_times) for arc in arcs]
    bank = prepared["sky"]["bank"]
    labels = bank["norad"]
    prior = 1 / np.maximum(1., bank["phase_sigma_s"])**2
    geometry = prepare_phase_geometry(bank, times)
    sample_setup = process_time_ns() - start
    projection = score_independent = score_pairing = 0
    points = []
    for probe in stencil(region):
        step = process_time_ns()
        grid = phase_linear_frequency(geometry, *probe["latlon"])
        projection += process_time_ns() - step
        step = process_time_ns()
        evidence = [terms(arc, *grid, ix) for arc, ix in zip(arcs, index, strict=True)]
        costs, selected = independent(arcs, evidence, prior, labels, PERIOD)
        score_independent += process_time_ns() - step
        step = process_time_ns()
        gain, assigned, paired = joint(arcs, evidence, pairs, prior, labels, PERIOD, costs, selected)
        score_pairing += process_time_ns() - step
        loss = sum(costs)
        points.append(dict(probe, independent_loss=loss / len(arcs), joint_loss=(loss - gain) / len(arcs),
                           independent=selected, joint=assigned, pairs=paired, gain=gain))
    if len(points) != 33:
        raise ValueError("Expected the 33 frozen centre and symmetric regional probes")
    clocks = dict(setup=sample_setup, projection=projection, independent=score_independent,
                  extra_joint=score_pairing, total=process_time_ns()-start,
                  elapsed=perf_counter_ns()-wall)
    return dict(points=points, arcs=[dict(track=a.key, receiver=a.receiver, channel=a.channel,
                                         rf_hz=a.rf_hz, observations=len(a.times)) for a in arcs],
                eligible_pairs=pairs, catalogue=len(labels), sampled_times=len(times), clocks_ns=clocks)
