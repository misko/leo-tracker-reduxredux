"""Bounded IID Student-t likelihood challengers for the DS11 hill climb.

The catalogue mixture and geometry are inherited from the corrected DS7
baseline.  Only the observation likelihood's fixed degrees of freedom and
scale change.  Every catalogue candidate retains its own profiled constant CFO
offset and every observation retains an individual Student-t contribution.
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


CFO_PRIOR_VARIANCE_HZ2 = 1e12


class ProfileNumericalError(RuntimeError):
    """The offset profiler failed numerically; this is not a scientific fit."""


@dataclass(frozen=True)
class Variant:
    name: str
    df: float
    scale_hz: float


VARIANTS = {
    "scale50": Variant("scale50", 4.0, 50.0),
    "scale200": Variant("scale200", 4.0, 200.0),
    "df2": Variant("df2", 2.0, 100.0),
    "df8": Variant("df8", 8.0, 100.0),
    # The frozen baseline is exposed for numerical parity tests and audits.  It
    # is not one of the four challenger arms.
    "baseline": Variant("baseline", 4.0, 100.0),
}

_ALIASES = {
    "scale_50": "scale50",
    "df4_scale50": "scale50",
    "t4_scale50": "scale50",
    "scale_200": "scale200",
    "df4_scale200": "scale200",
    "t4_scale200": "scale200",
    "df_2": "df2",
    "df2_scale100": "df2",
    "t2_scale100": "df2",
    "df_8": "df8",
    "df8_scale100": "df8",
    "t8_scale100": "df8",
    "df4_scale100": "baseline",
    "t4_scale100": "baseline",
}


def resolve_variant(value: str | dict | Variant) -> Variant:
    if isinstance(value, Variant):
        return value
    if isinstance(value, dict):
        try:
            df = float(value["df"])
            scale = float(value.get("scale_hz", value.get("scale")))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("variant dict requires finite df and scale_hz") from exc
        if not np.isfinite(df) or not np.isfinite(scale) or df <= 0 or scale <= 0:
            raise ValueError("Student-t df and scale_hz must be finite and positive")
        return Variant(str(value.get("name", f"df{df:g}_scale{scale:g}")), df, scale)
    key = _ALIASES.get(str(value).lower(), str(value).lower())
    try:
        return VARIANTS[key]
    except KeyError as exc:
        raise ValueError(f"unknown robust likelihood variant {value!r}") from exc


def student_t_log_density(residual: np.ndarray, df: float, scale_hz: float) -> np.ndarray:
    """Return the properly normalized scalar Student-t log density."""
    residual = np.asarray(residual, dtype=float)
    normalizer = (
        gammaln((df + 1.0) / 2.0)
        - gammaln(df / 2.0)
        - 0.5 * math.log(df * math.pi)
        - math.log(scale_hz)
    )
    return normalizer - 0.5 * (df + 1.0) * np.log1p(
        residual * residual / (df * scale_hz * scale_hz)
    )


def _offset_loss(offset: float, values: np.ndarray, variant: Variant) -> float:
    return float(
        -student_t_log_density(values - offset, variant.df, variant.scale_hz).sum()
        + 0.5 * offset * offset / CFO_PRIOR_VARIANCE_HZ2
    )


def _offset_gradient(offset: float, values: np.ndarray, variant: Variant) -> float:
    difference = offset - values
    denominator = variant.df * variant.scale_hz**2 + difference * difference
    return float(
        np.sum((variant.df + 1.0) * difference / denominator)
        + offset / CFO_PRIOR_VARIANCE_HZ2
    )


def _offset_curvature(offset: float, values: np.ndarray, variant: Variant) -> float:
    difference = offset - values
    base = variant.df * variant.scale_hz**2
    denominator = base + difference * difference
    return float(
        np.sum((variant.df + 1.0) * (base - difference * difference) / denominator**2)
        + 1.0 / CFO_PRIOR_VARIANCE_HZ2
    )


def fit_stationary_offsets(values: np.ndarray, variant: str | dict | Variant):
    """Profile one global-minimum CFO offset for every candidate row.

    Student-t offset objectives can be multimodal.  Quantile-seeded fixed-point
    iterations locate attraction basins; bracketing around all seeds and fixed
    points then enumerates the positive-curvature stationary roots.  The best
    stationary loss is selected rather than trusting a single local solve.
    """
    variant = resolve_variant(variant)
    values = np.asarray(values, dtype=float)
    if values.ndim != 2 or values.shape[1] == 0:
        raise ValueError("offset values must be a nonempty two-dimensional array")
    if not np.isfinite(values).all():
        raise ValueError("offset values must be finite")

    centers = np.median(values, axis=1)
    centered = values - centers[:, None]
    starts = [
        np.unique(np.r_[np.quantile(row, np.linspace(0.0, 1.0, 9)), 0.0])
        for row in centered
    ]

    guesses: list[np.ndarray | None] = [None] * len(centered)
    scale2 = variant.scale_hz**2
    for width in sorted({len(row) for row in starts}):
        indices = [index for index, row in enumerate(starts) if len(row) == width]
        group_values = centered[indices]
        group_guesses = np.stack([starts[index] for index in indices])
        active = np.ones(group_guesses.shape, dtype=bool)
        for _ in range(100):
            standardized = (
                group_values[:, None, :] - group_guesses[:, :, None]
            ) / variant.scale_hz
            weights = (variant.df + 1.0) / (variant.df + standardized * standardized)
            new = (
                (weights * group_values[:, None, :]).sum(axis=2)
                - scale2 * centers[indices, None] / CFO_PRIOR_VARIANCE_HZ2
            ) / (weights.sum(axis=2) + scale2 / CFO_PRIOR_VARIANCE_HZ2)
            done = np.abs(new - group_guesses) < 1e-6
            group_guesses = np.where(active, new, group_guesses)
            active &= ~done
            if not active.any():
                break
        for local, index in enumerate(indices):
            guesses[index] = group_guesses[local]

    offsets = np.empty(len(values), dtype=float)
    audits = []
    # Scale-relative probes cover the narrow and broad arms without silently
    # inheriting the baseline's scale-100-only absolute distances.
    distances = variant.scale_hz * np.array([1e-6, 1e-4, 1e-2, 0.1, 1.0, 10.0])
    for index, (row, center, y, row_starts, maybe_guesses) in enumerate(
        zip(values, centers, centered, starts, guesses, strict=True)
    ):
        assert maybe_guesses is not None
        row_guesses = maybe_guesses
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

        def centered_gradient(v):
            return _offset_gradient(float(center + v), row, variant)

        gradients = np.asarray([centered_gradient(node) for node in nodes])
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
            if _offset_curvature(offset, row, variant) > 0.0:
                roots.append(offset)
        if gradients[-1] == 0.0:
            offset = float(center + nodes[-1])
            if _offset_curvature(offset, row, variant) > 0.0:
                roots.append(offset)
        if not roots:
            raise ProfileNumericalError(
                f"no positive-curvature stationary CFO offset for candidate row {index}"
            )
        roots = np.unique(np.asarray(roots, dtype=float))
        best = min(roots, key=lambda offset: _offset_loss(float(offset), row, variant))
        gradient = _offset_gradient(float(best), row, variant)
        converged = bool(abs(gradient) < 1e-7)
        if not converged:
            raise ProfileNumericalError(
                f"CFO offset stationarity failure for candidate row {index}: {gradient}"
            )
        offsets[index] = best
        audits.append(
            {"converged": True, "gradient": float(gradient), "roots": int(len(roots))}
        )
    return offsets, audits


def profile_likelihood(residual: np.ndarray, mask: np.ndarray, variant: str | dict | Variant):
    """Profile candidate offsets and return train scores and influence."""
    variant = resolve_variant(variant)
    residual = np.asarray(residual, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    if residual.ndim != 2 or mask.shape != (residual.shape[1],):
        raise ValueError("residual and observation mask shapes differ")
    offsets, audits = fit_stationary_offsets(residual[:, mask], variant)
    centered = residual - offsets[:, None]
    train = student_t_log_density(centered[:, mask], variant.df, variant.scale_hz).sum(axis=1)
    train -= 0.5 * offsets * offsets / CFO_PRIOR_VARIANCE_HZ2
    denominator = variant.df * variant.scale_hz**2 + centered[:, mask] ** 2
    influence = (variant.df + 1.0) * centered[:, mask] / denominator
    return train, influence, offsets, audits


class RobustIID:
    def __init__(self, documents, config, variant, prediction_factory=baseline.Stationary):
        if not documents:
            raise ValueError("at least one document is required")
        self.documents = documents
        self.config = config
        self.variant = resolve_variant(variant)
        self.models = [prediction_factory(document, config) for document in documents]
        self.timing_bounds = tuple(config.get("timing_bounds_s", (-5.0, 5.0)))
        position_bounds = tuple(config.get("position_bounds_km", (-12.0, 12.0)))
        self.bounds = [position_bounds, position_bounds] + [self.timing_bounds] * len(documents)
        self.metadata = {
            "family": "iid_student_t_robustness",
            "variant": self.variant.name,
            "student_t_df": self.variant.df,
            "student_t_scale_hz": self.variant.scale_hz,
            "cfo_prior_sd_hz": math.sqrt(CFO_PRIOR_VARIANCE_HZ2),
            "likelihood_normalized": True,
            "offset_profile": "per_catalogue_candidate_global_stationary_minimum",
            "observation_weighting": "iid_per_observation",
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
                    residual, track["mask"], self.variant
                )
                minimum_stationary_roots = min(
                    (audit["roots"] for audit in audits),
                    default=minimum_stationary_roots,
                ) if minimum_stationary_roots is not None else min(
                    audit["roots"] for audit in audits
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
                        component_gradient = np.sum(
                            influence * prediction_derivative[:, track["mask"]], axis=1
                        )
                        value = float(responsibilities @ component_gradient)
                        target = axis if axis < 2 else document_index + 2
                        derivative[target] += value

        if not np.isfinite(total) or not np.isfinite(derivative).all():
            raise ProfileNumericalError("nonfinite robust likelihood evaluation")
        return {
            "score": float(total),
            "gradient": derivative,
            "diagnostics": {
                "variant": self.variant.name,
                "student_t_df": self.variant.df,
                "student_t_scale_hz": self.variant.scale_hz,
                "minimum_stationary_roots": minimum_stationary_roots,
            },
        }


def build_model(documents, config, variant, index=None):
    """Build one frozen robust challenger; ``index`` is provenance only."""
    del index
    return RobustIID(documents, config, variant)
