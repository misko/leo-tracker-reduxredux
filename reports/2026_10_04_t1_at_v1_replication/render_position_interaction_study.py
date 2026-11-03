"""Static scientific figures and auditable tables for the focused follow-up."""
import html
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import position_interaction_study as study
from polish_position_interaction_study import collect

COLORS={'fitted-c':'#0072B2','prior-c':'#009E73','zero-c':'#D55E00'}
LABELS={'fitted-c':'Free c','prior-c':'c prior: σ = 100 Hz/GHz','zero-c':'c = 0'}


def summary_rows(rows):
    lookup={(r['scan'],r['arm'],r['mode']):r for r in rows}
    totals=[]
    for arm in study.ARMS:
        for mode in study.MODES:
            group=[lookup[s,arm,mode] for s in study.SCANS]
            e=np.array([r['distance_m'] for r in group])
            # Two references: same-arm Gaussian and original free-c Gaussian.
            changes=e-np.array([lookup[s,arm,'G']['distance_m'] for s in study.SCANS])
            primary=e-np.array([lookup[s,'fitted-c','G']['distance_m'] for s in study.SCANS])
            totals.append(dict(arm=arm,mode=mode,median_error_m=float(np.median(e)),
                mean_error_m=float(np.mean(e)),p90_error_m=float(np.percentile(e,90)),
                below_1km=int(sum(e<1000)),converged=sum(r['converged'] for r in group),
                boundary=sum(r['boundary'] for r in group),
                improved_vs_same_arm_G=int(sum(changes < -1)),worsened_vs_same_arm_G=int(sum(changes > 1)),
                improved_vs_free_G=int(sum(primary < -1)),worsened_vs_free_G=int(sum(primary > 1)),
                median_posterior_rms_hz=float(np.median([r['posterior_weighted_residual_rms_hz'] for r in group])),
                median_abs_c_hz_ghz=float(np.median([abs(r['coefficient_hz_per_ghz']) for r in group])),
                total_changed_owner_windows=sum(r['strong_changed_owner_windows'] for r in group),
                mean_signal_posterior=float(np.mean([r['mean_signal_posterior'] for r in group]))))
    return totals


def table(rows, columns, precision=1):
    def show(v):
        if isinstance(v,float):return f'{v:.{precision}f}'
        return str(v)
    return '<table><tr>'+''.join('<th>'+html.escape(k)+'</th>' for k in columns)+'</tr>'+''.join(
        '<tr>'+''.join('<td>'+html.escape(show(r[k]))+'</td>' for k in columns)+'</tr>' for r in rows)+'</table>'


def main():
    rows=collect()
    lookup={(r['scan'],r['arm'],r['mode']):r for r in rows}
    totals=summary_rows(rows)
    target=study.OUT/'polished'
    study.old.csv_write(target/'summary.csv',totals)
    keys=['scan','arm','mode','windows','distance_m','converged','boundary','kkt','objective',
          'data_nll','timing_prior_nll','extra_prior_nll','coefficient_hz_per_ghz',
          'posterior_weighted_residual_rms_hz','owner_rms_hz','strong_changed_owner_windows',
          'mean_signal_posterior','common_reference_data_nll','rx0_extra_slope_hz_s','rx1_extra_slope_hz_s']
    study.old.csv_write(target/'per-scan.csv',[{k:r[k] for k in keys} for r in rows])
    paired=[]
    for s in study.SCANS:
        for m in study.MODES:
            ref=lookup[s,'fitted-c',m]
            for arm in ('prior-c','zero-c'):
                r=lookup[s,arm,m]
                paired.append(dict(scan=s,mode=m,arm=arm,
                    both_converged=ref['converged'] and r['converged'],
                    error_change_m=r['distance_m']-ref['distance_m'],
                    data_nll_change=r['data_nll']-ref['data_nll'],
                    posterior_rms_change_hz=r['posterior_weighted_residual_rms_hz']-ref['posterior_weighted_residual_rms_hz'],
                    coefficient_change=r['coefficient_hz_per_ghz']-ref['coefficient_hz_per_ghz'],
                    identity_switch_count_change=r['strong_changed_owner_windows']-ref['strong_changed_owner_windows']))
    study.old.csv_write(target/'rf-paired-changes.csv',paired)
    gradients=[]
    for r in rows:
        for g in r['roof_gradients']['satellites']:
            gradients.append(dict(scan=r['scan'],arm=r['arm'],mode=r['mode'],norad=g['norad'],
                nuisance_converged=r['roof_gradients']['nuisance_converged'],
                east_gradient_per_100m=g['gradient_per_100m'][0],north_gradient_per_100m=g['gradient_per_100m'][1],
                norm_per_100m=g['gradient_norm_per_100m'],original_windows=g['original_windows'],
                soft_expected_windows=g['soft_expected_windows']))
    study.old.csv_write(target/'roof-satellite-gradients.csv',gradients)
    fig,axes=plt.subplots(1,3,figsize=(17,5.3))
    modes=list(study.MODES)
    for ax,metric,title in zip(axes,['median_error_m','mean_error_m','p90_error_m'],
                             ['Median error','Mean error','90th-percentile error']):
        for i,arm in enumerate(study.ARMS):
            y=[next(r[metric] for r in totals if r['arm']==arm and r['mode']==m) for m in modes]
            bars=ax.bar(np.arange(4)+(i-1)*.26,y,width=.25,color=COLORS[arm],label=LABELS[arm])
            for b in bars:ax.text(b.get_x()+b.get_width()/2,b.get_height()+30,f'{b.get_height():.0f}',
                                 ha='center',va='bottom',fontsize=7,rotation=90)
        ax.set_xticks(range(4),['Gaussian','+ time\nbalance','Mixture','Mixture +\ntime balance'])
        ax.set_ylabel('Position error (m)');ax.set_title(title);ax.set_ylim(0,4400);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    axes[1].legend(loc='upper center',fontsize=8)
    fig.suptitle('N01–N16 · temporal weighting, robust errors and RF regularization',fontsize=15)
    fig.text(.5,.025,'All 16 scans included. Independent 4 km searches; full frozen input data and matched budgets. Development cohort, not held-out validation.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.07,1,.93]);fig.savefig(target/'summary.png',dpi=170);plt.close(fig)
    fig=plt.figure(figsize=(18,7.2));gs=fig.add_gridspec(3,2,width_ratios=[1,.025],hspace=.37,wspace=.07)
    for j,arm in enumerate(study.ARMS):
        ax=fig.add_subplot(gs[j,0]);arr=np.array([[lookup[s,arm,m]['distance_m'] for s in study.SCANS] for m in modes])
        im=ax.imshow(arr,vmin=0,vmax=4000,cmap='viridis_r',aspect='auto')
        for mi,m in enumerate(modes):
            for si,s in enumerate(study.SCANS):
                r=lookup[s,arm,m];label=f'{r["distance_m"]/1000:.2f}'+('△' if r['boundary'] else '')+('×' if not r['converged'] else '')
                ax.text(si,mi,label,ha='center',va='center',fontsize=8,color='white' if r['distance_m']>2300 else 'black')
        ax.set_xticks(range(16),study.SCANS);ax.set_yticks(range(4),[study.MODES[m]['label'] for m in modes],fontsize=9)
        ax.set_title(LABELS[arm],fontsize=11)
    fig.colorbar(im,cax=fig.add_subplot(gs[:,1]),label='Position error (m)')
    fig.subplots_adjust(left=.2,right=.95,bottom=.09,top=.9)
    fig.suptitle('Every scan and RF arm · numbers in km',fontsize=15)
    fig.text(.5,.02,'△ = 4 km search boundary; × = unconverged (KKT > 0.001). Best-found local results, not global certificates.',ha='center',fontsize=9)
    fig.savefig(target/'position-errors.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(15,6))
    for arm in ('prior-c','zero-c'):
        for mode,marker in zip(modes,['o','s','D','^']):
            p=[r for r in paired if (r['arm'],r['mode'])==(arm,mode)]
            axes[0].scatter([r['data_nll_change'] for r in p],[r['error_change_m'] for r in p],
                            c=COLORS[arm],marker=marker,s=35,alpha=.7,label=f'{LABELS[arm]} / {mode}')
            for r in p:
                if abs(r['error_change_m'])>1600:axes[0].annotate(r['scan'],(r['data_nll_change'],r['error_change_m']),fontsize=7)
    axes[0].axhline(0,color='.5',lw=1);axes[0].axvline(0,color='.5',lw=1)
    axes[0].set_xlabel('Data NLL change versus free c (within the same model)')
    axes[0].set_ylabel('Position error change (m; negative is better)')
    axes[0].set_title('Frequency fit is not position accuracy');axes[0].legend(fontsize=7,ncol=2)
    for arm in ('fitted-c','prior-c'):
        for mode,marker in zip(modes,['o','s','D','^']):
            subset=[lookup[s,arm,mode] for s in study.SCANS]
            axes[1].scatter([r['coefficient_hz_per_ghz'] for r in subset],[r['distance_m'] for r in subset],
                            c=COLORS[arm],marker=marker,s=35,alpha=.7,label=f'{LABELS[arm]} / {mode}')
    axes[1].set_xlabel('Fitted c (Hz/GHz)');axes[1].set_ylabel('Position error (m)')
    axes[1].set_title('Shrinking c is not uniformly helpful');axes[1].legend(fontsize=7,ncol=2)
    for ax in axes:ax.grid(alpha=.18)
    fig.tight_layout();fig.savefig(target/'fit-versus-position.png',dpi=170);plt.close(fig)
    unconverged=[{k:r[k] for k in ['scan','arm','mode','distance_m','kkt']} for r in rows if not r['converged']]
    nesting=[]
    for s in study.SCANS:
        for m in modes:
            a,b,c=[lookup[s,arm,m] for arm in study.ARMS]
            if a['objective']>b['objective']+1e-4 or b['objective']>c['objective']+1e-4:
                nesting.append(dict(scan=s,mode=m,free=a['objective'],prior=b['objective'],zero=c['objective']))
    audit=json.loads((target/'audit.json').read_text())
    audit.update(unconverged=unconverged,nested_objective_violations=nesting,
                 roof_nuisance_converged=sum(r['roof_gradients']['nuisance_converged'] for r in rows))
    (target/'diagnostic-audit.json').write_text(json.dumps(audit,indent=2))
    body='<h1>Focused position-model follow-up: time weighting × robust errors × RF prior</h1>'
    body+='<p>192 independent fits: 4 model combinations × 3 RF arms × 16 scans. All associated top-one windows retained; no folds, no new associations or calibration. Frozen upstream calibration was derived using the known roof, so this is development evidence, not blind localization validation.</p>'
    body+='<h2>Model</h2><p>J = −Σᵢ wᵢ log Lᵢ + ½(τ/10 s)² + ½Σₛ(δₛ/(⅓ s))² + optional ½(c/(100 Hz/GHz))². Same finite-set signal/clutter likelihood, detection budget 0.8, clutter rate 2. Gaussian width 200 Hz; robust mixture 90% × N(0,100²) + 10% × N(0,556.8²), wrapped modulo 227.273 kHz. Both kernels have the same unwrapped variance. Thus the mixture changes both core width and tail robustness; this experiment cannot attribute its effects to only one of those.</p>'
    body+='<p>Time weights are inverse counts within each occupied original-satellite/RX/5-second bin, normalized to mean 1. Every weight remains positive. This is a weighted/composite likelihood, not a claim of independently measured confidence. No per-scan variant selection by truth. The 100 Hz/GHz zero-centered prior is an exploratory sensitivity test, not a measured physical calibration prior.</p>'
    body+='<p>Free c and regularized c share an exactly identical c=0 control, computed once. Satellite identities remain soft within the unchanged candidate bank. Common timing bound ±10 s; total per-satellite timing ±20 s; independent 4 km disk. All 22 previous structural solutions are repriced for every case; all 12 new solutions per scan seed the second pass, identically in each arm.</p>'
    body+='<h2>Position results</h2><img src="summary.png"><img src="position-errors.png">'
    body+=table(totals,['arm','mode','median_error_m','mean_error_m','p90_error_m','below_1km','converged','boundary','improved_vs_same_arm_G','worsened_vs_same_arm_G'])
    body+='<h2>Frequency fit and identity sensitivity</h2><p>Raw scores across different kernels or weights are not interchangeable. The paired score plot compares RF arms only within the same kernel/weight model. Lower posterior-weighted residual RMS is not evidence of better position or better satellite identity.</p><img src="fit-versus-position.png">'
    body+=table(totals,['arm','mode','median_posterior_rms_hz','median_abs_c_hz_ghz','total_changed_owner_windows','mean_signal_posterior'],3)
    body+=f'<h2>Convergence and audit</h2><p>{audit["converged"]}/{len(rows)} position fits converged; {audit["boundary"]} hit the 4 km boundary. {audit["roof_nuisance_converged"]}/{len(rows)} fixed-roof nuisance fits converged. Satellite-gradient CSV labels the others as conditional, not converged profile gradients. {len(nesting)} nested-objective order violations.</p>'
    if unconverged:body+=table(unconverged,['scan','arm','mode','distance_m','kkt'],6)
    body+='<h2>Concrete convergence obstacle</h2><p>A separate read-only diagnostic found a hard-horizon discontinuity in the saved N08 time-balanced Gaussian fit. NORAD 62493 crosses the geometric horizon at one RX0/CH3 window at 9.495 s. Its frequency residual to that window is −65.1 kHz, so it is not a plausible identity there, yet the visible-satellite count changes the finite-set normalizer. The objective jumps by 0.035496 NLL for an arbitrarily small timing change. The smooth gradient does not include this boolean jump. This explains a stubborn smooth convergence failure, not the overall position bias. No gate change was applied in this comparison.</p><img src="../visibility-diagnostic/score-jump.png">'
    body+='<p>Numerical checks: 72 unit tests and 72 real-data gradient checks away from visibility jumps; control score/gradient/curvature parity. Final audit reconstructs input hashes, all fit/evaluation rows, coefficients, bounds, objectives and KKT residuals. Bounded multistart search does not certify a global minimum. We have repeatedly tuned this same cohort; improvements require new-scan confirmation, fitting every new scan on its full data.</p>'
    body+='<h2>Artifacts</h2><ul>'+''.join(f'<li><a href="{p}">{p}</a></li>' for p in ['summary.csv','per-scan.csv','rf-paired-changes.csv','roof-satellite-gradients.csv','audit.json','diagnostic-audit.json'])+'</ul>'
    (target/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Focused position-model follow-up</title><style>body{font:16px system-ui;max-width:1500px;margin:30px auto;padding:20px;line-height:1.5}img{width:100%}table{border-collapse:collapse;font-size:12px}th,td{border:1px solid #ddd;padding:5px;text-align:right}h2{margin-top:2em}</style>'+body)
    print(json.dumps(dict(summary=totals,audit=audit),indent=2))


if __name__=='__main__':main()
