"""Render frozen014 DBG01, graph recovery, temporal evidence and shared steps."""

from pathlib import Path
import shutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import probe_ds23_iteration014_recovery as binding
import probe_ds23_iteration014_cross_band_step as step
import report_ds23_dbg01_iteration_011 as common
import report_ds23_dbg01_iteration_001 as figures
import report_ds23_dbg01_iteration_004 as graph
import report_ds23_dbg01_iteration_007 as diagnostics
import report_ds23_dbg01_iteration_008 as paths_report
import report_ds23_dbg01_iteration_009 as restarts
from report_ds23_dbg01_iteration_005 import result_row
from evaluate_ds23_iteration010_short_confirmation import reported_fit
from plot_ds23_worst_association_bottleneck import raw_track_values
from run_algo01_ds23_sample import ROOT,read,write,sha
from report_algo02_ds23 import position_error
from ds23_supported_curvature import curvature_evidence

runner=binding.runner;paths=binding.paths.paths
RAW=runner.RAW;OUT=ROOT/'reports/2026_10_23_ds23_dbg01_iteration_014'


def save(fig,name):
    fig.savefig(OUT/'figures'/name,dpi=145);plt.close(fig)


def temporal(case,d,cov):
    t=read(RAW/'graph_seeded_paths'/(case+'.json'))['methods']['persistent5s']
    if not t.get('accepted'):return d,cov
    selected=read(RAW/'graph_seeded_paths'/(case+'_persistent5s_selection.json'))['selected']
    scan,entries=paths.native.append_native_paths(d['scan'],d['entries'],selected,paths.native.receiver_basis(d['scan']))
    return dict(d,scan=scan,entries=entries,arms=t['arms']),t['coverage']


def extra(case,d,fallback,cov):
    record=read(RAW/'point_rich_extra_curve'/(case+'.json'));t=record['selected']
    if t is None:return fallback,cov
    coverage=next(r['coverage'] for r in read(RAW/'recovery_endpoint_audit.json')['memberships'] if r['case']==case and r['kind']=='extra')
    return dict(d,node=t['node'],keep=np.asarray(t['mask'],bool),means=np.asarray(t['means']),entries=t['entries'],arms=t['arms']),coverage


def event(case,d,fallback,cov):
    t=read(step.OUT/(case+'.json'))['selected']
    if t is None:return fallback,cov
    return dict(d,node=t['node'],keep=np.asarray(t['mask'],bool),means=np.asarray(t['means']),entries=t['entries'],arms=t['arms']),t['coverage']


def overview(rows,ceilings):
    methods=['Incumbent','Graph recovery','Persistent temporal','Extra curve','Cross-band shared step'];fig,axes=plt.subplots(1,3,figsize=(18,5),layout='constrained')
    for k,case in enumerate(ceilings):
        for j,m in enumerate(methods):
            r=next(r for r in rows if r['case']==case and r['arm']=='fitted_c' and r['method']==m);x=k+(j-2)*.15
            axes[0].bar(x,r['associated_percent'],width=.145,color=f'C{j}',label=m if k==0 else None)
            axes[1].bar(x,r['position_error_km'],width=.145,color=f'C{j}');axes[1].text(x,r['position_error_km']+.03,f"{r['position_error_km']:.3f}",ha='center',rotation=45,fontsize=7)
        axes[2].bar(k,ceilings[case]['percent'],color='gray');axes[2].text(k,ceilings[case]['percent']+1,f"{ceilings[case]['percent']:.2f}%",ha='center')
    axes[0].set(ylabel='Original GLRT associated (%)',ylim=(0,100));axes[0].axhline(90,c='crimson',ls='--');axes[0].legend(fontsize=7,loc='lower left')
    axes[1].set(ylabel='Position error (km)',ylim=(0,3.5));axes[1].axhline(.5,c='green',ls='--');axes[2].set(ylabel='Original graph-only ceiling (%)',ylim=(0,100));axes[2].axhline(90,c='crimson',ls='--')
    for ax in axes:ax.set_xticks(range(2),list(ceilings));ax.grid(axis='y',alpha=.2)
    fig.suptitle('Iteration014 · fitted c · separate bounded policies, graph fallback where no proposal qualifies\nShared step and extra curve are not composed with temporal recovery; no full-DS23 or ALGO release claim')
    save(fig,'iteration_summary.png')


def step_figures(case,d):
    record=read(step.OUT/(case+'.json'));selected=record['selected']
    if selected is None:return []
    target=read(RAW/'step_transfer_diagnostic'/(case+'.json'))['targets'][0];tau=target['time_s'];controls=step.supporting_curves(target);rows=[]
    fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained')
    axes[0].plot(target['times'],target['residual_hz'],'.-',label=f"Proposed {target['norad']} · CH{target['channel']}")
    for c in controls:axes[0].plot(c['times'],c['residual_hz'],'.-',label=f"Original {c['norad']} · CH{c['channel']}")
    axes[0].axvline(tau,c='crimson',ls='--');axes[0].set(xlabel='Scan time (s)',ylabel='No-event causal-model residual (Hz)');axes[0].legend(fontsize=8)
    axes[1].bar(range(1+len(controls)),[-target['mean_difference_hz']]+[r['amplitude_hz'] for r in controls]);axes[1].axhline(0,c='gray');axes[1].set(xticks=range(1+len(controls)),xticklabels=['New-source CUSUM']+[str(r['norad'])+' other band' for r in controls],ylabel='After-minus-before amplitude (Hz)')
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle(case+f' · original cross-band curved evidence supports a receiver-wide step near {tau:.3f}s\nSame receiver, distinct families. Affine elimination is diagnostic; no linear source calibrates the event')
    save(fig,case+'_cross_band_step_transfer.png')
    fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained')
    for k,t in enumerate(record['trials']):
        for j,arm in enumerate(['c0','fitted_c']):
            axes[0].bar(k+(j-.5)*.3,t['gains'][arm],width=.28,color=f'C{j}',label=arm if k==0 else None)
            s=t['arms'][arm];rows.append(dict(case=case,base=t['model_base'],arm=arm,paired_valid=t['paired_valid'],accepted=t['accepted'],RF_gain=t['gains'][arm],search_penalty=t['search_penalty'],
                event_amplitude_hz=s['event_amplitudes_hz'][0],error_km=position_error(s['endpoint_latlon']),null_error_km=position_error(t['null_arms'][arm]['endpoint_latlon']),RMS_hz=s['RMS_hz']))
            axes[1].scatter(k+(j-.5)*.3,position_error(s['endpoint_latlon']),c=f'C{j}',s=65)
    axes[0].axhline(selected['search_penalty'],c='gray',ls='--',label='Fixed search penalty');axes[0].legend(fontsize=8);axes[0].set(ylabel='RF gain versus identical-mask null');axes[1].set(ylabel='Position error (km)')
    for ax in axes:ax.set_xticks(range(2),['Default base','Existing support base']);ax.grid(alpha=.2)
    fig.suptitle(case+' · original 300Hz event prior, no gate relaxation · both bases reach the same event endpoint\nDefault archived null includes attempted gate refinement; support null is the unconstrained 5×48 control')
    save(fig,case+'_shared_step_models.png')
    component=selected['additions'][0]['component'];track=next(t for t in d['scan'].tracks if t['key']==component);byid={o['observation_id']:o for o in d['observations']};times,raw=raw_track_values(track,range(len(track['times'])),byid)
    null=next(t for t in record['nulls'] if t['model_base']=='support');fig,axes=plt.subplots(1,2,figsize=(15,5),layout='constrained');series=[]
    axes[0].scatter(times,raw/1000,c='black',s=15,label='All original winning GLRT points')
    for name,t in [('Unconstrained same-mask null',null),('Shared receiver step',selected)]:
        p=step.build(d,t,'fitted_c',t['events']);c=p.calculate(np.asarray(t['arms']['fitted_c']['endpoint_east_north_km']));sl=next(s for r,s in zip(p.rows,p.slices,strict=True) if r['component']==component);res=c['conditional_residual_hz'][sl]
        for k,ix in enumerate(np.split(np.arange(len(times)),np.flatnonzero(abs(np.diff(raw-track['values']))>1e-5)+1)):
            axes[0].plot(times[ix],(raw-res)[ix]/1000,label=name if k==0 else None)
        axes[1].plot(times,res,'.-',label=name);series.append(dict(component=component,method=name,times=times,native_CFO_hz=raw,residual_hz=res))
    axes[0].set(ylabel='Native CFO (kHz)');axes[1].axhline(0,c='gray');axes[1].set(ylabel='Conditional residual (Hz)')
    for ax in axes:ax.axvline(tau,c='crimson',ls='--');ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle(case+' · entire 81-point source · causal orbit + radio/fragment nuisance prediction\nNo independent per-track jump, endpoint removal or following TLE in inference')
    save(fig,case+'_event_CFO_and_residuals.png');write(OUT/'evidence/event_residual_series.json',series);return rows


def source_integrity_figures(case):
    result=[]
    for r in read(RAW/'source_integrity'/(case+'.json'))['rows']:
        fig,axes=plt.subplots(1,3,figsize=(18,5),layout='constrained');t=np.asarray(r['times']);y=np.asarray(r['values_hz']);axes[0].scatter(t,y/1000,c='black',s=20,label='All original source observations')
        for piece in r['pieces']:
            grid=np.linspace(piece['start_s'],piece['end_s'],250);v=np.polynomial.legendre.legval((grid-piece['reference_time_s'])/piece['time_scale_s'],piece['coefficients_hz']);axes[0].plot(grid,v/1000,label='Persisted degree4 graph fit')
        for e in r['isolated_endpoints']:
            prediction=np.asarray(e['linear_core_prediction_hz']);use=np.asarray(e['core_indices']);axes[0].plot(t,prediction/1000,'--',label='Diagnostic core linear extrapolation');axes[1].plot(t[use],(y-prediction)[use],'.-')
            axes[1].axhline(0,c='gray');axes[1].set(title=f"20-point core: no distributed active curvature",ylabel='Linear-core residual (Hz)')
            result.append(dict(case=case,component=r['component'],whole_points=len(t),core_points=len(use),gap_s=e['gap_s'],endpoint_leverage=e['leverage'],
                whole_jackknife_curved=r['whole_curvature']['qualified'],core_jackknife_curved=e['core_curvature']['qualified'],
                whole_minimum_linear_RMS_hz=r['whole_curvature']['minimum_linear_RMS_hz'],whole_minimum_quadratic_BIC_gain=r['whole_curvature']['minimum_quadratic_BIC_gain']))
        axes[2].stem(t,r['leverage'],basefmt=' ');axes[2].axhline(.9,c='crimson',ls='--');axes[2].set(ylabel='Persisted-degree polynomial leverage',ylim=(0,1.02))
        axes[0].set(ylabel='Graph-unwrapped CFO (kHz)');axes[0].legend(fontsize=7)
        for ax in axes:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2)
        fig.suptitle(case+' · isolated endpoint creates apparent high-order curvature\nDiagnostic deletions only: no point removed, polynomial rewritten or linear source promoted to calibration')
        save(fig,case+'_isolated_endpoint_false_curvature.png')
    return result


def supplement():
    """Add independently audited late controls without rerendering the DBG01 atlas."""
    binding.configure('paths');step.binding.configure('support');common.RAW=RAW;common.OUT=OUT
    cases=read(RAW/'protocol.json')['cases'];witnesses=[];trial_rows=[];gate_rows=[];nominations=[]
    assert read(RAW/'augmented_family_replacement/independent_replay.json')['all_passed']
    for case in cases:
        original=runner.engine.current_setup(case)
        selected=read(step.OUT/(case+'.json'))['selected']
        if selected is not None:
            target=read(RAW/'step_transfer_diagnostic'/(case+'.json'))['targets'][0]
            for component in [target['component']]+[r['component'] for r in step.supporting_curves(target)]:
                index=next(i for i,t in enumerate(original['scan'].tracks) if t['key']==component);track=original['scan'].tracks[index];k=original['base'].members.index(index);sl=original['base'].slices[k]
                use=np.ones(len(track['times']),bool) if component==target['component'] else original['keep'][sl]
                evidence=curvature_evidence(dict(track,times=np.asarray(track['times'])[use],values=np.asarray(track['values'])[use]))
                witnesses.append(dict(case=case,component=component,points=int(use.sum()),qualified=evidence['qualified'],minimum_linear_RMS_hz=evidence['minimum_linear_RMS_hz'],minimum_quadratic_BIC_gain=evidence['minimum_quadratic_BIC_gain']))
        record=read(RAW/'augmented_family_replacement'/(case+'.json'))
        if not record['trials']:continue
        for r in record['nominations']:nominations.append(dict(case=case,norad=r['norad'],nomination_score=r['score'],qualified=r['qualified'],conditional_RMS_hz=r['conditional_RMS_hz'],phase_s=r['phase_s']))
        fig,axes=plt.subplots(1,3,figsize=(17,5),layout='constrained')
        for k,t in enumerate(record['trials']):
            for j,arm in enumerate(['c0','fitted_c']):
                s=t['arms'][arm];x=k+(j-.5)*.3
                axes[0].bar(x,s['corrected_selection_loss'],width=.28,color=f'C{j}',label=arm if k==0 else None)
                axes[1].bar(x,position_error(s['endpoint_latlon']),width=.28,color=f'C{j}')
                axes[2].bar(x,sum(not g['compatible'] for g in s['gates']['tracks']),width=.28,color=f'C{j}')
                trial_rows.append(dict(case=case,norad=t['candidate_norad'],arm=arm,added_curved_points=t['added_curved_points'],paired_valid=t['paired_valid'],accepted=t.get('accepted',False),
                    corrected_RF_loss=s['corrected_selection_loss'],error_km=position_error(s['endpoint_latlon']),RMS_hz=s['RMS_hz']))
            gate_rows.extend(common.gate_rows(case,'augmented_'+str(t['candidate_norad']),t))
        for ax in axes:ax.set_xticks(range(len(record['trials'])),[str(t['candidate_norad']) for t in record['trials']]);ax.grid(axis='y',alpha=.2)
        axes[0].set(ylabel='Corrected RF loss; same augmented mask');axes[0].legend(fontsize=8);axes[1].set(ylabel='Position error (km), diagnostic only');axes[2].set(ylabel='Failed curved-source gates')
        fig.suptitle(case+' · original family +89 new points · full-causal nomination with original family excluded\nBest alternative67119 fails original gates; no GPS-selected family deletion or relabeling is accepted')
        save(fig,case+'_augmented_family_replacement.png')
    for name,rows in [('curvature_witnesses',witnesses),('augmented_family_trials',trial_rows),('augmented_family_gates',gate_rows),('augmented_family_nominations',nominations)]:
        if rows:figures.csv_write(OUT/'tables'/(name+'.csv'),rows)
    write(OUT/'evidence/curvature_witnesses.json',dict(rows=witnesses,original_masks_and_values_unchanged=True))
    shutil.copyfile(RAW/'augmented_family_replacement/independent_replay.json',OUT/'evidence/augmented_family_independent_replay.json')
    for name in ['probe_ds23_iteration014_augmented_family.py','audit_ds23_iteration014_augmented_family.py','ds23_supported_curvature.py',Path(__file__).name]:shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    shutil.copyfile(ROOT/'tests/analysis/test_ds23_iteration014_augmented_family.py',OUT/'source/tests/test_ds23_iteration014_augmented_family.py')
    common.archive(cases);common.gallery()
    gallery=OUT/'FIGURES.md';gallery.write_text(gallery.read_text().replace('# Iteration011 figure inventory','# Iteration014 figure inventory',1))
    write(OUT/'evidence/source_hashes.json',{str(p.relative_to(OUT)):sha(p) for p in (OUT/'source').rglob('*.py')})
    print('014 finalized',len(list((OUT/'figures').glob('*.png'))),'figures',len(list((OUT/'tables').glob('*.csv'))),'tables',flush=True)


def main():
    binding.configure('paths');step.binding.configure('support');graph.RAW=RAW
    for f in ['figures','tables','evidence','source/tools','source/tests']:(OUT/f).mkdir(parents=True,exist_ok=True)
    for module in [figures,common,diagnostics,paths_report,restarts]:module.RAW=RAW;module.OUT=OUT
    figures.setup=runner.engine.current_setup
    for name in ['batch_execution.json','independent_iteration_audit.json','recovery_endpoint_audit.json']:assert read(RAW/name)['all_passed']
    cases=read(RAW/'protocol.json')['cases'];rows=[];trials=[];gates=[];controls=[];families=[];residuals=[];following=[];path_rows=[];rounds=[];step_rows=[];integrity=[];ceilings={}
    for case in cases:
        original=runner.engine.current_setup(case);initial=read(RAW/case/'inventory.json')['arms'];d,cov,kind,selected=paths.parent(case)
        for a,s in original['arms'].items():original['arms'][a]=reported_fit(runner.engine.baseline.build(original,a,s['phase_reference']),s)
        td,tcov=temporal(case,d,cov);xd,xcov=extra(case,original,d,cov);ed,ecov=event(case,original,d,cov)
        n=initial['fitted_c']['total_GLRT'];g=n-initial['fitted_c']['outside_graph_points'];ceilings[case]=dict(total_GLRT=n,graph_points=g,percent=100*g/n,minimum_outside_for90=max(0,int(np.ceil(.9*n))-g))
        for name,data,coverage in [('Incumbent',original,initial),('Graph recovery',d,cov),('Persistent temporal',td,tcov),('Extra curve',xd,xcov),('Cross-band shared step',ed,ecov)]:
            for arm,r in data['arms'].items():rows.append(result_row(case,name,arm,r,coverage[arm],initial[arm]))
            for associated in [True,False]:figures.glrt_figure(data,coverage['fitted_c'],name.lower().replace(' ','_'),associated)
        controls.extend(dict(case=case,**r) for r in figures.current_dbg_figures(case));rounds.extend(restarts.restart_figure(case));families.extend(figures.family_rows(case,original))
        residuals.extend(figures.residual_figures(case,original,dict(baseline_arms=original['arms'],policy_arms=d['arms'],selected=selected),None));following.extend(diagnostics.track_diagnostics(case,original));path_rows.extend(paths_report.path_figures(case,d,kind));step_rows.extend(step_figures(case,original));integrity.extend(source_integrity_figures(case))
        collections=[('Default graph',read(RAW/'single_curve_reentry'/(case+'_positions.json'))['trials']),('Support graph',read(RAW/'support_aware_reentry'/(case+'.json'))['trials']),('Extra curve',read(RAW/'point_rich_extra_curve'/(case+'.json'))['trials']),('Cross-band step',read(step.OUT/(case+'.json'))['trials'])]
        collections.extend((m,[v]) for m,v in read(RAW/'graph_seeded_paths'/(case+'.json'))['methods'].items() if 'arms' in v)
        for label,tt in collections:
            for i,t in enumerate(tt):
                gates.extend(common.gate_rows(case,label+':'+str(i),t))
                for arm,r in t['arms'].items():trials.append(dict(case=case,method=label,trial=i,arm=arm,paired_valid=t['paired_valid'],accepted=t.get('accepted',t['paired_valid']),new_curved_points=t.get('added_curved_points',0),new_predictive_points=t.get('new_points',0),position_error_km=position_error(r['endpoint_latlon']),RMS_hz=r['RMS_hz'],final_phase_change_s=r['final_phase_change_s']))
    overview(rows,ceilings)
    for name,data in [('position_and_association',rows),('prototype_trials',trials),('all_curved_gates',gates),('family_ablations',families),('all_interventions',controls),('residual_diagnostics',residuals),('following_TLE_profiles',following),('temporal_paths',path_rows),('restart_phase_rounds',rounds),('shared_step_models',step_rows),('source_integrity',integrity)]:
        if data:figures.csv_write(OUT/'tables'/(name+'.csv'),data)
    write(OUT/'evidence/evaluation.json',dict(rows=rows,trials=trials,graph_ceilings=ceilings,no_full_DS23_or_new_location_validation=True,new_ALGO_release=False))
    for name in ['protocol.json','batch_execution.json','orchestration_resume.json','independent_iteration_audit.json','RF_restart_selection.json','recovery_endpoint_audit.json']:shutil.copyfile(RAW/name,OUT/'evidence'/name)
    names=['run_ds23_dbg01_iteration_014.py','resume_ds23_dbg01_iteration_014.py','probe_ds23_iteration014_recovery.py','probe_ds23_iteration014_step_transfer.py','probe_ds23_iteration014_cross_band_step.py','diagnose_ds23_iteration014_false_curvature.py','audit_ds23_iteration014_recovery.py',Path(__file__).name]
    names.extend(['diagnose_ds23_iteration013_step_transfer.py','probe_ds23_iteration013_shared_step.py','probe_ds23_iteration013_supported_step.py','ds23_frequency_events.py','audit_ds23_iteration013_recovery.py'])
    for name in names:shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    tests=['test_ds23_dbg01_iteration_014.py','test_ds23_dbg01_iteration_014_resume.py','test_ds23_iteration014_recovery.py','test_ds23_iteration014_step_transfer.py','test_ds23_iteration014_cross_band_step.py']
    for name in tests:shutil.copyfile(ROOT/'tests/analysis'/name,OUT/'source/tests'/name)
    write(OUT/'evidence/source_hashes.json',{str(p.relative_to(OUT)):sha(p) for p in (OUT/'source').rglob('*.py')});print('014 report assets',len(list((OUT/'figures').glob('*.png'))),'figures',flush=True)
    supplement()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--supplement',action='store_true');args=parser.parse_args()
    supplement() if args.supplement else main()
