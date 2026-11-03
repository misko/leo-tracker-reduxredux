"""Degree selection with explicit clutter, on a fixed unwrapped CFO branch.

Every point contributes to the score. A Gaussian/reference-clutter contrast and
k log(n) penalty can prefer a simple curve plus an unassociated point over a
high-degree bend. No satellite, hardware calibration or location is consulted.
This is a bounded research estimator, not a calibrated identity probability.
"""

import numpy as np


def polynomial_orders(
    times,
    values,
    *,
    maximum_degree=4,
    noise_hz=150.0,
    clutter_probability=0.02,
    clutter_width_hz=1 / 4.4e-6,
    maximum_iterations=30,
):
    """Compare degrees 1..4 with all-point and every leave-one-out EM seed.

    Deleted points initialize candidates only: every EM iteration and final score
    use every observation. Full-length responsibilities explicitly retain clutter.
    Aliases are the input track's frozen unwrapped branches; none is reselected.
    The clutter width is a fixed density reference, not a free estimated scale.
    """
    t, y = np.asarray(times, float), np.asarray(values, float)
    if (
        t.ndim != 1
        or y.shape != t.shape
        or len(t) < 5
        or not np.isfinite(t).all()
        or not np.isfinite(y).all()
        or np.any(np.diff(t) <= 0)
    ):
        raise ValueError("at least five finite, strictly increasing paired observations required")
    if not isinstance(maximum_degree, int) or not 1 <= maximum_degree <= 4:
        raise ValueError("maximum degree must be an integer from one through four")
    if (
        not np.isfinite(noise_hz)
        or noise_hz <= 0
        or not np.isfinite(clutter_width_hz)
        or clutter_width_hz <= 0
        or not 0 < clutter_probability < 1
        or maximum_iterations < 1
    ):
        raise ValueError(
            "positive finite scales, proper clutter probability and iterations required"
        )
    n = len(t)
    reference, scale = (t[0] + t[-1]) / 2, np.ptp(t) / 2
    x = (t - reference) / scale
    center = np.median(y)
    target = y - center
    clean_zero = np.log1p(-clutter_probability) - np.log(noise_hz * np.sqrt(2 * np.pi))
    clutter = np.log(clutter_probability) - np.log(clutter_width_hz)
    reference_density = np.logaddexp(clean_zero, clutter)
    choices = []
    for degree in range(1, min(maximum_degree, n - 3) + 1):
        design = np.polynomial.polynomial.polyvander(x, degree)
        best = None
        for omitted in range(-1, n):
            seed = np.arange(n) != omitted
            coef = np.linalg.lstsq(design[seed], target[seed], rcond=None)[0]
            for iteration in range(maximum_iterations + 1):
                residual = target - design @ coef
                clean = clean_zero - 0.5 * (residual / noise_hz) ** 2
                density = np.logaddexp(clean, clutter)
                weights = np.exp(clean - density)
                inliers = weights >= 0.5
                data_cost = float(-2 * np.sum(density - reference_density))
                score = data_cost + (degree + 1) * np.log(n)
                if np.count_nonzero(inliers) >= max(4, degree + 2) and (
                    best is None or score < best["score"]
                ):
                    coefficients = coef.copy()
                    coefficients[0] += center
                    best = dict(
                        degree=degree,
                        reference_time_s=float(reference),
                        time_scale_s=float(scale),
                        coefficients_hz=coefficients,
                        prediction_hz=y - residual,
                        residual_hz=residual.copy(),
                        inlier_probabilities=weights.copy(),
                        inlier_mask=inliers.copy(),
                        score=float(score),
                        data_cost=data_cost,
                        parameter_penalty=float((degree + 1) * np.log(n)),
                        inlier_rms_hz=float(np.sqrt(np.mean(residual[inliers] ** 2))),
                        full_rms_hz=float(np.sqrt(np.mean(residual**2))),
                        points=n,
                        seed_omitted_index=omitted,
                        iterations=iteration,
                    )
                if iteration == maximum_iterations or weights.sum() < degree + 1:
                    break
                root_weight = np.sqrt(weights)
                new = np.linalg.lstsq(
                    design * root_weight[:, None], target * root_weight, rcond=None
                )[0]
                movement = np.max(np.abs(design @ (new - coef)))
                coef = new
                if movement < 1e-7:
                    # The preceding iterate already agrees within this numerical tolerance.
                    break
        if best is not None:
            choices.append(best)
    if not choices:
        raise ValueError("no polynomial has sufficient non-clutter support")
    return sorted(choices, key=lambda row: (row["score"], row["degree"]))
