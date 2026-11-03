"""Read saved research artifacts; never replace missing fits with zero error."""
import csv
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
WORK = Path('/srv/bulk/leo/recent-v16-rates-20261006')
ARMS = ('fitted-c', 'zero-c')
COLORS = {'fitted-c': '#0072b2', 'zero-c': '#d55e00'}
READ_WARNINGS = []


def read(path):
    if not path.exists():return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        READ_WARNINGS.append(dict(path=str(path),error=str(exc),
            status='unreadable or concurrent write; not counted as complete'))
        return None


def inspect(scan):
    label = scan['label']
    folder = WORK/'inputs'/label
    row = {k:scan[k] for k in ('label', 'session_id', 'sample_rate_hz', 'capture_utc')}
    row.update(status='awaiting GLRT export', passing_windows=None,
        scheduled_probes=None, raw_candidates=None, refined_candidates=0,
        refinement_complete=False, calibration_converged=None, positions={})
    observations = read(folder/'observations.json')
    if observations:
        summary = observations['summary']
        row.update(passing_windows=summary['passing_windows'],
            scheduled_probes=summary['all_scheduled_probes'],
            raw_candidates=summary['projected_passing_candidates'],
            recorded_edges=sorted({r['edge'] for r in observations['records']}),
            tle_snapshot_age_h=observations['tle']['age_s']/3600,
            status='awaiting orbit-blind refinement')
        refined = read(folder/'refinement/refined.json')
        if refined:
            row.update(refinement_complete=True,
                refined_candidates=refined['summary']['completed_candidates'],
                refinement_failures=refined['summary']['failed_refinements'],
                status='awaiting bootstrap/calibration')
            alias_hz = 1/4.4e-6
            shifts = np.array([abs((r['output_hz']-r['original_hz']+alias_hz/2)%alias_hz-alias_hz/2)
                               for r in refined['records']])
            original_top = {}
            for r in observations['records']:
                key=tuple(r['probe_key']); priority=(r['original_margin'],-r['row_index'])
                if key not in original_top or priority>original_top[key][0]:
                    original_top[key]=(priority,r['row_index'])
            retained_top=set(refined['top_rows'])
            row['refinement_diagnostics']=dict(
                median_absolute_frequency_change_hz=float(np.median(shifts)),
                p90_absolute_frequency_change_hz=float(np.percentile(shifts,90)),
                candidates_changed_over300_hz=int(sum(shifts>300)),
                windows_changing_top_candidate=sum(value[1] not in retained_top for value in original_top.values()))
        else:
            checkpoints = sorted((folder/'refinement').glob('visit-*.json'))
            for checkpoint in checkpoints:
                receipt=read(checkpoint)
                if receipt is None:
                    row.setdefault('incomplete_checkpoint_reads', []).append(str(checkpoint))
                else:
                    row['refined_candidates'] += len(receipt['records'])
            if checkpoints:row['status'] = 'refinement checkpointed / incomplete'
    calibration = read(WORK/'fits'/label/'calibration.json')
    if calibration:
        row['calibration_converged'] = calibration['converged']
        row['status'] = 'awaiting association' if calibration['converged'] else 'calibration unconverged'
    elif (WORK/'fits'/label/'calibration-pre-partial.json').exists():
        row['status'] = 'calibration prefit unconverged'
    for arm in ARMS:
        association = read(WORK/'fits'/label/'associations'/f'{arm}.json')
        if association:
            row[arm+'_association'] = {k:association['final'][k] for k in
                ('assigned', 'denominator', 'coverage', 'satellites', 'unassigned')}
            row[arm+'_association']['rms_hz'] = association['rms_hz']
            row['status'] = 'awaiting position search'
        fit = read(WORK/'positions'/label/f'{arm}.json')
        if fit:
            row['positions'][arm] = {k:fit[k] for k in (
                'distance_m', 'converged', 'boundary', 'objective', 'data_nll',
                'timing_prior_nll', 'kkt', 'windows', 'owner_rms_hz',
                'posterior_weighted_residual_rms_hz', 'mean_signal_posterior',
                'strong_soft_windows', 'strong_original_owner_windows', 'strong_changed_owner_windows',
                'input_sha256', 'spec', 'maximum_budgets_s', 'radius_km')}
            row['positions'][arm]['satellites'] = len(fit['numbers'])
            row['positions'][arm]['point_km'] = fit['best']['point_km']
    if len(row['positions']) == 2:
        for key in ('input_sha256', 'spec', 'maximum_budgets_s', 'radius_km', 'windows', 'satellites'):
            assert row['positions'][ARMS[0]][key] == row['positions'][ARMS[1]][key], key
        row['status'] = ('complete: both arms converged' if all(p['converged'] for p in row['positions'].values())
            else 'position results: convergence incomplete')
    elif row['positions']:
        row['status'] = 'position results: second RF arm pending'
    return row


def plots(rows):
    fig, axes = plt.subplots(2, 2, figsize=(15, 9), layout='constrained')
    fig.suptitle('Recent 16-scan cohort · frozen V16 · native-rate processing', fontsize=18)
    for column, rate in enumerate((2_500_000, 10_000_000)):
        group = [r for r in rows if r['sample_rate_hz']==rate]
        x = np.arange(len(group))
        labels = [r['label'] for r in group]
        ax = axes[0, column]
        for i, r in enumerate(group):
            if r['raw_candidates']:
                fraction = r['refined_candidates']/r['raw_candidates']
                ax.bar(i, 100, color='#ededed', width=.6)
                ax.bar(i, 100*fraction, color='#009e73', width=.6)
                ax.text(i, 104, f'{100*fraction:.0f}%', ha='center', fontsize=9)
            else:
                ax.text(i, 40, 'GLRT\npending', ha='center', fontsize=9)
        ax.set(title=f'{rate/1e6:g} MS/s · orbit-blind refinement', ylabel='Candidates refined (%)',
               ylim=(0, 115), xlim=(-.6,len(group)-.4), xticks=x, xticklabels=labels)
        ax.tick_params(axis='x', rotation=35)
        ax.grid(axis='y', alpha=.18)
        ax = axes[1, column]
        for arm, dx in zip(ARMS, (-.13, .13)):
            for i, r in enumerate(group):
                value = r['positions'].get(arm)
                if not value:continue
                ax.scatter(i+dx, value['distance_m'], color=COLORS[arm],
                    marker='^' if value['boundary'] else 'o', s=60)
                if not value['converged']:ax.scatter(i+dx,value['distance_m'],marker='x',c='black',s=70)
        for i, r in enumerate(group):
            if not r['positions']:
                ax.text(i, .035, 'pending', rotation=90, fontsize=8, color='#666666',
                    ha='center', va='bottom', transform=ax.get_xaxis_transform())
        ax.axhline(4000, color='#777777', ls=':', label='4 km search boundary')
        ax.set(title='Independent position searches · missing results not plotted',
            ylabel='Distance from known roof (m)', ylim=(0, 4300), xlim=(-.6,len(group)-.4), xticks=x, xticklabels=labels)
        ax.tick_params(axis='x', rotation=35)
        ax.grid(axis='y', alpha=.18)
    from matplotlib.lines import Line2D
    handles = [Line2D([],[],marker='o',color=c,ls='',label=a) for a,c in COLORS.items()]
    handles += [Line2D([],[],marker='^',color='#555555',ls='',label='Boundary'),
                Line2D([],[],marker='x',color='#222222',ls='',label='Unconverged')]
    fig.legend(handles=handles,loc='outside lower center',ncol=4)
    fig.savefig(HERE/'cohort-progress.png',dpi=160)
    plt.close(fig)
    if not any(r['positions'] for r in rows):return
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout='constrained')
    for arm in ARMS:
        for rate, marker in ((2_500_000,'o'), (10_000_000,'s')):
            group = [r for r in rows if r['sample_rate_hz']==rate and arm in r['positions']]
            for ax, key, xlabel in zip(axes, ('windows','posterior_weighted_residual_rms_hz'),
                                      ('Associated windows used in fit','Posterior-weighted residual RMS (Hz)')):
                ax.scatter([r['positions'][arm][key] for r in group],
                    [r['positions'][arm]['distance_m'] for r in group], color=COLORS[arm],
                    marker=marker, s=60, label=f'{rate/1e6:g} MS/s · {arm}')
                for r in group:
                    p=r['positions'][arm]
                    ax.annotate(r['label'], (p[key],p['distance_m']), xytext=(4,4),
                        textcoords='offset points',fontsize=8)
                ax.set(xlabel=xlabel,ylabel='Position error (m)')
                ax.grid(alpha=.2)
    axes[0].legend(fontsize=8)
    fig.suptitle('V16 · coverage and frequency fit are distinct from position accuracy')
    fig.savefig(HERE/'position-comparison.png',dpi=160)
    plt.close(fig)


def main():
    READ_WARNINGS.clear()
    cohort = read(HERE/'cohort-final.json')
    rows = [inspect(scan) for scan in cohort['scans']]
    counts = {str(rate): dict(selected=sum(r['sample_rate_hz']==rate for r in rows),
        glrt_exported=sum(r['sample_rate_hz']==rate and r['passing_windows'] is not None for r in rows),
        refinement_complete=sum(r['sample_rate_hz']==rate and r['refinement_complete'] for r in rows),
        position_pairs=sum(r['sample_rate_hz']==rate and len(r['positions'])==2 for r in rows))
        for rate in (2_500_000, 10_000_000)}
    result = dict(updated_utc=datetime.now(timezone.utc).isoformat(),
        start_utc=cohort['start_utc'],end_utc=cohort['end_utc'],counts=counts,rows=rows,
        read_warnings=list(READ_WARNINGS),
        caveats=[
            'Fixed time-based selection, no scan substitutions or new RF collection.',
            'Native 2.5 and 10 MS/s IQ; orbit-blind refinement before top-one selection.',
            'All-window known-roof upstream calibration; supported-window RX spline. No calibration folds.',
            'V16 hyperparameters frozen; fresh starts replace the historical cross-model start pool.',
            'Both final RF arms share fitted-c-associated windows, selected bank and fixed RX baseline.',
            'A 4 km boundary hit is not an unconstrained minimum. Convergence is reported separately.',
            'Frequency RMS in the scatter is posterior-weighted, not RMS over every original satellite owner. The CSV also reports owner RMS and final strongly associated window count.',
            'Different capture times and sky states; this is not a controlled sample-rate intervention.',
            'Known-roof upstream calibration makes this a conditional localization diagnostic, not blind validation.',
            'Missing and unconverged cases remain visible; no success-only cohort aggregate.'])
    (HERE/'status.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    flat=[]
    for row in rows:
        for arm in ARMS:
            association=row.get(arm+'_association',{})
            fit=row['positions'].get(arm,{})
            flat.append(dict(scan=row['label'],session_id=row['session_id'],sample_rate_hz=row['sample_rate_hz'],
                capture_utc=row['capture_utc'],arm=arm,status=row['status'],
                passing_windows=row['passing_windows'],refined_candidates=row['refined_candidates'],
                total_candidates=row['raw_candidates'],association_coverage=association.get('coverage'),
                associated_windows=association.get('assigned'),association_satellites=association.get('satellites'),
                fit_windows=fit.get('windows'),distance_m=fit.get('distance_m'),converged=fit.get('converged'),
                boundary=fit.get('boundary'),residual_rms_hz=fit.get('posterior_weighted_residual_rms_hz'),
                owner_rms_hz=fit.get('owner_rms_hz'),strong_soft_windows=fit.get('strong_soft_windows'),
                strong_original_owner_windows=fit.get('strong_original_owner_windows'),
                strong_changed_owner_windows=fit.get('strong_changed_owner_windows'),
                strong_soft_coverage_of_passing_windows=(fit['strong_soft_windows']/row['passing_windows']
                    if fit and row['passing_windows'] else None),
                objective=fit.get('objective'),data_nll=fit.get('data_nll'),timing_prior_nll=fit.get('timing_prior_nll')))
    with (HERE/'results.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(flat[0]))
        writer.writeheader();writer.writerows(flat)
    plots(rows)
    def fmt(value, digits=0):return 'pending' if value is None else f'{value:,.{digits}f}'
    table=[]
    for row in rows:
        coverage=row.get('fitted-c_association',{}).get('coverage')
        soft=row['positions'].get('fitted-c',{}).get('strong_soft_windows')
        table.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in (
            row['label'],row['session_id'],row['sample_rate_hz']/1e6,row['capture_utc'],
            fmt(row['passing_windows']), f'{100*coverage:.1f}%' if coverage is not None else 'pending',
            f'{100*soft/row["passing_windows"]:.1f}%' if soft is not None else 'pending',
            fmt(row['positions'].get('fitted-c',{}).get('distance_m')),
            fmt(row['positions'].get('zero-c',{}).get('distance_m')),row['status']))+'</tr>')
    (HERE/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Recent V16 cohort</title>'
        '<style>body{font:16px system-ui;margin:2rem;max-width:1500px}td,th{padding:.5rem;border-bottom:1px solid #ddd;text-align:left}'
        'img{max-width:100%}table{font-size:13px;border-collapse:collapse}</style>'
        '<h1>Recent 16-scan V16 evaluation</h1>'
        f'<p>Capture window: {cohort["start_utc"]} to {cohort["end_utc"]}. Updated {result["updated_utc"]}.</p>'
        '<p>This page is a saved snapshot, not a live job monitor. Missing results remain pending.</p>'
        '<img src="cohort-progress.png" alt="Refinement progress and position error">'
        '<table><tr><th>Scan</th><th>Session</th><th>MS/s</th><th>Captured UTC</th><th>Passing windows</th>'
        '<th>Greedy association, fitted c</th><th>Final satellite responsibility &gt;50%, fitted c</th>'
        '<th>Position m, fitted c</th><th>Position m, c=0</th><th>Status</th></tr>'
        +''.join(table)+'</table><h2>Interpretation</h2><ul>'
        +''.join('<li>'+html.escape(v)+'</li>' for v in result['caveats'])+'</ul>'
        '<p><a href="results.csv">Machine-readable results</a> · <a href="status.json">Detailed status</a> · '
        '<a href="cohort-final.json">Frozen cohort</a></p>')
    print(json.dumps(counts,indent=2))


if __name__=='__main__':main()
