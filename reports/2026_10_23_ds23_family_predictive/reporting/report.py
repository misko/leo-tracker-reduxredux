"""Reporting-only evaluation of fixed family-held-out position diagnostics."""
from pathlib import Path
import csv
import hashlib
import importlib.util
import json
import math
import statistics
import re
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
FROZEN=Path('/srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023')
HELPER=FROZEN/'source/report_full.py'
spec=importlib.util.spec_from_file_location('frozen_position_reporting',HELPER)
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
ARMS=('c0','fitted_c');THRESHOLD=.01/8

def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def qualified(fit):
    if 'gate_slacks' in fit:
        gates=bool(all(math.isfinite(v) and v>=0 for v in fit['gate_slacks'].values()))
    else:
        gates=bool(all(r['compatible'] for r in fit['gates']['tracks']) and all(r['compatible'] for r in fit.get('linear_gates',[])))
    return gates and fit.get('final_phase_change_s',0)<=.01

def load():
    protocol=read(ROOT/'protocol.json');jobs={};paths=[ROOT/'protocol.json',HELPER,Path(__file__),ROOT/'reporting/test_report.py']
    assert len(protocol['jobs'])==16
    for job in protocol['jobs']:
        path=ROOT/'raw'/job['name']/'result.json'
        if not path.exists():raise ValueError('incomplete16jobexecution')
        d=read(path)
        if d['status']!='complete':raise ValueError('noncompletejob:'+job['name'])
        assert d['job']==job and set(d['arms'])==set(ARMS)
        assert d['predictions']['c0']['observation_ids']==d['predictions']['fitted_c']['observation_ids']
        assert all(v['training_ID_overlap']==0 for v in d['predictions'].values())
        jobs[job['name']]=d;paths.append(path)
    return protocol,jobs,paths

def assemble(protocol,jobs):
    fits=[];paths=[];residuals=[];flags=[];blocks=[]
    for job in protocol['jobs']:
        d=jobs[job['name']];case=job['case'];family=job['family'];mode=job['mode']
        paired_flag=all(d['predictions'][a]['diagnostic_chi2_upper_tail']<THRESHOLD for a in ARMS)
        flags.append(dict(case=case,family=family,mode=mode,diagnostic_threshold=THRESHOLD,c0_p=d['predictions']['c0']['diagnostic_chi2_upper_tail'],fitted_c_p=d['predictions']['fitted_c']['diagnostic_chi2_upper_tail'],paired_diagnostic_flag=paired_flag,calibrated_test=False,paired_training_gates_pass=d['paired_training_gates_pass']))
        for arm in ARMS:
            fit=d['arms'][arm];p=d['predictions'][arm];s=d['sensitivity'][arm]
            heldcurved=sum(r['role']=='curved' for r in p['metadata']);heldnative=sum(r['role']=='native' for r in p['metadata'])
            assert heldnative==d['held_native_points'] and heldcurved==d['removed_curved_points']
            fails={k:v for k,v in fit['gate_slacks'].items() if v<0}
            fits.append(dict(case=case,family=family,mode=mode,arm=arm,error_km=helper.position_error(fit['endpoint_latlon']),
                latitude=fit['endpoint_latlon'][0],longitude=fit['endpoint_latlon'][1],RMS_hz=fit['RMS_hz'],training_gates_pass=qualified(fit),paired_training_gates_pass=d['paired_training_gates_pass'],
                failing_gate_count=len(fails),minimum_gate_slack=min(fit['gate_slacks'].values()),held_curved_points=heldcurved,held_native_points=heldnative,total_held_points=p['points'],
                newly_discovered_family_points=protocol['selection'][case]['all_native_family_point_counts'][str(family)],
                quadratic=p['quadratic'],quadratic_per_point=p['quadratic_per_point'],diagnostic_p=p['diagnostic_chi2_upper_tail'],paired_diagnostic_flag=paired_flag,
                native_only_quadratic_per_point=p['native_only']['quadratic_per_point'],native_only_diagnostic_p=p['native_only']['diagnostic_chi2_upper_tail'],
                final_phase_update_s=fit['final_phase_change_s'],local_GN_condition=s['condition_number'],local_GN_min_eigenvalue=s['eigenvalues'][0],local_GN_max_eigenvalue=s['eigenvalues'][-1],
                weak_direction_east=s['weak_direction_east_north'][0],weak_direction_north=s['weak_direction_east_north'][1],seconds=d['seconds']))
            for name,value in s['coefficient_derivative_norm_by_block'].items():blocks.append(dict(case=case,family=family,mode=mode,arm=arm,block=name,standardized_coefficient_derivative_norm_per_km=value,interpretation='dimensiondependent nuisance response; not correlation or position uncertainty'))
            for row in p['path_means']:paths.append(dict(case=case,mode=mode,arm=arm,**row,training_gates_pass=qualified(fit)))
            diagonal=np.diag(np.array(p['covariance_hz2']))
            for k,(meta,oid) in enumerate(zip(p['metadata'],p['observation_ids'],strict=True)):
                residuals.append(dict(case=case,mode=mode,arm=arm,**meta,observation_id=oid,innovation_hz=p['innovation_hz'][k],
                    raw_residual_hz=p['raw_residual_hz'][k],conditional_mean_correction_hz=p['conditional_mean_correction_hz'][k],marginal_prediction_sd_hz=float(np.sqrt(diagonal[k])),training_gates_pass=qualified(fit)))
    return fits,paths,residuals,flags,blocks

def baselines():
    rows=[];paths=[]
    for case in ['DS23-0259','DS23-0353']:
        p=FROZEN/'raw'/case/'result.json';d=read(p);paths.append(p)
        n=FROZEN/'raw'/case/'native'/(case+'.json');native=read(n)['methods']['persistent5s'];paths.append(n)
        for method,view in [('graph_parent',d['ordinary_graph']),('full_ordinary_native',native),('previous_final_constrained_policy',d['final'])]:
            for arm,fit in view['arms'].items():
                rows.append(dict(case=case,method=method,arm=arm,error_km=helper.position_error(fit['endpoint_latlon']),RMS_hz=fit['RMS_hz'],
                    training_gates_pass=qualified(fit),native_method_accepted=native.get('accepted') if method=='full_ordinary_native' else None,final_phase_update_s=fit.get('final_phase_change_s'),
                    note='prior frozen policy may use constrained rescue; no new selection' if method=='previous_final_constrained_policy' else 'frozen diagnostic endpoint'))
    return rows,paths

def table(name,rows):
    p=ROOT/'tables'/(name+'.csv');p.parent.mkdir(exist_ok=True)
    with p.open('w',newline='') as f:
        if not rows:return
        writer=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)),lineterminator='\n');writer.writeheader();writer.writerows(rows)

def plots(fits,paths,residuals,baseline):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    out=ROOT/'figures';out.mkdir(exist_ok=True)
    fig,axes=plt.subplots(2,2,figsize=(14,9),layout='constrained')
    colors={('native_only','c0'):'#5383b6',('native_only','fitted_c'):'#9bbcd9',('whole_family','c0'):'#c37a35',('whole_family','fitted_c'):'#e4bb8d'}
    for col,case in enumerate(['DS23-0259','DS23-0353']):
        families=list(dict.fromkeys(r['family'] for r in fits if r['case']==case))
        for j,(key,color) in enumerate(colors.items()):
            mode,arm=key;rr=[next(r for r in fits if r['case']==case and r['family']==family and r['mode']==mode and r['arm']==arm) for family in families]
            xx=np.arange(len(families))+(j-1.5)*.19
            for row,metric in [(0,'error_km'),(1,'quadratic_per_point')]:
                bars=axes[row,col].bar(xx,[r[metric] for r in rr],width=.18,color=color,label=mode+' '+arm)
                for bar,r in zip(bars,rr,strict=True):
                    if not r['training_gates_pass']:bar.set_hatch('///');bar.set_edgecolor('#333333')
                axes[row,col].set_xticks(range(len(families)),families);axes[row,col].set(title=case,xlabel='Held family',ylabel='Position error(km)' if row==0 else 'Held predictive Q / n (diagnostic)')
        axes[0,col].legend(fontsize=7,ncol=2);axes[1,col].axhline(1,c='black',ls='--',lw=.8)
    fig.suptitle('Frozen family labels/discovery/priors; positions refitted without held observations\nHatching: training gates fail; chi-square tails are uncalibrated diagnostics; no adoption')
    fig.savefig(out/'held_positions_and_predictive_q.png',dpi=180);plt.close(fig)
    # Path means are shown with the exact arithmetic-mean marginal prediction SD.
    fig,axes=plt.subplots(2,2,figsize=(15,9),layout='constrained')
    for col,case in enumerate(['DS23-0259','DS23-0353']):
        for row,mode in enumerate(['native_only','whole_family']):
            ax=axes[row,col];rr=[r for r in paths if r['case']==case and r['mode']==mode]
            keys=list(dict.fromkeys((r['family'],r['receiver'],r['band'],r['key'],r['role']) for r in rr));yy=np.arange(len(keys))
            for arm,offset,color in [('c0',-.13,'#285b93'),('fitted_c',.13,'#cf8a31')]:
                vv=[next(r for r in rr if (r['family'],r['receiver'],r['band'],r['key'],r['role'])==key and r['arm']==arm) for key in keys]
                ax.errorbar([r['mean_innovation_hz'] for r in vv],yy+offset,xerr=[r['mean_prediction_sd_hz'] for r in vv],fmt='o',ms=3,lw=.7,color=color,label=arm)
            def shortkey(key):
                if key.startswith('GRAPH_PATH'):return 'G'+key.split('_')[-1]
                match=re.search(r'-CH(\d+)-T(\d+)',key)
                return 'C'+match[1]+'T'+match[2] if match else key[-10:]
            labels=[f'{k[0]} RX{k[1]}/{k[2]} {k[4][0]} {shortkey(k[3])}' for k in keys]
            ax.set_yticks(yy,labels,fontsize=6);ax.axvline(0,c='black',lw=.7);ax.set(title=case+' '+mode,xlabel='Path mean innovation ± marginal prediction SD(Hz)');ax.legend(fontsize=8)
    fig.suptitle('Path means grouped by family / receiver / RF band · SD bars are not calibrated confidence intervals')
    fig.savefig(out/'path_means_receiver_band.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(14,8),layout='constrained')
    for col,case in enumerate(['DS23-0259','DS23-0353']):
        for row,mode in enumerate(['native_only','whole_family']):
            ax=axes[row,col]
            for arm,marker in [('c0','o'),('fitted_c','x')]:
                rr=[r for r in residuals if r['case']==case and r['mode']==mode and r['arm']==arm]
                groups=list(dict.fromkeys((r['family'],r['receiver'],r['band']) for r in rr))
                for group in groups:
                    vv=[r for r in rr if (r['family'],r['receiver'],r['band'])==group]
                    ax.scatter([r['time_s'] for r in vv],[r['innovation_hz'] for r in vv],s=9,marker=marker,alpha=.65,label=f'{group[0]} RX{group[1]}/{group[2]} {arm}')
            ax.axhline(0,c='black',lw=.7);ax.set(title=case+' '+mode,xlabel='Recording time(s)',ylabel='Held innovation(Hz)');ax.legend(fontsize=5,ncol=2)
    fig.suptitle('Conditional predictive residuals by receiver / RF band / family; held observations do not fit position')
    fig.savefig(out/'residuals_receiver_band.png',dpi=180);plt.close(fig)

def curvature():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    path=ROOT/'scalar_curvature.json';d=read(path);rows=[]
    assert len(d['rows'])==44
    for r in d['rows']:
        for c in r['curvatures']:
            rows.append(dict(case=r['case'],name=r['name'],arm=r['arm'],step_km=c['step_km'],fit_scalar_loss=c['score'],
                gradient_east=c['gradient'][0],gradient_north=c['gradient'][1],gradient_norm=float(np.linalg.norm(c['gradient'])),
                hessian_min_eigenvalue=c['eigenvalues'][0],hessian_max_eigenvalue=c['eigenvalues'][-1],hessian_condition=c['condition_number'],
                local_newton_step_km=float(np.linalg.norm(c['local_newton_step_km'])),interpretation='actual minimized scalar local finite-difference curvature; not calibrated confidence or global basin evidence'))
    table('scalar_objective_curvature',rows)
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for col,case in enumerate(['DS23-0259','DS23-0353']):
        names=['graph','ordinary_native','prior_final']
        for arm,offset,color in [('c0',-.13,'#285b93'),('fitted_c',.13,'#c77f2b')]:
            rr=[next(r for r in rows if r['case']==case and r['name']==n and r['arm']==arm and r['step_km']==.02) for n in names];xx=np.arange(3)+offset
            axes[0,col].scatter(xx,[r['hessian_min_eigenvalue'] for r in rr],color=color,marker='o',label=arm+' min')
            axes[0,col].scatter(xx,[r['hessian_max_eigenvalue'] for r in rr],color=color,marker='x',label=arm+' max')
            axes[1,col].bar(xx,[r['gradient_norm'] for r in rr],width=.24,color=color,label=arm)
        for ax in axes[:,col]:ax.set_xticks(range(3),names);ax.set_title(case)
        axes[0,col].set_ylabel('Actual fit-loss Hessian eigenvalues / km²');axes[0,col].legend(fontsize=8,ncol=2)
        axes[1,col].set_yscale('log');axes[1,col].set_ylabel('Actual fit-loss gradient norm / km');axes[1,col].legend(fontsize=8)
    fig.suptitle('Local scalar-objective diagnostics at frozen endpoints · 0.02km differences\nPrior constrained endpoints need not minimize the ordinary objective; no calibrated uncertainty')
    fig.savefig(ROOT/'figures/baseline_scalar_curvature.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,5),layout='constrained')
    for ax,case in zip(axes,['DS23-0259','DS23-0353'],strict=True):
        r=next(r for r in d['rows'] if r['case']==case and r['name']=='ordinary_native' and r['arm']=='fitted_c')
        g=next(r for r in d['rows'] if r['case']==case and r['name']=='graph' and r['arm']=='fitted_c')
        h=np.array(r['curvatures'][0]['hessian']);displacement=np.array(g['endpoint_east_north_km'])-r['endpoint_east_north_km'];extent=max(3.,float(abs(displacement).max())*1.15)
        grid=np.linspace(-extent,extent,301);xx,yy=np.meshgrid(grid,grid);delta=np.stack([xx,yy],axis=-1)
        loss=.5*np.einsum('...i,ij,...j->...',delta,h,delta)
        contour=ax.contour(xx,yy,loss,levels=[.5,1.,2.],colors=['#9ab7d4','#598abd','#205588']);ax.clabel(contour,inline=True,fontsize=8)
        ax.scatter([0],[0],marker='o',label='Ordinary native RF endpoint');ax.scatter([displacement[0]],[displacement[1]],marker='x',label='Graph endpoint displacement')
        ax.set(title=case+' fitted_c',xlabel='East displacement(km)',ylabel='North displacement(km)',aspect='equal');ax.legend(fontsize=7)
    fig.suptitle('Quadratic approximation to local fit-loss change (0.5,1,2), fixed phase reference\nExtrapolated local model; not measured global contours or probability/confidence regions; no GPS')
    fig.savefig(ROOT/'figures/local_quadratic_loss.png',dpi=180);plt.close(fig)
    return path,rows

def common_mask_lines():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    path=ROOT/'common_mask_lines.json';d=read(path);assert len(d['rows'])==66
    rows=[];groups=[('DS23-0259','graph_to_ordinary_native'),('DS23-0353','graph_to_ordinary_native'),('DS23-0353','ordinary_native_to_previous_final')]
    fig,axes=plt.subplots(2,3,figsize=(15,8),layout='constrained')
    summaries=[]
    for col,(case,line) in enumerate(groups):
        for arm,color in [('c0','#285b93'),('fitted_c','#c77f2b')]:
            rr=sorted([r for r in d['rows'] if r['case']==case and r['line']==line and r['arm']==arm],key=lambda r:r['fraction']);assert len(rr)==11
            ordinary=rr[-1] if line=='graph_to_ordinary_native' else rr[0];origin=ordinary['actual_fit_loss']
            for r in rr:
                assert r['phase_change_s']<=.01
                rows.append(dict(case=case,line=line,arm=arm,fraction=r['fraction'],east_km=r['position_east_north_km'][0],north_km=r['position_east_north_km'][1],
                    actual_full_mask_fit_loss=r['actual_fit_loss'],delta_loss_vs_ordinary_native=r['actual_fit_loss']-origin,
                    phase_update_s=r['phase_change_s'],minimum_gate_slack=r['minimum_gate_slack'],failing_gate_count=len(r['failing_gates']),
                    failing_gates=json.dumps(r['failing_gates'],sort_keys=True),posthoc=True,fixed_full_native_mask=True))
            xx=[r['fraction'] for r in rr];delta=[r['actual_fit_loss']-origin for r in rr];slacks=[r['minimum_gate_slack'] for r in rr]
            axes[0,col].plot(xx,delta,'-o',ms=3,color=color,label=arm)
            axes[1,col].plot(xx,slacks,'-o',ms=3,color=color,label=arm)
            bad=[i for i,r in enumerate(rr) if r['failing_gates']]
            axes[0,col].scatter([xx[i] for i in bad],[delta[i] for i in bad],marker='x',s=60,color='#cc3333')
            axes[1,col].scatter([xx[i] for i in bad],[slacks[i] for i in bad],marker='x',s=60,color='#cc3333')
            summaries.append(dict(case=case,line=line,arm=arm,start_loss=rr[0]['actual_fit_loss'],end_loss=rr[-1]['actual_fit_loss'],end_minus_start_loss=rr[-1]['actual_fit_loss']-rr[0]['actual_fit_loss'],start_minimum_gate_slack=rr[0]['minimum_gate_slack'],end_minimum_gate_slack=rr[-1]['minimum_gate_slack']))
        for row in range(2):
            axes[row,col].set(title=case+'\n'+line.replace('_',' '),xlabel='Fraction along frozen RF-endpoint line');axes[row,col].axhline(0,c='black',lw=.7);axes[row,col].legend(fontsize=8)
        axes[0,col].set_ylabel('Actual full-mask fit loss − ordinary-native loss')
        axes[1,col].set_ylabel('Minimum RF gate slack (negative fails)')
    fig.suptitle('Posthoc endpoint interpolation on identical full-native evidence · five phase refreshes per position\nRed crosses: RF gate violation; not a preregistered guard, global search, or adoption rule; no GPS')
    fig.savefig(ROOT/'figures/common_full_mask_lines.png',dpi=180);plt.close(fig)
    table('common_full_mask_lines',rows);table('common_full_mask_line_endpoints',summaries)
    return path,summaries

def main():
    protocol,jobs,inputs=load();fits,paths,residuals,flags,blocks=assemble(protocol,jobs);baseline,extra=baselines();inputs+=extra
    assert len(fits)==32
    summary=[]
    for case in ['DS23-0259','DS23-0353']:
        for mode in ['native_only','whole_family']:
            rr=[r for r in fits if r['case']==case and r['mode']==mode]
            summary.append(dict(case=case,mode=mode,arm_fits=len(rr),training_gate_passes=sum(r['training_gates_pass'] for r in rr),paired_diagnostic_flags=sum(r['case']==case and r['mode']==mode and r['paired_diagnostic_flag'] for r in flags),
                min_error_km=min(r['error_km'] for r in rr),max_error_km=max(r['error_km'] for r in rr),min_Q_per_n=min(r['quadratic_per_point'] for r in rr),max_Q_per_n=max(r['quadratic_per_point'] for r in rr)))
    for name,data in [('held_fit_results',fits),('baseline_endpoints',baseline),('paired_diagnostic_flags',flags),('path_means',paths),('held_residuals',residuals),('local_GN_nuisance_response',blocks),('summary',summary)]:table(name,data)
    plots(fits,paths,residuals,baseline)
    curvature_path,curvature_rows=curvature();inputs.append(curvature_path)
    lines_path,line_summaries=common_mask_lines();inputs.append(lines_path)
    failures=[dict(case=d['job']['case'],family=d['job']['family'],mode=d['job']['mode'],arm=arm,gate=gate,slack=slack) for d in jobs.values() for arm,f in d['arms'].items() for gate,slack in f['gate_slacks'].items() if slack<0];table('training_gate_failures',failures)
    receipt=dict(status='complete_reporting',GPS_reporting_only=True,completed_jobs=16,new_arm_fits=32,threshold=THRESHOLD,chi_square_tail_calibrated=False,
        no_selection_or_adoption=True,summary=summary,paired_flags=flags,admissible_paired_diagnostic_flags=sum(r['paired_diagnostic_flag'] and r['paired_training_gates_pass'] for r in flags),scalar_curvature_contexts=44,posthoc_common_full_mask_line_endpoints=line_summaries,input_hashes={str(p):sha(p) for p in inputs},
        notes=['native_only excludes ALL family predictive entries, including original graph-parent entries, while retaining family curved calibration.',
            'whole_family additionally withholds all original retained family curved observations. Discovery, aliases, identities and learned prior policy remain conditioned on original data; no independent crossvalidation claim.',
            'Errors use GPS only in this reporting process. Frequency-fit changes, predictive diagnostics and location accuracy are separate outcomes.',
            'Local GN sensitivity is not scalar objective curvature, calibrated position covariance or evidence against weak degeneracy.',
            '0353 prior constrained final may have low error although ordinary full native fails training gates; retained graph controls are explicit.'])
    (ROOT/'reporting/receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    findings=['# Family-held-out reporting findings','',
        'All16 jobs completed (32 c-arm fits). No diagnostic selects or adopts a new endpoint. GPS enters this reporting process only. Family discovery, labels, aliases and learned prior policy remain frozen from the original evidence, so these position holdouts are not independent crossvalidation.',
        '', '0259 ordinary full-native errors are3.5621/3.4213km (c0/fitted-c), versus graph-parent0.8634/0.9515km. Holding65340 native entries out reduces error to1.5018/1.4134km; holding its whole family out gives1.5449/1.4322km. For67618, native-only errors are1.8509/1.9169km and whole-family1.8484/1.8946km. All0259 training fits pass gates, and no family meets the paired diagnostic-tail flag. This supports family sensitivity without demonstrating a statistically calibrated inconsistency or a wrong identity.',
        '', '0353 previous constrained-policy errors are0.5789/0.5366km. Ordinary full-native errors are2.2844/2.2935km, with the fitted-c arm failing training gates, so the control benefit belongs to the constrained policy rather than an unconstrained native fit. Paired diagnostic flags occur for63201 in both holdout modes and62233 native-only; all flagged jobs fail paired training qualification. There is no admissible paired prediction flag and no guard can be adopted from this result. Their tails remain uncalibrated diagnostics, not valid rejection probabilities or adoption criteria.',
        '', 'Native-only removes ALL predictive entries of the family, including original parent entries; whole-family additionally removes retained curved calibration points. For0353/62233 this means96 native observations, not merely37 newly discovered points;62843 holds86 native observations, not merely34 new points. The CSVs retain both counts.',
        '', 'The predeclared flag is p<0.01/8 in BOTH arms. Schur-complement covariance retains shared calibration correlations. Chi-square tails assume an empirical Gaussian approximation with frozen discovery/labels and therefore are not calibrated frequentist probabilities. Large whole-family predictive covariance can lower Q/n; that is not evidence of better localization.',
        '', 'Actual scalar-objective Hessians supplement Gauss–Newton residual sensitivity. At full fitted-c endpoints,0259 eigenvalues are approximately0.7175/1.186, versus0353 approximately3.814/5.173:0259 is broader in both local directions, rather than having one nearly singular axis. Neither Hessian nor GN condition is calibrated position uncertainty.0353 constrained prior-final has a substantial ordinary-objective gradient and need not be an ordinary minimum. Local quadratic contours are extrapolated approximations, not measured global basins or confidence regions.',
        '', 'Path means localize conditional RF discrepancies without identifying their cause. In0259 native-only fits,65340 RX1/low-band paths001 and005 have means of roughly382–599Hz but prediction SDs449–525Hz; no path mean exceeds1.31 in magnitude relative to its marginal SD. In0353 native-only fits,62233 RX1/high path024 has mean685/811Hz with SD330/332Hz, while61635 RX1/high path023 is negative. Whole-family63201 shows coherent positive means across RX2/low and RX1/high native paths (approximately6.0–6.1kHz, about5 marginal SDs), but its training fit is invalid. These are correlated, discovery-conditioned diagnostics rather than independent receiver evidence.',
        '', 'For0259 whole-family fitted-c predictions,65340 native means span about−843 to+53Hz with SDs2352–3140Hz; its original RX2/CH2 curve mean is about−847±3378Hz.67618 native mean is about−33±1536Hz and its curved mean about−211±1781Hz. Both influential families have only low-band support;67618 is only RX1/CH4. Such large withheld-family mean uncertainty makes nonflagging weak evidence rather than proof of consistency. The joint Q accounts for relative patterns, but family means remain poorly constrained. This support cannot separate receiver from band faults and does not justify broad prior relaxation.',
        '', 'Posthoc common-mask endpoint lines use identical full-native evidence and refresh phase nuisance five times at each fixed RF position. The0259 graph-to-native line prefers the worse-localizing ordinary endpoint in RF fit loss; the0353 ordinary-to-constrained line trades higher RF loss for gate qualification and better reported accuracy. These endpoint-conditioned sensitivity lines were added after the preregistered family diagnostics and cannot be presented as a preregistered guard or a regional/global search.',
        '', 'Tables include every fit, baseline, diagnostic flag, per-path mean, per-observation residual, training failure, local GN nuisance response and scalar curvature at0.02/0.05km finite differences. Figures mark invalid training fits with hatching; path-mean SD bars are marginal prediction scales rather than calibrated confidence intervals.',
        '', '![Held positions and predictive Q](../figures/held_positions_and_predictive_q.png)','', '![Path means](../figures/path_means_receiver_band.png)','', '![Scalar curvature](../figures/baseline_scalar_curvature.png)','', '![Common-mask endpoint lines](../figures/common_full_mask_lines.png)','']
    (ROOT/'reporting/FINDINGS.md').write_text('\n'.join(findings))
    print(json.dumps(dict(summary=summary,paired_flags=[r for r in flags if r['paired_diagnostic_flag']])))

if __name__=='__main__':main()
