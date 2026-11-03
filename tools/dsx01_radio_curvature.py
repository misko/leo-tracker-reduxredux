"""Radio-only active-curvature check robust to a few wrong GLRT points."""

import numpy as np
from dsx01_clock_transfer_models import mixture_cost


def fit_polynomial(times, values, *, noise=150.0, contamination=5000.0, signal_probability=0.98):
    t, y = np.asarray(times, float), np.asarray(values, float)
    if (
        t.ndim != 1
        or y.shape != t.shape
        or len(t) < 12
        or np.ptp(t) <= 0
        or not np.isfinite(t).all()
        or not np.isfinite(y).all()
    ):
        raise ValueError("finite matching radio samples with temporal support required")
    z = (t - (t.min() + t.max()) / 2) / (np.ptp(t) / 2)
    center = float(np.median(y))
    data = y - center
    fits = []
    linear = None
    for degree in range(1, 5):
        design = np.vander(z, degree + 1, increasing=True)
        starts = [np.linalg.lstsq(design, data, rcond=None)[0]]
        if linear is not None:
            starts.append(np.r_[linear, np.zeros(degree - 1)])
        candidates = []
        for coefficient in starts:
            for _ in range(30):
                residual = data - design @ coefficient
                a = np.log(signal_probability / noise) - 0.5 * (residual / noise) ** 2
                b = (
                    np.log((1 - signal_probability) / contamination)
                    - 0.5 * (residual / contamination) ** 2
                )
                responsibility = np.exp(a - np.logaddexp(a, b))
                precision = responsibility / noise**2 + (1 - responsibility) / contamination**2
                updated = np.linalg.lstsq(
                    design * np.sqrt(precision[:, None]), data * np.sqrt(precision), rcond=None
                )[0]
                if np.max(abs(updated - coefficient)) < 1e-6:
                    coefficient = updated
                    break
                coefficient = updated
            residual = data - design @ coefficient
            cost = float(np.sum(mixture_cost(residual, noise, contamination, signal_probability)))
            candidates.append((cost, coefficient))
        cost, coefficient = min(candidates, key=lambda a: a[0])
        if degree == 1:
            linear = coefficient
        prediction = center + design @ coefficient
        residual = y - prediction
        a = np.log(signal_probability / noise) - 0.5 * (residual / noise) ** 2
        b = np.log((1 - signal_probability) / contamination) - 0.5 * (residual / contamination) ** 2
        weight = np.exp(a - np.logaddexp(a, b))
        affine = np.column_stack((np.ones(len(t)), z))
        beta = np.linalg.lstsq(
            affine * np.sqrt(weight[:, None]), prediction * np.sqrt(weight), rcond=None
        )[0]
        curvature = float(
            np.sqrt(np.sum(weight * (prediction - affine @ beta) ** 2) / max(weight.sum(), 1e-12))
        )
        strong = weight >= 0.5
        fits.append(
            dict(
                degree=degree,
                cost=cost,
                complexity_penalty=float((degree + 1) * np.log(len(t))),
                score=cost + (degree + 1) * np.log(len(t)),
                curvature_rms_hz=curvature,
                signal_points=int(strong.sum()),
                signal_span_s=float(np.ptp(t[strong])) if strong.any() else 0,
                effective_signal_points=float(weight.sum() ** 2 / max(weight @ weight, 1e-12)),
                prediction=prediction,
                signal_responsibility=weight,
            )
        )
    selected = min(fits, key=lambda r: r["score"])
    return dict(
        selected=selected,
        active_curvature=bool(
            selected["degree"] >= 2
            and selected["curvature_rms_hz"] >= 250
            and selected["signal_points"] >= 12
            and selected["signal_span_s"] >= 20
        ),
        fits=fits,
    )
