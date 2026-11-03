"""Causal phase/shape correlation from earlier TLE updates, without RF or GPS.

Coordinates match phase at scan midpoint plus the existing reference-aligned
mean-motion, inclination and RAAN directions. Marginal scales stay unchanged;
only correlations are learned. Later causal TLEs are prediction proxies, not
orbit truth. The two eccentricity directions are not represented here.
"""

import numpy as np
from sgp4.api import Satrec
from fit_s01_69333_tle_parameter import perturb
from investigate_ds23_adaptive_failures import causal_phase_sigma
from prototype_dsx01_mean_motion import reference_motion_satellite
from ds23_causal_shape_distribution import mean_elements
from learn_ds23_causal_phase_forecast import distribution_cost
from leo.sky.frames import julian_day_from_utc_ns


def state(satellite, utc_ns):
    jd, fr = julian_day_from_utc_ns(np.array([utc_ns]))
    error, position, velocity = satellite.sgp4(float(jd[0]), float(fr[0]))
    if error:
        raise ValueError("causal state propagation failed")
    return np.asarray(position), np.asarray(velocity)


def wrap_angle(value):
    return (value + np.pi) % (2*np.pi) - np.pi


def transition(a, b, c):
    published = c["collected_utc_ns"]
    if not (a["collected_utc_ns"] <= b["collected_utc_ns"] <= published and
            a["epoch"] < b["epoch"] < c["epoch"] <= published):
        return None
    gap = (b["epoch"]-a["epoch"])/1e9
    if gap < 1:
        return None
    target = published + 150_000_000_000
    sa, sb, sc = [Satrec.twoline2rv(*entry["lines"]) for entry in (a, b, c)]
    pa, _ = state(sa, target)
    pb, vb = state(sb, target)
    pc, _ = state(sc, target)
    raw_phase = float((pa-pb) @ vb / (vb @ vb))
    radial = pb/np.linalg.norm(pb)
    normal = np.cross(pb, vb)
    normal /= np.linalg.norm(normal)
    old_shape = pa-pb-raw_phase*vb
    sr = max(.05, float(abs(old_shape @ radial)))
    sn = max(.025, float(abs(old_shape @ normal)))
    radius = float(np.linalg.norm(pb))
    motion = sb.no_kozai*1440/(2*np.pi)
    scales = np.array([1.5*motion/radius*sr, sn/radius, sn/radius/max(abs(np.sin(sb.inclo)), .1)])
    eb = mean_elements(sb, b["epoch"])
    ec = mean_elements(sc, b["epoch"])
    delta = ec[:3]-eb[:3]
    delta[2] = wrap_angle(delta[2])
    elapsed_days = (target-b["epoch"])/86400e9
    pm = [state(reference_motion_satellite(sb, step, elapsed_days), target)[0] for step in (.001, -.001)]
    columns = [(pm[0]-pm[1])/.002]
    for parameter in ("inclination_deg", "raan_deg"):
        pp = [state(perturb(sb, parameter, step), target)[0] for step in (.001, -.001)]
        columns.append((pp[0]-pp[1])/np.deg2rad(.002))
    derivative = np.column_stack(columns)
    phase = float((pc-pb-derivative@delta) @ vb / (vb@vb))
    age = (target-b["epoch"])/1e9
    return dict(validation_time_ns=published, target_utc_ns=target,
        phase_residual_s=phase, shape_z=delta/scales,
        predicted_sigma_s=causal_phase_sigma(raw_phase, age, gap),
        unit_phase_forecast_s=float(-np.clip(age/gap, 0, 2)*raw_phase),
        phase_before_shape_removal_s=float((pc-pb) @ vb/(vb@vb)),
        shape_sigma=scales, age_s=age, epoch_gap_s=gap)


def standardized(rows, model):
    sigma = np.array([r["predicted_sigma_s"] for r in rows])
    prediction = np.array([r["unit_phase_forecast_s"] for r in rows])
    mean = np.clip(model["shrinkage"]*prediction, -np.minimum(15., 3*sigma), np.minimum(15., 3*sigma))
    phase = (np.array([r["phase_residual_s"] for r in rows])-mean)/(sigma*model["multiplier"])
    return np.column_stack((phase, np.array([r["shape_z"] for r in rows])))


def correlation_fit(z):
    """Robust zero-mean scatter, normalized to preserve every marginal scale."""
    z = np.asarray(z, float)
    if z.ndim != 2 or z.shape[1] != 4 or not np.isfinite(z).all() or len(z) < 4:
        raise ValueError("at least four finite phase/shape transitions required")
    covariance = np.eye(4)
    for _ in range(100):
        q = np.sum(np.linalg.solve(np.linalg.cholesky(covariance), z.T)**2, axis=0)
        weights = 7/(1+q)  # four-dimensional Student nu=3 robust scatter.
        candidate = (z.T*weights)@z/len(z)
        eigen, axes = np.linalg.eigh((candidate+candidate.T)/2)
        candidate = (axes*np.clip(eigen, .01, 100))@axes.T
        change = float(np.max(abs(candidate-covariance)))
        covariance = candidate
        if change < 1e-7:
            break
    sd = np.sqrt(np.diag(covariance))
    return covariance/sd[:,None]/sd[None,:]


def nll(z, correlation, phase_nu):
    z = np.asarray(z, float)
    root = np.linalg.cholesky(correlation)
    white = np.linalg.solve(root, z.T).T
    # The first latent coordinate retains ALGO02's Student phase distribution;
    # the other three are independent Gaussians conditional on that phase.
    return (distribution_cost(white[:,0], np.ones(len(z)), 1., phase_nu) +
        np.sum(white[:,1:]**2, axis=1) + 3*np.log(2*np.pi) + 2*np.log(np.diag(root)).sum())


def qualify(rows, boundary, prefix_phase, full_phase):
    training = [r for r in rows if r["validation_time_ns"] <= boundary]
    validation = [r for r in rows if r["validation_time_ns"] > boundary]
    fallback = dict(qualified=False, strength=0., correlation=np.eye(4),
        training_count=len(training), validation_count=len(validation))
    if len(training) < 30 or len(validation) < 30:
        return fallback
    train = standardized(training, prefix_phase)
    test = standardized(validation, prefix_phase)
    fitted = correlation_fit(train)
    candidates = []
    for strength in (0., .25, .5, .75, 1.):
        correlation = (1-strength)*np.eye(4)+strength*fitted
        cost = float(nll(train, correlation, prefix_phase["nu"]).sum())
        candidates.append(dict(strength=strength, training_BIC=cost+(0 if strength==0 else 6*np.log(len(train)))))
    chosen = min(candidates, key=lambda item:item["training_BIC"])
    strength = chosen["strength"]
    baseline = float(nll(test, np.eye(4), prefix_phase["nu"]).sum())
    alternative = float(nll(test, (1-strength)*np.eye(4)+strength*fitted, prefix_phase["nu"]).sum())
    qualified = strength > 0 and baseline-alternative > np.log(len(test))
    final = correlation_fit(standardized(rows, full_phase)) if qualified else np.eye(4)
    return dict(qualified=qualified, strength=strength if qualified else 0.,
        correlation=(1-strength)*np.eye(4)+strength*final if qualified else np.eye(4),
        training_correlation=fitted, candidates=candidates,
        validation_baseline_nll=baseline, validation_alternative_nll=alternative,
        validation_gain=baseline-alternative, training_count=len(training), validation_count=len(validation),
        marginal_scales_preserved=True, no_RF_or_GPS_selection=True)
