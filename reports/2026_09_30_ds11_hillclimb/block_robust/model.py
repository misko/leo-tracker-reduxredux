"""Intermediate time-block Student-t likelihood for the DS11 hill climb.

Each occupied time block has an independent inverse-scale draw.  Observations
within a block therefore form one normalized spherical multivariate Student-t
density.  Catalogue mixing, the 100 Hz base scale, df=4, and one weakly
regularized constant CFO per track and catalogue candidate remain unchanged.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import brentq
from scipy.special import gammaln, logsumexp

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import ds7_baseline_adapter as baseline  # noqa: E402


DF = 4.0
SCALE_HZ = 100.0
CFO_PRIOR_VARIANCE_HZ2 = 1e12


class ProfileNumericalError(RuntimeError):
    """The offset profiler failed numerically; this is not a scientific fit."""


@dataclass(frozen=True)
class Variant:
    name: str
    block_seconds: float


VARIANTS = {
    "block1": Variant("block1", 1.0),
    "block3": Variant("block3", 3.0),
    "block10": Variant("block10", 10.0),
}

_ALIASES = {
    "block1s": "block1",
    "block_1s": "block1",
    "block3s": "block3",
    "block_3s": "block3",
    "block10s": "block10",
    "block_10s": "block10",
}


@dataclass(frozen=True)
class BlockLayout:
    """Compact description of consecutive occupied time bins."""

    ids: np.ndarray
    starts: np.ndarray
    sizes: np.ndarray
    anchor_s: float
    block_seconds: float


def resolve_variant(value: str | Variant) -> Variant:
    if isinstance(value, Variant):
        return value
    key = _ALIASES.get(str(value).lower(), str(value).lower())
    try:
        return VARIANTS[key]
    except KeyError as exc:
        raise ValueError(f"unknown time-block robustness variant {value!r}") from exc


def make_block_layout(times_s, mask, block_seconds: float) -> BlockLayout:
    """Group training rows into occupied bins anchored at the first train time.

    Bins are half-open intervals ``[anchor+k*width, anchor+(k+1)*width)``.
    Held rows neither choose the anchor nor create or populate a bin.
    ``math.inf`` is accepted for numerical tests and creates one training block.
    """
    times = np.asarray(times_s, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    if times.ndim != 1 or mask.shape != times.shape or not np.isfinite(times).all():
        raise ValueError("times_s and mask must be same-length finite vectors")
    training_times = times[mask]
    if not len(training_times):
        raise ValueError("at least one training observation is required")
    if np.any(np.diff(training_times) < 0.0):
        raise ValueError("training timestamps must be nondecreasing")
    if not (math.isinf(block_seconds) or np.isfinite(block_seconds)) or block_seconds <= 0:
        raise ValueError("block_seconds must be positive")

    anchor = float(training_times[0])
    if math.isinf(block_seconds):
        raw = np.zeros(len(training_times), dtype=np.int64)
    else:
        raw = np.floor((training_times - anchor) / block_seconds).astype(np.int64)
    _, ids = np.unique(raw, return_inverse=True)
    starts = np.r_[0, np.flatnonzero(np.diff(ids)) + 1].astype(np.int64)
    sizes = np.diff(np.r_[starts, len(ids)]).astype(np.int64)
    return BlockLayout(ids, starts, sizes, anchor, float(block_seconds))


def _reduce_blocks(values: np.ndarray, layout: BlockLayout) -> np.ndarray:
    return np.add.reduceat(values, layout.starts, axis=-1)


def block_log_density(centered: np.ndarray, layout: BlockLayout) -> np.ndarray:
    """Normalized product of spherical multivariate t4 block densities."""
    centered = np.asarray(centered, dtype=float)
    if centered.shape[-1] != len(layout.ids):
        raise ValueError("centered residual and block layout shapes differ")
    q = _reduce_blocks(centered * centered, layout)
    size = layout.sizes.astype(float)
    normalizer = (
        gammaln((DF + size) / 2.0)
        - gammaln(DF / 2.0)
        - 0.5 * size * math.log(DF * math.pi)
        - size * math.log(SCALE_HZ)
    )
    return np.sum(
        normalizer - 0.5 * (DF + size) * np.log1p(q / (DF * SCALE_HZ**2)),
        axis=-1,
    )


def _block_influence(centered: np.ndarray, layout: BlockLayout) -> np.ndarray:
    q = _reduce_blocks(centered * centered, layout)
    factors = (DF + layout.sizes) / (DF * SCALE_HZ**2 + q)
    return centered * factors[..., layout.ids]


def _offset_loss(offset: float, values: np.ndarray, layout: BlockLayout) -> float:
    return float(
        -block_log_density(values - offset, layout)
        + 0.5 * offset * offset / CFO_PRIOR_VARIANCE_HZ2
    )


def _offset_gradients(offsets: np.ndarray, values: np.ndarray, layout: BlockLayout):
    offsets = np.asarray(offsets, dtype=float)
    difference = offsets[..., None] - values
    sums = _reduce_blocks(difference, layout)
    squares = _reduce_blocks(difference * difference, layout)
    return np.sum(
        (DF + layout.sizes) * sums / (DF * SCALE_HZ**2 + squares), axis=-1
    ) + offsets / CFO_PRIOR_VARIANCE_HZ2


def _offset_gradient(offset: float, values: np.ndarray, layout: BlockLayout) -> float:
    return float(_offset_gradients(np.asarray(offset), values, layout))


def _offset_curvature(offset: float, values: np.ndarray, layout: BlockLayout) -> float:
    difference = offset - values
    sums = _reduce_blocks(difference, layout)
    squares = _reduce_blocks(difference * difference, layout)
    denominator = DF * SCALE_HZ**2 + squares
    return float(
        np.sum(
            (DF + layout.sizes)
            * (layout.sizes * denominator - 2.0 * sums * sums)
            / denominator**2
        )
        + 1.0 / CFO_PRIOR_VARIANCE_HZ2
    )


def fit_stationary_offsets(values: np.ndarray, layout: BlockLayout):
    """Profile the lowest located stationary CFO for each candidate row.

    The block-t objective can be multimodal.  Ten batched fixed-point starts
    locate attraction basins, after which bracketing probes enumerate nearby
    positive-curvature stationary roots and retain the lowest loss.
    """
    values = np.asarray(values, dtype=float)
    if values.ndim != 2 or values.shape[1] != len(layout.ids) or not values.shape[1]:
        raise ValueError("offset values and block layout shapes differ")
    if not np.isfinite(values).all():
        raise ValueError("offset values must be finite")

    centers = np.median(values, axis=1)
    centered = values - centers[:, None]
    quantiles = np.quantile(centered, np.linspace(0.0, 1.0, 9), axis=1).T
    starts = np.concatenate((quantiles, -centers[:, None]), axis=1)
    guesses = starts.copy()
    block_sums = _reduce_blocks(centered, layout)
    size = layout.sizes.astype(float)
    active = np.ones(guesses.shape, dtype=bool)
    for _ in range(100):
        difference = guesses[:, :, None] - centered[:, None, :]
        squares = _reduce_blocks(difference * difference, layout)
        weights = (DF + size) / (DF + squares / SCALE_HZ**2)
        numerator = np.sum(weights * block_sums[:, None, :], axis=2)
        numerator -= SCALE_HZ**2 * centers[:, None] / CFO_PRIOR_VARIANCE_HZ2
        denominator = np.sum(weights * size, axis=2)
        denominator += SCALE_HZ**2 / CFO_PRIOR_VARIANCE_HZ2
        new = numerator / denominator
        done = np.abs(new - guesses) < 1e-6
        guesses = np.where(active, new, guesses)
        active &= ~done
        if not active.any():
            break
    if not np.isfinite(guesses).all():
        raise ProfileNumericalError("nonfinite block offset fixed-point iterate")

    distances = SCALE_HZ * np.array([1e-6, 1e-4, 1e-2, 0.1, 1.0, 10.0])
    offsets = np.empty(len(values), dtype=float)
    audits = []
    for index, (row, center, y, row_starts, row_guesses) in enumerate(
        zip(values, centers, centered, starts, guesses, strict=True)
    ):
        lower = min(float(y.min()), -float(center))
        upper = max(float(y.max()), -float(center))
        if lower == upper:
            offsets[index] = center + lower
            audits.append({"converged": True, "gradient": 0.0, "roots": 1})
            continue

        nodes = np.unique(
            np.r_[
                lower,
                upper,
                y,
                row_starts,
                row_guesses,
                np.clip(row_guesses[:, None] - distances, lower, upper).ravel(),
                np.clip(row_guesses[:, None] + distances, lower, upper).ravel(),
            ]
        )

        def centered_gradient(value):
            return _offset_gradient(float(center + value), row, layout)

        gradients = _offset_gradients(center + nodes, row, layout)
        roots = []
        for node_index in range(len(nodes) - 1):
            left, right = nodes[node_index : node_index + 2]
            gl, gr = gradients[node_index : node_index + 2]
            if gl == 0.0:
                root = float(left)
            elif gl < 0.0 < gr:
                root = brentq(centered_gradient, left, right, xtol=1e-9, rtol=1e-14)
            else:
                continue
            offset = float(center + root)
            if _offset_curvature(offset, row, layout) > 0.0:
                roots.append(offset)
        if gradients[-1] == 0.0:
            offset = float(center + nodes[-1])
            if _offset_curvature(offset, row, layout) > 0.0:
                roots.append(offset)
        if not roots:
            raise ProfileNumericalError(
                f"no positive-curvature stationary CFO offset for candidate row {index}"
            )
        roots = np.unique(np.asarray(roots, dtype=float))
        best = min(roots, key=lambda value: _offset_loss(float(value), row, layout))
        gradient = _offset_gradient(float(best), row, layout)
        if abs(gradient) >= 1e-7:
            raise ProfileNumericalError(
                f"CFO offset stationarity failure for candidate row {index}: {gradient}"
            )
        offsets[index] = best
        audits.append(
            {"converged": True, "gradient": float(gradient), "roots": int(len(roots))}
        )
    return offsets, audits


def profile_likelihood(
    residual: np.ndarray,
    mask: np.ndarray,
    times_s: np.ndarray,
    block_seconds: float,
):
    """Profile candidate offsets and return train scores and envelope influence."""
    residual = np.asarray(residual, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    if residual.ndim != 2 or mask.shape != (residual.shape[1],):
        raise ValueError("residual and observation mask shapes differ")
    layout = make_block_layout(times_s, mask, block_seconds)
    training = residual[:, mask]
    offsets, audits = fit_stationary_offsets(training, layout)
    centered = training - offsets[:, None]
    train = block_log_density(centered, layout)
    train -= 0.5 * offsets * offsets / CFO_PRIOR_VARIANCE_HZ2
    influence = _block_influence(centered, layout)
    return train, influence, offsets, audits


class BlockRobust:
    def __init__(self, documents, config, variant, prediction_factory=baseline.Stationary):
        if not documents:
            raise ValueError("at least one document is required")
        self.documents = documents
        self.variant = resolve_variant(variant)
        self.models = [prediction_factory(document, config) for document in documents]
        self.timing_bounds = tuple(config.get("timing_bounds_s", (-5.0, 5.0)))
        position_bounds = tuple(config.get("position_bounds_km", (-12.0, 12.0)))
        self.bounds = [position_bounds, position_bounds] + [self.timing_bounds] * len(documents)
        self.metadata = {
            "family": "independent_time_block_multivariate_t",
            "variant": self.variant.name,
            "student_t_df": DF,
            "student_t_scale_hz": SCALE_HZ,
            "block_seconds": self.variant.block_seconds,
            "block_anchor": "first_training_timestamp",
            "block_intervals": "half_open_occupied_bins",
            "held_rows_affect_grouping": False,
            "cfo_profile": "one_constant_per_track_and_catalogue_candidate",
            "cfo_prior_sd_hz": math.sqrt(CFO_PRIOR_VARIANCE_HZ2),
            "likelihood_normalized": True,
            "offset_profile": "batched_irls_then_lowest_located_stationary_minimum",
        }

    def coordinates(self, x):
        return self.models[0].coordinates(x)

    def _prediction_derivatives(self, engine, track, local, prediction):
        derivatives = []
        for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
            plus, minus = local.copy(), local.copy()
            plus[axis] += step
            minus[axis] -= step
            if axis == 2:
                plus[axis] = min(self.timing_bounds[1], plus[axis])
                minus[axis] = max(self.timing_bounds[0], minus[axis])
            width = plus[axis] - minus[axis]
            if width <= 0.0:
                raise ProfileNumericalError("zero-width prediction derivative")
            positive = engine.prediction(track, plus)[0]
            negative = engine.prediction(track, minus)[0]
            derivative = (positive - negative) / width
            if derivative.shape != prediction.shape or not np.isfinite(derivative).all():
                raise ProfileNumericalError("nonfinite prediction derivative")
            derivatives.append(derivative)
        return derivatives

    def evaluate(self, x, gradient=True):
        x = np.asarray(x, dtype=float)
        expected = len(self.documents) + 2
        if x.shape != (expected,) or not np.isfinite(x).all():
            raise ValueError(f"x must contain {expected} finite values")
        total = 0.0
        derivative = np.zeros_like(x)
        minimum_stationary_roots = None

        for document_index, (document, engine) in enumerate(
            zip(self.documents, self.models, strict=True)
        ):
            local = x[[0, 1, document_index + 2]]
            for track in document["tracks"]:
                prediction, visible = engine.prediction(track, local)
                residual = track["y"][None, :] - prediction
                candidate_score, influence, _, audits = profile_likelihood(
                    residual,
                    track["mask"],
                    track["times_s"],
                    self.variant.block_seconds,
                )
                roots = min(audit["roots"] for audit in audits)
                minimum_stationary_roots = (
                    roots
                    if minimum_stationary_roots is None
                    else min(minimum_stationary_roots, roots)
                )
                candidate_score = np.where(visible, candidate_score, -np.inf)
                normal = float(logsumexp(candidate_score))
                if not np.isfinite(normal):
                    raise ProfileNumericalError(
                        f"no visible finite catalogue candidate for track {track.get('track_id')}"
                    )
                total += normal - math.log(track["catalogue_size"])
                if gradient:
                    responsibilities = np.exp(candidate_score - normal)
                    prediction_derivatives = self._prediction_derivatives(
                        engine, track, local, prediction
                    )
                    for axis, prediction_derivative in enumerate(prediction_derivatives):
                        component = np.sum(
                            influence * prediction_derivative[:, track["mask"]], axis=1
                        )
                        target = axis if axis < 2 else document_index + 2
                        derivative[target] += float(responsibilities @ component)

        if not np.isfinite(total) or not np.isfinite(derivative).all():
            raise ProfileNumericalError("nonfinite block likelihood evaluation")
        return {
            "score": float(total),
            "gradient": derivative,
            "diagnostics": {
                "variant": self.variant.name,
                "minimum_stationary_roots": minimum_stationary_roots,
            },
        }


def build_model(documents, config, variant, index=None):
    """Build one frozen time-block challenger; ``index`` is provenance only."""
    del index
    return BlockRobust(documents, config, variant)
