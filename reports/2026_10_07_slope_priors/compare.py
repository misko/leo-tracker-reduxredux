"""Independently check matched receipts, then report localization/fit separately."""

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import nnls

import run as experiment


HERE = Path(__file__).resolve().parent
OUTPUT = HERE
OPTIONS = ['control', 'window60', 'window30', 'window10']
LABELS = ['Unrestricted', '±60 Hz/s', '±30 Hz/s', '±10 Hz/s']
COLORS = ['#666666', '#2176bd', '#db8724', '#229569']


def key(row):
    return tuple(row[k] for k in ['case', 'method', 'arm'])


def run_key(row):
    return tuple(row[k] for k in ['case', 'method', 'arm', 'basin', 'origin'])


def kkt(vector, gradient, obj, region, arm, width):
    """Reconstruct the feasible set without the prototype solver's internals."""
    v = np.asarray(vector)
    scale = np.ones(len(v))
    scale[[2, 4, 6]] = 200
    scale[[3, 5]] = 2
    free = np.arange(len(v)) if arm == 'fitted-c' else np.delete(np.arange(len(v)), 6)
    lower, upper = np.full(len(v), -np.inf), np.full(len(v), np.inf)
    lower[:2], upper[:2] = -obj.prior.radius_km, obj.prior.radius_km
    lower[6:8], upper[6:8] = [-5000, -10], [5000, 10]
    if width is not None:
        lower[[3, 5]], upper[[3, 5]] = -width, width
    assert np.all(v >= lower - 1e-7) and np.all(v <= upper + 1e-7)
    assert arm != 'zero-c' or v[6] == 0
    normals = []
    for index in free:
        for slack, sign in [(v[index] - lower[index], 1), (upper[index] - v[index], -1)]:
            if slack / scale[index] <= 1e-7:
                normal = np.zeros(len(v))
                normal[index] = sign / scale[index]
                normals.append(normal)
    for center, radius in [(np.zeros(2), obj.prior.radius_km),
                           (np.asarray(region['center_km']), 25.)]:
        delta = v[:2] - center
        slack = radius**2 - delta @ delta
        assert slack >= -1e-6
        if slack <= 1e-6:
            normal = np.zeros(len(v))
            normal[:2] = -2 * delta
            normals.append(normal)
    timing_design = np.zeros((len(obj.bank.numbers), len(v)))
    timing_design[:, 7] = 1
    timing_design[:, 8:] = obj.basis
    shifts = timing_design @ v
    lower_time = max(-20., obj.bank.nodes_s[0] - obj.observations.times_s.min())
    upper_time = min(20., obj.bank.nodes_s[-1] - obj.observations.times_s.max())
    assert np.all(shifts >= lower_time - 1e-7) and np.all(shifts <= upper_time + 1e-7)
    normals.extend(timing_design[shifts - lower_time <= 1e-6])
    normals.extend(-timing_design[upper_time - shifts <= 1e-6])
    residual = (gradient * scale)[free]
    if normals:
        matrix = (np.asarray(normals) * scale)[:, free].T
        multipliers, _ = nnls(matrix, residual, maxiter=100 * matrix.shape[1])
        residual = residual - matrix @ multipliers
    return float(abs(residual).max())


def write_csv(path, rows):
    with path.open('w') as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main(phase='screen'):
    global OUTPUT
    OUTPUT = HERE if phase == 'screen' else HERE / 'polished'
    manifest_path = HERE / 'inputs/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    cases = {r['case']: r for r in manifest['cases']}
    results = {o: json.loads((OUTPUT / o / 'results.json').read_text()) for o in OPTIONS}
    assert all(r['status'] == 'complete' for r in results.values())
    for field in ['manifest_sha256', 'protocol_sha256', 'seconds_per_fit', 'maximum_iterations', 'local_radius_km', 'relative_sigma_s', 'source_hashes']:
        assert all(r[field] == results['control'][field] for r in results.values()), field
    assert results['control']['manifest_sha256'] == experiment.digest(manifest_path.read_bytes())
    runs = {o: {run_key(r): r for r in v['runs']} for o, v in results.items()}
    assert all(len(rows) == len(results[o]['runs']) for o, rows in runs.items())
    assert all(set(r) == set(runs['control']) for r in runs.values())
    for trial in runs['control']:
        control = runs['control'][trial]
        for o in OPTIONS:
            row = runs[o][trial]
            fields = ['fixture_sha256', 'association_seed_sha256']
            if phase == 'screen':
                fields.append('shared_seed_sha256')
            for field in fields:
                assert row[field] == control[field], (trial, field)
    if phase == 'polished':
        for field in ['continuation_source_sha256', 'continuation_protocol_sha256']:
            assert all(r[field] == results['control'][field] for r in results.values()), field
        for option, receipt in results.items():
            parent_raw = (HERE/option/'results.json').read_bytes()
            assert receipt['parent_receipt_sha256'] == experiment.digest(parent_raw)
            parent = json.loads(parent_raw)
            for row in receipt['runs']:
                pool = [r for r in parent['candidates'] if key(r)==key(row) and r['basin']==row['basin'] and r['feasible']]
                seed = min(pool,key=lambda r:(r['selection_score'],r['origin']))
                assert row['parent_seed_sha256'] == experiment.vector_digest(seed['vector'])
                assert row['parent_origin'] == seed['origin']
    selected = {o: {key(r): r for r in v['selections']} for o, v in results.items()}
    assert all(set(s) == set(selected['control']) for s in selected.values())
    cache = {}
    audited = []
    output = []
    for option in OPTIONS:
        width = experiment.OPTIONS[option]
        for identity, row in selected[option].items():
            case = cases[row['case']]
            region = case['basins'][row['basin']]
            ck = row['case'], row['method'], row['basin']
            if ck not in cache:
                cache[ck] = experiment.load_objective(manifest_path.parent, case, row['basin'], row['method'])
            obj = cache[ck]
            assert obj.score.relative_sigma_s == 1.
            v = np.asarray(row['vector'])
            value, gradient, terms = obj.evaluate(v)
            np.testing.assert_allclose(value, row['objective'], atol=1e-7, rtol=0)
            np.testing.assert_allclose(terms.nll, row['data_nll'], atol=1e-7, rtol=0)
            stationarity = kkt(v, gradient, obj, region, row['arm'], width)
            np.testing.assert_allclose(stationarity, row['stationarity'], atol=1e-5, rtol=0)
            candidates = [r for r in results[option]['candidates'] if key(r) == identity and r['feasible']]
            winner = min(candidates, key=lambda r: (r['selection_score'], r['basin'], r['origin']))
            assert winner == row
            a, b = np.radians(experiment.coordinates(obj.prior, v[:2]))
            reference = case['evaluation_reference']
            x, y = np.radians([reference['latitude_deg'], reference['longitude_deg']])
            h = np.sin((a-x)/2)**2 + np.cos(a)*np.cos(x)*np.sin((b-y)/2)**2
            error = 2 * 6371008.8 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))
            np.testing.assert_allclose(error, row['horizontal_error_m'], atol=1e-5, rtol=0)
            base = selected['control'][identity]
            slopes = v[[3, 5]]
            calibration = np.asarray(region['calibration_vector'])[[3, 5]]
            audited.append(dict(option=option, case=row['case'], method=row['method'], arm=row['arm'],
                                objective_difference=float(value-row['objective']), independent_stationarity=stationarity))
            output.append(dict(option=option, case=row['case'], session_id=case['session_id'], method=row['method'], arm=row['arm'],
                               error_km=float(error / 1000), error_delta_km=float((error-base['horizontal_error_m'])/1000),
                               data_nll=row['data_nll'], data_nll_delta=row['data_nll']-base['data_nll'],
                               rms_hz=row['posterior_rms_hz'], rms_delta_hz=row['posterior_rms_hz']-base['posterior_rms_hz'],
                               signal_fraction=row['signal_fraction'], timing_penalty=row['timing_penalty'],
                               timing_penalty_delta=row['timing_penalty']-base['timing_penalty'],
                               selection_score=row['selection_score'], selection_score_delta=row['selection_score']-base['selection_score'],
                               converged=row['converged'], boundary=row['boundary'], stationarity=row['stationarity'],
                               slope_bound_hit=bool(row['slope_active_bounds']), slope_bound_hit_count=len(row['slope_active_bounds']),
                               rx0_additional_hz_s=float(slopes[0]), rx1_additional_hz_s=float(slopes[1]),
                               differential_additional_hz_s=float(slopes[1]-slopes[0]),
                               rx0_total_linear_hz_s=float(slopes[0]+calibration[0]), rx1_total_linear_hz_s=float(slopes[1]+calibration[1]),
                               c_hz_per_ghz=row['c_hz_per_ghz'], basin=row['basin'], origin=row['origin']))
    write_csv(OUTPUT / 'comparison.csv', output)
    nesting = []
    for identity in selected['control']:
        for i, wider in enumerate(OPTIONS[:-1]):
            for narrower in OPTIONS[i+1:]:
                gap = selected[wider][identity]['selection_score']-selected[narrower][identity]['selection_score']
                if gap > 1e-6:
                    nesting.append(dict(case=identity[0], method=identity[1], arm=identity[2], wider=wider,
                                        narrower=narrower, wider_minus_narrower_score=gap))
    grouped = []
    for option in OPTIONS:
        for method in ['V16', 'T1AT']:
            for arm in ['fitted-c', 'zero-c']:
                rows = [r for r in output if r['option']==option and r['method']==method and r['arm']==arm]
                grouped.append(dict(option=option, method=method, arm=arm, n=len(rows),
                                    median_error_km=float(np.median([r['error_km'] for r in rows])),
                                    maximum_error_km=max(r['error_km'] for r in rows),
                                    improved_over_100m=sum(r['error_delta_km'] < -.1 for r in rows),
                                    degraded_over_100m=sum(r['error_delta_km'] > .1 for r in rows),
                                    converged=sum(r['converged'] for r in rows),
                                    slope_bound_hits=sum(r['slope_bound_hit'] for r in rows),
                                    lower_frequency_nll=sum(r['data_nll_delta'] < -1e-6 for r in rows),
                                    median_rms_delta_hz=float(np.median([r['rms_delta_hz'] for r in rows]))))
    summary = dict(phase=phase, protocol_sha256=experiment.digest((HERE/'protocol.txt').read_bytes()),
                   runs_per_option={o:len(r['runs']) for o,r in results.items()},
                   failed_runs={o:sum(r.get('status')=='failed' for r in doc['runs']) for o,doc in results.items()},
                   fit_elapsed_s={o:doc['fit_elapsed_s'] for o,doc in results.items()},
                   selected_count=len(output), grouped=grouped, width_nesting_gaps=nesting,
                   c_nesting_gaps={o:r['nested_search_gaps'] for o,r in results.items()},
                   independent_selected_audits=audited)
    (OUTPUT/'summary.json').write_text(json.dumps(summary, indent=2))
    (OUTPUT/'audit.txt').write_text(f'Matched {len(runs["control"])} trial identities across all four options.\n'
                                 'All input, solver-source, prior and budget hashes match.\n'
                                 'Original screen seeds match; continuation seeds are verified own-option/own-arm best per basin.\n'
                                 f'Independently repriced and checked feasibility/KKT/selection/error for {len(audited)} selections.\n'
                                 f'Width-nesting search gaps: {len(nesting)}.\n')
    report = [f'Retrospective six-scan slope-window {phase}; relative timing sigma=1s.',
              'All widths bound additional slopes only; calibration remains frozen.',
              'Results compare fresh matched controls, not previously published values.', '',
              'Position error km: control | +/-60 | +/-30 | +/-10']
    for method in ['V16', 'T1AT']:
        for arm in ['fitted-c', 'zero-c']:
            report.append(f'\n{method}/{arm}')
            for case in cases:
                entries = [selected[o][case, method, arm] for o in OPTIONS]
                report.append(case + ': ' + ' | '.join(f'{r["horizontal_error_m"]/1000:.3f}' + ('' if r['converged'] else '*') for r in entries))
    report += ['', '* = first-order stationarity check failed; see comparison.csv for boundary/bound details.',
               f'Width-nesting gaps: {len(nesting)} (a tighter feasible set beat a wider search).',
               'These are optimization failures of the wider search, not likelihood evidence for the narrower prior.',
               'Data NLL and posterior RMS deltas are separate columns in comparison.csv.',
               'Six selected debugging scans and local candidate pools do not establish general performance.']
    (OUTPUT/'report.txt').write_text('\n'.join(report)+'\n')
    print('\n'.join(report))
    plot(output, list(cases))


def plot(rows, cases):
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharex=True, sharey=True)
    fig.subplots_adjust(left=.07, right=.98, top=.83, bottom=.23, wspace=.13, hspace=.25)
    fig.suptitle('Does limiting receiver slope improve position?', fontsize=20, weight='bold', y=.98)
    fig.text(.5, .93, 'Six saved scans · matched original starts and budgets · relative timing σ = 1 s\nHard bounds apply to additional slopes after frozen calibration', ha='center', va='top', fontsize=11)
    lookup = {(r['option'],r['case'],r['method'],r['arm']):r for r in rows}
    for mi, method in enumerate(['V16','T1AT']):
        for ai, arm in enumerate(['fitted-c','zero-c']):
            ax = axes[mi,ai]
            for option, label, color in zip(OPTIONS,LABELS,COLORS):
                group = [lookup[option,case,method,arm] for case in cases]
                y = [r['error_km'] for r in group]
                ax.plot(range(len(cases)),y,'o-',color=color,ms=5,lw=1.2,label=label)
                bad = [i for i,r in enumerate(group) if not r['converged']]
                ax.scatter(bad,[y[i] for i in bad],marker='x',s=45,c='black',zorder=5)
            ax.set_title(f'{method} · {arm}',loc='left',weight='bold',fontsize=13)
            ax.set_yscale('log');ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
            if ai==0: ax.set_ylabel('Position error (km, log scale)')
            ax.axvspan(3.5,5.5,color='#eeeeee',zorder=-1)
            if mi==1:
                ax.set_xticks(range(len(cases)),['12:39\nfailure','14:39\nfailure','15:52\noutlier','16:22\noutlier','14:09\nguard','19:23\nguard'])
                ax.set_xlabel('Oct 6 capture start (PDT); guards shaded')
    handles, labels=axes[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,.06),ncol=4,frameon=False)
    fig.text(.5,.025,'× marks a nonstationary selected fit. Lines guide the eye; cases are arranged by debugging role.',ha='center',fontsize=9)
    fig.savefig(OUTPUT/'position_comparison.png',dpi=180,facecolor='white')
    fig.savefig(OUTPUT/'position_comparison.svg',facecolor='white')
    plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',choices=['screen','polished'],default='screen')
    main(parser.parse_args().phase)
