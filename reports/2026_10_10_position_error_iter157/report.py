"""Fixed synthetic comparison of adaptive coverage and actual callback budgets."""
import json
import math
from pathlib import Path
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.special import ndtr

from adaptive import ENVELOPE, integrate


def main():
    root = Path(__file__).resolve().parent
    previous = json.loads((root.parent/'2026_10_10_position_error_iter156/SUMMARY.json').read_text())
    p = previous['parameters']
    def remote(x):
        signal = p['peak']*math.exp(-.5*((p['center']-x)/p['sigma'])**2)
        return (math.log(p['clutter']+signal)-.5*p['prior_precision']*x*x,
                signal/(p['clutter']+signal)*(p['center']-x)/p['sigma']**2-p['prior_precision']*x)
    h, u = ENVELOPE.curvature_bounds([1.], [p['peak']/p['clutter']], p['sigma'], p['prior_precision'])
    cases = [('remote_peak', remote, -5., 5., h, u, previous['exact_log_integral']),
             ('gaussian', lambda x: (-.5*x*x, -x), -3., 3., 1., -1.,
              .5*math.log(2*math.pi)+math.log(ndtr(3)-ndtr(-3)))]
    rows, terminal = [], {}
    for name, callback, lower, upper, hb, ub, exact in cases:
        for budget in (1, 3, 7, 15, 31, 63, 127, 255, 512):
            start = time.monotonic()
            result = integrate(callback, lower, upper, h_bound=hb, u_bound=ub,
                               seam_bound=lambda left, right: -math.inf,
                               maximum_calls=budget, target_log_width=1e-4)
            elapsed = time.monotonic()-start
            bounds = result['bounds']
            assert result['full_support_covered']
            assert bounds['log_lower'] <= exact <= bounds['log_upper']
            assert result['actual_calls'] <= budget
            rows.append(dict(case=name, declared_budget=budget, actual_calls=result['actual_calls'],
                             active_cells=len(result['active_partition_ids']), status=result['status'],
                             exact_log_integral=exact, **bounds, elapsed_s=elapsed))
            if budget == 512:
                terminal[name] = result
    (root/'SUMMARY.json').write_text(json.dumps(dict(scope='Synthetic coverage only; no positioning result', rows=rows), indent=2)+'\n')
    # The ledger contains intentional -inf for proven seam-free synthetic cells.
    def serial(value):
        if isinstance(value, float) and not math.isfinite(value): return str(value)
        if isinstance(value, dict): return {k:serial(v) for k,v in value.items()}
        if isinstance(value, list): return [serial(v) for v in value]
        return value
    (root/'TERMINAL_RECEIPTS.json').write_text(json.dumps(serial(terminal), indent=2, allow_nan=False)+'\n')
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for name in terminal:
        selected = [r for r in rows if r['case']==name]
        axes[0].loglog([r['actual_calls'] for r in selected], [r['log_width'] for r in selected], 'o-', label=name.replace('_',' '))
    axes[0].axhline(1e-4, color='black', linestyle='--', label='Width target')
    axes[0].set(xlabel='All callback calls (including parents)', ylabel='Log-integral bound width', title='Fixed budget: adaptive subdivision')
    axes[0].legend()
    receipt = terminal['remote_peak']
    cells = [receipt['ledger'][i] for i in receipt['active_partition_ids']]
    axes[1].plot([r['center'] for r in cells], [r['upper']-r['lower'] for r in cells], '.', color='teal')
    axes[1].set(xlabel='Synthetic amplitude', ylabel='Final cell width', title='Complete support remains represented')
    axes[1].set_yscale('log')
    fig.savefig(root/'adaptive_width.png', dpi=160)
    print(json.dumps([r for r in rows if r['declared_budget']==512], indent=2))


if __name__ == '__main__':
    main()
