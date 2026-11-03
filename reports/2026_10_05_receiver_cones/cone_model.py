"""Pure five-parameter, shared elliptical-cone conditional reception model.

Fixed nominal axes: az/el 270/70 and 90/70 degrees. Each cone has the same
two half-opening angles and edge softness; axial rolls are independent.
There is no obstruction, gain, scan/channel, position, or association fit.

The three outcomes are conditional on at least one receiver detecting. The
Bernoulli construction assumes receiver independence given direction. Its
latent propensities are NOT measured absolute detection probabilities.
"""

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

RAD = np.pi / 180
BORESIGHTS_DEG = ((270., 70.), (90., 70.))
BOUNDS = [(5*RAD, 85*RAD), (5*RAD, 85*RAD),
          (np.log(.01), np.log(2.)), (-np.pi, np.pi), (-np.pi, np.pi)]


def frame(azimuth_deg, elevation_deg):
    az, el = np.deg2rad([azimuth_deg, elevation_deg])
    bore = np.array([np.cos(el)*np.sin(az), np.cos(el)*np.cos(az), np.sin(el)])
    up = np.array([-np.sin(el)*np.sin(az), -np.sin(el)*np.cos(az), np.cos(el)])
    azimuth = np.array([np.cos(az), -np.sin(az), 0.])
    return np.stack((up, azimuth, bore))


def project(unit):
    unit = np.asarray(unit, float)
    if unit.ndim != 2 or unit.shape[1] != 3 or not np.isfinite(unit).all():
        raise ValueError('Expected finite N by 3 unit directions')
    if not np.allclose(np.linalg.norm(unit, axis=1), 1, atol=1e-7):
        raise ValueError('Directions must be unit length')
    return np.stack([unit @ frame(*angles).T for angles in BORESIGHTS_DEG], axis=1)


def logits_and_jacobian(theta, projected):
    """m = z - hypot(x/tan(alpha), y/tan(beta)); logit = m / softness.

    m=0 is the exact front-facing elliptical-cone boundary, without dividing
    by z. Negative/back-facing z cannot satisfy m>0. Softness is dimensionless
    in this unit-vector margin, not an angular beamwidth in degrees.
    """
    alpha, beta, log_width, roll0, roll1 = theta
    roll = np.array([roll0, roll1])
    c, s = np.cos(roll), np.sin(roll)
    p, q, z = projected.transpose(2, 0, 1)
    x, y = p*c+q*s, -p*s+q*c
    ca, cb = 1/np.tan(alpha), 1/np.tan(beta)
    h = np.sqrt((x*ca)**2+(y*cb)**2+1e-24)
    scale = np.exp(-log_width)
    logits = (z-h)*scale
    jac = np.zeros((len(projected), 2, 5))
    jac[:, :, 0] = x*x*ca/(np.sin(alpha)**2*h)*scale
    jac[:, :, 1] = y*y*cb/(np.sin(beta)**2*h)*scale
    jac[:, :, 2] = -logits
    dr = x*y*(cb*cb-ca*ca)/h*scale
    jac[:, 0, 3] = dr[:, 0]
    jac[:, 1, 4] = dr[:, 1]
    return logits, jac


def probabilities(theta, projected):
    logits, _ = logits_and_jacobian(theta, projected)
    scores = np.column_stack((logits, logits.sum(axis=1)))
    return np.exp(scores-logsumexp(scores, axis=1, keepdims=True))


def loss(theta, projected, outcome, weights):
    logits, jac = logits_and_jacobian(theta, projected)
    scores = np.column_stack((logits, logits.sum(axis=1)))
    norm = logsumexp(scores, axis=1)
    p = np.exp(scores-norm[:, None])
    weights = weights/weights.sum()
    value = weights @ (norm-scores[np.arange(len(outcome)), outcome])
    difference = np.column_stack((p[:, 0]+p[:, 2]-(outcome != 1),
                                  p[:, 1]+p[:, 2]-(outcome != 0)))
    grad = np.einsum('n,nr,nrp->p', weights, difference, jac)
    return float(value), grad


def canonical(theta):
    theta = np.array(theta, float).copy()
    if theta[0] < theta[1]:
        theta[:2] = theta[1::-1]
        theta[3:] += np.pi/2
    theta[3:] = (theta[3:]+np.pi/2) % np.pi - np.pi/2
    return theta


def parameters(theta):
    theta = canonical(theta)
    return dict(major_half_angle_deg=float(theta[0]/RAD),
                minor_half_angle_deg=float(theta[1]/RAD),
                edge_softness=float(np.exp(theta[2])),
                rx0_roll_deg=float(theta[3]/RAD), rx1_roll_deg=float(theta[4]/RAD))


def fit(unit, outcome, weights, *, circular=False, starts=12):
    projected = project(unit)
    outcome = np.asarray(outcome, int)
    weights = np.asarray(weights, float)
    if len(outcome) != len(unit) or weights.shape != outcome.shape:
        raise ValueError('Mismatched observations')
    if not np.isin(outcome, [0, 1, 2]).all() or not np.isfinite(weights).all() or np.any(weights <= 0):
        raise ValueError('Invalid outcomes or weights')
    rolls = [(0, 0), (45, 45), (0, 90), (90, 0), (45, -45), (-45, 45),
             (90, 90), (20, -65), (-65, 20), (60, -20), (-20, 60), (-30, -30)]
    runs = []
    for i in range(starts):
        r0, r1 = rolls[i % len(rolls)]
        initial = np.array([45*RAD, 25*RAD, np.log(.2), r0*RAD, r1*RAD])
        if circular:
            def objective(v):
                val, grad = loss(np.array([v[0], v[0], v[1], 0., 0.]), projected, outcome, weights)
                return val, np.array([grad[0]+grad[1], grad[2]])
            opt = minimize(objective, [(.3+.07*i), np.log(.2)], jac=True,
                           bounds=[BOUNDS[0], BOUNDS[2]], method='L-BFGS-B',
                           options=dict(maxiter=600, ftol=1e-12, gtol=1e-7, maxls=40))
            theta = np.array([opt.x[0], opt.x[0], opt.x[1], 0., 0.])
        else:
            opt = minimize(loss, initial, args=(projected, outcome, weights), jac=True,
                           bounds=BOUNDS, method='L-BFGS-B',
                           options=dict(maxiter=600, ftol=1e-12, gtol=1e-7, maxls=40))
            theta = canonical(opt.x)
        runs.append(dict(theta=theta.tolist(), loss=float(opt.fun), converged=bool(opt.success),
                         status=str(opt.message), iterations=int(opt.nit)))
    best = min(runs, key=lambda r: r['loss'])
    theta = np.array(best['theta'])
    p = probabilities(theta, projected)
    baseline = np.bincount(outcome, weights=weights, minlength=3)/sum(weights)
    selected = p[np.arange(len(outcome)), outcome]
    w = weights/weights.sum()
    return dict(theta=theta.tolist(), parameters=parameters(theta), runs=runs,
                converged=best['converged'], status=best['status'],
                in_sample_log_loss=best['loss'],
                null_log_loss=float(-w @ np.log(baseline[outcome])),
                in_sample_brier=float(w @ np.sum((p-np.eye(3)[outcome])**2, axis=1)),
                raw_outliers_005=int((selected < .05).sum()),
                weighted_outlier_fraction_005=float(w @ (selected < .05)),
                outcomes=np.bincount(outcome, minlength=3).tolist(), events=len(outcome),
                bound_hits=[i for i, (a, b) in enumerate(BOUNDS[:3])
                            if min(abs(theta[i]-a), abs(theta[i]-b)) < 1e-4])


def boundary(theta, receiver, size=361):
    """Exact cone edge in ENU unit directions; roll 0 aligns major axis up."""
    alpha, beta, _, *rolls = theta
    roll = rolls[receiver]
    up, az, bore = frame(*BORESIGHTS_DEG[receiver])
    e1 = np.cos(roll)*up+np.sin(roll)*az
    e2 = -np.sin(roll)*up+np.cos(roll)*az
    phi = np.linspace(0, 2*np.pi, size)
    u = bore+np.tan(alpha)*np.cos(phi)[:, None]*e1+np.tan(beta)*np.sin(phi)[:, None]*e2
    return u/np.linalg.norm(u, axis=1)[:, None]
