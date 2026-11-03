"""Frozen013 report: shared-step/support composition and constrained prediction."""

from pathlib import Path
import shutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import probe_ds23_iteration013_existing_recovery as binding
import probe_ds23_iteration013_supported_step as step
import report_ds23_dbg01_iteration_011 as common
import report_ds23_dbg01_iteration_001 as figures
import report_ds23_dbg01_iteration_004 as graph
import report_ds23_dbg01_iteration_007 as diagnostics
import report_ds23_dbg01_iteration_008 as paths_report
import report_ds23_dbg01_iteration_009 as restarts
from report_ds23_dbg01_iteration_005 import result_row
from evaluate_ds23_iteration010_short_confirmation import reported_fit
from plot_ds23_worst_association_bottleneck import raw_track_values
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import ROOT,read,write,sha

runner=binding.runner;paths=binding.paths.paths
RAW=runner.RAW;OUT=ROOT/'reports/2026_10_23_ds23_dbg01_iteration_013'


def save(fig,name):
    fig.savefig(OUT/'figures'/name,dpi=145);plt.close(fig)


def temporal(case,d,cov):
    old=read(RAW/'graph_seeded_paths'/(case+'.json'))['methods']['persistent5s'];new=read(RAW/'temporal_feasibility'/(case+'.json'))
    t=new if new['accepted'] else old if old.get('accepted') else None
    if t is None:return d,cov
    selected=t.get('selected_paths') or read(RAW/'graph_seeded_paths'/(case+'_persistent5s_selection.json'))['selected']
    scan,entries=paths.native.append_native_paths(d['scan'],d['entries'],selected,paths.native.receiver_basis(d['scan']))
    return dict(d,scan=scan,entries=entries,arms=t['arms']),t['coverage']


def event_policy(case,d,cov):
    record=read(step.OUT/(case+'.json'));t=record['selected']
    if t is None:return d,cov,t
    index=next(i for i,v in enumerate(record['trials']) if v['kind']==t['kind'] and v['additions']==t['additions'])
    audit=next(r for r in read(RAW/'recovery_endpoint_audit.json')['memberships'] if r['case']==case and r['variant']=='support')
    coverage=audit['trials'][index]['coverage'];changed=dict(d,node=t['node'],keep=np.asarray(t['mask'],bool),means=np.asarray(t['means']),entries=t['entries'],arms=t['arms'])
    return changed,coverage,t


def overview(rows,ceilings):
    methods=['Incumbent','Graph recovery','Temporal policy','Supported shared step'];fig,axes=plt.subplots(1,3,figsize=(17,5),layout='constrained')
    for k,case in enumerate(ceilings):
        for j,m in enumerate(methods):
            r=next(r for r in rows if r['case']==case and r['arm']=='fitted_c' and r['method']==m);x=k+(j-1.5)*.18
            axes[0].bar(x,r['associated_percent'],width=.17,color=f'C{j}',label=m if k==0 else None)
            axes[1].bar(x,r['position_error_km'],width=.17,color=f'C{j}');axes[1].text(x,r['position_error_km']+.05,f"{r['position_error_km']:.3f}",ha='center',fontsize=7)
        axes[2].bar(k,ceilings[case]['percent'],color='gray');axes[2].text(k,ceilings[case]['percent']+1,f"{ceilings[case]['percent']:.2f}%",ha='center')
    axes[0].set(ylabel='Original GLRT associated (%)',ylim=(0,100));axes[0].legend(fontsize=7,loc='lower left');axes[0].axhline(90,c='crimson',ls='--')
    axes[1].set(ylabel='Position error (km)');axes[1].axhline(.5,c='green',ls='--');axes[2].set(ylabel='Original graph-only ceiling (%)',ylim=(0,100));axes[2].axhline(90,c='crimson',ls='--')
    for ax in axes:ax.set_xticks(range(2),list(ceilings));ax.grid(axis='y',alpha=.2)
    fig.suptitle('Iteration013 · fitted c · separate bounded policies, graph fallback where no step qualifies\n0064 temporal uses original gate-constrained refinement; no full-DS23 or ALGO release claim')
    save(fig,'iteration_summary.png')


def historical_timeout_context():
    root=ROOT/'reports/2026_10_22_ds23_reentry_family_cavity/full_DS23';rows=[];receipts=[]
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,case in zip(axes,read(RAW/'protocol.json')['cases'],strict=True):
        source=root/'reentry'/(case+'.json');record=read(source);final_source=root/'position'/(case+'.json');final=read(final_source)
        passing=[t for t in record['trials'] if t['paired_valid'] and all(v['final_phase_change_s']<=.01 for v in t['arms'].values())]
        if record['status']!='budget_exhausted' or not passing:raise ValueError('historical timeout context differs from inspected source')
        # This is historical context only, not a geography-ranked selection:
        # both cases have exactly one completed passing candidate.
        if len(passing)!=1:raise ValueError('do not select a historical candidate by geography')
        trial=passing[0]
        for arm,r in trial['arms'].items():rows.append(dict(case=case,arm=arm,added_curved_points=trial['group']['added_points'],partial_candidate_error_km=position_error(r['endpoint_latlon']),
            returned_policy_error_km=position_error(final['policy_arms'][arm]['endpoint_latlon']),phase_change_s=r['final_phase_change_s'],
            saved_paired_gates_pass=True,search_status=record['status'],receiver_basis='historical fine basis',not_current_controlled_ablation=True))
        ax.bar([0,1],[position_error(final['policy_arms']['fitted_c']['endpoint_latlon']),position_error(trial['arms']['fitted_c']['endpoint_latlon'])],color=['C0','gray'])
        ax.set(xticks=[0,1],xticklabels=['Historical returned policy','Completed partial candidate'],ylabel='Fitted-c position error (km)',title=case);ax.grid(axis='y',alpha=.2)
        receipts.append(dict(case=case,source=str(source),source_sha256=sha(source),status=record['status'],error=record['error'],seconds=record['seconds'],
            completed_trials=len(record['trials']),passing_completed_trial=trial,returned_source=str(final_source),returned_source_sha256=sha(final_source),
            historical_model_masks_and_search_differ_no_new_fit_or_adoption=True))
    fig.suptitle('Existing full-run timeout evidence reused · no new fit or algorithm selection\nCompleted valid candidates were discarded when a later candidate exceeded the400s search budget')
    save(fig,'historical_timeout_completed_candidates.png');figures.csv_write(OUT/'tables/historical_timeout_context.csv',rows)
    write(OUT/'evidence/historical_timeout_context.json',dict(rows=receipts,no_GPS_selection_or_new_model_fit=True,full_population_anytime_rescue_not_tested=True))


def step_figures(case,d):
    target=read(RAW/'step_transfer_diagnostic'/(case+'.json'))['targets']
    if not target:return []
    t0=target[0];tau=t0['time_s'];controls=t0['independent_original_parent_curves'];record=read(step.OUT/(case+'.json'));chosen=record['selected'];rows=[]
    fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained')
    axes[0].plot(t0['times'],t0['residual_hz'],'.-',label='Proposed67992 source: default single fit');axes[0].axvline(tau,c='crimson',ls='--',label=f'RF split{tau:.3f}s')
    for r in controls:axes[0].plot(r['times'],r['residual_hz'],'.-',label=f"Original parent {r['norad']} CH{r['channel']}")
    axes[0].set(xlabel='Scan time (s)',ylabel='Causal model residual (Hz)');axes[0].legend(fontsize=7)
    labels=['Target before−after sign reversed']+[str(r['norad'])+' CH'+str(r['channel']) for r in controls]
    values=[-t0['mean_difference_hz']]+[r['amplitude_hz'] for r in controls];axes[1].bar(range(len(values)),values,color=['C0']+['C1']*len(controls));axes[1].axhline(0,c='gray');axes[1].set(xticks=range(len(labels)),xticklabels=labels,ylabel='After-minus-before step amplitude (Hz)')
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle(case+' · shared-step diagnostic before new event fits\nOne other original-parent family supports the sign; affine removal is diagnostic and does not calibrate linear sources')
    save(fig,case+'_step_transfer.png')
    fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained')
    for folder,label,offset in [('shared_step','Default support',-.17),('supported_shared_step','Active-owner support',.17)]:
        for k,t in enumerate(read(RAW/folder/(case+'.json'))['trials']):
            for arm,r in t['arms'].items():rows.append(dict(case=case,base=label,kind=t['kind'],points=t['added_curved_points'],arm=arm,paired_valid=t['paired_valid'],accepted=t['accepted'],RF_gain=t['gains'][arm],penalty=t['search_penalty'],event_amplitude_hz=r['event_amplitudes_hz'][0],error_km=position_error(r['endpoint_latlon']),RMS_hz=r['RMS_hz']))
            axes[0].bar(k+offset,t['gains']['fitted_c'],width=.32,color='C0' if offset<0 else 'C1',label=label if k==0 else None)
            axes[1].scatter(k+offset,position_error(t['arms']['fitted_c']['endpoint_latlon']),marker='o' if t['paired_valid'] else 'x',s=70,c='C0' if offset<0 else 'C1')
    names=[t['kind']+' '+str(t['added_curved_points'])+'pts' for t in record['trials']]
    axes[0].axhline(record['trials'][0]['search_penalty'],c='gray',ls='--',label='Time/model search penalty');axes[0].set(ylabel='Matched-null RF gain, fitted c');axes[0].legend(fontsize=7);axes[1].set(ylabel='Position error (km); X fails paired gates')
    for ax in axes:ax.set_xticks(range(len(names)),names,rotation=20);ax.grid(alpha=.2)
    fig.suptitle(case+' · support-aware composition preserves the two-owner gate by removing unsupported orbital modes\nSame masks, original event prior300Hz and fixed RF split; RF gains compared only to their own matched null')
    save(fig,case+'_step_model_comparison.png')
    null=next(t for t in record['nulls'] if t['additions']==chosen['additions']);models=[('Support-aware matched null',null['arms'],[]),('Shared receiver step',chosen['arms'],chosen['events'])]
    byid={o['observation_id']:o for o in d['observations']};fig,axes=plt.subplots(len(chosen['additions']),2,figsize=(15,4*len(chosen['additions'])),squeeze=False,layout='constrained');details=[]
    for label,arms,event_list in models:
        saved=arms['fitted_c'];p=step.build(d,chosen,'fitted_c',saved['phase_reference'],event_list);c=p.calculate(np.asarray(saved['endpoint_east_north_km']))
        for k,addition in enumerate(chosen['additions']):
            track=next(t for t in d['scan'].tracks if t['key']==addition['component']);times,raw=raw_track_values(track,range(len(track['times'])),byid);sl=next(s for r,s in zip(p.rows,p.slices,strict=True) if r['component']==track['key']);residual=c['conditional_residual_hz'][sl]
            if label==models[0][0]:axes[k,0].scatter(times,raw/1000,c='black',s=14,label='Original winning GLRT')
            for j,run in enumerate(np.split(np.arange(len(times)),np.flatnonzero((abs(np.diff(raw-track['values']))>1e-5)|(np.diff(times)>10))+1)):
                axes[k,0].plot(times[run],(raw-residual)[run]/1000,label=label if j==0 else None,marker='.' if len(run)==1 else None)
            axes[k,1].plot(times,residual,'.-',label=label);axes[k,1].axhline(0,c='gray');axes[k,0].set(title=track['key'].split('-RF')[0]+f" · {addition['norad']}",ylabel='Native CFO (kHz)');axes[k,1].set(ylabel='Conditional residual (Hz)')
            for ax in axes[k]:ax.axvline(tau,c='crimson',ls='--');ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2);ax.legend(fontsize=7)
            details.append(dict(component=track['key'],model=label,times=times,native_CFO_hz=raw,residual_hz=residual))
    fig.suptitle(case+' · same111 original observations · causal orbit + radio/fragment nuisance prediction\nEvent shared by RX1 across channels; no point trimming or independent per-track jump')
    save(fig,case+'_event_CFO_and_residuals.png');write(OUT/'evidence/step_residual_series.json',details);return rows


def main():
    binding.configure('paths');graph.RAW=RAW
    for f in ['figures','tables','evidence','source/tools','source/tests']:(OUT/f).mkdir(parents=True,exist_ok=True)
    for module in [figures,common,diagnostics,paths_report,restarts]:module.RAW=RAW;module.OUT=OUT
    figures.setup=runner.engine.current_setup
    assert read(RAW/'batch_execution.json')['all_passed'];assert read(RAW/'independent_iteration_audit.json')['all_passed'];assert read(RAW/'recovery_endpoint_audit.json')['all_passed'];assert read(RAW/'step_null_audit.json')['all_passed']
    cases=read(RAW/'protocol.json')['cases'];rows=[];trials=[];gates=[];controls=[];families=[];residuals=[];following=[];path_rows=[];rounds=[];step_rows=[];ceilings={}
    for case in cases:
        original=runner.engine.current_setup(case);initial=read(RAW/case/'inventory.json')['arms'];d,cov,kind,selected=paths.parent(case)
        for a,s in original['arms'].items():original['arms'][a]=reported_fit(runner.engine.baseline.build(original,a,s['phase_reference']),s)
        td,tcov=temporal(case,d,cov);ed,ecov,event=event_policy(case,original,initial)
        if event is None:ed,ecov=d,cov
        n=initial['fitted_c']['total_GLRT'];g=n-initial['fitted_c']['outside_graph_points'];ceilings[case]=dict(total_GLRT=n,graph_points=g,percent=100*g/n,minimum_outside_for90=max(0,int(np.ceil(.9*n))-g))
        for name,data,coverage in [('Incumbent',original,initial),('Graph recovery',d,cov),('Temporal policy',td,tcov),('Supported shared step',ed,ecov)]:
            for arm,r in data['arms'].items():rows.append(result_row(case,name,arm,r,coverage[arm],initial[arm]))
            for associated in [True,False]:figures.glrt_figure(data,coverage['fitted_c'],name.lower().replace(' ','_'),associated)
        controls.extend(dict(case=case,**r) for r in figures.current_dbg_figures(case));rounds.extend(restarts.restart_figure(case));families.extend(figures.family_rows(case,original))
        residuals.extend(figures.residual_figures(case,original,dict(baseline_arms=original['arms'],policy_arms=d['arms'],selected=selected),None));following.extend(diagnostics.track_diagnostics(case,original));path_rows.extend(paths_report.path_figures(case,d,kind));step_rows.extend(step_figures(case,original))
        collections=[('Default graph',read(RAW/'single_curve_reentry'/(case+'_positions.json'))['trials']),('Support graph',read(RAW/'support_aware_reentry'/(case+'.json'))['trials']),('Extra curve',read(RAW/'point_rich_extra_curve'/(case+'.json'))['trials'])]
        collections.extend((m,[v]) for m,v in read(RAW/'graph_seeded_paths'/(case+'.json'))['methods'].items() if 'arms' in v)
        constrained=read(RAW/'temporal_feasibility'/(case+'.json'))
        if 'arms' in constrained:collections.append(('Constrained temporal',[constrained]))
        for folder in ['shared_step','supported_shared_step']:collections.append((folder,read(RAW/folder/(case+'.json'))['trials']))
        for label,tt in collections:
            for i,t in enumerate(tt):
                gates.extend(common.gate_rows(case,label+':'+str(i),t))
                for arm,r in t['arms'].items():trials.append(dict(case=case,method=label,trial=i,arm=arm,paired_valid=t['paired_valid'],accepted=t.get('accepted',t['paired_valid']),new_curved_points=t.get('added_curved_points',0),new_predictive_points=t.get('new_points',0),position_error_km=position_error(r['endpoint_latlon']),RMS_hz=r['RMS_hz'],final_phase_change_s=r['final_phase_change_s']))
    overview(rows,ceilings);historical_timeout_context()
    for name,data in [('position_and_association',rows),('prototype_trials',trials),('all_curved_gates',gates),('family_ablations',families),('all_interventions',controls),('residual_diagnostics',residuals),('following_TLE_profiles',following),('temporal_paths',path_rows),('restart_phase_rounds',rounds),('shared_step_models',step_rows)]:
        if data:figures.csv_write(OUT/'tables'/(name+'.csv'),data)
    write(OUT/'evidence/evaluation.json',dict(rows=rows,trials=trials,graph_ceilings=ceilings,no_full_DS23_or_new_location_validation=True,new_ALGO_release=False))
    common.archive(cases);common.gallery()
    for name in ['protocol.json','batch_execution.json','independent_iteration_audit.json','RF_restart_selection.json','recovery_endpoint_audit.json','step_null_audit.json']:shutil.copyfile(RAW/name,OUT/'evidence'/name)
    names=['run_ds23_dbg01_iteration_013.py','probe_ds23_iteration013_existing_recovery.py','probe_ds23_iteration013_feasibility.py','probe_ds23_iteration013_extra_curve.py','diagnose_ds23_iteration013_step_transfer.py','probe_ds23_iteration013_shared_step.py','probe_ds23_iteration013_supported_step.py','ds23_frequency_events.py','audit_ds23_iteration013_recovery.py','audit_ds23_iteration013_step_nulls.py',Path(__file__).name]
    for name in names:shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    tests=['test_ds23_dbg01_iteration_013.py','test_ds23_iteration013_existing_recovery.py','test_ds23_iteration013_feasibility.py','test_ds23_iteration013_extra_curve.py','test_ds23_iteration013_step_transfer.py','test_ds23_iteration013_shared_step.py','test_ds23_frequency_events.py']
    for name in tests:shutil.copyfile(ROOT/'tests/analysis'/name,OUT/'source/tests'/name)
    write(OUT/'evidence/source_hashes.json',{str(p.relative_to(OUT)):sha(p) for p in (OUT/'source').rglob('*.py')});print('013 report assets',len(list((OUT/'figures').glob('*.png'))),'figures',flush=True)


if __name__=='__main__':main()
