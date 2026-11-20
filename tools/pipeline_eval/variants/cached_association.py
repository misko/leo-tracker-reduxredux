"""Evaluate joint-orbit matches from an alias-centered whitened Gram block."""

from dataclasses import dataclass
from time import process_time

import numpy as np

from . import joint_orbits as joint
from . import robust_em as lean

METHOD = "cached_association"
BOUNDARY = "Stored native GLRT through frozen Graph and cached joint-orbit matching"
ROUND_OFF = 128 * np.finfo(np.float64).eps


@dataclass(frozen=True)
class Features:
    anchor: np.ndarray
    parallel: np.ndarray
    gram: np.ndarray
    constant_norm: float
    phase_energy: np.ndarray


def prepare(arc):
    track = arc.track
    # Remove a whole-period anchor before whitening. The orthogonal projection
    # represents the constant sixth feature as one scalar per remaining feature.
    anchor = np.rint(arc.residual[:, len(track.t) // 2] / lean.PERIOD)
    raw = arc.residual - anchor[:, None] * lean.PERIOD
    n, length = raw.shape
    basis = np.empty((n, 5, length))
    basis[:, 0] = raw @ track.whiten.T
    basis[:, 1:3] = np.swapaxes(arc.xy, 1, 2) @ track.whiten.T
    basis[:, 3] = track.whiten @ track.drift
    basis[:, 4] = arc.phase @ track.whiten.T
    constant = track.whiten.sum(axis=1)
    constant_norm = np.linalg.norm(constant)
    unit = constant / constant_norm
    parallel = basis @ unit
    phase_energy = np.sum(basis[:, 4] ** 2, axis=1)
    basis -= parallel[:, :, None] * unit
    gram = basis @ np.swapaxes(basis, 1, 2)
    return Features(anchor, parallel, gram, float(constant_norm), phase_energy)


def evaluate(arc, state, features):
    """Return matches or signal that stock arithmetic must resolve a rounding edge."""
    track = arc.track
    lane = track.lane
    values = np.array([1, -state.xy[0], -state.xy[1], -state.drift[lane]])
    radio_constant = state.bias[lane] + (track.rf / 1e9 - 11.5) * state.c_hz_per_ghz
    constant = features.constant_norm
    raw_level = features.parallel[:, :4] @ values - constant * radio_constant
    phase_level = features.parallel[:, 4]
    shift_level = phase_level * state.phase[arc.orbit]
    relative_alias = (raw_level - shift_level) / (lean.PERIOD * constant)
    absolute_alias = features.anchor + relative_alias
    alias = np.rint(absolute_alias)
    # Ties-to-even depends on the parity of the absolute integer. The original
    # direct reduction supplies its rounding order at near-half integers.
    resolution = np.maximum(1, np.abs(features.anchor) + np.abs(relative_alias))
    if np.any(0.5 - np.abs(absolute_alias - alias) <= ROUND_OFF * resolution):
        return None
    dc = raw_level - (alias - features.anchor) * (lean.PERIOD * constant)
    contraction = features.gram[:, :, :4] @ values
    centered_energy = contraction[:, :4] @ values
    reference_scale = np.diagonal(features.gram, axis1=1, axis2=2)[:, :4] @ (values**2)
    if np.any(centered_energy < ROUND_OFF * reference_scale):
        return None
    weight = joint._weight(arc) / len(track.t)
    energy = weight * (centered_energy + dc**2)
    impulse = weight * (contraction[:, 4] + dc * phase_level)
    information = weight * features.phase_energy
    return tuple(
        joint.Match(int(orbit), (float(e), float(g), float(s)), int(k))
        for orbit, e, g, s, k in zip(arc.orbit, energy, impulse, information, alias, strict=True)
    )


class Matcher:
    """Own the lazily reused cache and matched timing within a single inference."""

    def __init__(self, stock, cached):
        self.stock = stock
        self.cached = cached
        self.features = {}
        self.calls = self.fallbacks = 0
        self.prepare_cpu_s = self.matches_cpu_s = 0.0
        self.bytes = 0

    def __call__(self, arc, state):
        began = process_time()
        self.calls += 1
        try:
            if self.cached:
                key = id(arc)
                if key not in self.features:
                    prep_start = process_time()
                    features = prepare(arc)
                    self.features[key] = (arc, features)
                    self.bytes += (
                        sum(
                            array.nbytes
                            for array in (
                                features.anchor,
                                features.parallel,
                                features.gram,
                                features.phase_energy,
                            )
                        )
                        + 8
                    )
                    self.prepare_cpu_s += process_time() - prep_start
                matches = evaluate(arc, state, self.features[key][1])
                if matches is not None:
                    return matches
                self.fallbacks += 1
            return self.stock(arc, state)
        finally:
            self.matches_cpu_s += process_time() - began

    def receipt(self):
        return dict(
            calls=self.calls,
            direct_fallbacks=self.fallbacks,
            gram_preparation_cpu_s=self.prepare_cpu_s,
            match_and_preparation_cpu_s=self.matches_cpu_s,
            cached_tracks=len(self.features),
            cache_array_bytes=self.bytes,
        )
