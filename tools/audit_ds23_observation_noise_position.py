"""Replay noise-partition trials before position-error reporting."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np

from ds23_observation_noise import make_observation_noise_problem
from probe_ds23_frequency_events import summary
from probe_ds23_sign_carrier_position import context_signed
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha
import probe_ds23_observation_noise_position as inference


def replay(case):
    saved = read(inference.BULK/(case+'.json'))
    if saved['status'] != 'complete':
        raise ValueError(f'{case}: noise trial unavailable: {saved}')
    scan, node, mask, powers, means, hyper, entries, signed, source = context_signed(case)
    if sha(source) != saved['signed_incumbent_sha256'] or signed['policy_arms'] != saved['incumbent_arms']:
        raise ValueError('noise comparison incumbent changed')
    for actual, expected in [(mask, saved['original_mask']), (powers, saved['powers']), (means, saved['means_s'])]:
        np.testing.assert_array_equal(actual, expected)
    if hyper != saved['hyper'] or entries != saved['entries']:
        raise ValueError('noise comparison changed physical priors or predictive observations')
    def endpoint(model, arm, old, linear):
        p = make_observation_noise_problem(scan, node, mask, arm, np.array(old['phase_reference']),
                                            powers, means, hyper, entries if linear else [], inference.MODELS[model])
        x = np.array(old['endpoint_east_north_km']); r = summary(p, x, entries if linear else [])
        c = p.calculate(x); delta = r['negative_twice_elbo']-old['negative_twice_elbo']
        if abs(delta) > 1e-6 or r['linear_calibration_max_difference'] != 0:
            raise ValueError('noise likelihood or no-linear-calibration failed replay')
        np.testing.assert_allclose(c['noise_precision'], old['noise_precision'], rtol=1e-10, atol=1e-10)
        np.testing.assert_array_equal(p.noise_groups, old['noise_groups'])
        np.testing.assert_array_equal(p.original_noise_groups, old['original_noise_groups'])
        for key in ['gates', 'linear_gates']:
            one = r[key]['tracks'] if key == 'gates' else r[key]
            two = old[key]['tracks'] if key == 'gates' else old[key]
            if [(v['component'], v['compatible']) for v in one] != [(v['component'], v['compatible']) for v in two]:
                raise ValueError('noise original residual gates failed replay')
        r.update(final_phase_change_s=old['final_phase_change_s'], final_log_precision_change=c['final_log_precision_change'])
        return p, r, float(delta)
    curved = {}
    for model, old in saved['curved_selection'].items():
        _, r, _ = endpoint(model, 'c0', old, False); curved[model] = r
    eligible = [m for m in inference.MODELS if m != 'fragment'
        and curved['fragment']['negative_twice_elbo']-curved[m]['negative_twice_elbo'] > inference.PENALTY
        and curved[m]['final_phase_change_s'] <= .01 and curved[m]['final_log_precision_change'] <= 1e-4]
    choice = min(eligible, key=lambda m: curved[m]['negative_twice_elbo']) if eligible else 'fragment'
    if choice != saved['selected_model']:
        raise ValueError('curved-only model selection failed replay')
    rows = [dict(case=case, method='incumbent', arm=a, policy_latlon=r['endpoint_latlon'], trial_latlon=r['endpoint_latlon'],
        paired_valid=True, frequency_RMS_hz=r['RMS_hz']) for a, r in signed['policy_arms'].items()]
    for model, branch in saved['results'].items():
        pair = {}
        for arm, old in branch['arms'].items():
            p, r, delta = endpoint(model, arm, old, True); pair[arm] = r
            # Coarse original curve precision and new point precision are
            # indexed through distinct ownership maps, never interchanged.
            precision = np.array(old['noise_precision'])[p.noise_groups[p.keep]]
            rows.append(dict(case=case, method=model, arm=arm, paired_valid=branch['paired_valid'],
                policy_latlon=branch['policy_arms'][arm]['endpoint_latlon'], trial_latlon=old['endpoint_latlon'],
                objective_replay_difference=delta, frequency_RMS_hz=r['RMS_hz'], negative_twice_elbo=r['negative_twice_elbo'],
                median_point_precision=float(np.median(precision)), point_precision_below_point1=int((precision < .1).sum()),
                original_curved_points=r['active_points'], original_predictive_points=r['predictive_points'],
                failed_curved=[v['component'] for v in r['gates']['tracks'] if not v['compatible']],
                failed_linear=[v['component'] for v in r['linear_gates'] if not v['compatible']]))
        accepted = valid(pair) and all(r['final_log_precision_change'] <= 1e-4 for r in pair.values())
        if accepted != branch['paired_valid'] or branch['policy_arms'] != (branch['arms'] if accepted else signed['policy_arms']):
            raise ValueError('paired noise policy or exact fallback changed')
    expected = signed['policy_arms'] if choice == 'fragment' else saved['results'][choice]['policy_arms']
    if expected != saved['policy_arms']:
        raise ValueError('RF-selected noise policy changed')
    for arm in ARMS:
        selected = next(r for r in rows if r['method'] == choice and r['arm'] == arm)
        rows.append(dict(selected, method='RF_selected', selected_model=choice,
                         policy_latlon=saved['policy_arms'][arm]['endpoint_latlon']))
    return rows


def report():
    protocol = read(inference.OUT/'protocol.json')
    for name, expected in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name) != expected:
            raise ValueError('noise prototype source changed after freeze')
    with ProcessPoolExecutor(max_workers=8) as pool:
        rows = [r for f in as_completed([pool.submit(replay, c) for c in protocol['cases']]) for r in f.result()]
    from report_algo02_ds23 import position_error
    for r in rows:
        r['position_error_km'] = position_error(r['policy_latlon']); r['trial_position_error_km'] = position_error(r['trial_latlon'])
    methods = ['incumbent', *inference.MODELS, 'RF_selected']; statistics = {}
    for method in methods:
        statistics[method] = {}
        for arm in ARMS:
            group = [r for r in rows if (r['method'], r['arm']) == (method, arm)]
            if len(group) != len(protocol['cases']):
                raise ValueError('incomplete noise comparison denominator')
            baseline = {r['case']: r['position_error_km'] for r in rows if (r['method'], r['arm']) == ('incumbent', arm)}
            errors = [r['position_error_km'] for r in group]
            change = [r['position_error_km']-baseline[r['case']] for r in group]
            statistics[method][arm] = dict(count=len(group), mean_km=float(np.mean(errors)), median_km=float(np.median(errors)),
                p90_km=float(np.quantile(errors, .9)), paired_valid=sum(r['paired_valid'] for r in group),
                improved=sum(v < -1e-6 for v in change), regressed=sum(v > 1e-6 for v in change))
    write(inference.OUT/'independent_replay_audit.json', dict(rows=rows, statistics=statistics,
        protocol_sha256=sha(inference.OUT/'protocol.json'), all_original_points_and_gates_replayed=True,
        marginal_noise_prior_variance_unchanged=True, linear_data_never_calibrate=True,
        no_GPS_inference=True, full_DS23_goal_achieved=False))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    for ax, arm in zip(axes, ARMS, strict=True):
        for key, delta in [('mean_km', -.18), ('median_km', .18)]:
            bars = ax.bar(np.arange(len(methods))+delta, [statistics[m][arm][key] for m in methods], width=.34,
                          label=key.removesuffix('_km'))
            ax.bar_label(bars, fmt='%.3f', fontsize=8)
        ax.set(xticks=np.arange(len(methods)), xticklabels=[m.replace('_', '\n') for m in methods],
               ylabel='Position error (km)', title=arm)
        ax.axhline(.5, color='k', ls='--', lw=.6); ax.legend(); ax.grid(axis='y', alpha=.2)
    fig.suptitle(f'Fragment versus observation noise · {len(protocol["cases"])} development scans\nSame original measurements and marginal noise prior; original paired gates and exact fallback')
    fig.savefig(inference.OUT/'position_comparison.png', dpi=160); plt.close(fig)
    print('OBSERVATION_NOISE_AUDIT', statistics, flush=True)


if __name__ == '__main__':
    report()
