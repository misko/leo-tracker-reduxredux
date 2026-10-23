"""Render sealed012 evidence; no geographic selection or new position fits."""

from pathlib import Path
import shutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import probe_ds23_iteration012_curve_recovery as binding
import report_ds23_dbg01_iteration_011 as common
import report_ds23_dbg01_iteration_010 as short_report
import report_ds23_dbg01_iteration_001 as figures
import report_ds23_dbg01_iteration_007 as diagnostics
import report_ds23_dbg01_iteration_008 as paths_report
import report_ds23_dbg01_iteration_009 as restart_report
from evaluate_ds23_iteration010_short_confirmation import reported_fit
from report_ds23_dbg01_iteration_005 import result_row
from ds23_receiver_curve_consistency import shared_shape
from ds23_supported_curvature import curvature_evidence
from plot_ds23_worst_association_bottleneck import raw_track_values
from run_algo01_ds23_sample import ROOT,read,write,sha
from report_algo02_ds23 import position_error
import probe_ds23_new_family_prediction as new_model
import evaluate_ds23_new_family_prediction as new_evaluation
from ds23_new_family_prediction import new_gates
from ds23_frequency_events import make_event_problem
from audit_ds23_family_cavity import density

runner=binding.binding.runner
paths=binding.binding.paths.paths
RAW=runner.RAW
OUT=ROOT/'reports/2026_10_23_ds23_dbg01_iteration_012'


def save(fig,name):
    fig.savefig(OUT/'figures'/name,dpi=145);plt.close(fig)


def core_view(case,d,cov,kind):
    record=read(binding.OUT/(case+'.json'));t=next((r for r in record['trials'] if r['method']=='core_curved' and r['accepted']),None)
    if t is None:return d,cov,t
    p=paths.build(d,kind,'c0',d['arms']['c0']['phase_reference'])
    changed,_,_=binding.core.curved_core_view(d,p,t['offer']['fragment'],t['offer']['source_index'])
    return dict(changed,arms=t['arms']),t['coverage'],t


def overview(rows,ceilings):
    methods=['Incumbent','Graph recovery','Persistent temporal','Whole short curves','Source core'];fig,axes=plt.subplots(1,3,figsize=(18,5),layout='constrained')
    for k,case in enumerate(ceilings):
        for j,m in enumerate(methods):
            r=next(r for r in rows if r['case']==case and r['arm']=='fitted_c' and r['method']==m);x=k+(j-2)*.15
            axes[0].bar(x,r['associated_percent'],width=.145,color=f'C{j}',label=m if k==0 else None)
            axes[1].bar(x,r['position_error_km'],width=.145,color=f'C{j}');axes[1].text(x,r['position_error_km']+.04,f"{r['position_error_km']:.3f}",rotation=45,ha='center',fontsize=7)
        axes[2].bar(k,ceilings[case]['percent'],color='gray');axes[2].text(k,ceilings[case]['percent']+1,f"{ceilings[case]['percent']:.2f}%",ha='center')
    axes[0].set(ylabel='Original GLRT associated (%)',ylim=(0,100));axes[0].axhline(90,c='crimson',ls='--');axes[0].legend(fontsize=7,loc='lower left')
    axes[1].set(ylabel='Position error (km)',ylim=(0,3.7));axes[1].axhline(.5,c='green',ls='--')
    axes[2].set(ylabel='Original graph-only ceiling (%)',ylim=(0,100));axes[2].axhline(90,c='crimson',ls='--')
    for ax in axes:ax.set_xticks(range(2),list(ceilings));ax.grid(axis='y',alpha=.2)
    fig.suptitle('Iteration012 · bounded same-site development · fitted c\nSeparate policies, graph fallback when no core. No new full-DS23 or ALGO-series accuracy claim')
    save(fig,'iteration_summary.png')


def source_diagnostics(d,kind):
    case=d['scan'].case;byid={o['observation_id']:o for o in d['observations']};saved=d['arms']['fitted_c'];x=np.asarray(saved['endpoint_east_north_km']);p=paths.build(d,kind,'fitted_c',saved['phase_reference']);c=p.calculate(x)
    fig,axes=plt.subplots(2,3,figsize=(18,9),layout='constrained');evidence=[];table=[]
    chosen=read(RAW/'graph_seeded_paths'/(case+'_persistent5s_selection.json'))['selected']
    for row,(index,norad,alias) in enumerate([(25,66582,0),(35,66525,1)]):
        t=d['scan'].tracks[index];times,raw=raw_track_values(t,range(len(t['times'])),byid);candidate=next(j for j,n in enumerate(d['scan'].norads) if int(n)==norad)
        entry=dict(track_index=index,candidate_index=candidate,alias=alias)
        view,values,*_=paths.linear_geometry(p,[entry]);geometry=paths.geometry_features(view,x,0.);prediction=view.q*geometry['intercept']+geometry['features']@c['coefficient'];residual=values-prediction
        ids=set().union(*(set(f['observation_ids']) for f in chosen if f['norad']==norad));use=np.array([oid in ids for oid in t['observation_ids']]);core=dict(t,times=t['times'][use],values=t['values'][use]);q=curvature_evidence(core)
        z=(times-times.mean())/np.ptp(times);degree=t['pieces'][0]['degree'];u=np.polynomial.legendre.legvander(z,degree);leverage=np.sum(u*np.linalg.pinv(u).T,axis=1)
        axes[row,0].scatter(times[use],raw[use]/1000,c='C2',label='Original IDs retained by frozen persistent path')
        axes[row,0].scatter(times[~use],raw[~use]/1000,c='crimson',marker='x',s=70,label='Original IDs not selected by that path')
        for k,run in enumerate(np.split(np.arange(len(times)),np.flatnonzero((abs(np.diff(raw-np.asarray(t['values'])))>1e-5)|(np.diff(times)>10))+1)):
            axes[row,0].plot(times[run],(raw-residual)[run]/1000,c='C0',marker='.' if len(run)==1 else None,label=f'Causal {norad} + fixed graph-parent radio' if k==0 else None)
        for k,(grid,y) in enumerate(figures.polynomial_segments(t,range(len(times)),byid)):axes[row,0].plot(grid,y/1000,c='gray',ls='--',label='Persisted graph polynomial' if k==0 else None)
        axes[row,0].set(title=t['key'].split('-RF')[0],ylabel='Native CFO (kHz)')
        axes[row,1].plot(times,residual,'.-',c='C0');axes[row,1].scatter(times[~use],residual[~use],c='crimson',marker='x',s=70);axes[row,1].axhline(0,c='gray');axes[row,1].set(ylabel='Fixed-radio prediction residual (Hz)',title=f"Source-owned core: {int(use.sum())}pts, independently curved={q['qualified']}")
        axes[row,2].stem(times,leverage,basefmt=' ');axes[row,2].axhline(.9,c='crimson',ls='--');axes[row,2].set(ylabel=f'Degree{degree} polynomial leverage',ylim=(0,1.02))
        for ax in axes[row]:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2)
        axes[row,0].legend(fontsize=7)
        evidence.append(dict(component=t['key'],norad=norad,alias=alias,times=times,native_CFO_hz=raw,fixed_parent_residual_hz=residual,
            selected_original_IDs=[oid for oid,v in zip(t['observation_ids'],use,strict=True) if v],leverage=leverage,core_curvature=q,
            no_phase_or_position_refit_or_GPS_used=True))
        table.append(dict(component=t['key'],norad=norad,whole_points=len(times),selected_source_points=int(use.sum()),
            whole_span_s=float(np.ptp(times)),core_span_s=float(np.ptp(times[use])),maximum_leverage=float(max(leverage)),
            core_curvature_qualified=q['qualified'],minimum_core_linear_RMS_hz=q.get('minimum_linear_RMS_hz'),minimum_core_quadratic_BIC_gain=q.get('minimum_quadratic_BIC_gain')))
    fig.suptitle('DS23-0215 · whole-source failure versus independently recovered source IDs\nCH2 early two points remain unused; CH3 isolated endpoint has leverage0.918. Raw prediction uses the frozen causal graph-parent radio')
    save(fig,'DS23-0215_source_endpoints_and_predictions.png');write(OUT/'evidence/source_endpoints.json',evidence)
    pair=shared_shape([d['scan'].tracks[9],d['scan'].tracks[25]],overlap_only=True);write(OUT/'evidence/same_RX_curvature.json',pair)
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for method,fit in pair['best'].items():
        axes[0].scatter(pair['times'],fit['residual_hz'],s=15,label=f"{method} d{fit['degree']}, {fit['RMS_hz']:.1f}Hz")
    for k,method in enumerate(['shared','independent']):axes[1].bar(k,pair['best'][method]['BIC'],color=f'C{k}')
    axes[0].axhline(0,c='gray');axes[0].set(xlabel='Scan time (s)',ylabel='RF-normalized residual (Hz)');axes[0].legend(fontsize=8)
    axes[1].set(xticks=[0,1],xticklabels=['Shared curvature','Independent curvature'],ylabel='BIC (lower better)')
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle(f"0215 RX2 CH1/CH2 actual overlap · BIC(shared) − BIC(independent) = {pair['BIC_shared_minus_independent']:+.2f}\nSeparate affine terms absorb constant/linear differences. Diagnostic only; no GPS/TLE or forced merge")
    save(fig,'DS23-0215_overlap_curvature.png');return table


def single_source_diagnostics():
    rows=[];audits=[];reuse=[];folder=RAW/'single_source_new_family'
    assert read(folder/'execution.json')['all_passed']
    old=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_007_raw/new_family_full_DS23'
    for case in read(RAW/'protocol.json')['cases']:
        # Retain the already completed full-population group experiment as context.
        source=old/case/'result.json';evaluation=old.parent/'new_family_evaluation/cases'/(case+'.json')
        record=read(evaluation);reuse.append(dict(case=case,source=str(source),source_sha256=sha(source),
            evaluation_source=str(evaluation),evaluation_sha256=sha(evaluation),rows=record['rows'],no_new_fit=True))
        d,original,kind,_=paths.parent(case);trial_record=read(folder/(case+'.json'))
        if not trial_record['trials']:continue
        if kind!='default':raise ValueError('report singleton default model must match experiment')
        for method,trial in trial_record['trials'].items():
            for arm,saved in trial['arms'].items():
                p=new_model.build(d,arm,saved['phase_reference'],saved['new_reference'],trial['entries'],trial['physical_modes']);x=np.asarray(saved['endpoint_east_north_km']);c=p.calculate(x)
                delta=c['negative_twice_elbo']-saved['negative_twice_elbo']
                if abs(delta)>1e-5:raise ValueError('single-source objective no longer replays')
                curved=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.asarray(saved['phase_reference']),d['powers'],d['means'],d['model'],[])
                audit=density(d,curved,x,d['means'],[])
                if np.max(abs(curved.calculate(x)['coefficient']-c['coefficient']))>1e-12:raise ValueError('new source changed calibration at fixed position')
                if new_gates(p,x)!=saved['linear_gates'][-len(trial['entries']):]:raise ValueError('new source gates no longer replay')
                cov=new_evaluation.coverage(d,arm,saved,trial['entries']);retained=set(original[arm]['accepted_observation_ids'])<=set(cov['accepted_observation_ids'])
                if not retained:raise ValueError('singleton prediction lost parent membership')
                rows.append(dict(case=case,method=method,arm=arm,accepted=trial['accepted'],associated_points=cov['associated'],associated_percent=cov['percent'],
                    position_error_km=position_error(saved['endpoint_latlon']),new_predictive_points=sum(e['points'] for e in trial['entries']),
                    calibration_points_unchanged=saved['active_points'],all_parent_IDs_preserved=True,new_family_phase_s=saved['new_family_phases_s'][0]))
                audits.append(dict(case=case,method=method,arm=arm,objective_difference=delta,**audit,**saved['audit']))
            if method!='phase_only':continue
            cov=new_evaluation.coverage(d,'fitted_c',saved:=trial['arms']['fitted_c'],trial['entries'])
            for associated in [True,False]:figures.glrt_figure(d,cov,'single_source_new_family',associated)
            p=new_model.build(d,'fitted_c',saved['phase_reference'],saved['new_reference'],trial['entries'],False);c=p.calculate(np.asarray(saved['endpoint_east_north_km']))
            entry=trial['entries'][0];track=d['scan'].tracks[entry['track_index']];times,raw=raw_track_values(track,range(len(track['times'])),{o['observation_id']:o for o in d['observations']});residual=c['new_raw_prediction_residual_hz'][p.new_slices[0]]
            fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained');axes[0].scatter(times,raw/1000,c='black',s=20,label='Original29 GLRT')
            for k,run in enumerate(np.split(np.arange(len(times)),np.flatnonzero((abs(np.diff(raw-track['values']))>1e-5)|(np.diff(times)>10))+1)):
                axes[0].plot(times[run],(raw-residual)[run]/1000,c='C0',marker='.' if len(run)==1 else None,label='Causal60316 + original radio + phase' if k==0 else None)
            axes[1].plot(times,residual,'.-');axes[1].axhline(0,c='gray');axes[0].set(ylabel='Native CFO (kHz)');axes[1].set(ylabel='Fixed-radio prediction residual (Hz)')
            for ax in axes:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2)
            axes[0].legend(fontsize=8);fig.suptitle('0281 RX2 CH2 T002 ·29 points explained as a new predictive family60316\nPassed RF-only proposal and final gates; error worsens3.032→3.171km. No calibration update or ALGO promotion')
            save(fig,'DS23-0281_single_source_prediction.png')
    figures.csv_write(OUT/'tables/single_source_new_family.csv',rows)
    write(OUT/'evidence/single_source_audit.json',dict(rows=audits,all_passed=True,no_new_fit_or_GPS_selection=True))
    write(OUT/'evidence/reused007_new_family_results.json',dict(rows=reuse,all_case_evidence_reused_without_new_fits=True))


def main():
    binding.configure('core')
    for folder in ['figures','tables','evidence','source/tools','source/tests']:(OUT/folder).mkdir(parents=True,exist_ok=True)
    for module in [figures,diagnostics,paths_report,restart_report,short_report,common]:module.RAW=RAW;module.OUT=OUT
    figures.setup=runner.engine.current_setup;short_report.binding=binding.binding.paths
    assert read(RAW/'batch_execution.json')['all_passed'];assert read(RAW/'independent_iteration_audit.json')['all_passed'];assert read(RAW/'recovery_endpoint_audit.json')['all_passed']
    cases=read(RAW/'protocol.json')['cases'];rows=[];trials=[];gates=[];controls=[];families=[];residuals=[];following=[];path_rows=[];short_rows=[];rounds=[];source_rows=[];ceilings={}
    for case in cases:
        original=runner.engine.current_setup(case);initial=read(RAW/case/'inventory.json')['arms'];d,cov,kind,selected=paths.parent(case)
        for a,s in original['arms'].items():original['arms'][a]=reported_fit(runner.engine.baseline.build(original,a,s['phase_reference']),s)
        td,tcov,_=common.temporal_view(case,d,cov,kind,'graph_seeded_paths');sd,scov,skind,_=short_report.short_policy(case,d,cov,kind);cd,ccov,ct=core_view(case,d,cov,kind)
        n=initial['fitted_c']['total_GLRT'];g=n-initial['fitted_c']['outside_graph_points'];ceilings[case]=dict(total_GLRT=n,graph_points=g,percent=100*g/n,minimum_outside_for90=max(0,int(np.ceil(.9*n))-g))
        for label,data,coverage,k in [('Incumbent',original,initial,'default'),('Graph recovery',d,cov,kind),('Persistent temporal',td,tcov,kind),('Whole short curves',sd,scov,skind),('Source core',cd,ccov,kind)]:
            for arm,r in data['arms'].items():rows.append(result_row(case,label,arm,reported_fit(paths.build(data,k,arm,r['phase_reference']),r),coverage[arm],initial[arm]))
            for associated in [True,False]:figures.glrt_figure(data,coverage['fitted_c'],label.lower().replace(' ','_'),associated)
        controls.extend(dict(case=case,**r) for r in figures.current_dbg_figures(case));rounds.extend(restart_report.restart_figure(case));families.extend(figures.family_rows(case,original))
        residuals.extend(figures.residual_figures(case,original,dict(baseline_arms=original['arms'],policy_arms=d['arms'],selected=selected),None))
        following.extend(diagnostics.track_diagnostics(case,original));path_rows.extend(paths_report.path_figures(case,d,kind));short_rows.extend(short_report.short_figures(case,d,kind))
        if case=='DS23-0215':source_rows.extend(source_diagnostics(d,kind))
        collections=[('Default graph',read(RAW/'single_curve_reentry'/(case+'_positions.json'))['trials']),('Support graph',read(RAW/'support_aware_reentry'/(case+'.json'))['trials']),('Whole short',read(RAW/'short_whole_curves'/(case+'.json'))['trials'])]
        collections.extend((m,[v]) for m,v in read(RAW/'graph_seeded_paths'/(case+'.json'))['methods'].items() if 'arms' in v)
        collections.extend((t['method'],[t]) for t in read(binding.OUT/(case+'.json'))['trials'])
        for label,tt in collections:
            for i,t in enumerate(tt):
                gates.extend(common.gate_rows(case,label+':'+str(i),t))
                for arm,r in t['arms'].items():trials.append(dict(case=case,method=label,trial=i,arm=arm,paired_valid=t['paired_valid'],accepted=t.get('accepted',t['paired_valid']),new_curved_points=t.get('added_curved_points',t.get('independent_curved_core_points',0) if label=='core_curved' else 0),new_predictive_points=t.get('new_points',t.get('independent_curved_core_points',0) if label=='core_predictive' else 0),position_error_km=position_error(r['endpoint_latlon']),RMS_hz=r['RMS_hz'],final_phase_change_s=r['final_phase_change_s']))
    overview(rows,ceilings);single_source_diagnostics()
    for name,data in [('position_and_association',rows),('prototype_trials',trials),('all_curved_gates',gates),('family_ablations',families),('all_interventions',controls),('residual_diagnostics',residuals),('following_TLE_profiles',following),('temporal_paths',path_rows),('short_curvature',short_rows),('restart_phase_rounds',rounds),('source_endpoint_diagnostics',source_rows)]:
        if data:figures.csv_write(OUT/'tables'/(name+'.csv'),data)
    write(OUT/'evidence/evaluation.json',dict(rows=rows,trials=trials,graph_ceilings=ceilings,no_full_DS23_or_new_location_claim=True,new_ALGO_release=False))
    common.archive(cases);common.gallery()
    for name in ['protocol.json','batch_execution.json','independent_iteration_audit.json','RF_restart_selection.json','recovery_endpoint_audit.json']:shutil.copyfile(RAW/name,OUT/'evidence'/name)
    names=['run_ds23_dbg01_iteration_012.py','probe_ds23_iteration012_existing_recovery.py','probe_ds23_iteration012_curve_recovery.py','probe_ds23_iteration012_single_family.py','audit_ds23_iteration012_recovery.py',Path(__file__).name]
    for name in names:shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    tests=['test_ds23_dbg01_iteration_012.py','test_ds23_iteration012_existing_recovery.py','test_ds23_iteration012_curve_recovery.py','test_ds23_iteration012_single_family.py','test_ds23_curved_core_view.py','test_ds23_short_whole_curve_view.py','test_ds23_supported_curvature.py']
    for name in tests:shutil.copyfile(ROOT/'tests/analysis'/name,OUT/'source/tests'/name)
    write(OUT/'evidence/source_hashes.json',{str(p.relative_to(OUT)):sha(p) for p in (OUT/'source').rglob('*.py')})
    print('012 report assets:',len(list((OUT/'figures').glob('*.png'))),'figures',flush=True)


if __name__=='__main__':main()
