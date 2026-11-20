"""Score fixed v5 cavity phase nominations in receiver-mode space."""

from dataclasses import dataclass

import numpy as np
from scipy.linalg import cho_solve

PERIOD = 1 / 4.4e-6
COMPONENT_SIGMA_HZ = 300.0
BLOCK_ROWS = 48
METHOD = "v5_cavity_covariance"
BOUNDARY = "Complete compact v5 with low-rank cavity nomination"


@dataclass(frozen=True)
class BaseCovariance:
    noise: np.ndarray
    radio: np.ndarray
    radio_covariance: np.ndarray
    groups: np.ndarray

    def dense(self):
        return (
            np.diag(self.noise**2)
            + self.radio @ self.radio_covariance @ self.radio.T
            + COMPONENT_SIGMA_HZ**2 * (self.groups[:, None] == self.groups[None, :])
        )


class ModeSpace:
    def __init__(self, covariance):
        self.inverse_noise = 1 / covariance.noise
        self.logdet = 2 * float(np.log(covariance.noise).sum())
        self.components = []
        for group in np.unique(covariance.groups):
            indices = np.flatnonzero(covariance.groups == group)
            direction = self.inverse_noise[indices]
            information = float(direction @ direction)
            logdet = np.log1p(COMPONENT_SIGMA_HZ**2 * information)
            self.components.append(
                (indices, direction / np.sqrt(information), -np.expm1(-logdet / 2))
            )
            self.logdet += logdet
        radio_root = np.linalg.cholesky(covariance.radio_covariance)
        self.modes = self.base_whiten((covariance.radio @ radio_root).T).T
        self.root = np.linalg.cholesky(np.eye(self.modes.shape[1]) + self.modes.T @ self.modes)
        self.logdet += 2 * float(np.log(np.diag(self.root)).sum())

    def base_whiten(self, rows):
        whitened = rows * self.inverse_noise
        for indices, direction, shrink in self.components:
            part = whitened[:, indices]
            whitened[:, indices] = part - (shrink * (part @ direction))[:, None] * direction
        return whitened

    def augmented_whiten(self, rows):
        white = self.base_whiten(rows)
        coefficient = cho_solve((self.root, True), (white @ self.modes).T).T
        # The posterior residual and standard-prior term form an exact square
        # root of the marginal precision without subtracting large energies.
        return np.column_stack((white - coefficient @ self.modes.T, coefficient))


def coarse_phase_scores(
    values, radio_mean, frequency, derivative, phase_sigma, covariance, groups, *, stock, telemetry
):
    y, r, f, d, sd, g = map(
        np.asarray, (values, radio_mean, frequency, derivative, phase_sigma, groups)
    )
    if (
        f.ndim != 2
        or f.shape != d.shape
        or f.shape[1] != len(y)
        or r.shape != y.shape
        or sd.shape != (len(f),)
        or not np.array_equal(g, covariance.groups)
        or covariance.noise.shape != y.shape
        or covariance.radio.shape[0] != len(y)
    ):
        raise ValueError("matching family data and low-rank factors required")
    space = ModeSpace(covariance)
    aliases = np.zeros((len(f), int(g.max()) + 1), int)
    score, phase = np.empty(len(f)), np.empty(len(f))
    constant = space.logdet + len(y) * np.log(2 * np.pi)
    for begin in range(0, len(f), BLOCK_ROWS):
        sl = slice(begin, begin + BLOCK_ROWS)
        raw = y[None, :] - r[None, :] - f[sl]
        for k in range(aliases.shape[1]):
            use = g == k
            # Preserve the exact frozen arithmetic and parity at integer ties.
            aliases[sl, k] = np.rint(-raw[:, use].mean(axis=1) / PERIOD).astype(int)
        raw = raw + aliases[sl][:, g] * PERIOD
        a = space.augmented_whiten(d[sl] * sd[sl, None])
        b = space.augmented_whiten(raw)
        norm = np.sum(a * a, axis=1)
        z = np.sum(a * b, axis=1) / (1 + norm)
        residual = b - z[:, None] * a
        score[sl] = np.sum(residual * residual, axis=1) + z**2 + np.log1p(norm) + constant
        phase[sl] = z
    # A close adjacent rank can move under the changed floating-point reduction.
    # The unchanged dense function supplies the exact legacy order on that family.
    ordered = np.sort(score)
    gap = np.diff(ordered)
    uncertainty = 2e-10 * np.maximum(1.0, np.abs(ordered[1:]))
    near_rank = bool(np.any(gap <= uncertainty) or not np.isfinite(score).all())
    telemetry.append(
        dict(
            points=len(y),
            candidates=len(f),
            modes=space.modes.shape[1],
            components=len(space.components),
            dense_fallback=near_rank,
            dense_covariance_bytes=8 * len(y) ** 2,
            radio_mode_array_bytes=space.modes.nbytes,
        )
    )
    if near_rank:
        return stock(
            values, radio_mean, frequency, derivative, phase_sigma, covariance.dense(), groups
        )
    return dict(score=score, aliases=aliases, phase_z=phase)
