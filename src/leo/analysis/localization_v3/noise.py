"""Original radio-only uncertainty estimate from graph-polynomial residuals."""
import numpy as np

from leo.analysis.localization_v3.tracks import active_curvature


def fit_variance(margins, squares):
    m, y = np.asarray(margins), np.asarray(squares)
    if m.ndim != 1 or y.shape != m.shape or not len(m) or np.any(m <= 0) or np.any(y < 0):
        raise ValueError('positive margins and nonnegative squared residuals required')
    if not np.isfinite(m).all() or not np.isfinite(y).all():
        raise ValueError('finite noise observations required')

    def profile(ratio):
        shape = 1 + ratio / m
        maximum = min(360000, 360000 / ratio) if ratio else 360000
        floor = np.clip(np.mean(y / shape), 1600, maximum)
        variance = floor * shape
        return float(np.mean(np.log(variance) + y / variance)), np.array([floor, floor * ratio])

    grid = np.r_[0, np.geomspace(1e-6, 225, 257)]
    values = np.array([profile(r)[0] for r in grid])
    best = int(np.argmin(values))
    left, right = grid[max(0, best - 1)], grid[min(len(grid) - 1, best + 1)]
    phi = (np.sqrt(5) - 1) / 2
    for _ in range(64):
        a, b = right - phi * (right - left), left + phi * (right - left)
        if profile(a)[0] < profile(b)[0]:
            right = b
        else:
            left = a
    candidates = [profile(grid[best]), profile((left + right) / 2)]
    return min(candidates, key=lambda pair: pair[0])[1]


def estimate_noise(tracks, observations):
    margins_by_id = {r['observation_id']: r['fractional_margin'] for r in observations}
    margins, squares = [], []
    for track in tracks:
        t, y = np.array(track['times']), np.array(track['values'])
        if not active_curvature(dict(times=t, values=y)):
            continue
        for piece in track['pieces']:
            use = (t >= piece['start_s']) & (t <= piece['end_s'])
            degree = piece['degree']
            if use.sum() < 2 * (degree + 1) + 3:
                continue
            times, values = t[use], y[use]
            z = (times - times.mean()) / max(1., float(np.ptp(times)))
            q, _ = np.linalg.qr(np.vander(z, degree + 1, increasing=True))
            leverage = np.sum(q**2, axis=1)
            residual = values - q @ (q.T @ values)
            squares.extend(residual**2 / (1 - leverage))
            margins.extend(margins_by_id[oid] for oid, active in zip(
                track['observation_ids'], use, strict=True) if active)
    if not squares:
        return dict(constant_radio_sigma_hz=150., extra_parameter_BIC_gain=0.,
                    noise_samples=0, per_observation_noise_sigma_hz={
                        r['observation_id']: 150. for r in observations},
                    rule='no eligible radio-polynomial residuals; fixed 150 Hz fallback')
    m, s = np.array(margins), np.array(squares)
    constant = float(np.clip(s.mean(), 40**2, 600**2))
    floor, strength = fit_variance(m, s)
    proposed = np.clip(floor + strength / m, 40**2, 600**2)
    gain = float(np.sum(np.log(constant) + s / constant - np.log(proposed) - s / proposed))
    bic = gain - np.log(len(s))
    noise = {r['observation_id']: float(np.sqrt(np.clip(
        floor + strength / r['fractional_margin'], 40**2, 600**2))) for r in observations}
    return dict(constant_radio_sigma_hz=float(np.sqrt(constant)),
                extra_parameter_BIC_gain=bic, noise_samples=len(s),
                floor_sigma_hz=float(np.sqrt(floor)), strength_hz2=float(strength),
                per_observation_noise_sigma_hz=noise, heteroscedastic_selected=bic > 0,
                rule=('floor + strength/margin; enable heteroscedasticity '
                      'only if extra BIC gain > 0'),
                model_is_uncertainty_proxy_not_calibrated_error_bar=True,
                no_GPS_TLE_or_satellite_residuals_used=True)
