"""Reproducible synthetic envelope-width diagnostic; no recording access."""
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.special import logsumexp, ndtr

from envelopes import cell_envelope, curvature_bounds


def main():
    root = Path(__file__).resolve().parent
    # Deliberately difficult missed-mode example, chosen before recording tests.
    sigma, peak, clutter, mu, radius, precision = .05, 100., .01, 3., 5., 1e-12
    hb, ub = curvature_bounds([1.], [peak/clutter], sigma, precision)
    # Product of the signal Gaussian and proper Gaussian prior, integrated exactly.
    combined = 1/sigma**2 + precision
    shifted = mu/sigma**2/combined
    signal_mass = (peak * math.exp(-.5*mu**2*precision/(1+precision*sigma**2))
                   * math.sqrt(2*math.pi/combined)
                   * (ndtr(math.sqrt(combined)*(radius-shifted))
                      - ndtr(math.sqrt(combined)*(-radius-shifted))))
    clutter_mass = clutter*math.sqrt(2*math.pi/precision)*math.erf(radius*math.sqrt(precision/2))
    exact = math.log(signal_mass+clutter_mass)
    rows = []
    for count in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512):
        half = radius/count
        centers = -radius + half + np.arange(count)*2*half
        bounds = []
        for a in centers:
            signal = peak*math.exp(-.5*((mu-a)/sigma)**2)
            value = math.log(clutter+signal)-.5*precision*a*a
            gradient = signal/(clutter+signal)*(mu-a)/sigma**2-precision*a
            bounds.append(cell_envelope(value, gradient, half, hb, ub, seam_log_total=-math.inf))
        lower = float(logsumexp([b['log_lower'] for b in bounds]))
        upper = float(logsumexp([b['log_upper'] for b in bounds]))
        assert lower <= exact <= upper, (count, lower, exact, upper)
        rows.append(dict(cells=count, log_lower=lower, log_upper=upper, log_width=upper-lower))
    result = dict(scope='Synthetic uniform partitions, not adaptive integration or position accuracy',
                  parameters=dict(sigma=sigma, peak=peak, clutter=clutter, center=mu,
                                  support=[-radius, radius], prior_precision=precision),
                  exact_log_integral=exact, h_bound=hb, u_bound=ub, rows=rows,
                  target_log_width=1e-4, meets_target_at_512=rows[-1]['log_width'] <= 1e-4)
    (root/'SUMMARY.json').write_text(json.dumps(result, indent=2)+'\n')
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    x = np.linspace(-radius, radius, 4001)
    axes[0].semilogy(x, (clutter+peak*np.exp(-.5*((x-mu)/sigma)**2))*np.exp(-.5*precision*x*x))
    axes[0].scatter([0], [clutter], color='darkorange', label='Initial midpoint')
    axes[0].set(xlabel='Synthetic clock-mode amplitude', ylabel='Integrand', title='Remote peak must remain covered')
    axes[0].legend()
    axes[1].loglog([r['cells'] for r in rows], [r['log_width'] for r in rows], 'o-', label='Global-curvature envelope')
    axes[1].axhline(1e-4, color='darkorange', linestyle='--', label='Proposed width target')
    axes[1].set(xlabel='Uniform cells / value-and-gradient calls', ylabel='Upper − lower log integral', title='Conservative does not imply inexpensive')
    axes[1].legend()
    fig.savefig(root/'envelope_width.png', dpi=160)
    print(json.dumps(dict(exact_log_integral=exact, width_at_512=rows[-1]['log_width'], meets_target_at_512=result['meets_target_at_512'])))


if __name__ == '__main__':
    main()
