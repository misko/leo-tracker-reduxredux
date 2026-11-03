"""Precision counterfactual for three archived added curved components.

The supplied designs already condition shared RF errors on primary data. Only
conditional secondary noise is varied. This does not assert that such RF
precision is attainable, or that the mean model is unbiased.
"""

from pathlib import Path
import numpy as np
import diagnose_ds23_added_curve_information as original
from ds23_position_information import marginal_position_information
from ds23_precision_sensitivity import precision_sweep
from run_algo01_ds23_sample import ROOT, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_precision_sensitivity'


def one(case, root, prepare, arm):
    calls = []
    def capture(j, u, w, prior):
        calls.append(tuple(np.asarray(a).copy() for a in (j, u, w, prior)))
        return marginal_position_information(j, u, w, prior)
    saved = original.marginal_position_information
    try:
        original.marginal_position_information = capture
        source = original.one(case, root, prepare, arm)
    finally:
        original.marginal_position_information = saved
    if len(calls) != 4:
        raise ValueError('expected paired before/after designs for two phase controls')
    results = {}
    for name, (before, after) in zip(['phase_uncertain', 'phase_fixed_at_RF_fit'],
                                    [(calls[0], calls[1]), (calls[2], calls[3])], strict=True):
        j, u, w, prior = before; aj, au, aw, ap = after; n = len(j)
        if not all(np.array_equal(a, b) for a, b in [(j, aj[:n]), (u, au[:n]), (w, aw[:n]), (prior, ap)]):
            raise ValueError('before design or nuisance prior changed when adding observations')
        result = precision_sweep(j, u, w, aj[n:], au[n:], aw[n:], prior, [1., .3, .1, .03, .01])
        np.testing.assert_allclose(result['rows'][0]['information'], source['results'][name]['after_information'], rtol=1e-10, atol=1e-8)
        results[name] = result
    return dict(case=case, arm=arm, results=results, source_result_sha256=source['result_sha256'],
                original_curved_points=source['original_curved_points'], added_curved_points=source['added_curved_points'])


def main():
    OUT.mkdir(exist_ok=True)
    jobs = [('DS23-0132', original.ANCHOR, original.anchor_prepare),
            ('DS23-0377', original.ANCHOR, original.anchor_prepare),
            ('DS23-0014', original.INDEPENDENT, original.independent_prepare)]
    rows = []
    for case, root, prepare in jobs:
        for arm in ['c0', 'fitted_c']:
            row = one(case, root, prepare, arm); rows.append(row)
            print(case, arm, {k: [v['scales']['major_local_sigma_km'] for v in r['rows']]
                             for k, r in row['results'].items()}, flush=True)
    write(OUT/'evaluation.json', dict(rows=rows, sigma_factors=[1., .3, .1, .03, .01],
        local_mean_design_diagnostic_only=True, Gamma_precisions_and_nuisance_priors_held_fixed=True,
        new_conditional_noise_only_scaled=True, all_existing_measurements_unchanged=True,
        no_new_position_estimate_or_accuracy_claim=True, no_GPS_in_design=True,
        RF_precision_counterfactual_not_validated_measurement_precision=True,
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_precision_sensitivity.py',
                                             ROOT/'tools/diagnose_ds23_added_curve_information.py']}))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5), constrained_layout=True)
    for ax, (case, _, _) in zip(axes, jobs, strict=True):
        row = next(r for r in rows if r['case'] == case and r['arm'] == 'fitted_c')
        for name, result in row['results'].items():
            scale = np.array([r['sigma_factor'] for r in result['rows']])
            ax.plot(1/scale, [r['scales']['major_local_sigma_km'] for r in result['rows']], 'o-',
                    label='Phase uncertain' if name == 'phase_uncertain' else 'Phase fixed at RF estimate')
            ax.axhline(result['before_scales']['major_local_sigma_km'], color='gray', ls=':', lw=.8)
        ax.set(xscale='log', yscale='log', xlabel='Added frequency precision multiplier',
               ylabel='Local Gaussian major scale (km)', title=case)
        ax.grid(alpha=.2); ax.legend(fontsize=7)
    fig.suptitle('Counterfactual: can more precise secondary CFO separate position from nuisance terms?\nFixed local design and Gamma precisions; scales are not measured errors or calibrated confidence')
    fig.savefig(OUT/'precision_sensitivity.png', dpi=160); plt.close(fig)


if __name__ == '__main__':
    main()
