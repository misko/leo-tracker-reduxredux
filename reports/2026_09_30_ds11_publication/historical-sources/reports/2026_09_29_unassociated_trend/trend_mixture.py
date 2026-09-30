"""Conditional retained-bank satellite mixture with an unassociated linear trend."""

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "2026_09_29_frequency_contrast"))
from contrast_position import ContrastPosition, contrast_density  # noqa: E402


def trend_density(values, times, noise_scale=100.0, slope_scale=2000.0):
    """Student-t4 contrast density after marginalizing a shared-scale slope.

    The original scale is noise_scale^2 I + slope_scale^2 t t^T. The constant
    frequency is eliminated by contrasts. Orthogonal projection avoids the
    cancellation of subtracting a large rank-one quadratic-form correction.
    """
    y, t = np.asarray(values, dtype=float), np.asarray(times, dtype=float)
    if y.ndim != 1 or y.shape != t.shape or len(y) < 2:
        raise ValueError("Require matching one-dimensional values/times, n >= 2")
    if not np.isfinite(y).all() or not np.isfinite(t).all():
        raise ValueError("Require finite values and times")
    if not np.isfinite(noise_scale) or noise_scale <= 0:
        raise ValueError("Require positive finite noise scale")
    if not np.isfinite(slope_scale) or slope_scale < 0:
        raise ValueError("Require nonnegative finite slope scale")
    y, t = y - y[0], t - t[0]
    z, centered_t = y - y.mean(), t - t.mean()
    t2 = float(centered_t @ centered_t)
    variance = noise_scale**2
    ratio = slope_scale**2 * t2 / variance
    if t2:
        direction = centered_t / math.sqrt(t2)
        projection = float(z @ direction)
        perpendicular = z - projection * direction
        q = float(perpendicular @ perpendicular) / variance
        q += projection**2 / (variance * (1 + ratio))
    else:
        q = float(z @ z) / variance
    dimension = len(y) - 1
    logdet = dimension * math.log(variance) + math.log(len(y)) + math.log1p(ratio)
    return (
        math.lgamma((4 + dimension) / 2)
        - math.lgamma(2)
        - 0.5 * (dimension * math.log(4 * math.pi) + logdet)
        - (4 + dimension) / 2 * math.log1p(q / 4)
    )


class TrendMixturePosition(ContrastPosition):
    """A normalized conditional-bank model, not a full-catalogue posterior.

    Signal priors are uniform over retained candidates passing the original
    training horizon gate. The model domain requires at least one such candidate
    for each track, in every arm including the unit-background diagnostic. No
    candidate means explicit abstention, never silent renormalization to clutter.
    All finite differences must preserve the visible set.
    """

    def __init__(
        self,
        documents,
        config,
        model_factory,
        background_probability,
        noise_scale=100.0,
        slope_scale=2000.0,
    ):
        super().__init__(documents, config, model_factory)
        if not np.isfinite(background_probability) or not 0 <= background_probability <= 1:
            raise ValueError("Require background probability in [0, 1]")
        self.background_probability = float(background_probability)
        self.background = {}
        for di, doc in enumerate(documents):
            for ti, track in enumerate(doc["tracks"]):
                mask = track["mask"]
                times = np.asarray(track["times_s"], dtype=float)
                self.background[di, ti] = (
                    trend_density(track["y"][mask], times[mask], noise_scale, slope_scale),
                    trend_density(track["y"], times, noise_scale, slope_scale),
                )

    def evaluate(self, x, gradient=True, held=False):
        x = np.asarray(x, dtype=float)
        if x.shape != (2 + len(self.documents),) or not np.isfinite(x).all():
            raise ValueError("Require shared E/N and one finite timing per recording")
        probability = self.background_probability
        log_signal_prior = math.log1p(-probability) if probability < 1 else -np.inf
        log_background_prior = math.log(probability) if probability > 0 else -np.inf
        score, derivative, rows = 0.0, np.zeros_like(x), []
        for di, (doc, model) in enumerate(zip(self.documents, self.models, strict=True)):
            local = np.array([x[0], x[1], x[di + 2]])
            for ti, track in enumerate(doc["tracks"]):
                mask = track["mask"]
                prediction, visible = model.prediction(track, local)
                count = int(visible.sum())
                if count == 0:
                    raise ValueError(
                        "No visible retained candidate: outside conditional-bank domain"
                    )
                residual = track["y"][None, :] - prediction
                train, influence = contrast_density(residual[:, mask])
                train = np.where(visible, train, -np.inf)
                signal_normal = np.logaddexp.reduce(train)
                signal_train = signal_normal - math.log(count)
                bg_train, bg_joint = self.background[di, ti]
                normal = np.logaddexp(
                    log_signal_prior + signal_train, log_background_prior + bg_train
                )
                responsibility = float(np.exp(log_signal_prior + signal_train - normal))
                weights = np.exp(train - signal_normal)
                score += float(normal)
                if gradient and responsibility:
                    for axis in range(3):
                        step = 1e-4 if axis < 2 else 1e-5
                        plus, minus = local.copy(), local.copy()
                        plus[axis] += step
                        minus[axis] -= step
                        if axis == 2:
                            plus[axis] = min(5, plus[axis])
                            minus[axis] = max(-5, minus[axis])
                        pp, vp = model.prediction(track, plus)
                        pm, vm = model.prediction(track, minus)
                        assert np.array_equal(visible, vp) and np.array_equal(visible, vm)
                        dp = (pp[:, mask] - pm[:, mask]) / (plus[axis] - minus[axis])
                        index = axis if axis < 2 else di + 2
                        derivative[index] += responsibility * float(
                            weights @ np.sum(influence * dp, axis=1)
                        )
                if held:
                    full, _ = contrast_density(residual)
                    signal_joint = np.logaddexp.reduce(np.where(visible, full, -np.inf)) - math.log(
                        count
                    )
                    joint = np.logaddexp(
                        log_signal_prior + signal_joint, log_background_prior + bg_joint
                    )
                    rows.append(
                        {
                            "session_id": doc["session_id"],
                            "track_id": track["track_id"],
                            "training_log_score": float(normal),
                            "held_log_score": float(joint - normal),
                            "signal_training_log_density": float(signal_train),
                            "background_training_log_density": bg_train,
                            "signal_responsibility": responsibility,
                            "weights_given_signal": weights.tolist(),
                            "visible_candidates": count,
                            "held_observations": int((~mask).sum()),
                        }
                    )
        return {"score": score, "gradient": derivative, "rows": rows}
