"""Quantify the explicit prior change required by finite-domain integration."""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.integrate import quad
from scipy.stats import t

HERE = Path(__file__).resolve().parent


def check():
    rows = []
    evidence = json.loads((HERE/'phase_linearization.json').read_text())
    for case in evidence['cases']:
        item = case['evaluations'][0]
        mu, sigma, nu = item['phase_mean_s'], item['phase_marginal_sd_s'], item['phase_nu']
        scale = sigma*np.sqrt((nu-2)/nu)
        low, high = t.cdf((-15-mu)/scale, nu), t.cdf((15-mu)/scale, nu)
        mass = high-low
        def pdf(phase):
            return t.pdf((phase-mu)/scale, nu)/scale/mass
        mean = quad(lambda phase: phase*pdf(phase), -15, 15, epsabs=1e-11)[0]
        variance = quad(lambda phase: (phase-mean)**2*pdf(phase), -15, 15, epsabs=1e-11)[0]
        checks = []
        for order in (81, 161):
            nodes, weights = np.polynomial.legendre.leggauss(order)
            phase = mu+scale*t.ppf(low+(nodes+1)/2*mass, nu)
            weights /= 2
            approximate_mean = float(weights@phase)
            approximate_variance = float(weights@(phase-approximate_mean)**2)
            checks.append(dict(order=order, mean_error_s=approximate_mean-mean,
                variance_error_s2=approximate_variance-variance,
                normalized_weight_error=float(weights.sum()-1)))
        rows.append(dict(case=case['case'], original_location_s=mu, original_marginal_sd_s=sigma,
            physical_domain_s=[-15, 15], prior_mass_removed=1-mass,
            conditional_mean_s=mean, conditional_sd_s=float(np.sqrt(variance)), quadrature_moment_checks=checks))
    result = dict(status='diagnostic_only', does_not_authorize_prior_change=True, position_fits=0,
        GPS_used=False, source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), cases=rows)
    with (HERE/'phase_domain.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    check()
