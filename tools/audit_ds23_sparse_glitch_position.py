"""Replay sparse-glitch fits and calibration separation, then score geography."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
from ds23_sparse_glitch_noise import make_glitch_problem
from probe_ds23_frequency_events import summary
from probe_ds23_sign_carrier_position import context_signed
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha
import probe_ds23_sparse_glitch_position as inference


def replay(case):
    saved = read(inference.BULK/(case+'.json'))
    if saved['status'] != 'complete':
        raise ValueError(f'{case}: sparse glitch trial unavailable: {saved}')
    scan, node, mask, powers, means, hyper, entries, signed, source = context_signed(case)
    if sha(source) != saved['incumbent_sha256'] or signed['policy_arms'] != saved['incumbent_arms']:
        raise ValueError('sparse-glitch incumbent changed')
    for actual, expected in [(mask, saved['original_mask']), (powers, saved['powers']), (means, saved['means_s'])]:
        np.testing.assert_array_equal(actual, expected)
    if hyper != saved['hyper'] or entries != saved['entries']:
        raise ValueError('sparse-glitch priors or predictive observations changed')
    def endpoint(model, arm, old, linear):
        p = make_glitch_problem(scan, node, mask, arm, np.array(old['phase_reference']), powers, means, hyper,
                               entries if linear else [], *inference.MODELS[model])
        x = np.array(old['endpoint_east_north_km']); r = summary(p, x, entries if linear else []); c = p.calculate(x)
        delta = r['negative_twice_elbo']-old['negative_twice_elbo']
        if abs(delta) > 1e-6 or r['linear_calibration_max_difference'] != 0:
            raise ValueError('sparse-glitch objective or fixed calibration failed replay')
        np.testing.assert_allclose(c['glitch_probability'], old['glitch_probability'], rtol=1e-10, atol=1e-10)
        np.testing.assert_allclose(c.get('linear_glitch_probability', []), old['linear_glitch_probability'], rtol=1e-10, atol=1e-10)
        for key in ['gates', 'linear_gates']:
            one = r[key]['tracks'] if key == 'gates' else r[key]; two = old[key]['tracks'] if key == 'gates' else old[key]
            if [(v['component'], v['compatible']) for v in one] != [(v['component'], v['compatible']) for v in two]:
                raise ValueError('sparse-glitch original gate mismatch')
        r.update(final_phase_change_s=old['final_phase_change_s'], final_log_precision_change=c['final_log_precision_change'],
                 linear_mixture_convergence=c.get('linear_mixture_convergence', 0.))
        return p, r, delta, c
    curved = {}
    for model, old in saved['curved_selection'].items():
        _, curved[model], _, _ = endpoint(model, 'c0', old, False)
    rows = [dict(case=case, method='incumbent', arm=a, paired_valid=True,
                 policy_latlon=r['endpoint_latlon'], trial_latlon=r['endpoint_latlon'], frequency_RMS_hz=r['RMS_hz'])
            for a, r in signed['policy_arms'].items()]
    branches = {}
    for model, branch in saved['results'].items():
        pair = {}
        for arm, old in branch['arms'].items():
            p, r, delta, c = endpoint(model, arm, old, True); pair[arm] = r
            rows.append(dict(case=case, method=model, arm=arm, paired_valid=branch['paired_valid'],
                policy_latlon=branch['policy_arms'][arm]['endpoint_latlon'], trial_latlon=old['endpoint_latlon'],
                frequency_RMS_hz=r['RMS_hz'], negative_twice_elbo=r['negative_twice_elbo'], objective_replay_difference=delta,
                original_curved_points=r['active_points'], original_predictive_points=r['predictive_points'],
                curved_glitches_posterior_above_half=int((np.array(c['glitch_probability'])[mask]>.5).sum()),
                predictive_glitches_posterior_above_half=int((np.array(c.get('linear_glitch_probability', []))>.5).sum()),
                failed_curved=[v['component'] for v in r['gates']['tracks'] if not v['compatible']],
                failed_linear=[v['component'] for v in r['linear_gates'] if not v['compatible']]))
        accepted = valid(pair) and all(inference.converged(r) for r in pair.values())
        if accepted != branch['paired_valid'] or branch['policy_arms'] != (branch['arms'] if accepted else signed['policy_arms']):
            raise ValueError('sparse-glitch paired decision or fallback changed')
        branches[model] = dict(arms=pair, paired_valid=accepted)
    # Independent conditional selection: linears do not choose calibration's
    # tail model, only the measurement tail in the predictive likelihood.
    cgain = curved['fragment']['negative_twice_elbo']-curved['curved_tail']['negative_twice_elbo']
    parent = 'curved_tail' if (cgain > np.log(max(2, curved['fragment']['active_points']))
        and curved['curved_tail']['final_phase_change_s'] <= .01 and inference.converged(curved['curved_tail'])) else 'fragment'
    alternative = 'both' if parent == 'curved_tail' else 'predictive_tail'
    gain = branches[parent]['arms']['c0']['negative_twice_elbo']-branches[alternative]['arms']['c0']['negative_twice_elbo']
    choice = alternative if gain > np.log(max(2, branches[parent]['arms']['c0']['predictive_points'])) and branches[alternative]['paired_valid'] else parent
    if choice != saved['selection']['model'] or parent != saved['selection']['curved_choice']:
        raise ValueError('sparse-glitch RF-only selection changed')
    expected = signed['policy_arms'] if choice == 'fragment' else saved['results'][choice]['policy_arms']
    if saved['policy_arms'] != expected:
        raise ValueError('sparse-glitch selected policy changed')
    for arm in ARMS:
        r = next(v for v in rows if (v['method'], v['arm']) == (choice, arm))
        rows.append(dict(r, method='RF_selected', policy_latlon=expected[arm]['endpoint_latlon'], selected_model=choice))
    calibration_checks = []
    for arm in ARMS:
        old = signed['policy_arms'][arm]; x = np.array(old['endpoint_east_north_km'])
        for epsilon in [0., .01]:
            a = make_glitch_problem(scan, node, mask, arm, np.array(old['phase_reference']), powers, means, hyper, entries, epsilon, 0.)
            b = make_glitch_problem(scan, node, mask, arm, np.array(old['phase_reference']), powers, means, hyper, entries, epsilon, .01)
            np.testing.assert_array_equal(a.calculate(x)['coefficient'], b.calculate(x)['coefficient'])
            calibration_checks.append(dict(arm=arm, curved_epsilon=epsilon, maximum_coefficient_change=0.))
    return dict(rows=rows, calibration_checks=calibration_checks, result_sha256=sha(inference.BULK/(case+'.json')))


def report():
    protocol = read(inference.OUT/'protocol.json')
    for name, digest in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name) != digest:
            raise ValueError('sparse-glitch source changed after freeze')
    with ProcessPoolExecutor(max_workers=8) as pool:
        receipts = [f.result() for f in as_completed([pool.submit(replay, c) for c in protocol['cases']])]
    rows = [r for receipt in receipts for r in receipt['rows']]
    from report_algo02_ds23 import position_error
    for r in rows:
        r['position_error_km'] = position_error(r['policy_latlon']); r['trial_position_error_km'] = position_error(r['trial_latlon'])
    methods = ['incumbent', *inference.MODELS, 'RF_selected']; statistics = {}
    for method in methods:
        statistics[method] = {}
        for arm in ARMS:
            group = [r for r in rows if (r['method'], r['arm']) == (method, arm)]
            if len(group) != len(protocol['cases']):
                raise ValueError('incomplete sparse-glitch denominator')
            baseline = {r['case']: r['position_error_km'] for r in rows if (r['method'], r['arm']) == ('incumbent', arm)}
            error = [r['position_error_km'] for r in group]; changes = [r['position_error_km']-baseline[r['case']] for r in group]
            statistics[method][arm] = dict(count=len(group), mean_km=float(np.mean(error)), median_km=float(np.median(error)),
                p90_km=float(np.quantile(error, .9)), paired_valid=sum(r['paired_valid'] for r in group),
                improved=sum(v < -1e-6 for v in changes), regressed=sum(v > 1e-6 for v in changes))
    write(inference.OUT/'independent_replay_audit.json', dict(rows=rows, statistics=statistics, receipts=receipts,
        original_observations_priors_aliases_and_gates_replayed=True, no_GPS_inference=True,
        no_linear_calibration_changes_at_fixed_position_verified=True, matched_c0_fitted_c=True, full_DS23_goal_achieved=False))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), constrained_layout=True)
    for ax, arm in zip(axes, ARMS, strict=True):
        for key, offset in [('mean_km', -.18), ('median_km', .18)]:
            bars = ax.bar(np.arange(len(methods))+offset, [statistics[m][arm][key] for m in methods], width=.34, label=key[:-3])
            ax.bar_label(bars, fmt='%.3f', fontsize=8)
        ax.set(xticks=np.arange(len(methods)), xticklabels=[m.replace('_', '\n') for m in methods], ylabel='Position error (km)', title=arm)
        ax.axhline(.5, ls='--', color='k', lw=.6); ax.legend(); ax.grid(axis='y', alpha=.2)
    fig.suptitle(f'Shared fragment noise plus sparse measurement glitches · {len(protocol["cases"])} development scans\nOriginal points and gates retained; marginal variance matched; fixed-position calibration independent of linear data')
    fig.savefig(inference.OUT/'position_comparison.png', dpi=160); plt.close(fig)
    print('SPARSE_GLITCH_AUDIT', statistics, flush=True)


if __name__ == '__main__':
    report()
