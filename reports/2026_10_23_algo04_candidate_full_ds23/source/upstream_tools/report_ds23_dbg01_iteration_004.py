"""Report the closed worst-two batch and bounded orphan-mixture experiments."""

from pathlib import Path
import shutil
import tarfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import run_ds23_dbg01_iteration_004 as runner
import report_ds23_dbg01_iteration_001 as figures
import report_ds23_dbg01_iteration_002 as curves
from report_ds23_dbg01_iteration_003 import result_row
from probe_ds23_reentry_family_cavity import audit_baseline
from run_algo01_ds23_sample import ROOT,read,write,sha

RAW=runner.RAW
OUT=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_004'


def graph_policy(data,initial,support):
    candidates=[(initial['selected'],'default')] if initial['selected'] else []
    if support['selected']:candidates.append((support['selected'],'support'))
    return max(candidates,key=lambda r:r[0]['added_curved_points']) if candidates else (None,'default')


def residual_and_coverage(data,trial,kind):
    dd,arms=curves.baseline_or_trial(data,trial)
    if trial is None:return dd,arms,read(RAW/data['scan'].case/'inventory.json')['arms']
    coverage={}
    for arm,saved in arms.items():
        if kind=='support':
            p=runner.engine.support.build(data,trial['node'],np.asarray(trial['mask'],bool),arm,
                saved['phase_reference'],np.asarray(trial['means']))
            from evaluate_ds23_phase_refreshed import extend_associations
            from audit_ds23_algo01_coverage import retained_metrics
            from dbg01_unassociated import ownership
            extended=extend_associations(p,np.asarray(saved['endpoint_east_north_km']),retained_metrics(p,np.asarray(saved['endpoint_east_north_km'])))
            lookup={t['key']:t for t in data['scan'].tracks}
            rows=[dict(r,observation_ids=r.get('observation_ids',lookup[r['component']]['observation_ids'])) for r in extended['tracks']]
            ids=ownership(rows)
            coverage[arm]=dict(total_GLRT=len(data['observations']),associated=len(ids),percent=100*len(ids)/len(data['observations']),
                associated_tracks=sum(r['compatible'] for r in rows),accepted_observation_ids=sorted(ids),
                active_curved_points=int(np.asarray(trial['mask']).sum()),predictive_points=sum(e['points'] for e in data['entries']),associations=extended)
        else:coverage[arm]=runner.engine.baseline.inventory(dict(dd,arms=arms),arm)
    return dd,arms,coverage


def overview(rows,ceilings):
    fig,axes=plt.subplots(1,3,figsize=(15,5),layout='constrained');cases=list(ceilings)
    for k,case in enumerate(cases):
        for j,label in enumerate(['Published incumbent','RF-qualified graph policy']):
            r=next(r for r in rows if r['case']==case and r['method']==label and r['arm']=='fitted_c');x=k+(j-.5)*.25
            axes[0].bar(x,r['associated_percent'],width=.23,color=['tab:blue','tab:orange'][j],label=label if k==0 else None)
            axes[1].bar(x,r['position_error_km'],width=.23,color=['tab:blue','tab:orange'][j])
            axes[0].text(x,r['associated_percent']+1,f"{r['associated_percent']:.2f}",ha='center',fontsize=8)
            axes[1].text(x,r['position_error_km']+.07,f"{r['position_error_km']:.3f}",ha='center',fontsize=8)
        axes[2].bar(k,ceilings[case]['percent'],color='0.6')
        axes[2].text(k,ceilings[case]['percent']+1,f"{ceilings[case]['percent']:.2f}%",ha='center')
    axes[0].axhline(90,c='crimson',ls='--');axes[2].axhline(90,c='crimson',ls='--');axes[1].axhline(.5,c='green',ls='--')
    axes[0].set(ylabel='Original GLRT associated (%)',ylim=(0,100));axes[0].legend(fontsize=8)
    axes[1].set(ylabel='Position error (km)');axes[2].set(ylabel='Maximum coverage using current graph (%)',ylim=(0,100))
    for ax in axes:ax.set_xticks(range(len(cases)),cases);ax.grid(axis='y',alpha=.2)
    fig.suptitle('DBG01 iteration 004 · fitted c · conditional graph repairs; full-DS23 reference unchanged')
    fig.savefig(OUT/'figures/iteration_summary.png',dpi=160);plt.close(fig)


def mixture_figures(cases):
    records=[]
    for c in cases:
        for folder,method in [('orphan_mixture','Prior draws,1024'),('orphan_adaptive','EM importance,1024'),
                              ('orphan_adaptive/refinement16384','EM importance,16384')]:
            for p in sorted((RAW/folder).glob(c+'*qualification.json')):
                d=read(p)
                rows=d['rows'] if 'rows' in d else [d]
                for r in rows:
                    records.append(dict(case=c,method=method,arm=r['arm'],bias_sigma_hz=r['bias_sigma_hz'],
                        loss_mean=float(np.mean([v['relative_negative_twice_log_likelihood'] for v in r['trials']])),
                        seed_loss_difference=r['seed_loss_difference'],minimum_ESS=min(v['effective_nuisance_draws'] for v in r['trials']),
                        qualified=r.get('qualified',r.get('qualified_for_position_fit'))))
    fig,axes=plt.subplots(2,2,figsize=(14,9),layout='constrained')
    for k,c in enumerate(cases):
        for col,(metric,label) in enumerate([('minimum_ESS','Minimum effective nuisance draws'),('seed_loss_difference','Independent-seed loss difference')]):
            for j,method in enumerate(['Prior draws,1024','EM importance,1024','EM importance,16384']):
                a=[r for r in records if r['case']==c and r['method']==method]
                axes[k,col].scatter(np.arange(len(a))+(j-1)*.13,[r[metric] for r in a],label=method,s=40)
            axes[k,col].set_xticks(range(4),['c0 / bias0','c0 / bias300','fitted / bias0','fitted / bias300'])
            axes[k,col].set(title=c,ylabel=label,yscale='log');axes[k,col].grid(alpha=.2)
            axes[k,col].axhline(32 if col==0 else .5,c='crimson',ls='--')
    axes[0,0].legend(fontsize=8)
    fig.suptitle('All orphan points: model unchanged, numerical integration refined\n'
                 '32 minimum ESS and0.5 maximum seed difference; only0221/bias0 qualifies both c arms')
    fig.savefig(OUT/'figures/orphan_integration_qualification.png',dpi=160);plt.close(fig)
    case='DS23-0221';root=RAW/'orphan_adaptive/regional_position'/case
    nodes=[read(p) for p in root.glob('level4_point*.json')]
    coarse=[read(p) for p in root.glob('level0_point*.json')]
    fig,axes=plt.subplots(2,2,figsize=(13,11),layout='constrained')
    for col,arm in enumerate(['c0','fitted_c']):
        for row,source in enumerate([coarse,nodes]):
            ax=axes[row,col];points=np.array([v['point'] for v in source]);loss=np.array([v['arms'][arm]['combined_negative_twice_objective'] for v in source]);loss-=loss.min()
            scatter=ax.scatter(points[:,0],points[:,1],c=loss,cmap='viridis',s=85 if row==0 else 110)
            fig.colorbar(scatter,ax=ax,label='Approximate combined RF cost minus sampled minimum')
            if row==1:
                invalid=[v for v in source if not v['paired_integration_qualified']]
                ax.scatter([v['point'][0] for v in invalid],[v['point'][1] for v in invalid],c='crimson',marker='x',s=60,label='Fails joint c-arm integration checks')
                ax.legend(fontsize=7)
            ax.set(title=arm+(' · exploratory1024 draws' if row==0 else ' · final16384 draws'),xlabel='East from regional center (km)',ylabel='North from regional center (km)');ax.grid(alpha=.2)
    fig.suptitle('0221 direct-point composite diagnostic · no validated new minimum\n'
                 'All9 proposed fine-grid nodes fail numerical checks; the only eligible points are the original RF endpoints')
    fig.savefig(OUT/'figures/orphan_regional_search.png',dpi=160);plt.close(fig)
    # Confidence in signal versus clutter is not a satellite identity or an
    # accepted track. Keep these points distinct from hard GLRT association.
    d=runner.engine.current_setup(case)
    from ds23_orphan_predictive_mixture import orphan_rows
    observations=orphan_rows(d)
    joint=read(RAW/'orphan_adaptive/joint_linear_control'/(case+'_fitted_c_incumbent.json'))
    probabilities=np.mean([t['point_signal_probabilities'] for t in joint['trials']],axis=0)
    fig,axes=plt.subplots(2,4,figsize=(16,8),layout='constrained')
    for rx in [1,2]:
        for ch in range(1,5):
            ax=axes[rx-1,ch-1];all_rows=[o for o in d['observations'] if (o['receiver'],o['channel'])==(rx,ch)]
            ax.scatter([o['time_s'] for o in all_rows],[o['measured_cfo_hz']/1000 for o in all_rows],c='0.85',s=7)
            selected=[i for i,o in enumerate(observations) if (o['receiver'],o['channel'])==(rx,ch)]
            scatter=ax.scatter([observations[i]['time_s'] for i in selected],[observations[i]['measured_cfo_hz']/1000 for i in selected],c=probabilities[selected],cmap='viridis',vmin=0,vmax=1,s=15)
            ax.set(title=f'RX{rx} CH{ch}',xlabel='Device time (s)',ylabel='Raw GLRT CFO (kHz)');ax.grid(alpha=.2)
    fig.colorbar(scatter,ax=axes.ravel().tolist(),label='Conditional probability of signal versus clutter')
    fig.suptitle('0221 · original orphan winning GLRT only · proper joint old-linear/orphan covariance\n'
                 'Gray=all original GLRT; probability is not satellite identity confidence or a new hard association')
    fig.savefig(OUT/'figures/orphan_signal_probabilities.png',dpi=155);plt.close(fig)
    write(OUT/'evidence/orphan_signal_summary.json',dict(points=len(observations),
        expected_signal_points=float(probabilities.sum()),points_signal_probability_at_least99=int(sum(probabilities>=.99)),
        hard_satellite_associations_claimed=0,proper_joint_control_only_at_fixed_incumbent_RF_endpoint=True))
    return records


def owner_confirmation():
    root=RAW/'owner_only_confirmation19'
    assert read(root/'execution.json')['all_passed']
    assert read(root/'execution.json')['RF_selection_sealed_before_geographic_scoring']
    cases=read(root/'protocol.json')['cases'];rows=[]
    for case in cases:
        d=runner.engine.current_setup(case);original=read(runner.PRIOR/case/'inventory.json')['arms']
        repair=read(root/(case+'.json'))
        _,arms,coverage=residual_and_coverage(d,repair['selected'],'support') if repair['selected'] else (d,d['arms'],original)
        for method,pair,cov in [('Published incumbent',d['arms'],original),('Owner-only repair',arms,coverage)]:
            for arm,r in pair.items():rows.append(result_row(case,method,arm,r,cov[arm],original[arm]))
    summaries=[]
    for arm in ['c0','fitted_c']:
        for method in ['Published incumbent','Owner-only repair']:
            a=[r for r in rows if r['arm']==arm and r['method']==method]
            errors=np.array([r['position_error_km'] for r in a]);total=sum(r['all_GLRT'] for r in a);associated=sum(r['associated_points'] for r in a)
            summaries.append(dict(method=method,arm=arm,cases=len(a),mean_error_km=float(np.mean(errors)),
                median_error_km=float(np.median(errors)),p90_error_km=float(np.quantile(errors,.9)),
                associated_points=associated,total_GLRT=total,associated_percent=100*associated/total,
                mean_frequency_RMS_hz=float(np.mean([r['RMS_hz'] for r in a]))))
    fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained')
    for method,color in [('Published incumbent','tab:blue'),('Owner-only repair','tab:orange')]:
        a=[next(r for r in rows if r['case']==c and r['method']==method and r['arm']=='fitted_c') for c in sorted(cases)]
        axes[0].plot(range(19),[r['position_error_km'] for r in a],'.-',c=color,label=method)
        axes[1].scatter([r['associated_percent'] for r in a],[r['position_error_km'] for r in a],s=25,c=color,label=method)
    axes[0].set_xticks(range(19),[c.replace('DS23-','') for c in sorted(cases)],rotation=70)
    axes[0].set(ylabel='Position error (km)',xlabel='Confirmation scan');axes[0].legend(fontsize=8)
    axes[1].set(ylabel='Position error (km)',xlabel='Original GLRT associated (%)')
    for ax in axes:ax.axhline(.5,c='gray',ls='--');ax.grid(alpha=.2)
    fig.suptitle('Owner-only rejection repair ·19 confirmation scans · fitted c\n'
                 '0322 development excluded; no already-valid broad-growth proposal offered; exact fallback otherwise')
    fig.savefig(OUT/'figures/owner_confirmation19.png',dpi=160);plt.close(fig)
    figures.csv_write(OUT/'tables/owner_confirmation_positions.csv',rows)
    figures.csv_write(OUT/'tables/owner_confirmation_summary.csv',summaries)
    write(OUT/'evidence/owner_confirmation_evaluation.json',dict(rows=rows,summary=summaries,
        RF_selection_sealed_before_geographic_scoring=True,development0322_excluded=True,no_new_location_generalization=True))
    for r in summaries:print('Owner19 summary',r,flush=True)
    for c in cases:
        a=[r for r in rows if r['case']==c and r['arm']=='fitted_c']
        if a[0]['associated_points']!=a[1]['associated_points']:print('Owner19 changed',c,a[0]['position_error_km'],a[1]['position_error_km'],a[1]['associated_points']-a[0]['associated_points'],flush=True)


def support_figure():
    from report_algo02_ds23 import position_error
    case='DS23-0322';initial=read(RAW/'single_curve_reentry'/(case+'_positions.json'))
    rejected=next(t for t in initial['trials'] if t['added_curved_points']==26)
    repaired=read(RAW/'support_aware_reentry'/(case+'_audited.json'))['selected']
    prior=read(runner.PRIOR/'all_curve_families'/(case+'_positions.json'))['selected']
    records=[('Incumbent',dict(arms=initial['baseline_arms'],paired_valid=True)),
             ('26 points; all nominees',rejected),('26 points; active owners',repaired),('64 points; two owners',prior)]
    fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained');rows=[]
    for k,(label,record) in enumerate(records):
        for offset,arm,color in [(-.1,'c0','tab:blue'),(.1,'fitted_c','tab:orange')]:
            r=record['arms'][arm];error=position_error(r['endpoint_latlon'])
            axes[0].scatter(k+offset,error,c=color,marker='o' if record['paired_valid'] else 'x',s=55,
                            label=arm if k==0 else None)
            axes[1].scatter(k+offset,r['RMS_hz'],c=color,marker='o' if record['paired_valid'] else 'x',s=55)
            rows.append(dict(method=label,arm=arm,paired_valid=record['paired_valid'],error_km=error,RMS_hz=r['RMS_hz']))
    for ax in axes:ax.set_xticks(range(4),[r[0] for r in records],rotation=15,fontsize=8);ax.grid(axis='y',alpha=.2)
    axes[0].set(ylabel='Position error (km)');axes[0].legend(fontsize=8);axes[1].set(ylabel='Curved calibration RMS (Hz)')
    fig.suptitle('0322 · mode-support repair versus a larger shared-family union\n'
                 '26-point default passes frequency/alias/horizon checks but fails two-owner support; 64-point fit passes yet worsens position')
    fig.savefig(OUT/'figures/DS23-0322_support_and_union.png',dpi=160);plt.close(fig)
    figures.csv_write(OUT/'tables/support_and_union.csv',rows)


def feasible_bank_figure():
    from report_algo02_ds23 import position_error
    fig,axes=plt.subplots(2,2,figsize=(13,9),layout='constrained');rows=[]
    for k,case in enumerate(read(RAW/'protocol.json')['cases']):
        record=read(RAW/'feasible_bank_control'/(case+'.json'))
        for t in record['trials']:
            index=t['bank_index'];gain=record['incumbent_corrected_loss']-t['arms']['c0']['corrected_selection_loss']
            axes[k,0].bar(index,gain,color='tab:blue' if t['paired_valid'] else 'crimson')
            for offset,arm,color in [(-.1,'c0','tab:blue'),(.1,'fitted_c','tab:orange')]:
                error=position_error(t['arms'][arm]['endpoint_latlon'])
                axes[k,1].scatter(index+offset,error,c=color,marker='o' if t['paired_valid'] else 'x',s=50)
                rows.append(dict(case=case,index=index,arm=arm,paired_valid=t['paired_valid'],
                    constrained_rescue=t['constrained_refinement_attempted'],position_error_km=error,c0_RF_gain=gain))
        axes[k,0].axhline(record['penalty'],c='gray',ls='--',label='Declared bank penalty')
        axes[k,0].set(title=case,ylabel='Corrected c0 RF gain versus incumbent',xlabel='Existing bank branch');axes[k,0].legend(fontsize=8)
        axes[k,1].set(title=case+' · blue c0, orange fitted c',ylabel='Position error (km)',xlabel='Existing bank branch')
        for ax in axes[k]:ax.set_xticks(range(len(record['trials'])));ax.grid(alpha=.2)
    fig.suptitle('Existing-bank feasibility control · same observations, identities and priors\n'
                 '0322 branch3 needs constrained rescue; gain1.171<2.773, so the valid incumbent remains')
    fig.savefig(OUT/'figures/feasible_bank_control.png',dpi=160);plt.close(fig)
    figures.csv_write(OUT/'tables/feasible_bank_control.csv',rows)


def main():
    runner.configure();curves.RAW=RAW;curves.OUT=OUT
    figures.OUT,figures.RAW=OUT,RAW;figures.REENTRY=RAW/'single_curve_reentry';figures.SUPPORT=RAW/'support_aware_reentry'
    figures.setup=runner.engine.current_setup
    for part in ['figures','tables','evidence','source/tools','source/tests']:(OUT/part).mkdir(parents=True,exist_ok=True)
    assert read(RAW/'independent_iteration_audit.json')['all_passed']
    assert read(RAW/'orphan_adaptive/joint_linear_control/execution.json')['all_passed']
    rows=[];families=[];controls=[];residuals=[];diagnostics=[];ceilings={};reuse=[]
    for case in read(RAW/'protocol.json')['cases']:
        data=runner.engine.current_setup(case);original=read(RAW/case/'inventory.json')['arms']
        initial=read(RAW/'single_curve_reentry'/(case+'_positions.json'));support=read(RAW/'support_aware_reentry'/(case+'_audited.json'))
        selected,kind=graph_policy(data,initial,support);dd,arms,coverage=residual_and_coverage(data,selected,kind)
        n=original['fitted_c']['total_GLRT'];g=n-original['fitted_c']['outside_graph_points']
        ceilings[case]=dict(points=g,percent=100*g/n,minimum_outside_graph_for90=int(np.ceil(.9*n))-g)
        for label,pair,cov,prefix in [('Published incumbent',data['arms'],original,'published'),('RF-qualified graph policy',arms,coverage,'graph_policy')]:
            for arm,fit in pair.items():rows.append(result_row(case,label,arm,fit,cov[arm],original[arm]))
            for associated in [True,False]:figures.glrt_figure(data,cov['fitted_c'],prefix,associated)
        controls.extend(dict(case=case,**r) for r in figures.current_dbg_figures(case));families.extend(figures.family_rows(case,data))
        residuals.extend(figures.residual_figures(case,data,dict(baseline_arms=data['arms'],policy_arms=arms,selected=selected),None))
        diagnostics.extend(curves.candidate_diagnostics(case,data))
        build=runner.engine.baseline.build
        if kind=='support':
            runner.engine.baseline.build=lambda changed,arm,reference:runner.engine.support.build(data,changed['node'],changed['keep'],arm,reference,changed['means'])
        try:curves.recovered_curves(case,data,selected)
        finally:runner.engine.baseline.build=build
        if case=='DS23-0322':
            source=runner.PRIOR/'all_curve_families'/(case+'_positions.json');prior=read(source)['selected']
            checkdata=dict(data,node=prior['node'],keep=np.asarray(prior['mask'],bool),entries=prior['entries'],means=np.asarray(prior['means']))
            checks=[audit_baseline(checkdata,a,r) for a,r in prior['arms'].items()]
            _,prior_arms,prior_coverage=residual_and_coverage(data,prior,'default')
            for arm,fit in prior_arms.items():rows.append(result_row(case,'Previously rejected64-point growth',arm,fit,prior_coverage[arm],original[arm]))
            reuse.append(dict(case=case,source=str(source),sha256=sha(source),checks=checks,no_position_refit=True))
    overview(rows,ceilings)
    for name,records in [('position_and_association',rows),('family_ablations',families),('all_interventions',controls),
        ('residual_diagnostics',residuals),('following_TLE_profiles',diagnostics),('orphan_integration',mixture_figures(list(ceilings)))]:
        figures.csv_write(OUT/'tables'/(name+'.csv'),records)
    owner_confirmation();support_figure();feasible_bank_figure()
    write(OUT/'evidence/evaluation.json',dict(rows=rows,graph_ceilings=ceilings,no_full_DS23_gain_or_ALGO_promotion=True,
        no_orphan_driven_position_adopted=True,original_causal_inputs_and_no_GPS_inference=True))
    write(OUT/'evidence/reused0322_group_audit.json',reuse)
    with tarfile.open(OUT/'evidence/raw_scientific_receipts.tar.gz','w:gz') as archive:
        for p in sorted(RAW.rglob('*')):
            if p.is_file() and p.suffix in ['.json','.csv','.py']:archive.add(p,arcname=str(p.relative_to(RAW)),recursive=False)
    tools=['run_ds23_dbg01_iteration_004.py','run_ds23_dbg01_iteration_002.py','ds23_current_assignment_context.py',
        'ds23_orphan_predictive_mixture.py','probe_ds23_orphan_mixture.py','ds23_orphan_adaptive_importance.py',
        'probe_ds23_orphan_adaptive.py','refine_ds23_orphan_importance.py','probe_ds23_orphan_position.py',
        'ds23_orphan_joint_predictive.py','control_ds23_orphan_joint.py','confirm_ds23_owner_only_reentry.py',
        'control_ds23_dbg01_feasible_bank.py',Path(__file__).name]
    for name in tools:shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    for name in ['test_ds23_dbg01_iteration_004.py','test_ds23_orphan_predictive_mixture.py','test_ds23_orphan_adaptive_importance.py',
                 'test_ds23_orphan_position.py','test_ds23_orphan_joint_predictive.py','test_ds23_owner_only_reentry.py',
                 'test_ds23_feasible_bank_control.py']:
        shutil.copyfile(ROOT/'tests/analysis'/name,OUT/'source/tests'/name)
    print('Iteration004 figures/tables generated',flush=True)


if __name__=='__main__':main()
