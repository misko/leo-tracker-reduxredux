"""Independent small density/geometry oracles, without corpus propagation."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp, roots_legendre
from scipy.stats import t

HERE = Path(__file__).resolve().parent
SCIENTIFIC = HERE.parent/'scientific'
sys.path.insert(0, str(SCIENTIFIC))
import support_bounds as b
import support_geometry as g
import support_math as m
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency, paired_phase_states
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checks():
    rows = []
    def check(name, condition, **evidence):
        rows.append(dict(name=name, passed=bool(condition), **evidence))
    rng = np.random.default_rng(2026102517)
    # Compare the certificate's actual rotation/interpolation to the original
    # helper, not to a second copy of its own h(phi) implementation.
    knots = np.array([-30., -4., 2., 30.])
    positions = np.array([[7000., -90., 310.], [7002., 40., 305.],
                          [6999., 68., 309.], [6995., 210., 301.]])
    velocities = np.array([[0., 7., .1], [.01, 7.1, .12],
                           [-.01, 7.2, .09], [0., 7., .11]])
    bank = dict(time_s=knots, position_km=positions[None], velocity_km_s=velocities[None])
    up = np.array([.6, 0., .8]); observer = np.array([3800., 0., 5100.])
    maximum = 0.
    for stamp in (-.37, 1.13):
        cuts = np.unique(np.r_[-15., knots[(knots > stamp-15)&(knots < stamp+15)]-stamp, 15.])
        for lo, hi in zip(cuts[:-1], cuts[1:]):
            mid = (lo+hi)/2
            j = np.searchsorted(knots, stamp+mid, side='right')-1
            slope = (positions[j+1]-positions[j])/(knots[j+1]-knots[j])
            pos = positions[j]+(stamp+mid-knots[j])*slope
            phi = np.linspace(lo, hi, 9)
            actual = paired_phase_states(dict(bank,
                position_km=np.repeat(positions[None], len(phi), axis=0),
                velocity_km_s=np.repeat(velocities[None], len(phi), axis=0)),
                np.full(len(phi), stamp), np.arange(len(phi)), phi)[0]
            expected = actual@up-observer@up
            computed = g.piece_function(mid, pos, slope, up, observer)(phi)[0]
            maximum = max(maximum, float(np.max(abs(expected-computed))))
    check('certificate agrees with original paired interpolation/rotation', maximum < 1e-9,
          maximum_height_error_km=maximum)

    times = np.array([-.37, .21, .83, 1.13])
    modes = dict(time_s=knots,
        position_km=rng.normal(size=(3, len(knots), 3))*.08,
        velocity_km_s=rng.normal(size=(3, len(knots), 3))*.001)
    d = dict(target_sky=bank, target_mode_bank=modes, target_track=dict(times=times))
    q = np.array([.97, .99, 1.01, 1.03])
    def geometry(phi):
        phi = np.asarray(phi); n = len(phi)
        sky = dict(time_s=knots,
                   position_km=np.repeat(bank['position_km'], n, axis=0),
                   velocity_km_s=np.repeat(bank['velocity_km_s'], n, axis=0))
        mode = dict(time_s=knots,
                    position_km=np.tile(modes['position_km'], (n, 1, 1)),
                    velocity_km_s=np.tile(modes['velocity_km_s'], (n, 1, 1)))
        labels = np.repeat(np.arange(n), len(times)); flat = np.tile(times, n)
        frequency = paired_phase_frequency(sky, flat, labels, phi, 0., 0.)[0]
        shape = paired_frequency_modes(sky, mode, flat, labels, phi, 0., 0.)
        return dict(frequency_hz=frequency.reshape(n, -1), shape_columns_hz=shape.reshape(n, -1, 3))
    pieces = np.array([[.10, .12], [.90, .92]])
    center = pieces.mean(axis=1); half = np.diff(pieces, axis=1)[:, 0]/2
    fd, bd = b.derivative_bounds(d, center, half, np.array([6378.137, 0., 0.]), q)
    actual_f = []; actual_b = []
    for phase in np.linspace(-.009, .009, 7):
        eps = 1e-5; plus = geometry(center+phase+eps); minus = geometry(center+phase-eps)
        actual_f.append(abs((plus['frequency_hz']-minus['frequency_hz'])/(2*eps))*q)
        actual_b.append(abs((plus['shape_columns_hz']-minus['shape_columns_hz'])/(2*eps))*q[None, :, None])
    fratio = float(np.max(np.asarray(actual_f)/fd[None]))
    bratio = float(np.max(np.asarray(actual_b)/bd[None]))
    check('analytic frequency and physical-mode derivative bounds cover direct finite differences',
          fratio <= 1+1e-7 and bratio <= 1+1e-7,
          maximum_frequency_ratio=fratio, maximum_mode_ratio=bratio)

    v = rng.normal(size=(4, 2))*17
    covariance = np.eye(4)*40**2+v@v.T+300**2
    root = np.linalg.cholesky(covariance)
    shifts = np.arange(-4, 5)[:, None]*np.ones((1, 4))*227272.7272727273
    base = geometry(center)['frequency_hz']*q
    raw = base[0]+np.array([30., -21., 13., 42.])
    comp = dict(root=root, raw=raw, q=q, observer=np.array([6378.137, 0., 0.]),
                noise_minimum_sd=40., base_logdet=float(2*np.log(np.diag(root)).sum()),
                whitened_aliases=solve_triangular(root, shifts.T, lower=True).T)
    distribution = t(3, loc=.2, scale=6/np.sqrt(3)); mass=distribution.cdf(15)-distribution.cdf(-15)
    law = dict(distribution=distribution, sd=6., mass=mass)
    lower, upper = b.physical_panel_bounds(d, comp, geometry, law, pieces)
    nodes, weights = roots_legendre(192)
    oracle = []
    for lo, hi in pieces:
        phi = (lo+hi)/2+(hi-lo)/2*nodes; geo = geometry(phi); logs=[]
        for j, value in enumerate(phi):
            shape = geo['shape_columns_hz'][j]*q[:, None]
            full = covariance+shape@shape.T
            rr = np.linalg.cholesky(full)
            residual = raw-geo['frequency_hz'][j]*q
            whitened = solve_triangular(rr, (residual[None]+shifts).T, lower=True).T
            cost = np.sum(whitened**2, axis=1)+2*np.log(np.diag(rr)).sum()+4*np.log(2*np.pi)
            logs.append(logsumexp(-cost/2)-np.log(len(shifts))+distribution.logpdf(value)-np.log(mass))
        oracle.append(float(logsumexp(np.asarray(logs)+np.log(weights*(hi-lo)/2))))
    oracle = np.asarray(oracle)
    check('full observation-space Gaussian/alias/prior integrals lie within physical enclosures',
          np.all(oracle >= lower-1e-7) and np.all(oracle <= upper+1e-7),
          lower_log_integrals=lower.tolist(), oracle_log_integrals=oracle.tolist(),
          upper_log_integrals=upper.tolist())

    for width in (.01, .1, 2.):
        center = .123456789; sigma=1e-4
        fun = lambda x: -1e6+np.logaddexp(np.log(.99)-.5*((x-center)/sigma)**2-np.log(sigma*np.sqrt(2*np.pi)), np.log(.01/2))
        ell = fun(np.array([0.]))
        derivative = (abs(center)+width/2)/sigma**2
        lo, hi = b.log_lipschitz_integrals(ell, derivative, np.array([width]))
        check('off-grid mixture cannot be certified by tiny quadrature errors',
              float(2*(hi-lo)[0]) > 1e-3, interval_width_s=width,
              objective_enclosure_width=float(2*(hi-lo)[0]))
    return rows


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True)
    args = parser.parse_args(); output=Path(args.output)
    if output.exists(): raise FileExistsError('preserve independent numerical receipts')
    sources = {str(p):sha(p) for p in [Path(__file__), SCIENTIFIC/'support_bounds.py',
        SCIENTIFIC/'support_geometry.py', SCIENTIFIC/'support_math.py']}
    started=time.monotonic(); rows=checks(); elapsed=time.monotonic()-started
    unchanged=all(sha(p)==digest for p,digest in sources.items())
    receipt=dict(all_passed=unchanged and all(row['passed'] for row in rows),
        source_hashes=sources, sources_unchanged=unchanged, checks=rows,
        numeric_seconds=elapsed, corpus_propagation_calls=0, position_fits=0,
        synthetic_geometry_only=True, geographic_truth_read=False)
    output.write_text(json.dumps(receipt, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(path=str(output), all_passed=receipt['all_passed'],
                         numeric_seconds=elapsed, failed=[r['name'] for r in rows if not r['passed']])))


if __name__ == '__main__': main()
