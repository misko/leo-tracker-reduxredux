"""Research position proposal with a finite Gaussian profile and family splits."""

from collections import Counter
from itertools import product

import numpy as np
from scipy.linalg import solve

from leo.analysis.localization_v3.scan import group
from leo.analysis.localization_v3.tracks import active_curvature
from leo.analysis.research.continuous_curve_fit import (
    paired_phase_states,
    phase_frequency_from_states,
)
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.retained_track_likelihood import PERIOD

ARMS = ("c0", "fitted_c")
BIAS_SIGMA_HZ = 1000.0
PHASE_LIMIT_S = 15.0


def nominate(tracks, bank, region, noise):
    samples = [np.linspace(0, len(t["times"]) - 1, min(9, len(t["times"])), dtype=int)
               for t in tracks]
    times = np.unique(np.concatenate([t["times"][i] for t, i in zip(tracks, samples, strict=True)]))
    geometry = prepare_phase_geometry(bank, times)
    frequency, elevation, derivative = phase_linear_frequency(geometry, *region.center)
    ranked = []
    for track, sample in zip(tracks, samples, strict=True):
        indices = np.searchsorted(times, track["times"][sample])
        q = track["rf_hz"] / 11.5e9
        response = track["values"][sample] - q * frequency[:, indices]
        phase_column = q * derivative[:, indices]
        y = response - response.mean(axis=1, keepdims=True)
        h = phase_column - phase_column.mean(axis=1, keepdims=True)
        prior = (noise / np.maximum(1., bank["phase_sigma_s"])) ** 2
        phase = np.sum(y * h, axis=1) / (np.sum(h * h, axis=1) + prior)
        phase = np.clip(phase, -PHASE_LIMIT_S, PHASE_LIMIT_S)
        residual = response - phase_column * phase[:, None]
        alias = np.rint(-residual.mean(axis=1) / PERIOD).astype(int)
        residual += PERIOD * alias[:, None]
        bias = residual.mean(axis=1)
        residual -= bias[:, None]
        squared = np.sum(residual * residual, axis=1)
        score = ((squared + prior * phase**2) / noise**2
                 + bias**2 / (BIAS_SIGMA_HZ**2 + noise**2 / len(sample)))
        score[elevation[:, indices].min(axis=1) < 0.] = np.inf
        winner, alternate = np.argsort(score, kind="stable")[:2]
        if not np.isfinite(score[winner]):
            continue
        if squared[winner] / len(sample) > 450.**2 or abs(bias[winner]) > 3000.:
            continue
        ranked.append((track, int(winner), int(alias[winner]),
                       float(score[alternate] - score[winner])))
    return ranked


def eliminate_track_offsets(array, track_slices, noise):
    """Whiten after integrating independent zero-mean Gaussian track offsets."""
    result = array / noise
    for rows in track_slices:
        count = rows.stop - rows.start
        shrinkage = 1. - noise / np.sqrt(noise**2 + count * BIAS_SIGMA_HZ**2)
        result[rows] -= shrinkage * result[rows].mean(axis=0)
    return result


def ridge_profile(gram, rhs, square):
    candidate = solve(gram + np.eye(len(rhs)), rhs, assume_a="pos", check_finite=False)
    return max(0., float(square - rhs @ candidate)), candidate


class FamilyProfile:
    def __init__(self, nominations, bank, region, noise):
        self.region, self.noise = region, noise
        tracks, owners, aliases, _ = zip(*nominations, strict=True)
        counts = np.array([len(t["times"]) for t in tracks])
        ends = np.r_[0, np.cumsum(counts)]
        self.slices = [slice(a, b) for a, b in zip(ends[:-1], ends[1:], strict=True)]
        self.times = np.concatenate([t["times"] for t in tracks])
        self.labels, indices = np.unique(owners, return_inverse=True)
        self.family = np.repeat(indices, counts)
        self.values = np.concatenate([t["values"] + PERIOD * a
                                      for t, a in zip(tracks, aliases, strict=True)])
        self.q = np.repeat([t["rf_hz"] / 11.5e9 for t in tracks], counts)
        self.phase_sigma = np.maximum(1., bank["phase_sigma_s"][self.labels])
        all_owners = np.repeat(owners, counts)
        zero = np.zeros(len(bank["norad"]))
        self.states = [paired_phase_states(bank, self.times, all_owners, zero + dt)
                       for dt in (0., -.05, .05)]

        # One fixed layout for both arms and all hypotheses. The c column is
        # last so the fixed-zero arm removes exactly that column.
        hardware = np.zeros((len(self.times), 8))
        for rows, t in zip(self.slices, tracks, strict=True):
            radio_group = group(t)
            drift = 4 + 2 * (t["receiver"] - 1)
            hardware[rows, radio_group] = PERIOD / np.sqrt(12.)
            hardware[rows, drift] = t["times"] - 150.
            hardware[rows, drift + 1] = (t["times"] - 150.) * (-.5 if radio_group % 2 == 0 else .5)
        self.radio = np.c_[hardware, (self.q * 11.5 - 11.5) * 200000.]
        support = np.bincount(self.family)
        order = np.argsort(-support, kind="stable")
        self.splits = [np.isin(self.family, part) for part in (order[::2], order[1::2])]
        self.cache = {}

    def at(self, point):
        point = tuple(point)
        if point in self.cache:
            return self.cache[point]
        latlon = self.region.latlon(point)
        latlon = latlon[0], (latlon[1] + 180.) % 360. - 180.
        (frequency, elevation), (minus, _), (plus, _) = [
            phase_frequency_from_states(*state, *latlon) for state in self.states
        ]
        phase = self.q * (plus - minus) / .1 * self.phase_sigma[self.family]
        features = np.zeros((len(phase), 9 + len(self.labels)))
        features[:, :8] = self.radio[:, :8]
        features[np.arange(len(phase)), 8 + self.family] = phase
        features[:, -1] = self.radio[:, -1]
        raw = self.values - self.q * frequency
        design = eliminate_track_offsets(features, self.slices, self.noise)
        response = eliminate_track_offsets(raw, self.slices, self.noise)
        grams = []
        for mask in self.splits:
            a, y = design[mask], response[mask]
            grams.append((a.T @ a, a.T @ y, y @ y))
        metrics = []
        combined = tuple(a + b for a, b in zip(*grams, strict=True))
        for gram, rhs, square in (combined, *grams):
            metrics.append([ridge_profile(gram[:width, :width], rhs[:width], square)
                            for width in (features.shape[1] - 1, features.shape[1])])
        rms = []
        for _, coef in metrics[0]:
            residual = raw - features[:, :len(coef)] @ coef
            for rows in self.slices:
                count = rows.stop - rows.start
                variance = count * BIAS_SIGMA_HZ**2
                residual[rows] -= variance / (self.noise**2 + variance) * residual[rows].mean()
            rms.append(float(np.sqrt(np.mean(residual * residual))))
        result = dict(scores=[[r[0] for r in pair] for pair in metrics], rms=rms,
                      phases=[float(np.max(np.abs(coef[8:8 + len(self.labels)] * self.phase_sigma)))
                              for _, coef in metrics[0]], visible=bool(np.min(elevation) >= 0.))
        self.cache[point] = result
        return result

    def minimize(self):
        coarse = self.region.grid
        radius = self.region.half_width_km
        fits = []
        for part in range(3):
            paired = []
            for arm in range(2):
                def score(point, part=part, arm=arm):
                    result = self.at(point)
                    return result["scores"][part][arm] if result["visible"] else np.inf

                point = np.array(min(coarse, key=score))
                for spacing in (.125, .0625, .03125, .015625, .0078125):
                    offsets = np.array(list(product((-1, 0, 1), repeat=2)))
                    points = np.clip(point + offsets * self.region.width_km * spacing,
                                     -radius, radius)
                    point = min(points, key=score)
                competing = min(score(x) for x in coarse
                                if np.linalg.norm(point - x) >= self.region.width_km / 4)
                if not np.isfinite(score(point)):
                    return None
                paired.append((point, score(point), min(1e30, competing - score(point))))
            fits.append(paired)
        return fits


def propose(prepared, region):
    if prepared["status"] != "inputs_prepared":
        return dict(fallback=["inputs"])
    tracks = [dict(t, times=np.asarray(t["times"]), values=np.asarray(t["values"]))
              for t in prepared["tracks"]["tracks"]]
    tracks = [t for t in tracks if active_curvature(t)]
    if not tracks or len(prepared["sky"]["bank"]["norad"]) < 2:
        return dict(fallback=["track_or_catalogue_support"])
    noise = float(prepared["noise"]["constant_radio_sigma_hz"])
    bank = prepared["sky"]["bank"]
    rows = nominate(tracks, bank, region, noise)
    counts = Counter(owner for _, owner, _, _ in rows)
    total = sum(len(t["times"]) for t in tracks)
    unique = sum(len(t["times"]) for t, _, _, margin in rows if margin >= 9.)
    issues = []
    if unique < .8 * total:
        issues.append("ambiguous_or_unmatched_ownership")
    report = dict(fallback=issues, curved_points=total, robust_nomination_points=unique,
                  nominated_tracks=len(rows), families=len(counts))
    if len(counts) < 6:
        issues.append("family_support")
        return report
    try:
        model = FamilyProfile(rows, bank, region, noise)
        fits = model.minimize()
    except np.linalg.LinAlgError:
        issues.append("unstable_profile_factorization")
        return report
    if fits is None:
        issues.append("visibility")
        return report
    report["arms"] = arms = {}
    for index, arm in enumerate(ARMS):
        (point, score, margin), (left, *_), (right, *_) = [item[index] for item in fits]
        distance = float(np.linalg.norm(left - right))
        metrics = model.at(point)
        arms[arm] = dict(latlon=list(region.latlon(point)), east_north_km=point.tolist(),
                         profiled_quadratic=score, rf_rms_hz=metrics["rms"][index],
                         split_distance_km=distance, remote_grid_gap=margin,
                         maximum_phase_s=metrics["phases"][index])
        if distance > 2.:
            issues.append(f"{arm}_split_disagreement")
        if region.half_width_km - np.max(np.abs(point)) < 1.:
            issues.append(f"{arm}_boundary")
        if margin < 9.:
            issues.append(f"{arm}_weak_grid_minimum")
        if metrics["phases"][index] > PHASE_LIMIT_S:
            issues.append(f"{arm}_phase_tangent")
    report["evaluated_points"] = len(model.cache)
    return report
