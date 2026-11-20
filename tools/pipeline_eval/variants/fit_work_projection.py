"""Fixed observation-time basis for the constrained cavity residual gates."""

import numpy as np

_BIC_EDGES = (9.89999, 9.9, 10.0)
_EPS = np.finfo(np.float64).eps


class FixedNoiseScreen:
    """Apply a fixed quadratic regression projector to new frequency residuals."""

    def __init__(self, times, stock):
        t = np.array(times, dtype=float, copy=True)
        if t.ndim != 1 or len(t) < 4 or not np.isfinite(t).all() or np.ptp(t) <= 0:
            raise ValueError("finite samples and positive time span required")
        t.setflags(write=False)
        self.times, self.stock = t, stock
        n = len(t)
        x = t - t.mean()
        tx = x / max(float(np.ptp(t)) / 2, 1.0)
        design = np.stack([np.ones(n), tx, tx * tx], axis=1)
        orthogonal, singular, _ = np.linalg.svd(design, full_matrices=False)
        # A nearly rank-deficient design belongs to the original rank decision.
        self.basis = orthogonal if singular[-1] > np.sqrt(_EPS) * singular[0] else None
        self.x, self.x_norm = x, np.sqrt(x @ x)
        self.sqrt_n, self.log_n = np.sqrt(n), np.log(n)
        self.splits = np.arange(4, n - 3)
        self.jump_scale = np.sqrt(1 / self.splits + 1 / (n - self.splits))
        self.bic_radius_scale = 128 * _EPS * n * n

    def __call__(self, residual):
        if self.basis is None:
            return self.stock(residual, self.times)
        r = np.asarray(residual, float)
        n = len(self.times)
        if r.ndim != 2 or r.shape[1] != n or not np.isfinite(r).all():
            raise ValueError("matching finite residual/time samples required")
        mean = r.mean(axis=1)
        sigma = np.maximum(np.std(r, axis=1, ddof=1), 75.0)
        mean_z = np.abs(mean) * self.sqrt_n / sigma
        slope_z = np.abs(r @ self.x) / np.maximum(sigma * self.x_norm, 1e-12)
        fitted = (r @ self.basis) @ self.basis.T
        rss0 = np.maximum(np.sum(r * r, axis=1), n * 75.0**2)
        rss1 = np.maximum(np.sum((r - fitted) ** 2, axis=1), n * 75.0**2)
        bic = n * np.log(rss0 / rss1) - 3 * self.log_n
        # Recompute at gates where representation-level rounding can flip a comparison.
        radius = self.bic_radius_scale * np.maximum(1.0, rss0 / rss1)
        if len(r) == 1:
            value = float(bic[0])
            a, b, c = _BIC_EDGES
            distance = min(abs(value - a), abs(value - b), abs(value - c))
            guarded = not np.isfinite(value) or distance <= radius[0]
        else:
            guarded = not np.isfinite(bic).all() or any(
                np.any(abs(bic - edge) <= radius) for edge in _BIC_EDGES
            )
        if guarded:
            return self.stock(r, self.times)
        splits = self.splits
        if len(splits):
            sums = np.cumsum(r, axis=1)[:, splits - 1]
            jump = sums / splits - (r.sum(axis=1)[:, None] - sums) / (n - splits)
            step_z = np.max(np.abs(jump) / (sigma[:, None] * self.jump_scale), axis=1)
        else:
            step_z = np.zeros(len(r))
        centered = r - mean[:, None]
        acf = np.sum(centered[:, :-1] * centered[:, 1:], axis=1) / np.maximum(
            np.sum(centered * centered, axis=1), 1e-12
        )
        passed = (mean_z <= 3) & (slope_z <= 3) & (bic <= 10) & (step_z <= 4)
        passed &= np.abs(acf) <= 4 / self.sqrt_n
        return dict(
            noise_screen_pass=passed,
            mean_z=mean_z,
            slope_z=slope_z,
            quadratic_bic_gain=bic,
            maximum_step_z=step_z,
            lag1_acf=acf,
        )


def prepare(problem, entries, stock):
    """One basis per distinct held row set in a single matched hypothesis."""
    tracks = problem.scan.tracks
    curved = {
        sl.start: FixedNoiseScreen(tracks[i]["times"][problem.keep[sl]], stock)
        for i, sl in zip(problem.members, problem.slices, strict=True)
        if problem.keep[sl].any()
    }
    linear = {
        entry["track_index"]: FixedNoiseScreen(tracks[entry["track_index"]]["times"], stock)
        for entry in entries
    }
    return curved, linear
