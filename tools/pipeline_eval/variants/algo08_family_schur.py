"""Profile a fixed regional linearization by eliminating track and family blocks."""

from dataclasses import dataclass

import numpy as np
from scipy.linalg import cho_factor, cho_solve


@dataclass(frozen=True)
class TrackBlock:
    group: int
    gram: np.ndarray
    rhs: np.ndarray
    energy: float


@dataclass(frozen=True)
class FamilyBlock:
    modes: tuple[int, ...]
    tracks: tuple[TrackBlock, ...]


@dataclass(frozen=True)
class ReducedFamily:
    modes: tuple[int, ...]
    radio_gram: np.ndarray
    radio_rhs: np.ndarray
    cross: np.ndarray
    mode_mean: np.ndarray
    mode_covariance: np.ndarray
    track_updates: tuple
    logdet: float


class TrackStatistics:
    """Own frozen, noise-normalized geometry. Gamma weights are set at reduction."""

    def __init__(self, design, raw, sigma, groups, family_groups, shared_width, family_modes):
        raw, sigma, design, groups = map(np.asarray, (raw, sigma, design, groups))
        self.shared_width = shared_width
        self.family_groups = tuple(family_groups)
        self.width = shared_width + sum(map(len, family_modes)) + len(family_groups)
        if (raw.ndim != 1 or sigma.shape != raw.shape or groups.shape != raw.shape
                or len(raw) == 0 or design.shape != (len(raw), self.width)
                or np.any(sigma <= 0) or groups.dtype.kind not in "iu"
                or np.any(groups < 0) or np.any(groups >= len(family_groups))
                or not all(np.isfinite(v).all() for v in (raw, sigma, design))):
            raise ValueError("Invalid grouped regional linearization")
        modes = tuple(j for cols in family_modes for j in cols)
        if sorted(modes) != list(range(shared_width, self.width - len(family_groups))):
            raise ValueError("Partition the local modes among all families")
        self.track_start = self.width - len(family_groups)
        active = [[] for _ in family_modes]
        for group, family in enumerate(family_groups):
            if not 0 <= family < len(family_modes):
                raise ValueError("Missing track family membership")
            use = groups == group
            if not use.any():
                continue
            cols = [*range(shared_width), *family_modes[family], self.track_start + group]
            supported = np.zeros(self.width, dtype=bool)
            supported[cols] = True
            rows = design[use]
            if np.any(rows[:, ~supported]):
                raise ValueError("Cross-family mode or cross-track constant")
            normalized = rows[:, cols] / sigma[use, None]
            rhs = raw[use] / sigma[use]
            active[family].append(TrackBlock(group, normalized.T @ normalized,
                                             normalized.T @ rhs, float(rhs @ rhs)))
        self.families = tuple(FamilyBlock(tuple(cols), tuple(blocks))
                              for cols, blocks in zip(family_modes, active, strict=True))

    def reduce(self, track_weights, prior_precision):
        """Refactor whenever a variational noise or prior precision changes."""
        track_weights, prior = map(np.asarray, (track_weights, prior_precision))
        if (track_weights.shape != (len(self.family_groups),) or prior.shape != (self.width,)
                or np.any(track_weights < 0) or np.any(prior <= 0)
                or not all(np.isfinite(a).all() for a in (track_weights, prior))):
            raise ValueError("Matching finite nonnegative weights and positive priors required")
        return ReducedProblem(self, track_weights.copy(), prior.copy())


class ReducedProblem:
    """A fixed-weight Gaussian factorization with leave-family-out radio downdates."""

    def __init__(self, statistics, point_weights, prior):
        self.statistics, self.prior = statistics, prior
        n = statistics.shared_width
        self.n = n
        self.blocks = tuple(self._factor_family(block, point_weights)
                            for block in statistics.families)
        self.radio_gram = np.diag(prior[:n])
        self.radio_rhs = np.zeros(n)
        for block in self.blocks:
            self.radio_gram += block.radio_gram
            self.radio_rhs += block.radio_rhs

    def _factor_family(self, family, weights):
        n = self.n
        modes = list(family.modes)
        gram = np.diag(np.r_[np.zeros(n), self.prior[modes]])
        rhs = np.zeros(len(gram))
        track_updates = []
        logdet = 0.
        for track in family.tracks:
            weight = weights[track.group]
            k = self.statistics.track_start + track.group
            diagonal = weight * track.gram[-1, -1] + self.prior[k]
            cross = weight * track.gram[:-1, -1]
            mean = weight * track.rhs[-1] / diagonal
            transfer = cross / diagonal
            gram += weight * track.gram[:-1, :-1] - np.outer(cross, transfer)
            rhs += weight * track.rhs[:-1] - cross * mean
            logdet += np.log(diagonal / self.prior[k])
            track_updates.append((k, mean, transfer, 1 / diagonal))
        root = cho_factor(gram[n:, n:], lower=True)
        radio_mode = gram[:n, n:]
        combined = np.column_stack((rhs[n:], radio_mode.T))
        posterior = cho_solve(root, combined)
        mode_mean, transfer = posterior[:, 0], posterior[:, 1:]
        mode_covariance = cho_solve(root, np.eye(len(modes)))
        logdet += 2 * np.log(np.diag(root[0])).sum() - np.log(self.prior[modes]).sum()
        return ReducedFamily(family.modes, gram[:n, :n] - radio_mode @ transfer,
                             rhs[:n] - radio_mode @ mode_mean, transfer, mode_mean,
                             mode_covariance, tuple(track_updates), float(logdet))

    def solve(self, *, omit=None):
        """Omit one family at frozen weights and recover the VB marginal diagonals."""
        if omit is not None and not 0 <= omit < len(self.blocks):
            raise ValueError("Invalid family omission")
        n = self.n
        gram, rhs = self.radio_gram, self.radio_rhs
        if omit is not None:
            block = self.blocks[omit]
            gram, rhs = gram - block.radio_gram, rhs - block.radio_rhs
        root = cho_factor(gram, lower=True)
        radio = cho_solve(root, rhs)
        cov_radio = cho_solve(root, np.eye(n))
        coefficients = np.zeros(len(self.prior))
        diagonal = 1 / self.prior
        coefficients[:n], diagonal[:n] = radio, np.diag(cov_radio)
        logdet = 2 * np.log(np.diag(root[0])).sum() - np.log(self.prior[:n]).sum()
        covariances = {}
        for index, block in enumerate(self.blocks):
            if index == omit:
                continue
            modes = list(block.modes)
            family_mean = block.mode_mean - block.cross @ radio
            full = np.r_[radio, family_mean]
            cov_mode_radio = -block.cross @ cov_radio
            cov_mode = block.mode_covariance - cov_mode_radio @ block.cross.T
            cov = np.block([[cov_radio, cov_mode_radio.T], [cov_mode_radio, cov_mode]])
            coefficients[modes], diagonal[modes] = family_mean, np.diag(cov_mode)
            logdet += block.logdet
            for k, mean, transfer, diag in block.track_updates:
                cov_cross = -cov @ transfer
                diagonal[k] = diag - transfer @ cov_cross
                coefficients[k] = mean - transfer @ full
                covariances[k - self.statistics.track_start] = (cov, cov_cross, diagonal[k])
        return coefficients, diagonal, float(logdet), covariances


def track_moments(statistics, coefficients, covariances):
    """Residual energies and covariance traces for the normal-Gamma update."""
    energy = np.zeros(len(statistics.family_groups))
    variance = np.zeros_like(energy)
    for family in statistics.families:
        base = [*range(statistics.shared_width), *family.modes]
        for track in family.tracks:
            g = track.group
            if g not in covariances:
                continue
            mu = coefficients[[*base, statistics.track_start + g]]
            cov, cross, last = covariances[g]
            gram = track.gram
            energy[g] = track.energy - 2 * (mu @ track.rhs) + mu @ gram @ mu
            variance[g] = (np.sum(gram[:-1, :-1] * cov) + 2 * (gram[-1, :-1] @ cross)
                           + gram[-1, -1] * last)
    return energy, variance
