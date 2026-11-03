"""Frozen015 report: RF parent choice, constrained native recovery and hard curves."""

from pathlib import Path
import shutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import probe_ds23_iteration015_recovery as binding
import probe_ds23_iteration015_guard_parent as guard
import probe_ds23_iteration015_joint_step as joint
import probe_ds23_iteration015_joint_phase_alias as phase_alias
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

runner=binding.runner;paths=binding.paths.paths
RAW=runner.RAW;OUT=ROOT/'reports/2026_10_23_ds23_dbg01_iteration_015'
METHODS=['Incumbent','Graph recovery','Persistent temporal','Guard parent (011)','Guard temporal policy']


def save(fig,name):fig.savefig(OUT/'figures'/name,dpi=145);plt.close(fig)


def temporal(case,d,cov,folder,constrained=None):
    t=constrained if constrained and constrained.get('accepted') else read(folder/(case+'.json'))['methods']['persistent5s']
    if not t.get('accepted'):return d,cov
    selected=t.get('selected_paths') or read(folder/(case+'_persistent5s_selection.json'))['selected']
    scan,entries=paths.native.append_native_paths(d['scan'],d['entries'],selected,paths.native.receiver_basis(d['scan']))
    return dict(d,scan=scan,entries=entries,arms=t['arms']),t['coverage']


def overview(rows,ceilings):
    fig,axes=plt.subplots(1,3,figsize=(18,5),layout='constrained')
    for k,case in enumerate(ceilings):
        for j,m in enumerate(METHODS):
            r=next(r for r in rows if r['case']==case and r['arm']=='fitted_c' and r['method']==m);x=k+(j-2)*.15
            axes[0].bar(x,r['associated_percent'],width=.145,color=f'C{j}',label=m if k==0 else None);axes[1].bar(x,r['position_error_km'],width=.145,color=f'C{j}');axes[1].text(x,r['position_error_km']+.03,f"{r['position_error_km']:.3f}",rotation=45,ha='center',fontsize=7)
        axes[2].bar(k,ceilings[case]['percent'],color='gray');axes[2].text(k,ceilings[case]['percent']+1,f"{ceilings[case]['percent']:.2f}%",ha='center')
    axes[0].set(ylabel='Original GLRT associated (%)',ylim=(0,100));axes[0].axhline(90,c='crimson',ls='--');axes[0].legend(fontsize=7,loc='lower left');axes[1].set(ylabel='Position error (km)',ylim=(0,3.5));axes[1].axhline(.5,c='green',ls='--');axes[2].set(ylabel='Original graph-only ceiling (%)',ylim=(0,100));axes[2].axhline(90,c='crimson',ls='--')
    for ax in axes:ax.set_xticks(range(2),list(ceilings));ax.grid(axis='y',alpha=.2)
    fig.suptitle('Iteration015 · fitted c · existing011 guard reused, not a new parent-selection discovery\n0273 guard temporal uses original constrained solver;0049 guard rows reuse the unchanged graph parent')
    save(fig,'iteration_summary.png')


def guarded_residual(case):
    choice=next(r for r in read(guard.OUT/'RF_selection.json')['rows'] if r['case']==case)
    if not choice['use_guard']:return []
    d,cov,kind,_=guard.parent(case);primary=read(guard.PATHS/(case+'.json'))['methods']['persistent5s'];refined=read(guard.OUT/'temporal_feasibility'/(case+'.json'))
    bad=[g for g in primary['arms']['fitted_c']['gates']['tracks'] if not g['compatible']];rows=[]
    if not bad:return rows
    component=bad[0]['component'];i=next(i for i,t in enumerate(d['scan'].tracks) if t['key']==component);track=d['scan'].tracks[i];byid={o['observation_id']:o for o in d['observations']};times,raw=raw_track_values(track,range(len(track['times'])),byid)
    selected=read(guard.PATHS/(case+'_persistent5s_selection.json'))['selected'];scan,entries=paths.native.append_native_paths(d['scan'],d['entries'],selected,paths.native.receiver_basis(d['scan']));dd=dict(d,scan=scan,entries=entries)
    fig,axes=plt.subplots(1,2,figsize=(15,5),layout='constrained')
    for name,data,arms in [('Guard parent',d,d['arms']),('Unconstrained native',dd,primary['arms']),('Original constrained solver',dd,refined['arms'])]:
        s=arms['fitted_c'];p=paths.build(data,kind,'fitted_c',s['phase_reference']);sl=next(sl for row,sl in zip(p.rows,p.slices,strict=True) if row['component']==component);use=p.keep[sl];res=p.calculate(np.asarray(s['endpoint_east_north_km']))['conditional_residual_hz'][sl]
        if name=='Guard parent':axes[0].scatter(times[use],raw[use]/1000,c='black',s=20,label='Original active GLRT')
        axes[0].plot(times[use],(raw-res)[use]/1000,label=name);axes[1].plot(times[use],res[use],'.-',label=name)
        gate=next(g for g in s['gates']['tracks'] if g['component']==component);diag=gate['conditional_residual_gate']['diagnostics'];rows.append(dict(case=case,method=name,component=component,norad=gate['norad'],points=gate['points'],compatible=gate['compatible'],RMS_hz=gate['conditional_residual_gate']['rms_hz'],**diag))
    axes[0].set(ylabel='Native CFO (kHz)');axes[1].axhline(0,c='gray');axes[1].set(ylabel='Conditional residual (Hz)')
    for ax in axes:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle(case+' · original62115 source must remain compatible when native points are added\nSame28 predictive points, original parent mask and all gates; no source removed or threshold relaxed')
    save(fig,case+'_guard_parent_retention.png');return rows


def joint_controls(case):
    record=read(joint.OUT/(case+'.json'));diag=read(joint.OUT/(case+'_RF_diagnostic.json'));rows=[]
    if not record['trials']:return rows
    target=diag['targets'][0];fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained');axes[0].plot(target['times'],target['residual_hz'],'.-',label='New69500 source in failed joint fit')
    for c in target['independent_original_parent_curves']:axes[0].plot(c['times'],c['residual_hz'],'.-',label=f"Original {c['norad']} CH{c['channel']}")
    axes[0].axvline(target['time_s'],c='crimson',ls='--');axes[0].set(xlabel='Scan time (s)',ylabel='No-event residual (Hz)');axes[0].legend(fontsize=7)
    for k,t in enumerate(record['trials']):
        for j,arm in enumerate(['c0','fitted_c']):
            axes[1].bar(k+(j-.5)*.3,t['gains'][arm],width=.28,color=f'C{j}',label=arm if k==0 else None);s=t['arms'][arm]
            rows.append(dict(case=case,kind=t['kind'],arm=arm,gain=t['gains'][arm],penalty=t['search_penalty'],accepted=t['accepted'],paired_valid=t['paired_valid'],error_km=position_error(s['endpoint_latlon']),amplitude_hz=s['event_amplitudes_hz'][0]))
    axes[1].axhline(target['search_penalty'],c='crimson',ls='--',label='Search penalty');axes[1].set(xticks=range(len(record['trials'])),xticklabels=[r['kind'] for r in record['trials']],ylabel='RF gain versus same-mask unconstrained null');axes[1].legend(fontsize=8)
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle(case+' · individually passing sources need not pass jointly\nShared-step alternatives worsen RF evidence and retain a failing source; both rejected')
    save(fig,case+'_joint_curve_step_control.png');return rows


def phase_alias_figures(case,d):
    record=read(phase_alias.OUT/(case+'.json'));rows=[]
    if not record['targets']:return rows
    target=record['targets'][0];track=d['scan'].tracks[target['track_index']];byid={o['observation_id']:o for o in d['observations']};times,raw=raw_track_values(track,range(len(track['times'])),byid)
    fig,axes=plt.subplots(1,2,figsize=(15,5),layout='constrained');axes[0].scatter(times,raw/1000,c='black',s=20,label='All29 original GLRT points')
    for grid,y in figures.polynomial_segments(track,range(len(times)),byid):axes[0].plot(grid,y/1000,c='C2',label='One persisted cubic, graph RMS36.3Hz')
    old=read(RAW/'single_curve_reentry'/(case+'_positions.json'))['trials'];old=next(t for t in old if len(t['additions'])==1 and t['additions'][0]['component']==target['component'])
    for label,trial in [('Original56030 standalone',old),('Broader62563 joint nominee',record['trials'][0])]:
        dd=dict(d,node=trial['node'],keep=np.asarray(trial['mask'],bool),means=np.asarray(trial['means']),entries=trial['entries']);s=trial['arms']['fitted_c'];p=runner.engine.baseline.build(dd,'fitted_c',s['phase_reference']);sl=next(sl for r,sl in zip(p.rows,p.slices,strict=True) if r['component']==target['component']);res=p.calculate(np.asarray(s['endpoint_east_north_km']))['conditional_residual_hz'][sl]
        for j,run in enumerate(np.split(np.arange(len(times)),np.flatnonzero(abs(np.diff(raw-track['values']))>1e-5)+1)):axes[0].plot(times[run],(raw-res)[run]/1000,label=label if j==0 else None)
        axes[1].plot(times,res,'.-',label=label)
    axes[0].set(ylabel='Native CFO (kHz)');axes[1].axhline(0,c='gray');axes[1].set(ylabel='Conditional residual (Hz)')
    for ax in axes:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle(case+' · longest remaining curved source · one smooth polynomial, no isolated endpoints\nBoth physical joint fits retain large smooth residual structure and are rejected; following TLE is not used')
    save(fig,case+'_hard_curve_CFO_and_residuals.png')
    fig,axes=plt.subplots(1,2,figsize=(15,5),layout='constrained');rank=target['grid_ranking'];rr=target['candidates'];axes[0].bar(range(len(rank)),[r['score'] for r in rank]);axes[0].set(xticks=range(len(rank)),xticklabels=[str(r['norad']) for r in rank],ylabel='Nonlinear phase/alias quadrature score',xlabel='Causal candidate (proposal only)')
    axes[1].bar(range(len(rr)),[r['conditional_RMS_hz'] for r in rr]);axes[1].set(xticks=range(len(rr)),xticklabels=[str(r['norad']) for r in rr],ylabel='Refined predictive residual RMS (Hz)',xlabel='Same physical-mode candidate refiner')
    for ax in axes:ax.grid(axis='y',alpha=.2);ax.tick_params(axis='x',rotation=40)
    fig.suptitle(case+' · all causal candidates ×121 phase values, nearest alias proposed at each phase\nOriginal priors, phase limit and final residual gates unchanged; nomination scores are not identity probabilities')
    save(fig,case+'_joint_phase_alias_search.png')
    for r in rr:rows.append(dict(case=case,component=target['component'],norad=r['norad'],quadrature_score=r['joint_phase_score'],grid_phase_s=r['joint_grid_phase_s'],refined_score=r['score'],RMS_hz=r['conditional_RMS_hz'],qualified=r['qualified'],alias=r['aliases']))
    return rows


def main():
    binding.configure('paths');graph.RAW=RAW
    for f in ['figures','tables','evidence','source/tools','source/tests']:(OUT/f).mkdir(parents=True,exist_ok=True)
    for m in [figures,common,diagnostics,paths_report,restarts]:m.RAW=RAW;m.OUT=OUT
    figures.setup=runner.engine.current_setup;paths_report.paths=paths
    for f in ['batch_execution.json','independent_iteration_audit.json','recovery_endpoint_audit.json','extended_endpoint_audit.json']:assert read(RAW/f)['all_passed']
    assert read(guard.OUT/'temporal_feasibility/independent_replay.json')['all_passed']
    cases=read(RAW/'protocol.json')['cases'];rows=[];trials=[];gates=[];controls=[];families=[];residuals=[];following=[];path_rows=[];rounds=[];guard_rows=[];joint_rows=[];phase_rows=[];ceilings={}
    for case in cases:
        original=runner.engine.current_setup(case);initial=read(RAW/case/'inventory.json')['arms'];d,cov,kind,selected=paths.parent(case);gd,gcov,gkind,_=guard.parent(case)
        for a,s in original['arms'].items():original['arms'][a]=reported_fit(runner.engine.baseline.build(original,a,s['phase_reference']),s)
        td,tcov=temporal(case,d,cov,RAW/'graph_seeded_paths');ft=read(guard.OUT/'temporal_feasibility'/(case+'.json'));gtd,gtcov=temporal(case,gd,gcov,guard.PATHS,ft)
        n=initial['fitted_c']['total_GLRT'];g=n-initial['fitted_c']['outside_graph_points'];ceilings[case]=dict(total_GLRT=n,graph_points=g,percent=100*g/n,minimum_outside_for90=max(0,int(np.ceil(.9*n))-g))
        for name,data,coverage in zip(METHODS,[original,d,td,gd,gtd],[initial,cov,tcov,gcov,gtcov],strict=True):
            for arm,s in data['arms'].items():rows.append(result_row(case,name,arm,s,coverage[arm],initial[arm]))
            for associated in [True,False]:figures.glrt_figure(data,coverage['fitted_c'],name.lower().replace(' ','_').replace('(011)','011'),associated)
        controls.extend(dict(case=case,**r) for r in figures.current_dbg_figures(case));rounds.extend(restarts.restart_figure(case));families.extend(figures.family_rows(case,original));residuals.extend(figures.residual_figures(case,original,dict(baseline_arms=original['arms'],policy_arms=d['arms'],selected=selected),None));following.extend(diagnostics.track_diagnostics(case,original));path_rows.extend(paths_report.path_figures(case,d,kind));guard_rows.extend(guarded_residual(case));joint_rows.extend(joint_controls(case));phase_rows.extend(phase_alias_figures(case,original))
        collections=[('Default graph',read(RAW/'single_curve_reentry'/(case+'_positions.json'))['trials']),('Support graph',read(RAW/'support_aware_reentry'/(case+'.json'))['trials']),('Joint step',read(joint.OUT/(case+'.json'))['trials']),('Joint phase alias',read(phase_alias.OUT/(case+'.json'))['trials'])]
        for folder,label in [(RAW/'graph_seeded_paths','Temporal'),(guard.PATHS,'Guard temporal')]:collections.extend((label+' '+m,[v]) for m,v in read(folder/(case+'.json'))['methods'].items() if 'arms' in v)
        if 'arms' in ft:collections.append(('Guard constrained',[ft]))
        for label,tt in collections:
            for i,t in enumerate(tt):
                gates.extend(common.gate_rows(case,label+':'+str(i),t))
                for arm,s in t['arms'].items():trials.append(dict(case=case,method=label,trial=i,arm=arm,paired_valid=t['paired_valid'],accepted=t.get('accepted',t['paired_valid']),new_curved_points=t.get('added_curved_points',0),new_predictive_points=t.get('new_points',0),error_km=position_error(s['endpoint_latlon']),RMS_hz=s['RMS_hz'],final_phase_change_s=s['final_phase_change_s']))
    overview(rows,ceilings)
    for name,data in [('position_and_association',rows),('prototype_trials',trials),('all_curved_gates',gates),('family_ablations',families),('all_interventions',controls),('residual_diagnostics',residuals),('following_TLE_profiles',following),('temporal_paths',path_rows),('restart_phase_rounds',rounds),('guard_retention_gates',guard_rows),('joint_step_models',joint_rows),('joint_phase_alias_candidates',phase_rows)]:
        if data:figures.csv_write(OUT/'tables'/(name+'.csv'),data)
    write(OUT/'evidence/evaluation.json',dict(rows=rows,trials=trials,graph_ceilings=ceilings,existing011guard_parent_gain_not_a_new_discovery=True,no_full_DS23_or_new_location_claim=True,new_ALGO_release=False))
    finalize()


def finalize():
    binding.configure('paths');common.RAW=RAW;common.OUT=OUT;cases=read(RAW/'protocol.json')['cases']
    control=read(phase_alias.OUT/'linearized_matched_control.json');assert control['all_common_scores_match'];controls=[]
    for row in control['rows']:
        case=row['case'];phase_alias_figures(case,runner.engine.current_setup(case))
        fig,axes=plt.subplots(1,2,figsize=(15,5),layout='constrained')
        for k,(key,label) in enumerate([('linearized_candidates','Original linearized screen'),('nonlinear_candidates','Nonlinear phase/alias screen')]):
            rr=row[key];axes[k].bar(range(len(rr)),[r['score'] for r in rr]);axes[k].set(xticks=range(len(rr)),xticklabels=[str(r['norad']) for r in rr],ylabel='Original physical-mode predictive score',title=label)
            for r in rr:controls.append(dict(case=case,screen=label,norad=r['norad'],score=r['score'],alias=r['aliases'],qualified=r['qualified']))
        for ax in axes:ax.tick_params(axis='x',rotation=40);ax.grid(axis='y',alpha=.2)
        fig.suptitle(case+' · matched proposal control at the same graph parent and inference position\nLinearized best56030 versus nonlinear62563; common candidate/alias scores replay exactly. Final new joint fit rejects')
        save(fig,case+'_matched_proposal_screens.png')
    figures.csv_write(OUT/'tables/matched_proposal_screens.csv',controls)
    shutil.copyfile(phase_alias.OUT/'linearized_matched_control.json',OUT/'evidence/linearized_matched_control.json')
    common.archive(cases);common.gallery();gallery=OUT/'FIGURES.md';gallery.write_text(gallery.read_text().replace('# Iteration011 figure inventory','# Iteration015 figure inventory',1))
    for name in ['protocol.json','batch_execution.json','independent_iteration_audit.json','RF_restart_selection.json','recovery_endpoint_audit.json','extended_endpoint_audit.json']:shutil.copyfile(RAW/name,OUT/'evidence'/name)
    shutil.copyfile(guard.OUT/'temporal_feasibility/independent_replay.json',OUT/'evidence/guard_constrained_independent_replay.json')
    shutil.copyfile(guard.guard.SOURCE/'DS23-0273.json',OUT/'evidence/original_full_source_DS23-0273.json')
    names=['run_ds23_dbg01_iteration_015.py','probe_ds23_iteration015_recovery.py','probe_ds23_iteration015_guard_parent.py','probe_ds23_iteration015_guard_feasibility.py','probe_ds23_iteration015_joint_step.py','probe_ds23_iteration015_joint_phase_alias.py','ds23_joint_phase_alias_nomination.py','audit_ds23_iteration015_recovery.py','audit_ds23_iteration015_guard_feasibility.py','diagnose_ds23_iteration015_linearized_control.py',Path(__file__).name,'probe_ds23_iteration014_recovery.py','probe_ds23_iteration014_step_transfer.py','probe_ds23_iteration014_cross_band_step.py','probe_ds23_iteration014_augmented_family.py','diagnose_ds23_iteration014_false_curvature.py','probe_ds23_iteration010_path_feasibility.py']
    for name in names:shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    tests=['test_ds23_dbg01_iteration_015.py','test_ds23_iteration015_recovery.py','test_ds23_iteration015_guard_parent.py','test_ds23_iteration015_joint_step.py','test_ds23_joint_phase_alias_nomination.py','test_ds23_iteration010_path_feasibility.py']
    for name in tests:shutil.copyfile(ROOT/'tests/analysis'/name,OUT/'source/tests'/name)
    write(OUT/'evidence/source_hashes.json',{str(p.relative_to(OUT)):sha(p) for p in (OUT/'source').rglob('*.py')});print('015 report',len(list((OUT/'figures').glob('*.png'))),'figures',len(list((OUT/'tables').glob('*.csv'))),'tables',flush=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--finalize',action='store_true');args=parser.parse_args()
    finalize() if args.finalize else main()
