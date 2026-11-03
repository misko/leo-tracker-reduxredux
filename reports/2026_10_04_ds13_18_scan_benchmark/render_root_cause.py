"""Tables/figures for post-hoc position-bias diagnostics, not a tuned model."""
import argparse
import csv
import html
import json
from pathlib import Path
import numpy as np
from root_cause import LABELS, ARMS


def write_csv(path, rows):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def pooled_rx_stats(diag):
    parts=diag['per_rx']; n=sum(p['windows'] for p in parts)
    if not n:return None,None,None
    linear=np.sqrt(sum(p['windows']*p['linear_rms_hz']**2 for p in parts)/n)
    quad=np.sqrt(sum(p['windows']*p['quadratic_rms_hz']**2 for p in parts)/n)
    return float(linear),float(quad),float(linear/quad) if quad>1e-8 else None


def table(rows, columns):
    def fmt(v):
        if v is None:return '—'
        if isinstance(v,float):return f'{v:,.3f}' if abs(v)<10 else f'{v:,.1f}'
        return html.escape(str(v))
    return '<table><thead><tr>'+''.join('<th>'+html.escape(title)+'</th>' for _,title in columns)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+fmt(row.get(key))+'</td>' for key,_ in columns)+'</tr>' for row in rows)+'</tbody></table>'


def run(source,output):
    output.mkdir(parents=True,exist_ok=True)
    geometry=json.loads((source/'geometry.json').read_text())
    geom={(r['label'],r['arm']):r for r in geometry}
    scans=[];rows=[];tracks=[]
    benchmark=Path(__file__).parent
    for label in LABELS:
        screen=json.loads((source/'screen'/label/'baseline.json').read_text())
        confirm=source/'confirm'/label/'baseline.json'
        baseline=json.loads(confirm.read_text()) if confirm.exists() else screen
        diagnostics={(d['arm'],d['satellite']):d for d in screen['roof_satellite_diagnostics']}
        orientation=json.loads((benchmark/f'pilot-{label}-seeded/alternatives-diagnostics.json').read_text())['rows']
        for arm in ARMS:
            b=baseline['arms'][arm];g=geom[label,arm]
            scans.append(dict(scan=label,arm=arm,windows=g['windows'],
                non_top_windows=g['non_top_windows'],non_top_percent=100*g['non_top_windows']/g['windows'],
                original_error_m=g['radius_m'],control_error_m=b['radius_m'],
                control_status=b['best']['status'],control_joint_converged=b['converged_joint'],
                original_status=g['best_status'],original_converged=g['best_converged'],
                original_roof_converged=g['roof_converged'],boundary=g['boundary'],
                fold_common_timing_range_s=g.get('fold_common_timing_range_s'),
                fold_rx0_offset_range_hz=g.get('fold_rx0_offset_range_hz'),
                fold_rx1_offset_range_hz=g.get('fold_rx1_offset_range_hz'),
                fold_rx0_drift_range_hz_s=g.get('fold_rx0_drift_range_hz_s'),
                fold_rx1_drift_range_hz_s=g.get('fold_rx1_drift_range_hz_s'),
                calibration_warning=g['calibration_warning'],
                control_kkt=b['best']['kkt_residual'],
                original_best_minus_roof_nll=g['total_nll_best_minus_roof'],
                profile_information_percent=100*g['fisher']['remaining_trace_fraction'],
                profile_condition=g['fisher']['condition_number'],
                delta_rx0_drift_hz_s=g['delta_rx0_drift_hz_s'],delta_rx1_drift_hz_s=g['delta_rx1_drift_hz_s'],
                delta_c_hz_per_ghz=g['delta_c_hz_per_ghz'],timing_change_rms_s=g['timing_change_rms_s']))
        for path in sorted((source/'screen'/label).glob('drop-*.json')):
            short=json.loads(path.read_text()); number=short['signature']['satellite']
            confirmation=source/'confirm'/label/path.name
            selected=json.loads(confirmation.read_text()) if confirmation.exists() else short
            for arm in ARMS:
                d=diagnostics[arm,number];r=selected['arms'][arm];b=baseline['arms'][arm];g=geom[label,arm]
                stats=d['stats'] or {}; lin,quad,ratio=pooled_rx_stats(d)
                ori=[x for x in orientation if x['arm']=='fitted-c' and x['satellite']==number]
                den=sum(x['windows'] for x in ori)
                wrong=sum(x['windows']*x['opposite_east_west_fraction'] for x in ori)/den if den else None
                behind=sum(x['windows']*x['behind_nominal_axis_fraction'] for x in ori)/den if den else None
                contribution=next(x for x in g['contributions'] if x['satellite']==number)
                row=dict(scan=label,arm=arm,satellite=number,windows=d['windows'],rx0_windows=d['rx0_windows'],rx1_windows=d['rx1_windows'],
                    span_s=d['span_s'],non_top_windows=contribution['non_top_windows'],
                    association_mode_offset_s=contribution.get('association_mode_offset_s'),
                    association_rms_hz=contribution.get('association_native_rms_hz'),
                    roof_relative_timing_s=contribution.get('roof_relative_timing_s'),
                    roof_timing_prior_nll=contribution.get('roof_timing_prior_nll'),
                    roof_mean_own_association_probability=contribution.get('roof_mean_own_association_probability'),
                    roof_rms_hz=stats.get('rms_hz'),linear_rms_hz=lin,quadratic_rms_hz=quad,linear_quad_ratio=ratio,
                    max_rx_curvature_ratio=max([p['curvature_ratio'] for p in d['per_rx'] if p['curvature_ratio'] is not None],default=None),
                    rx_channel_controlled_ratio=stats.get('channel_controlled_curvature_ratio'),
                    nominal_opposite_half_fraction=wrong,nominal_behind_axis_fraction=behind,
                    gradient_per_100m=d['gradient_strength_per_100m'],
                    original_error_m=g['radius_m'],control_error_m=b['radius_m'],without_error_m=r['radius_m'],
                    improvement_vs_control_m=b['radius_m']-r['radius_m'],
                    without_status=r['best']['status'],without_joint_converged=r['converged_joint'],
                    without_kkt=r['best']['kkt_residual'],without_boundary=r['boundary'],
                    control_joint_converged=b['converged_joint'],calibration_warning=g['calibration_warning'],
                    roof_converged=r['roof']['success'],
                    without_best_minus_roof_nll=r['best_minus_roof_nll'],
                    original_group_nll_best_minus_roof=contribution['data_nll_best_minus_roof'],
                    phase='confirm' if confirmation.exists() else 'screen')
                rows.append(row)
        tracks.extend(dict(scan=label,**d) for d in screen['roof_satellite_diagnostics'])
    write_csv(output/'scan-status.csv',scans);write_csv(output/'satellite-removal.csv',rows)
    (output/'satellite-residual-details.json').write_text(json.dumps(tracks,indent=2))
    (output/'geometry.json').write_text(json.dumps(geometry,indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors={'fitted-c':'#0072B2','zero-c':'#D55E00'}
    fig,axes=plt.subplots(3,1,figsize=(15,12),sharex=True)
    for arm,offset in [('fitted-c',-.14),('zero-c',.14)]:
        s=[next(r for r in scans if r['scan']==label and r['arm']==arm) for label in LABELS]
        xx=np.arange(len(s))+offset
        for x,r in zip(xx,s):
            axes[0].scatter(x,r['original_error_m'],color=colors[arm],marker='^' if r['boundary'] else ('o' if r['original_converged'] else 'x'),s=55)
        axes[0].plot(xx,[r['original_error_m'] for r in s],alpha=.25,color=colors[arm],label=arm)
        axes[1].plot(xx,[r['profile_information_percent'] for r in s],'o-',color=colors[arm],label=arm)
        maximum=[]
        for label in LABELS:
            use=[r for r in rows if r['scan']==label and r['arm']==arm and r['phase']=='confirm' and r['without_joint_converged'] and r['control_joint_converged'] and not r['calibration_warning']]
            maximum.append(max([r['improvement_vs_control_m'] for r in use],default=np.nan))
        axes[2].bar(xx,maximum,width=.26,color=colors[arm],label=arm)
    axes[0].axhline(2000,color='#666',ls=':');axes[0].set_ylabel('Original best-found roof error (m)')
    axes[0].set_title('Triangle = 2 km search boundary; × = nonconverged interior result')
    axes[1].set_ylabel('Position information remaining (%)')
    axes[1].set_title('Local Fisher approximation after allowing nuisance adjustments; not calibrated uncertainty')
    axes[2].set_ylabel('Largest confirmed reduction in error (m)')
    axes[2].set_title('Single-satellite removal; only converged control + removal pairs; missing bar = no qualifying confirmation')
    for ax in axes:ax.grid(alpha=.15);ax.legend()
    axes[-1].set_xticks(range(len(LABELS)),LABELS)
    fig.suptitle('DS13 · position-bias root-cause audit',fontsize=18)
    fig.tight_layout();fig.savefig(output/'overview.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(14,5))
    for ax,arm in zip(axes,ARMS):
        use=[r for r in rows if r['arm']==arm and r['linear_quad_ratio'] is not None]
        for converged in (False,True):
            rr=[r for r in use if (r['without_joint_converged'] and r['control_joint_converged'])==converged]
            ax.scatter([r['linear_quad_ratio'] for r in rr],[r['improvement_vs_control_m'] for r in rr],
                s=[15+.12*r['windows'] for r in rr],alpha=.5,marker='o' if converged else 'x',
                color=colors[arm] if converged else '#999999',label='Converged pair' if converged else 'Unconverged diagnostic')
        ax.axvline(1.1,ls=':',color='#777');ax.axhline(0,color='#555',lw=.8)
        ax.set(xlabel='RMS after line / RMS after quadratic (separate RX fits)',ylabel='Position-error reduction after removal (m)',title=arm)
        ax.grid(alpha=.15);ax.legend(fontsize=8)
    fig.suptitle('Residual curvature is not the same as position influence · marker size follows window support')
    fig.tight_layout();fig.savefig(output/'curvature-vs-removal.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(3,3,figsize=(17,14),sharex=True)
    selected_labels=['B','N05','N06','N07','N10','N12','N15','N16','N14']
    for ax,label in zip(axes.flat,selected_labels):
        use=[r for r in rows if r['scan']==label and r['arm']=='fitted-c']
        use=sorted(use,key=lambda r:r['improvement_vs_control_m'],reverse=True)[:8]
        yy=np.arange(len(use));ax.barh(yy,[r['improvement_vs_control_m'] for r in use],color=['#0072b2' if r['without_joint_converged'] else '#aaaaaa' for r in use])
        ax.set_yticks(yy,[f"{r['satellite']} · {r['windows']} win" for r in use]);ax.invert_yaxis()
        ax.axvline(0,color='#555',lw=.8);ax.set_title(label);ax.grid(axis='x',alpha=.15)
        ax.set_xlabel('Position-error reduction (m)')
    fig.suptitle('Largest single-satellite influences · fitted c\nGray = removal fit not converged; includes short-budget screening results',fontsize=16)
    fig.tight_layout(rect=(0,0,1,.96));fig.savefig(output/'largest-influences.png',dpi=150);plt.close(fig)
    status_columns=[('scan','Scan'),('arm','RF arm'),('windows','Windows'),('non_top_percent','Non-top %'),('original_error_m','Original error m'),('original_status','Original status'),('original_roof_converged','Roof converged'),('calibration_warning','Calibration warning'),('profile_information_percent','Remaining info %')]
    cols=[('satellite','Satellite'),('windows','# windows'),('span_s','Span s'),('association_rms_hz','Selection RMS Hz'),('roof_rms_hz','Roof RMS Hz'),('linear_rms_hz','+line Hz'),('quadratic_rms_hz','+quad Hz'),('linear_quad_ratio','Line/quad'),('association_mode_offset_s','Selection shift s'),('roof_relative_timing_s','Roof relative shift s'),('roof_mean_own_association_probability','Own posterior'),('gradient_per_100m','Gradient /100m'),('control_error_m','Control m'),('without_error_m','Without m'),('improvement_vs_control_m','Improvement m'),('without_status','Fit status'),('phase','Budget tier')]
    parts=['<!doctype html><meta charset="utf-8"><title>DS13 position bias audit</title><style>body{font:16px system-ui;max-width:1500px;margin:40px auto;padding:0 24px;color:#182330}h1,h2{font-weight:600}img{width:100%}table{border-collapse:collapse;font-size:12px;width:100%}th,td{padding:7px;border-bottom:1px solid #ddd;text-align:right}th{position:sticky;top:0;background:#eaf1f5}details{margin:16px 0}summary{cursor:pointer;font-size:20px}.note{background:#fff5d8;padding:18px}</style>',
        '<h1>Why does the position fit move away from the known roof?</h1>',
        '<p>Post-hoc diagnostic audit of all 18 independent scans. This does not change the frozen benchmark, choose new hyperparameters, or establish satellite identities.</p>',
        '<p class="note"><b>A point at 2,000 m is a search-boundary result, not a discovered minimum beyond 2 km.</b> Convergence, constrained stationarity and interior localization accuracy are distinct. Earlier descriptions of all current windows as top-GLRT-only were incorrect: the alternatives method may substitute a lower-ranked candidate, but retains at most one candidate per window.</p>',
        '<h2>Method and interpretation</h2><p>Each deletion removes a satellite from the likelihood bank and removes all windows owned by it in the frozen fitted-c association. No other windows are added or reassigned. Both RF arms use the same remaining observations and bank, the same timing priors and maximum fit budgets, and the same original RF reference. The saved nonlinear receiver correction stays fixed. Removing a bank member also changes the 0.8/K detection probability and the zero-sum timing basis; this is a whole-model deletion, not a pure measurement-only causal intervention.</p>',
        '<p>Screen: 8 s maximum per RF arm (2 s roof, two 3 s position searches). Confirmation: longer matched budgets for selected influences and their no-deletion controls. Starts are the saved roof and distant fit, with timing remapped to preserve total shifts. Reported improvements compare to the current no-deletion control; unequal convergence can confound short-budget differences. Raw objective values across different observation sets are not ranked. Best-minus-roof NLL is computed within each retained set. No global optimum certificate.</p>',
        '<p>RMS statistics reconstruct the original saved full-set roof position model, on frozen owner labels; native Hz. Linear/quadratic fits are separate per receiver and their residual energies are pooled. Channel-controlled ratios and per-receiver details are provided in the files. These are in-sample descriptive fits, not evidence that a polynomial is a physical correction. Very short/sparse tracks can overfit. Orientation is nominal geometry, not a measured beam exclusion.</p>',
        '<p>The receiver correction is not retrained after a satellite is removed, so this does not remove that satellite’s possible influence on the earlier calibration. A favorable deletion identifies model influence, not proof of a wrong satellite identity. Known-roof-based removal rankings are oracle diagnostics, not deployable selection rules. These post-hoc analyses must not be presented as fresh held-out validation of any subsequently tuned model.</p>',
        '<h2>A concrete objective mismatch</h2><p>Selection maximizes explained windows minus ten per satellite. Residual SSE and the timing Gaussian enter its tie-breaker, not that primary objective. The position fit instead pays the timing prior in its negative log likelihood and can move windows to clutter or other satellites. Thus a selected ±10–20 s timing mode with modest support can disappear during the position refit. Selection RMS and the refitted roof RMS on the same frozen owner labels are both tabulated. Own posterior measures whether that original identity remains supported. Selection uses fold-specific receiver lines/RF calibration whereas position fitting uses one refitted line per receiver and one RF coefficient; this is another model-transfer difference, not an isolated proof of a timing-prior cause.</p>',
        '<p>Fold-to-fold nuisance ranges in the scan CSV expose calibration instability. For example N06 fitted-c fold RX0 offsets span about 10.9 kHz, common timing about 3.94 s, and RX0 drift about 22 Hz/s. N15 is much more stable (RX0 offsets about 67 Hz, common timing about 0.028 s). Passing an optimizer convergence check does not establish a uniquely identified or consistent calibration.</p>',
        '<p>The position-information percentage is trace(H<sub>profile</sub>)/trace(H<sub>fixed nuisance</sub>) from the local Fisher approximation and a Schur complement. It measures local parameter confounding, not actual position-error variance, and ignores active bounds and visibility jumps. Reconstruction and score decomposition were checked numerically against saved fits.</p>',
        '<p><a href="scan-status.csv">Scan status CSV</a> · <a href="satellite-removal.csv">Every satellite removal CSV</a> · <a href="satellite-residual-details.json">RX residual details</a> · <a href="geometry.json">Geometry and exact score decomposition</a></p>',
        '<p><a href="radius8/report.html">Expanded 8 km minimum search</a> (separate from these 2 km deletion fits)</p>',
        '<img src="overview.png"><h2>Basic status</h2>',table(scans,status_columns),'<h2>Curvature versus influence</h2><img src="curvature-vs-removal.png"><img src="largest-influences.png">']
    for label in LABELS:
        parts.append(f'<h2>{label}</h2>')
        for arm in ARMS:
            use=sorted([r for r in rows if r['scan']==label and r['arm']==arm],key=lambda r:-r['improvement_vs_control_m'])
            parts.append(f'<details><summary>{arm}: {len(use)} individual removals</summary>'+table(use,cols)+'</details>')
    restore_path=source/'timing-restore.json'
    if restore_path.exists():
        restored=json.loads(restore_path.read_text());(output/'timing-restore.json').write_text(json.dumps(restored,indent=2))
        restore_rows=[dict(scan=r['scan'],arm=r['arm'],satellite=r['satellite'],windows=r['windows'],
            before_rms=r['before']['owner_rms_hz'],restored_rms=r['restored']['owner_rms_hz'],
            data_change=r['change_data_nll'],prior_change=r['change_prior_nll'],total_change=r['change_total_nll']) for r in restored['rows']]
        parts.append('<h2>Counterfactual timing restoration</h2><p>Restore only one satellite to its prepared selection timing, preserving all other total timings and receiver/RF parameters at the roof. Not a refit. Lower NLL is better. Restoring timing alone does not restore the full selection model: data loss can worsen even when that satellite’s owner-label RMS improves. Thus this is not evidence that simply weakening the timing prior will fix localization. <a href="timing-restore.json">Exact counterfactuals</a></p>'+table(restore_rows,[('scan','Scan'),('arm','RF'),('satellite','Satellite'),('windows','Windows'),('before_rms','Original RMS Hz'),('restored_rms','Restored RMS Hz'),('data_change','Δ data NLL'),('prior_change','Δ prior NLL'),('total_change','Δ total NLL')]))
    (output/'report.html').write_text('\n'.join(parts))
    print(json.dumps(dict(scans=len(scans),removals=len(rows),confirmed=sum(r['phase']=='confirm' for r in rows),output=str(output))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.source,a.output)
