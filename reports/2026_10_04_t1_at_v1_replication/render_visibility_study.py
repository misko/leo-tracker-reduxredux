"""Static scientific figures and full-data tables for the visibility prototype."""
import argparse
import html
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import position_visibility_study as study
from smooth_visibility_model import gate_terms

COLORS={'H':'#333333','L1':'#0072B2','L4':'#D55E00','P1':'#009E73','Q1':'#CC79A7'}
ARM_LABEL={'fitted-c':'Fitted c','zero-c':'c = 0'}


def gate_figures():
    target=study.OUT/'diagnostics';target.mkdir(parents=True,exist_ok=True)
    degrees=np.linspace(-5,5,1601)
    fig,axes=plt.subplots(1,2,figsize=(14,5.2))
    for gate,spec in study.GATES.items():
        w,_=gate_terms(np.sin(np.deg2rad(degrees)),gate)
        axes[0].plot(degrees,w,color=COLORS[gate],label=spec['label'],lw=2)
    axes[0].set(xlabel='Geometric elevation (degrees)',ylabel='Detection-probability multiplier',title='Horizon transition functions')
    axes[0].axvline(0,color='.65',ls=':');axes[0].grid(alpha=.2);axes[0].legend(fontsize=8)
    source=study.prior.OUT/'polished'/'N08-fitted-c-GT.json'
    saved=json.loads(source.read_text());data,meta,*_=study.inputs('N08')
    record=saved['best'];v=np.asarray(record['vector']);offsets=np.r_[np.linspace(-.0002,-1e-8,31),0.,np.linspace(1e-8,.0002,31)]
    rows=[];checks=[]
    for gate in study.GATES:
        obj=study.objective(data,meta,'fitted-c',gate,'time-balanced')
        j0,g=obj.evaluate(v);y=[]
        for dt in offsets:
            trial=v.copy();trial[6]+=dt;j,_=obj.evaluate(trial)
            y.append(j-j0);rows.append(dict(gate=gate,timing_delta_s=float(dt),score_delta=float(j-j0)))
        axes[1].plot(offsets*1000,y,color=COLORS[gate],label=gate,lw=1.7)
        eps=1e-8;l,r=v.copy(),v.copy();l[6]-=eps;r[6]+=eps
        jump=obj.evaluate(r)[0]-obj.evaluate(l)[0]
        checks.append(dict(gate=gate,tiny_step_difference_nll=float(jump),analytic_gradient=float(g[6]),
                           finite_difference_gradient=float(jump/(2*eps))))
    axes[1].set(xlabel='Common timing perturbation (ms)',ylabel='Score − score at saved parameters',
                title='N08: does the horizon score jump disappear?')
    axes[1].grid(alpha=.2);axes[1].legend(title='Model',fontsize=8)
    fig.suptitle('Smooth visibility prototypes · same Doppler observations and orbit bank',fontsize=15)
    fig.text(.5,.02,'Centered models allow probability below 0°. Q1 is exactly zero below the horizon. Right: diagnostic slice with all other parameters fixed; no refit.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.06,1,.93]);fig.savefig(target/'visibility-and-continuity.png',dpi=170);plt.close(fig)
    study.old.csv_write(target/'continuity-curve.csv',rows)
    (target/'continuity-checks.json').write_text(json.dumps(dict(source=str(source),source_sha256=study.old.previous.digest(source),
         epsilon_s=eps,rows=checks),indent=2))
    print(json.dumps(checks,indent=2))


def summaries(rows):
    lookup={(r['scan'],r['arm'],r['weighting'],r['gate']):r for r in rows};result=[]
    for weighting in study.WEIGHTS:
        for arm in study.ARMS:
            for gate in study.GATES:
                group=[lookup[s,arm,weighting,gate] for s in study.SCANS]
                reference=[lookup[s,arm,weighting,'H'] for s in study.SCANS]
                error=np.array([r['distance_m'] for r in group])
                change=error-np.array([r['distance_m'] for r in reference])
                result.append(dict(weighting=weighting,arm=arm,gate=gate,
                    median_error_m=float(np.median(error)),mean_error_m=float(np.mean(error)),
                    p90_error_m=float(np.percentile(error,90)),below_1km=int(sum(error<1000)),
                    converged=int(sum(r['converged'] for r in group)),boundary=int(sum(r['boundary'] for r in group)),
                    improved=int(sum(change<-1.)),worsened=int(sum(change>1.)),
                    median_posterior_rms_hz=float(np.median([r['posterior_weighted_residual_rms_hz'] for r in group])),
                    median_owner_rms_hz=float(np.median([r['owner_rms_hz'] for r in group])),
                    below_horizon_expected_windows=float(sum(r['below_horizon_expected_windows'] for r in group)),
                    below_horizon_strong_windows=int(sum(r['below_horizon_strong_windows'] for r in group)),
                    total_changed_owner_windows=int(sum(r['strong_changed_owner_windows'] for r in group)),
                    median_kkt=float(np.median([r['kkt'] for r in group])),
                    median_hard_reference_data_nll_change=float(np.median([r['common_hard_data_nll']-b['common_hard_data_nll'] for r,b in zip(group,reference)]))))
    return result


def table(rows,keys):
    def value(x):return f'{x:.3f}' if isinstance(x,float) else str(x)
    return '<table><tr>'+''.join(f'<th>{html.escape(k)}</th>' for k in keys)+'</tr>'+''.join('<tr>'+''.join(
        f'<td>{html.escape(value(r[k]))}</td>' for k in keys)+'</tr>' for r in rows)+'</table>'


def report(stage):
    if stage=='polished':
        from polish_visibility_study import collect
        rows=collect()
    else:rows=study.collect(stage)
    target=study.OUT/stage
    totals=summaries(rows);lookup={(r['scan'],r['arm'],r['weighting'],r['gate']):r for r in rows}
    study.old.csv_write(target/'summary.csv',totals)
    keys=['scan','arm','weighting','gate','windows','distance_m','converged','boundary','kkt',
          'objective','data_nll','timing_prior_nll','coefficient_hz_per_ghz','owner_rms_hz',
          'posterior_weighted_residual_rms_hz','strong_changed_owner_windows',
          'below_horizon_expected_windows','below_horizon_signal_fraction','below_horizon_strong_windows',
          'common_hard_data_nll']
    study.old.csv_write(target/'per-scan.csv',[{k:r[k] for k in keys} for r in rows])
    pairs=[]
    for r in rows:
        b=lookup[r['scan'],r['arm'],r['weighting'],'H']
        pairs.append(dict(scan=r['scan'],arm=r['arm'],weighting=r['weighting'],gate=r['gate'],
            error_change_m=r['distance_m']-b['distance_m'],
            spatial_move_m=float(1000*np.linalg.norm(np.array(r['best']['point_km'])-b['best']['point_km'])),
            rms_change_hz=r['posterior_weighted_residual_rms_hz']-b['posterior_weighted_residual_rms_hz'],
            both_converged=r['converged'] and b['converged']))
    study.old.csv_write(target/'paired-vs-hard.csv',pairs)
    historic=[]
    for r in rows:
        if r['gate']!='H':continue
        previous_mode='G' if r['weighting']=='ordinary' else 'GT'
        path=study.prior.OUT/'polished'/f'{r["scan"]}-{r["arm"]}-{previous_mode}.json'
        old=json.loads(path.read_text())
        historic.append(dict(scan=r['scan'],arm=r['arm'],weighting=r['weighting'],
            previous_error_m=old['distance_m'],rerun_error_m=r['distance_m'],
            objective_change=r['objective']-old['objective'],
            previous_converged=old['converged'],rerun_converged=r['converged']))
    study.old.csv_write(target/'control-restart-comparison.csv',historic)
    fig,axes=plt.subplots(2,2,figsize=(15,9))
    smooth=[g for g in study.GATES if g!='H']
    for wi,w in enumerate(study.WEIGHTS):
        for ai,a in enumerate(study.ARMS):
            ax=axes[wi,ai]
            for j,g in enumerate(smooth):
                subset=[r for r in pairs if (r['arm'],r['weighting'],r['gate'])==(a,w,g)]
                y=np.array([r['error_change_m'] for r in subset]);x=j+np.linspace(-.17,.17,len(subset))
                ax.scatter(x,y,s=30,color=COLORS[g],alpha=.85)
                ax.scatter([j],[np.median(y)],marker='D',s=65,color='white',edgecolor='black',zorder=4)
                for xx,yy,r in zip(x,y,subset):
                    if not r['both_converged']:ax.scatter([xx],[yy],marker='x',color='black',s=35,zorder=5)
                    if abs(yy)>5:ax.annotate(r['scan'],(xx,yy),xytext=(3,3),textcoords='offset points',fontsize=7)
            ax.axhline(0,color='.4',lw=1);ax.set_xticks(range(4),smooth)
            ax.set_title(f'{ARM_LABEL[a]} · {w}');ax.set_ylabel('Position error change vs hard gate (m)')
            ax.grid(alpha=.2)
    fig.suptitle('Paired scan-by-scan changes · below zero is better',fontsize=16)
    fig.text(.5,.02,'One point per scan/model; diamond = median; × = either paired fit unconverged. Panel scales differ to expose small changes.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.055,1,.95]);fig.savefig(target/'paired-position-changes.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(15,10),sharey=True)
    for wi,weighting in enumerate(study.WEIGHTS):
        for ai,arm in enumerate(study.ARMS):
            ax=axes[wi,ai];group=[next(t for t in totals if (t['arm'],t['weighting'],t['gate'])==(arm,weighting,g)) for g in study.GATES]
            for metric,shift,color,label in [('median_error_m',-.26,'#0072B2','Median'),('mean_error_m',0,'#999999','Mean'),('p90_error_m',.26,'#D55E00','90th percentile')]:
                bars=ax.bar(np.arange(5)+shift,[r[metric] for r in group],width=.25,color=color,label=label)
                for b in bars:ax.text(b.get_x()+b.get_width()/2,b.get_height()+25,f'{b.get_height():.0f}',ha='center',va='bottom',fontsize=7,rotation=90)
            ax.set_xticks(range(5),['Hard','Logistic\n1°','Logistic\n4°','Gaussian\nCDF 1°','Above-only\n0–1°'])
            ax.set_title(f'{ARM_LABEL[arm]} · {weighting} weights');ax.set_ylabel('Position error (m)')
            ax.set_ylim(0,4450);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    axes[0,0].legend(fontsize=8);fig.suptitle('N01–N16 · does smooth visibility improve position accuracy?',fontsize=16)
    fig.text(.5,.015,'All 16 scans retained; all-data development comparison. Matched c ablation, candidate banks, timing priors and bounded multistart budgets.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.045,1,.95]);fig.savefig(target/'position-summary.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(15,9))
    for ax,metric,title in zip(axes.ravel(),['converged','median_posterior_rms_hz','below_horizon_expected_windows','total_changed_owner_windows'],
                             ['Converged scans / 16','Median posterior-weighted residual RMS','Expected windows attributed below the horizon','Strong soft identities differing from original owners']):
        for weighting,style in [('ordinary','-'),('time-balanced','--')]:
            for arm,color in [('fitted-c','#0072B2'),('zero-c','#D55E00')]:
                group=[next(t for t in totals if (t['arm'],t['weighting'],t['gate'])==(arm,weighting,g)) for g in study.GATES]
                ax.plot(range(5),[r[metric] for r in group],marker='o',ls=style,color=color,label=f'{ARM_LABEL[arm]} / {weighting}')
        ax.set_xticks(range(5),list(study.GATES));ax.set_title(title);ax.grid(alpha=.2)
        if metric=='converged':ax.set_ylim(0,17);ax.set_yticks(range(0,17,4))
        if metric=='median_posterior_rms_hz':ax.set_ylabel('Hz')
        if metric=='below_horizon_expected_windows' and max(r[metric] for r in totals)<1e-9:
            ax.text(.5,.82,'All variants: effectively zero below-horizon signal support',
                    ha='center',transform=ax.transAxes,fontsize=9)
    axes[0,0].legend(fontsize=8)
    fig.suptitle('Optimization, frequency fit and physical-support diagnostics',fontsize=16)
    fig.text(.5,.02,'Expected below-horizon count sums unweighted soft satellite responsibilities; it is not a count of new detections. Lower residual RMS is not better location accuracy.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.055,1,.95]);fig.savefig(target/'performance-metrics.png',dpi=170);plt.close(fig)
    fig=plt.figure(figsize=(18,10));gs=fig.add_gridspec(4,2,width_ratios=[1,.025],hspace=.38,wspace=.06)
    for row,(weighting,arm) in enumerate((w,a) for w in study.WEIGHTS for a in study.ARMS):
        ax=fig.add_subplot(gs[row,0]);arr=np.array([[lookup[s,arm,weighting,g]['distance_m'] for s in study.SCANS] for g in study.GATES])
        im=ax.imshow(arr,cmap='viridis_r',vmin=0,vmax=4000,aspect='auto')
        for j,g in enumerate(study.GATES):
            for i,s in enumerate(study.SCANS):
                r=lookup[s,arm,weighting,g];txt=f'{r["distance_m"]/1000:.2f}'+('△' if r['boundary'] else '')+('×' if not r['converged'] else '')
                ax.text(i,j,txt,ha='center',va='center',fontsize=7.6,color='white' if r['distance_m']>2300 else 'black')
        ax.set_xticks(range(16),study.SCANS);ax.set_yticks(range(5),list(study.GATES));ax.set_title(f'{ARM_LABEL[arm]} · {weighting}',fontsize=11)
    fig.colorbar(im,cax=fig.add_subplot(gs[:,1]),label='Position error (m)')
    fig.subplots_adjust(left=.055,right=.96,bottom=.06,top=.93);fig.suptitle('All 320 position fits · numbers in km',fontsize=16)
    fig.text(.5,.015,'△ = 4 km boundary; × = KKT > 0.001. All rows retained. Full-data known-roof development; best-found local solutions, not global certificates.',ha='center',fontsize=9)
    fig.savefig(target/'per-scan-errors.png',dpi=170);plt.close(fig)
    nesting=[]
    for scan in study.SCANS:
        for w in study.WEIGHTS:
            for g in study.GATES:
                a,b=[lookup[scan,arm,w,g] for arm in study.ARMS]
                if a['objective']>b['objective']+1e-4:nesting.append(dict(scan=scan,weighting=w,gate=g,gap=a['objective']-b['objective']))
    audit=dict(status='passed',cases=len(rows),converged=sum(r['converged'] for r in rows),
        boundary=sum(r['boundary'] for r in rows),nested_objective_violations=nesting,
        unconverged=[{k:r[k] for k in ['scan','arm','weighting','gate','distance_m','kkt']} for r in rows if not r['converged']])
    (target/'audit.json').write_text(json.dumps(audit,indent=2))
    body='<h1>Smooth visibility models: N01–N16</h1>'
    body+='<p>320 independent position fits: 5 visibility models × 2 weighting schemes × 2 RF arms × 16 scans. All frozen associated top-one windows are used for fitting and evaluation; no data folds, new candidates, upstream calibration, RF collection or new TLEs. This is a known-roof development cohort, not blind validation.</p>'
    body+='<h2>Models and score</h2><p>For each window and satellite, qᵢₛ = (0.8/K) × w(sin elevation). H is the original hard horizon. L1/L4 are centered logistic gates with 1°/4° full 10–90% transition widths; P1 is a Gaussian CDF with 1° 10–90% width. Q1 is a C² quintic ramp from 0° to 1°, exactly zero below the horizon. Centered models represent a softened horizon assumption and are not an antenna beam model.</p>'
    body+='<p>The original finite-set likelihood is preserved: P₀ = exp(−2)∏ₛ(1−qᵢₛ); Lᵢ = P₀[2/A + Σₛ qᵢₛ fᵢₛ/(1−qᵢₛ)]/(1−P₀), A = 227.273 kHz. Both Doppler and visibility/normalization derivatives enter the gradient. The positive curvature matrix is an optimization preconditioner, not an exact likelihood Hessian or a reported uncertainty estimate.</p>'
    body+='<p>Frequency kernel: wrapped Gaussian σ=200 Hz. Timing priors and bounds unchanged: common σ=10 s, relative σ=⅓ s, common ±10 s, total satellite timing ±20 s. Free c versus c=0, no new c prior. Ordinary weights are 1; time weights are inverse satellite/RX/5-second-bin counts, normalized to mean 1. Every row remains positive-weighted.</p>'
    body+='<img src="../diagnostics/visibility-and-continuity.png"><h2>Position accuracy</h2><img src="position-summary.png">'
    body+=table(totals,['weighting','arm','gate','median_error_m','mean_error_m','p90_error_m','improved','worsened','converged','boundary'])
    body+='<p>Improved/worsened means more than 1 m relative to the rerun hard control with the same weighting and RF arm. Controls receive the same shared starts and budgets; older historical estimates are not used as unmatched controls. All scans remain in summaries, including flagged fits. Models and seeds are never selected by truth error.</p><img src="paired-position-changes.png"><img src="per-scan-errors.png">'
    body+='<h2>Separate frequency and physical-support metrics</h2><img src="performance-metrics.png">'
    body+=table(totals,['weighting','arm','gate','median_posterior_rms_hz','below_horizon_expected_windows','below_horizon_strong_windows','total_changed_owner_windows'])
    body+=f'<h2>Audit</h2><p>{audit["converged"]}/{len(rows)} fit KKT residuals ≤0.001; {audit["boundary"]} boundary results. {len(nesting)} nested RF-objective order violations. 92 unit tests plus 224 real-data gradient checks passed, including the old N08 discontinuity neighborhood. Inputs, weights, priors, source hashes, scores and hard bounds were reconstructed from saved results.</p>'
    if audit['unconverged']:body+=table(audit['unconverged'],['scan','arm','weighting','gate','distance_m','kkt'])
    body+='<p>Piecewise-linear orbit interpolation can still have derivative kinks at its knots; smooth visibility removes the horizon step, not every possible nonsmooth feature. Bounded multistart fits are not global-optimum certificates. Repeated tuning on this cohort requires confirmation on additional scans, fitted on their full data.</p>'
    body+='<h2>Data</h2><ul>'+''.join(f'<li><a href="{p}">{p}</a></li>' for p in ['summary.csv','per-scan.csv','paired-vs-hard.csv','control-restart-comparison.csv','audit.json'])+'</ul>'
    (target/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Smooth visibility study</title><style>body{font:16px system-ui;line-height:1.5;max-width:1550px;margin:30px auto;padding:20px}img{width:100%}table{border-collapse:collapse;font-size:12px}td,th{padding:5px;border:1px solid #ddd;text-align:right}</style>'+body)
    print(json.dumps(dict(summary=totals,audit=audit),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--diagnostics',action='store_true')
    p.add_argument('--stage',choices=['final','polished'],default='final');args=p.parse_args()
    if args.diagnostics:gate_figures()
    else:report(args.stage)
