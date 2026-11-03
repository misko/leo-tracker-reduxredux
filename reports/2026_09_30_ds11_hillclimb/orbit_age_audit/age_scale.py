"""Normalized t4 scale likelihood and frozen hierarchical weighting."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math

import numpy as np
from scipy.optimize import brentq


LOG_NORMALIZER = math.lgamma(2.5) - math.lgamma(2.0) - 0.5 * math.log(4.0 * math.pi)
OFFSET_VARIANCE = 1e12


def scale_from_age(age_days, k_hz_per_day):
    age = np.asarray(age_days, dtype=float)
    return np.sqrt(100.0**2 + (float(k_hz_per_day) * age) ** 2)


def log_density(residual, offset, scale):
    residual = np.asarray(residual, dtype=float)
    scale = np.asarray(scale, dtype=float)
    z = (residual - np.asarray(offset, dtype=float)[..., None]) / scale[..., None]
    return LOG_NORMALIZER - np.log(scale)[..., None] - 2.5 * np.log1p(z * z / 4.0)


def hierarchical_weights(rows):
    """Equal dataset, scan, source, and track weights in that order."""
    datasets = sorted({row["dataset"] for row in rows})
    if datasets != ["DS7", "DS8", "DS9"]:
        raise ValueError(f"expected DS7--DS9, got {datasets}")
    scans = defaultdict(set)
    sources = defaultdict(set)
    tracks = defaultdict(set)
    for row in rows:
        dataset, scan = row["dataset"], row["session_id"]
        source = (scan, int(row["number"]), float(row["rf_hz"]))
        track = (scan, row["track_id"])
        scans[dataset].add(scan)
        sources[(dataset, scan)].add(source)
        tracks[(dataset, source)].add(track)
    weights = []
    for row in rows:
        dataset, scan = row["dataset"], row["session_id"]
        source = (scan, int(row["number"]), float(row["rf_hz"]))
        weights.append(
            1.0
            / len(datasets)
            / len(scans[dataset])
            / len(sources[(dataset, scan)])
            / len(tracks[(dataset, source)])
        )
    result = np.asarray(weights)
    if not np.isfinite(result).all() or abs(float(result.sum()) - 1.0) > 1e-12:
        raise ValueError("invalid hierarchical weights")
    return result


@dataclass
class ProfiledCases:
    residuals: list[np.ndarray]
    masks: list[np.ndarray]
    ages: np.ndarray
    weights: np.ndarray

    @classmethod
    def from_rows(cls, rows):
        residuals = [np.asarray(row["residual"], dtype=float) for row in rows]
        masks = [np.asarray(row["mask"], dtype=bool) for row in rows]
        ages = np.asarray([row["age_days"] for row in rows], dtype=float)
        for residual, mask in zip(residuals, masks, strict=True):
            if (
                residual.ndim != 1
                or mask.shape != residual.shape
                or mask.sum() < 2
                or (~mask).sum() < 1
                or not np.isfinite(residual).all()
            ):
                raise ValueError("invalid retained residual case")
        if np.any(ages < 0) or not np.isfinite(ages).all():
            raise ValueError("invalid element age")
        return cls(residuals, masks, ages, hierarchical_weights(rows))

    def profile(self, scales):
        """Best located positive-curvature training stationary point per case."""
        scales = np.asarray(scales, dtype=float)
        if scales.shape != self.ages.shape or np.any(scales <= 0) or not np.isfinite(scales).all():
            raise ValueError("invalid case scales")
        offsets = np.empty(len(self.residuals))
        groups = defaultdict(list)
        for index, mask in enumerate(self.masks):
            groups[int(mask.sum())].append(index)
        quantiles = np.linspace(0.0, 1.0, 9)
        for indices in groups.values():
            values = np.stack([self.residuals[i][self.masks[i]] for i in indices])
            centers = np.median(values, axis=1)
            y = values - centers[:, None]
            sigma = scales[indices]
            guesses = np.concatenate(
                [np.quantile(y, quantiles, axis=1).T, np.zeros((len(indices), 1))], axis=1
            )
            for _ in range(200):
                r = (y[:, None, :] - guesses[:, :, None]) / sigma[:, None, None]
                weight = 5.0 / (4.0 + r * r)
                new = (
                    np.sum(weight * y[:, None, :], axis=2)
                    - sigma[:, None] ** 2 * centers[:, None] / OFFSET_VARIANCE
                ) / (np.sum(weight, axis=2) + sigma[:, None] ** 2 / OFFSET_VARIANCE)
                change = np.max(abs(new - guesses))
                guesses = new
                if change < 1e-9:
                    break
            for local, index in enumerate(indices):
                center, values, scale = centers[local], y[local], sigma[local]
                starts = np.unique(np.r_[np.quantile(values, quantiles), 0.0])
                lower, upper = min(float(values.min()), -center), max(float(values.max()), -center)
                if lower == upper:
                    offsets[index] = center + lower
                    continue

                def loss(value):
                    return float(
                        2.5 * np.log1p(((values - value) / scale) ** 2 / 4.0).sum()
                        + 0.5 * ((center + value) ** 2) / OFFSET_VARIANCE
                    )

                def derivative(value):
                    r = value - values
                    return float(
                        np.sum(5.0 * r / (4.0 * scale * scale + r * r))
                        + (center + value) / OFFSET_VARIANCE
                    )

                def curvature(value):
                    r = value - values
                    den = 4.0 * scale * scale + r * r
                    return float(
                        np.sum(5.0 * (4.0 * scale * scale - r * r) / den**2)
                        + 1.0 / OFFSET_VARIANCE
                    )

                distances = scale * np.array([1e-6, 1e-4, 1e-2, 0.1, 1.0, 10.0])
                local_guesses = guesses[local]
                nodes = np.unique(np.r_[
                    lower, upper, starts, local_guesses,
                    np.clip(local_guesses[:, None] - distances, lower, upper).ravel(),
                    np.clip(local_guesses[:, None] + distances, lower, upper).ravel(),
                ])
                residual = nodes[:, None] - values[None, :]
                gradients = (
                    np.sum(5.0 * residual / (4.0 * scale * scale + residual * residual), axis=1)
                    + (center + nodes) / OFFSET_VARIANCE
                )
                roots = []
                for node_index in range(len(nodes) - 1):
                    if gradients[node_index] <= 0 <= gradients[node_index + 1]:
                        root = brentq(
                            derivative, nodes[node_index], nodes[node_index + 1],
                            xtol=1e-9, rtol=1e-14,
                        )
                        if curvature(root) > 0:
                            roots.append(root)
                if not roots:
                    raise RuntimeError(f"no positive-curvature stationary offset for case {index}")
                best = min(roots, key=loss)
                if abs(derivative(best)) > 1e-7:
                    raise RuntimeError(f"offset stationarity audit failed for case {index}")
                offsets[index] = center + best
        return offsets

    def training_objective(self, scales):
        scales = np.asarray(scales, dtype=float)
        offsets = self.profile(scales)
        scores = np.empty(len(self.residuals))
        for i, (residual, mask) in enumerate(zip(self.residuals, self.masks, strict=True)):
            density = log_density(residual[None, :], np.asarray([offsets[i]]), np.asarray([scales[i]]))[0]
            scores[i] = (
                float(density[mask].sum()) - 0.5 * offsets[i] ** 2 / OFFSET_VARIANCE
            ) / int(mask.sum())
        return float(self.weights @ scores), offsets

    def held_scores(self, scales):
        scales = np.asarray(scales, dtype=float)
        offsets = self.profile(scales)
        scores = np.empty(len(self.residuals))
        for i, (residual, mask) in enumerate(zip(self.residuals, self.masks, strict=True)):
            density = log_density(residual[None, :], np.asarray([offsets[i]]), np.asarray([scales[i]]))[0]
            scores[i] = float(density[~mask].mean())
        return scores, offsets
