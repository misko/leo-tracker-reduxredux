"""Publishable evidence for bounded DBG01 iteration005; geography is report-only."""

from pathlib import Path
import shutil
import tarfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import run_ds23_dbg01_iteration_005 as runner
import report_ds23_dbg01_iteration_001 as figures
import report_ds23_dbg01_iteration_002 as curves
import report_ds23_dbg01_iteration_004 as previous
import probe_ds23_temporal_predictive_recovery as temporal
import refine_ds23_temporal_predictive_recovery as screened
from report_ds23_dbg01_iteration_003 import result_row as original_result_row
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import ROOT,read,write,sha

RAW=runner.RAW
OUT=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_005'


def result_row(case,method,arm,fit,inventory,original):
    row=original_result_row(case,method,arm,fit,inventory,original)
    maximum=float(np.max(abs(np.asarray(fit['state']['phases']))))
    row.update(maximum_absolute_phase_s=maximum,strict15s_phase_limit_pass=maximum<=15.000001,
        phase_refresh_converged=fit['final_phase_change_s']<=.01)
    return row


def overview(rows,ceilings):
    methods=['Published incumbent','RF-qualified graph policy','Screened independent predictive','Screened temporal predictive']
    fig,axes=plt.subplots(1,3,figsize=(17,5),layout='constrained')
    for k,case in enumerate(ceilings):
        for j,method in enumerate(methods):
            r=next(r for r in rows if r['case']==case and r['method']==method and r['arm']=='fitted_c');x=k+(j-1.5)*.19
            for ax,value in [(axes[0],r['associated_percent']),(axes[1],r['position_error_km'])]:
                ax.bar(x,value,width=.18,color=f'C{j}',label=method if k==0 else None)
                ax.text(x,value+.07,f'{value:.2f}',ha='center',fontsize=7)
        axes[2].bar(k,ceilings[case]['percent'],color='0.6')
        axes[2].text(k,ceilings[case]['percent']+1,f"{ceilings[case]['percent']:.2f}%",ha='center')
    axes[0].axhline(90,c='crimson',ls='--');axes[2].axhline(90,c='crimson',ls='--');axes[1].axhline(.5,c='green',ls='--')
    axes[0].set(ylabel='Original winning GLRT associated (%)',ylim=(0,100));axes[0].legend(fontsize=7)
    axes[1].set(ylabel='Position error (km)');axes[2].set(ylabel='Maximum coverage within original graph (%)',ylim=(0,100))
    for ax in axes:ax.set_xticks(range(len(ceilings)),list(ceilings));ax.grid(axis='y',alpha=.2)
    fig.suptitle('Iteration005 · fitted c · separate frozen proposals; archived baseline fallback when checks fail\n0068 inherited baseline exceeds15s phase gate; no new ALGO release or combined graph/temporal claim')
    fig.savefig(OUT/'figures/iteration_summary.png',dpi=160);plt.close(fig)


def temporal_figures(case,data):
    discovery=read(temporal.OUT/(case+'_discovery.json'));positions=read(temporal.OUT/(case+'_positions.json'))
    lane_rows=[];path_rows=[];trials=[]
    fig,axes=plt.subplots(1,2,figsize=(15,5),layout='constrained')
    for col,(method,proposal) in enumerate(discovery['methods'].items()):
        for k,lane in enumerate(proposal['lanes']):
            controls=lane['permutation_log_ratios'];axes[col].plot([k,k],[min(controls),max(controls)],c='0.7',lw=4)
            axes[col].scatter(k,lane['native_log_ratio'],c='tab:blue' if lane['passed'] else 'crimson',s=32)
            axes[col].scatter(k,lane['threshold'],c='black',marker='_',s=70)
            lane_rows.append(dict(case=case,method=method,receiver=lane['lane'][0],channel=lane['lane'][1],
                RF_hz=lane['lane'][2],points=lane['points'],native_log_ratio=lane['native_log_ratio'],
                maximum_permutation_log_ratio=max(controls),threshold=lane['threshold'],passed=lane['passed']))
        axes[col].set(title=method,xlabel='Physical RX/channel/actual RF lane',ylabel='Discovery log likelihood versus clutter')
        axes[col].grid(alpha=.2)
        chosen={f['key'] for f in proposal['selected']}
        for path in proposal['paths']:
            for arm,check in path['checks'].items():
                path_rows.append(dict(case=case,method=method,arm=arm,path=path['fragment']['key'],
                    norad=path['fragment']['norad'],points=path['points'],span_s=path['span_s'],
                    nominal_class_probability=float(check['probabilities'][check['best_local_index']+1]),
                    gain_vs_clutter=check['gain_vs_clutter'],marginal_SD_hz=check['maximum_marginal_SD_hz'],
                    lane_pass=path['lane_coherence_passed'],passed=path['passed'],selected=path['fragment']['key'] in chosen))
        result=positions['methods'][method]
        if 'arms' not in result:continue
        for arm,saved in result['arms'].items():
            trials.append(dict(case=case,method=method,arm=arm,accepted=result['accepted'],paired_valid=result['paired_valid'],
                IDs_preserved=result['incumbent_IDs_preserved'][arm],position_error_km=position_error(saved['endpoint_latlon']),
                RMS_hz=saved['RMS_hz'],new_paths=result['new_paths'],new_points=result['new_points'],
                final_phase_change_s=saved['final_phase_change_s'],
                all_new_predictive_gates_pass=all(r['compatible'] for r in saved['linear_gates'][len(data['entries']):])))
        # Every offered original path, including those causing final rejection.
        scan,entries=temporal.temporal.append_fragments(data['scan'],data['entries'],proposal['selected'])
        saved=result['arms']['fitted_c'];p=runner.engine.baseline.build(dict(data,scan=scan,entries=entries),'fitted_c',saved['phase_reference'])
        residual=p.calculate(np.asarray(saved['endpoint_east_north_km']))['linear_raw_prediction_residual_hz']
        by_id={o['observation_id']:o for o in data['observations']}
        for page,start in enumerate(range(0,len(proposal['selected']),6),1):
            subset=proposal['selected'][start:start+6];panel,axs=plt.subplots(len(subset),2,figsize=(14,3*len(subset)),squeeze=False,layout='constrained')
            for row,fragment in enumerate(subset):
                j=len(data['entries'])+start+row;sl=p.linear_slices[j];r=residual[sl];times=np.asarray(fragment['times'])
                raw=np.array([by_id[o]['measured_cfo_hz'] for o in fragment['observation_ids']]);bias=float(np.mean(r))
                axs[row,0].scatter(times,raw/1000,s=14,c='black',label='Original winning GLRT')
                for run in np.split(np.arange(len(times)),np.flatnonzero((abs(np.diff(raw))>temporal.temporal.PERIOD/2)|(np.diff(times)>10))+1):
                    if len(run):axs[row,0].plot(times[run],(raw-r+bias)[run]/1000,c='tab:blue')
                axs[row,1].plot(times,r-bias,'.-',c='tab:blue');axs[row,1].axhline(0,c='black',lw=.7)
                gate=saved['linear_gates'][j]
                axs[row,0].set(title=f"RX{fragment['receiver']} CH{fragment['channel']} · {fragment['norad']} · {len(times)} points",ylabel='Raw CFO (kHz)')
                axs[row,1].set(title=f"Predictive gate {'passes' if gate['compatible'] else 'fails'} · trial {'accepted' if result['accepted'] else 'rejected'}",ylabel='Mean-centered prediction residual (Hz)')
                for ax in axs[row]:ax.set_xlabel('Device time (s)');ax.grid(alpha=.2)
            panel.suptitle(f'{case} · {method} · every offered path, page{page}\nOrbit + unchanged curved radio calibration + descriptive path mean; no path trimmed after fit')
            panel.savefig(OUT/'figures'/f'{case}_{method}_predictive_paths_{page}.png',dpi=145);plt.close(panel)
    fig.suptitle(case+' · temporal proposal control\nGray=range of19 CFO/time permutations; black=maximum +2log20; permutations are a coherence diagnostic')
    fig.savefig(OUT/'figures'/(case+'_temporal_coherence.png'),dpi=160);plt.close(fig)
    return lane_rows,path_rows,trials


def main():
    runner.configure();curves.RAW=RAW;curves.OUT=OUT;previous.RAW=RAW
    figures.OUT,figures.RAW=OUT,RAW;figures.REENTRY=RAW/'single_curve_reentry';figures.SUPPORT=RAW/'support_aware_reentry'
    figures.setup=runner.engine.current_setup
    for part in ['figures','tables','evidence','source/tools','source/tests']:(OUT/part).mkdir(parents=True,exist_ok=True)
    assert read(RAW/'independent_iteration_audit.json')['all_passed']
    assert read(temporal.OUT/'positions_execution.json')['all_terminal']
    assert read(screened.OUT/'execution.json')['all_terminal']
    rows=[];families=[];controls=[];residuals=[];diagnostics=[];ceilings={};lane_rows=[];paths=[];trials=[]
    for case in read(RAW/'protocol.json')['cases']:
        data=runner.engine.current_setup(case);original=read(RAW/case/'inventory.json')['arms']
        initial=read(RAW/'single_curve_reentry'/(case+'_positions.json'));support=read(RAW/'support_aware_reentry'/(case+'_audited.json'))
        selected,kind=previous.graph_policy(data,initial,support)
        dd,arms,cov=previous.residual_and_coverage(data,selected,kind)
        n=original['fitted_c']['total_GLRT'];g=n-original['fitted_c']['outside_graph_points']
        ceilings[case]=dict(points=g,percent=100*g/n,minimum_outside_graph_for90=max(0,int(np.ceil(.9*n))-g))
        for label,pair,coverage,prefix in [('Published incumbent',data['arms'],original,'published'),('RF-qualified graph policy',arms,cov,'graph_policy')]:
            for arm,fit in pair.items():rows.append(result_row(case,label,arm,fit,coverage[arm],original[arm]))
            for associated in [True,False]:figures.glrt_figure(data,coverage['fitted_c'],prefix,associated)
        temporal_result=read(temporal.OUT/(case+'_positions.json'))
        for method,label in [('independent','Independent predictive policy'),('persistent5s','Temporal predictive policy')]:
            trial=temporal_result['methods'][method];accepted=trial['accepted']
            pair=trial['arms'] if accepted else data['arms'];coverage=trial['coverage'] if accepted else original
            for arm,fit in pair.items():rows.append(result_row(case,label,arm,fit,coverage[arm],original[arm]))
        whole=read(screened.OUT/(case+'.json'))
        for method,label in [('independent','Screened independent predictive'),('persistent5s','Screened temporal predictive')]:
            trial=whole['methods'][method];accepted=trial['accepted']
            pair=trial['arms'] if accepted else data['arms'];coverage=trial['coverage'] if accepted else original
            for arm,fit in pair.items():rows.append(result_row(case,label,arm,fit,coverage[arm],original[arm]))
            plotdata=data;plotcoverage=coverage['fitted_c']
            if accepted:
                fragments=read(screened.OUT/(case+'_'+method+'_selection.json'))['selected']
                scan,_=temporal.temporal.append_fragments(data['scan'],data['entries'],fragments)
                plotdata=dict(data,scan=scan)
                plotcoverage=dict(plotcoverage,associations=dict(tracks=plotcoverage['associations']['tracks']+plotcoverage['new_paths']))
            for associated in [True,False]:figures.glrt_figure(plotdata,plotcoverage,'screened_'+method,associated)
            if 'arms' in trial:
                for arm,saved in trial['arms'].items():
                    trials.append(dict(case=case,method='screened_'+method,arm=arm,accepted=trial['accepted'],paired_valid=trial['paired_valid'],
                        IDs_preserved=trial['incumbent_IDs_preserved'][arm],position_error_km=position_error(saved['endpoint_latlon']),
                        RMS_hz=saved['RMS_hz'],new_paths=trial['new_paths'],new_points=trial['new_points'],
                        final_phase_change_s=saved['final_phase_change_s'],
                        all_new_predictive_gates_pass=all(r['compatible'] for r in saved['linear_gates'][len(data['entries']):])))
        controls.extend(dict(case=case,**r) for r in figures.current_dbg_figures(case));families.extend(figures.family_rows(case,data))
        residuals.extend(figures.residual_figures(case,data,dict(baseline_arms=data['arms'],policy_arms=arms,selected=selected),None))
        diagnostics.extend(curves.candidate_diagnostics(case,data))
        build=runner.engine.baseline.build
        if kind=='support':runner.engine.baseline.build=lambda changed,arm,reference:runner.engine.support.build(data,changed['node'],changed['keep'],arm,reference,changed['means'])
        try:curves.recovered_curves(case,data,selected)
        finally:runner.engine.baseline.build=build
        a,b,c=temporal_figures(case,data);lane_rows.extend(a);paths.extend(b);trials.extend(c)
    overview(rows,ceilings)
    for name,records in [('position_and_association',rows),('family_ablations',families),('all_interventions',controls),
        ('residual_diagnostics',residuals),('following_TLE_profiles',diagnostics),('temporal_lanes',lane_rows),
        ('temporal_paths',paths),('temporal_position_trials',trials)]:
        if records:figures.csv_write(OUT/'tables'/(name+'.csv'),records)
    write(OUT/'evidence/evaluation.json',dict(rows=rows,graph_ceilings=ceilings,temporal_trials=trials,
        no_full_DS23_gain_or_ALGO_promotion=True,original_causal_inputs_and_no_GPS_inference=True))
    with tarfile.open(OUT/'evidence/raw_scientific_receipts.tar.gz','w:gz') as archive:
        for p in sorted(RAW.rglob('*')):
            if p.is_file() and p.suffix in ['.json','.csv','.py']:archive.add(p,arcname=str(p.relative_to(RAW)),recursive=False)
    tools=['run_ds23_dbg01_iteration_005.py','run_ds23_dbg01_iteration_002.py','ds23_current_assignment_context.py',
        'ds23_temporal_predictive_recovery.py','probe_ds23_temporal_predictive_recovery.py',
        'refine_ds23_temporal_predictive_recovery.py','prepare_ds23_dbg01_following.py',
        'diagnose_ds23_iteration002_curves.py',Path(__file__).name]
    for name in tools:shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    for name in ['test_ds23_dbg01_iteration_005.py','test_ds23_temporal_predictive_recovery.py']:
        shutil.copyfile(ROOT/'tests/analysis'/name,OUT/'source/tests'/name)
    print('Iteration005 figures and tables generated',flush=True)


if __name__=='__main__':main()
