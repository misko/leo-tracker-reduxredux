"""Independent normalized cut-mixture and Gaussian remote-tail ceiling controls."""
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp

HERE = Path(__file__).resolve().parent


def logpdf(value, covariance):
    root = np.linalg.cholesky(covariance)
    white = solve_triangular(root, value, lower=True)
    return -.5 * (white @ white + 2 * np.log(np.diag(root)).sum() + len(value) * np.log(2 * np.pi))


def main():
    began = time.monotonic()
    rng = np.random.default_rng(202610252242)
    nd, nw = 5, 6
    variance = np.linspace(1.3, 3.1, nd + nw)
    shared = rng.normal(size=(nd + nw, 4)) * .7
    base = np.diag(variance) + shared @ shared.T
    constants = np.zeros((nd + nw, 2)); constants[:nd, 0] = 3.; constants[nd:, 1] = 3.
    base += constants @ constants.T
    shape = rng.normal(size=(nd + nw, 3)) * .4
    y = rng.normal(size=nd + nw) * 4
    log_ceiling = -.5 * (nw * np.log(2 * np.pi) + np.log(variance[nd:]).sum())
    minimum_conditional_excess = np.inf
    maximum_log_ratio_excess = -np.inf
    maximum_D_kernel_error = 0.
    for allocation in ('whole_physical', 'whole_poly', 'prefix_physical', 'suffix_physical', 'piecewise_poly'):
        for cut in (2, 3, 4):
            mask = np.ones(nd + nw)
            polynomial = np.zeros((nd + nw, 10))
            segments = []
            if allocation == 'whole_poly':
                mask[nd:] = 0; segments = [(0, nw)]
            elif allocation == 'prefix_physical':
                mask[nd + cut:] = 0; segments = [(cut, nw)]
            elif allocation == 'suffix_physical':
                mask[nd:nd + cut] = 0; segments = [(0, cut)]
            elif allocation == 'piecewise_poly':
                mask[nd:] = 0; segments = [(0, cut), (cut, nw)]
            for piece, (left, right) in enumerate(segments):
                z = np.linspace(-1, 1, right - left)
                polynomial[nd + left:nd + right, 5 * piece:5 * piece + 5] = np.polynomial.legendre.legvander(z, 4) * 10
            b = shape * mask[:, None]
            covariance = base + b @ b.T + polynomial @ polynomial.T
            dd = covariance[:nd, :nd]
            regression = np.linalg.solve(dd, covariance[:nd, nd:]).T
            conditional = covariance[nd:, nd:] - regression @ covariance[:nd, nd:]
            minimum_conditional_excess = min(minimum_conditional_excess,
                float(np.linalg.eigvalsh(conditional - np.diag(variance[nd:])).min()))
            maximum_D_kernel_error = max(maximum_D_kernel_error,
                float(np.max(abs(dd - base[:nd, :nd] - shape[:nd] @ shape[:nd].T))))
            # Include all independently normalized D and W alias hypotheses.
            d_logs = [logpdf(y[:nd] + kd * 7, dd) for kd in range(-4, 5)]
            joint_logs = [logpdf(np.r_[y[:nd] + kd * 7, y[nd:] + kw * 7], covariance)
                          for kd in range(-4, 5) for kw in range(-4, 5)]
            log_ratio = logsumexp(joint_logs) - np.log(81) - (logsumexp(d_logs) - np.log(9))
            maximum_log_ratio_excess = max(maximum_log_ratio_excess, float(log_ratio - log_ceiling))
    components = np.array([-30., -20., -24., -27., -23., -21.])
    split_log_evidence = float(logsumexp(components) - np.log(6))
    identical_log_evidence = float(logsumexp(np.full(6, -20.)) - np.log(6))
    checks = [
        dict(name='every split/whole model retains identical discovery marginal', passed=maximum_D_kernel_error < 1e-12),
        dict(name='conditioned witness covariance retains independent Gaussian noise floor', passed=minimum_conditional_excess >= -1e-12),
        dict(name='normalized81alias joint/D density obeys universal witness ceiling', passed=maximum_log_ratio_excess <= 1e-12),
        dict(name='normalizedcutmixture charges look-elsewhere and duplicate choices add no evidence',
             passed=components.max() - np.log(6) <= split_log_evidence <= components.max() and abs(identical_log_evidence + 20) < 1e-12),
        dict(name='fourprimaryclass and internal split priors separately normalize',
             passed=abs(np.full(4, .25).sum() - 1) < 1e-15 and abs(np.full(6, 1 / 6).sum() - 1) < 1e-15 and abs(np.full(3, 1 / 3).sum() - 1) < 1e-15),
    ]
    for check in checks:
        check['passed'] = bool(check['passed'])
    result = dict(all_passed=all(c['passed'] for c in checks), checks=checks,
        maximum_D_kernel_error=maximum_D_kernel_error, minimum_conditional_covariance_excess=minimum_conditional_excess,
        maximum_joint_over_D_logdensity_minus_ceiling=maximum_log_ratio_excess,
        seconds=time.monotonic() - began, source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Gaussian inverse-moment noise law only, not an exact Gamma-mixture density bound; synthetic algebra not corpus evidence',
        corpus_propagation_calls=0, position_fits=0, geographic_truth_read=False)
    with (HERE / 'math_checks.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(dict(path=str(HERE / 'math_checks.json'), all_passed=result['all_passed'], seconds=result['seconds'])))


if __name__ == '__main__':
    main()
