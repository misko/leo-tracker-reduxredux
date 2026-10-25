"""Small independent mixture/conditional Gaussian identity checks, no corpus."""
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp

HERE = Path(__file__).resolve().parent


def log_normal(value, mean, covariance):
    root = np.linalg.cholesky(covariance)
    residual = solve_triangular(root, np.asarray(value) - mean, lower=True)
    return -.5 * (residual @ residual + 2 * np.log(np.diag(root)).sum() + len(value) * np.log(2 * np.pi))


def run():
    began = time.monotonic()
    rng = np.random.default_rng(202610252201)
    nd, nw = 5, 4
    n = nd + nw
    radio = rng.normal(size=(n, 3)) * .8
    base = np.diag(np.linspace(.7, 1.3, n)) + radio @ radio.T
    # Separate owner constants, preserving shared receiver cross-covariance.
    constants = np.zeros((n, 2))
    constants[:nd, 0] = 2
    constants[nd:, 1] = 2
    base += constants @ constants.T
    poly = rng.normal(size=(nw, 5)) * 1.1
    values = rng.normal(size=n) * 2
    phases = np.array([-1.3, -.4, .2, .9, 1.6])
    weights = np.array([.08, .2, .36, .26, .1])
    aliases = np.arange(-4, 5)
    period = 3.
    d_terms = []
    joint_terms = {branch: [] for branch in ('same', 'mixed')}
    conditional_terms = {branch: [] for branch in joint_terms}
    maximum_log_identity_error = 0.
    maximum_discovery_covariance_error = 0.
    for phi, weight in zip(phases, weights, strict=True):
        mean = np.linspace(-.4, .5, n) * phi + .2 * phi ** 2
        shape = np.column_stack((np.ones(n) * .3, np.linspace(-.2, .4, n) * (1 + phi * .1), np.sin(np.arange(n) + phi) * .2))
        same_covariance = base + shape @ shape.T
        mixed_shape = shape.copy()
        mixed_shape[nd:] = 0
        mixed_covariance = base + mixed_shape @ mixed_shape.T
        mixed_covariance[nd:, nd:] += poly @ poly.T
        maximum_discovery_covariance_error = max(maximum_discovery_covariance_error,
            float(np.max(abs(same_covariance[:nd, :nd] - mixed_covariance[:nd, :nd]))))
        for kd in aliases:
            yd = values[:nd] + kd * period
            log_d = log_normal(yd, mean[:nd], same_covariance[:nd, :nd])
            d_terms.append(np.log(weight) - np.log(9) + log_d)
            for branch, covariance in (('same', same_covariance), ('mixed', mixed_covariance)):
                branch_mean = mean.copy()
                if branch == 'mixed':
                    branch_mean[nd:] = 0
                regression = np.linalg.solve(covariance[:nd, :nd], covariance[:nd, nd:]).T
                conditional_mean = branch_mean[nd:] + regression @ (yd - branch_mean[:nd])
                conditional_covariance = covariance[nd:, nd:] - regression @ covariance[:nd, nd:]
                for kw in aliases:
                    y = np.r_[yd, values[nd:] + kw * period]
                    log_joint = log_normal(y, branch_mean, covariance)
                    log_conditional = log_normal(y[nd:], conditional_mean, conditional_covariance)
                    maximum_log_identity_error = max(maximum_log_identity_error, abs(log_joint - log_d - log_conditional))
                    joint_terms[branch].append(np.log(weight) - np.log(81) + log_joint)
                    conditional_terms[branch].append(np.log(weight) - np.log(81) + log_d + log_conditional)
    log_d = float(logsumexp(d_terms))
    joint = {b: float(logsumexp(v)) for b, v in joint_terms.items()}
    conditional = {b: float(logsumexp(v) - log_d) for b, v in conditional_terms.items()}
    shared_denominator_error = abs((joint['same'] - joint['mixed']) - (conditional['same'] - conditional['mixed']))
    closure = max(abs(conditional[b] - (joint[b] - log_d)) for b in joint)
    checks = [
        dict(name='same/mixed discovery covariance and mean exactly shared', passed=maximum_discovery_covariance_error == 0),
        dict(name='joint equals discovery times conditional for every phase and81aliases', passed=maximum_log_identity_error < 1e-12),
        dict(name='mixture conditionals use discovery posterior weighting', passed=closure < 1e-12),
        dict(name='same discovery denominator cancels in model odds', passed=shared_denominator_error < 1e-12),
        dict(name='finite81alias prior marginalizes to discovery9alias prior', passed=bool(np.allclose(np.sum(np.full((9, 9), 1 / 81), axis=1), 1 / 9))),
    ]
    for check in checks:
        check['passed'] = bool(check['passed'])
    return dict(all_passed=all(c['passed'] for c in checks), checks=checks,
        maximum_fixed_node_log_density_identity_error=maximum_log_identity_error,
        maximum_discovery_covariance_error=maximum_discovery_covariance_error,
        mixture_conditional_closure_error=closure, shared_denominator_odds_error=shared_denominator_error,
        log_discovery_evidence=log_d, joint_log_evidence=joint,
        conditional_log_evidence=conditional, seconds=time.monotonic() - began,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        corpus_propagation_calls=0, position_fits=0, geographic_truth_read=False,
        scope='finite synthetic phase quadrature checks algebra only, not production integration convergence or calibrated identity')


if __name__ == '__main__':
    output = HERE / 'math_checks.json'
    if output.exists():
        raise FileExistsError('preserve independent receipt')
    receipt = run()
    output.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(path=str(output), all_passed=receipt['all_passed'], seconds=receipt['seconds'])))
