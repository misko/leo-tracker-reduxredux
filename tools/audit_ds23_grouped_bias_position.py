"""Replay frozen grouped-bias fits, then evaluate and visualize geography."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np

from ds23_grouped_bias_prior import make_grouped_bias_problem
from probe_ds23_frequency_events import summary
from probe_ds23_grouped_bias_position import OUT, BULK, MODELS, PENALTY
from probe_ds23_sign_carrier_position import context_signed
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha


def replay(case, stage):
    path = BULK/stage/(case+'.json'); saved = read(path)
    if saved['status'] != 'complete':
        raise ValueError(f'{case} inference unavailable: {saved}')
    scan, node, mask, powers, means, hyper, entries, signed, source = context_signed(case)
    if sha(source) != saved['incumbent_sha256'] or signed['policy_arms'] != saved['incumbent_arms']:
        raise ValueError('incumbent changed')
    np.testing.assert_array_equal(mask, saved['original_mask'])
    np.testing.assert_array_equal(powers, saved['powers'])
    np.testing.assert_array_equal(means, saved['means_s'])
    if hyper != saved['hyper'] or entries != saved['entries']:
        raise ValueError('physical priors or predictive observations changed')
    def fresh(model, arm, old, include_linear):
        p = make_grouped_bias_problem(scan, node, mask, arm, np.array(old['phase_reference']),
            powers, means, hyper, entries, *MODELS[model], include_linear=include_linear)
        # Independent direct indicator construction, including unobserved rows.
        indices = p.members+[e['track_index'] for e in entries]
        keys = [(scan.tracks[i]['receiver'], scan.tracks[i]['channel'], scan.tracks[i]['rf_hz']) for i in indices]
        families = [r['candidate_index'] for r in p.rows]+[e['candidate_index'] for e in entries]
        ch, fam = MODELS[model]
        expected = np.eye(len(indices))*(1-ch-fam)
        for i in range(len(indices)):
            for j in range(len(indices)):
                expected[i, j] += ch*(keys[i] == keys[j])+fam*(families[i] == families[j])
        np.testing.assert_allclose(p.bias_covariance, expected*300**2, atol=1e-10, rtol=0)
        r = summary(p, np.array(old['endpoint_east_north_km']), entries if include_linear else [])
        delta = r['negative_twice_elbo']-old['negative_twice_elbo']
        if abs(delta) > 1e-6 or r['linear_calibration_max_difference'] != 0:
            raise ValueError('likelihood or no-linear-calibration failed replay')
        for key in ['gates', 'linear_gates']:
            one = r[key]['tracks'] if key == 'gates' else r[key]
            two = old[key]['tracks'] if key == 'gates' else old[key]
            if [(v['component'], v['compatible']) for v in one] != [(v['component'], v['compatible']) for v in two]:
                raise ValueError('unchanged gates failed replay')
        r['final_phase_change_s'] = old['final_phase_change_s']
        return r, float(delta)
    curves = {}
    for model, record in saved['curved_selection'].items():
        curves[model], _ = fresh(model, 'c0', record, False)
    # Recompute model choice separately from inference's selection function.
    eligible = [m for m in MODELS if m != 'null'
                and curves['null']['negative_twice_elbo']-curves[m]['negative_twice_elbo'] > PENALTY
                and curves[m]['final_phase_change_s'] <= .01]
    selected = min(eligible, key=lambda m: curves[m]['negative_twice_elbo']) if eligible else 'null'
    if selected != saved['selected_model']:
        raise ValueError('RF-only covariance choice changed')
    rows = [dict(case=case, method='incumbent', arm=a, policy_latlon=r['endpoint_latlon'],
                 trial_latlon=r['endpoint_latlon'], paired_valid=True, frequency_RMS_hz=r['RMS_hz'],
                 curved_only_selection=selected) for a, r in signed['policy_arms'].items()]
    for model, branch in saved['results'].items():
        pair = {}
        for arm, record in branch['arms'].items():
            r, delta = fresh(model, arm, record, True); pair[arm] = r
            rows.append(dict(case=case, method=model, arm=arm, policy_latlon=branch['policy_arms'][arm]['endpoint_latlon'],
                trial_latlon=record['endpoint_latlon'], paired_valid=branch['paired_valid'],
                objective_replay_difference=delta, frequency_RMS_hz=record['RMS_hz'],
                negative_twice_elbo=record['negative_twice_elbo'],
                curved_only_selection=selected, linear_calibration_max_difference=r['linear_calibration_max_difference'],
                failed_curved=[v['component'] for v in r['gates']['tracks'] if not v['compatible']],
                failed_linear=[v['component'] for v in r['linear_gates'] if not v['compatible']]))
        if valid(pair) != branch['paired_valid']:
            raise ValueError('paired acceptance changed')
        if branch['policy_arms'] != (branch['arms'] if branch['paired_valid'] else signed['policy_arms']):
            raise ValueError('exact incumbent fallback changed')
    if saved['policy_arms'] != saved['results'][selected]['policy_arms']:
        raise ValueError('selected policy mismatch')
    rows += [dict(r, method='RF_selected') for r in list(rows) if r['method'] == selected]
    return dict(case=case, rows=rows, result_sha256=sha(path), selected_model=selected)


def report(stage):
    protocol_path = OUT/(stage+'_protocol.json'); protocol = read(protocol_path)
    for name, expected in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name) != expected:
            raise ValueError('frozen inference source changed')
    with ProcessPoolExecutor(max_workers=8) as pool:
        receipts = [f.result() for f in as_completed([pool.submit(replay, c, stage) for c in protocol['cases']])]
    rows = [r for receipt in receipts for r in receipt['rows']]
    # No geographic information is available to the inference or model choice.
    from report_algo02_ds23 import position_error
    for r in rows:
        r['policy_position_error_km'] = position_error(r['policy_latlon'])
        r['trial_position_error_km'] = position_error(r['trial_latlon'])
    methods = ['incumbent', 'null', *[m for m in MODELS if m != 'null'], 'RF_selected'] if stage == 'development' else ['incumbent', 'null', 'RF_selected']
    statistics = {}
    for method in methods:
        statistics[method] = {}
        for arm in ARMS:
            group = [r for r in rows if (r['method'], r['arm']) == (method, arm)]
            if len(group) != len(protocol['cases']):
                raise ValueError('incomplete comparison denominator')
            baseline = {r['case']: r['policy_position_error_km'] for r in rows if (r['method'], r['arm']) == ('incumbent', arm)}
            values = [r['policy_position_error_km'] for r in group]
            change = [r['policy_position_error_km']-baseline[r['case']] for r in group]
            statistics[method][arm] = dict(count=len(values), mean_km=float(np.mean(values)), median_km=float(np.median(values)),
                p90_km=float(np.quantile(values, .9)), paired_valid=sum(r['paired_valid'] for r in group),
                improved=sum(v < -1e-6 for v in change), regressed=sum(v > 1e-6 for v in change),
                unchanged=sum(abs(v) <= 1e-6 for v in change))
    write(OUT/(stage+'_independent_replay.json'), dict(rows=rows, statistics=statistics, receipts=receipts,
        protocol_sha256=sha(protocol_path), unchanged_observations_aliases_gates=True,
        all_marginal_fragment_variances_fixed=True, full_linear_covariance_replayed=True,
        geography_used_only_after_inference=True, full_DS23_goal_achieved=False))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), constrained_layout=True)
    for ax, arm in zip(axes, ARMS, strict=True):
        x = np.arange(len(methods))
        for key, offset in [('mean_km', -.18), ('median_km', .18)]:
            bars = ax.bar(x+offset, [statistics[m][arm][key] for m in methods], width=.34, label=key.replace('_km', ''))
            ax.bar_label(bars, fmt='%.3f', fontsize=8)
        ax.set(xticks=x, xticklabels=[m.replace('_', '\n') for m in methods], ylabel='Position error (km)', title=arm)
        ax.axhline(.5, color='k', ls='--', lw=.7); ax.legend(); ax.grid(axis='y', alpha=.2)
    fig.suptitle(f'Fixed300Hz marginal bias uncertainty · {stage} · {len(protocol["cases"])} DS23 scans\nCovariance selected by curved RF likelihood; unchanged gates and exact incumbent fallback')
    fig.savefig(OUT/(stage+'_position_comparison.png'), dpi=160); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    for ax, arm in zip(axes, ARMS, strict=True):
        baseline = {r['case']: r['policy_position_error_km'] for r in rows if (r['method'], r['arm']) == ('incumbent', arm)}
        for r in [r for r in rows if (r['method'], r['arm']) == ('RF_selected', arm)]:
            ax.scatter(baseline[r['case']], r['policy_position_error_km'], marker='o' if r['paired_valid'] else 'x',
                       color='tab:blue' if r['paired_valid'] else '.6')
            if stage == 'development':
                ax.annotate(r['case'].split('-')[1], (baseline[r['case']], r['policy_position_error_km']), fontsize=8)
        limit=max(ax.get_xlim()[1], ax.get_ylim()[1]); ax.plot([0, limit], [0, limit], 'k--', lw=.6)
        ax.set(xlabel='Incumbent position error (km)', ylabel='RF-selected covariance error (km)', title=arm)
        ax.grid(alpha=.2)
    fig.suptitle('Blue: paired gates accepted · gray cross: exact incumbent fallback\nBelow diagonal improves localization; a better RF bound alone does not establish accuracy')
    fig.savefig(OUT/(stage+'_paired_errors.png'), dpi=160); plt.close(fig)
    print(stage, statistics, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['development', 'confirmation'], required=True)
    report(parser.parse_args().stage)
