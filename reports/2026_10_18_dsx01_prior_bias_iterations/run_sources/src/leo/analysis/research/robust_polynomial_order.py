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


def partition_catalogue(tracks, **fit_options):
    """Return fitted cores plus explicit original background records, losslessly.

    Original piecewise curves and fragments too small for the order comparison
    are retained unchanged. This measured intervention currently supports only
    single-piece fragments. It never smooths or alters CFO measurements.
    """
    originals = [oid for track in tracks for oid in track["observation_ids"]]
    if len(set(originals)) != len(originals):
        raise ValueError("duplicate original observation ownership")
    cores, background, reviews = [], [], []
    for track in tracks:
        n = len(track["times"])
        if n < 5 or len(track.get("pieces", [None])) != 1:
            cores.append(track.copy())
            reviews.append(
                dict(
                    component=track["key"],
                    original_points=n,
                    curve_points=n,
                    background_points=0,
                    status="original_population_retained",
                )
            )
            continue
        fits = polynomial_orders(track["times"], track["values"], **fit_options)
        best = fits[0]
        mask = best["inlier_mask"]
        t, y = np.asarray(track["times"]), np.asarray(track["values"])
        ids = [oid for i, oid in enumerate(track["observation_ids"]) if mask[i]]
        indices = [index for i, index in enumerate(track.get("indices", range(n))) if mask[i]]
        piece = dict(
            degree=best["degree"],
            reference_time_s=best["reference_time_s"],
            time_scale_s=best["time_scale_s"],
            coefficients_hz=best["coefficients_hz"],
            start_s=float(t[mask][0]),
            end_s=float(t[mask][-1]),
            indices=indices,
            observation_ids=ids,
        )
        # Rebuild scientific fields instead of carrying stale residual diagnostics.
        core = {
            name: track[name]
            for name in ("key", "source_id", "receiver", "channel", "bank", "rf_hz")
            if name in track
        }
        core.update(
            times=t[mask],
            values=y[mask],
            observation_ids=ids,
            indices=indices,
            pieces=[piece],
            start_s=piece["start_s"],
            end_s=piece["end_s"],
            residual_rms_hz=best["inlier_rms_hz"],
        )
        cores.append(core)
        for i, oid in enumerate(track["observation_ids"]):
            if not mask[i]:
                background.append(
                    dict(
                        component=track["key"],
                        observation_id=oid,
                        time_s=float(t[i]),
                        cfo_hz=float(y[i]),
                        receiver=track["receiver"],
                        channel=track["channel"],
                        residual_to_core_hz=float(best["residual_hz"][i]),
                    )
                )
        reviews.append(
            dict(
                component=track["key"],
                original_points=n,
                curve_points=len(ids),
                background_points=int(np.sum(~mask)),
                degree=best["degree"],
                original_degrees=[p["degree"] for p in track.get("pieces", [])],
                score=best["score"],
                curve_rms_hz=best["inlier_rms_hz"],
                status="robust_single_piece_partition",
            )
        )
    retained = [oid for track in cores for oid in track["observation_ids"]]
    retained += [row["observation_id"] for row in background]
    if sorted(retained) != sorted(originals) or len(set(retained)) != len(retained):
        raise RuntimeError("polynomial partition changed original observation ownership")
    return cores, background, reviews
