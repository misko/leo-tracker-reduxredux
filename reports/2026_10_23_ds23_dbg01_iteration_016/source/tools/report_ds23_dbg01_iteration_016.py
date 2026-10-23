"""Frozen016 report; distinguish added evidence from geographic accuracy."""

from pathlib import Path
import shutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import probe_ds23_iteration016_recovery as binding
import report_ds23_dbg01_iteration_011 as common
import report_ds23_dbg01_iteration_001 as figures
import report_ds23_dbg01_iteration_004 as graph
import report_ds23_dbg01_iteration_007 as diagnostics
import report_ds23_dbg01_iteration_008 as paths_report
import report_ds23_dbg01_iteration_009 as restarts
from report_ds23_dbg01_iteration_005 import result_row
from evaluate_ds23_iteration010_short_confirmation import reported_fit
from ds23_distributed_polynomial_curvature import evidence
from run_algo01_ds23_sample import ROOT,read,write,sha
from report_algo02_ds23 import position_error

runner=binding.runner;paths=binding.paths.paths
RAW=runner.RAW;OUT=ROOT/'reports/2026_10_23_ds23_dbg01_iteration_016'
METHODS=['Incumbent','Graph recovery','Persistent temporal','Extra curve']


def temporal(case,data,coverage):
    saved=read(RAW/'temporal_feasibility'/(case+'.json'))
    if not saved.get('accepted'):
        saved=read(RAW/'graph_seeded_paths'/(case+'.json'))['methods']['persistent5s']
    if not saved.get('accepted'):return data,coverage
    selected=saved.get('selected_paths') or read(RAW/'graph_seeded_paths'/(case+'_persistent5s_selection.json'))['selected']
    scan,entries=paths.native.append_native_paths(data['scan'],data['entries'],selected,paths.native.receiver_basis(data['scan']))
    return dict(data,scan=scan,entries=entries,arms=saved['arms']),saved['coverage']


def overview(rows,ceilings):
    fig,axes=plt.subplots(1,3,figsize=(18,5),layout='constrained')
    for k,case in enumerate(ceilings):
        for j,method in enumerate(METHODS):
            row=next(r for r in rows if r['case']==case and r['method']==method and r['arm']=='fitted_c');x=k+(j-1.5)*.18
            axes[0].bar(x,row['associated_percent'],width=.17,color=f'C{j}',label=method if k==0 else None)
            axes[1].bar(x,row['position_error_km'],width=.17,color=f'C{j}');axes[1].text(x,row['position_error_km']+.04,f"{row['position_error_km']:.3f}",ha='center',rotation=45,fontsize=8)
        axes[2].bar(k,ceilings[case]['percent'],color='gray');axes[2].text(k,ceilings[case]['percent']+1,f"{ceilings[case]['percent']:.2f}%",ha='center')
    axes[0].set(ylabel='Original GLRT associated (%)',ylim=(0,100));axes[0].axhline(90,c='crimson',ls='--');axes[0].legend(fontsize=8,loc='lower left')
    axes[1].set(ylabel='Position error (km)',ylim=(0,3.5));axes[1].axhline(.5,c='green',ls='--');axes[2].set(ylabel='Original graph-only coverage ceiling (%)',ylim=(0,100));axes[2].axhline(90,c='crimson',ls='--')
    for ax in axes:ax.set_xticks(range(2),list(ceilings));ax.grid(axis='y',alpha=.2)
    fig.suptitle('Iteration016 · separate frozen policies · fitted c\nExtra-curve trials start at the incumbent; rejected policies retain their graph parent. No ALGO release')
    fig.savefig(OUT/'figures/iteration_summary.png',dpi=145);plt.close(fig)


def source_figures(case):
    rows=[]
    for row in read(RAW/'source_integrity'/(case+'.json'))['rows']:
        t=np.asarray(row['times']);y=np.asarray(row['values_hz']);whole=evidence(dict(times=t,values=y))
        fig,axes=plt.subplots(1,3,figsize=(18,5),layout='constrained')
        axes[0].scatter(t,y/1000,s=20,c='black',label='All original GLRT')
        for piece in row['pieces']:
            grid=np.linspace(piece['start_s'],piece['end_s'],250);v=np.polynomial.legendre.legval((grid-piece['reference_time_s'])/piece['time_scale_s'],piece['coefficients_hz']);axes[0].plot(grid,v/1000,label='Persisted graph polynomial')
        for endpoint in row['isolated_endpoints']:
            use=np.asarray(endpoint['core_indices']);tt=t[use];yy=y[use];core=evidence(dict(times=tt,values=yy));z=(tt-tt.mean())/np.ptp(tt)
            for degree in [1,2,4]:
                u=np.polynomial.legendre.legvander(z,degree);pred=u@np.linalg.lstsq(u,yy,rcond=None)[0];axes[1].plot(tt,yy-pred,'.-',label=f'Degree{degree}')
            rows.append(dict(case=case,component=row['component'],whole_points=len(t),core_points=len(use),endpoint_leverage=endpoint['leverage'],gap_s=endpoint['gap_s'],
                quadratic_only_whole_qualified=row['whole_curvature']['qualified'],degree4_whole_qualified=whole['qualified'],degree4_core_qualified=core['qualified'],
                whole_minimum_nonlinear_RMS_hz=whole.get('minimum_nonlinear_RMS_hz'),core_minimum_nonlinear_RMS_hz=core.get('minimum_nonlinear_RMS_hz')))
        axes[2].stem(t,row['leverage'],basefmt=' ');axes[2].axhline(.9,c='crimson',ls='--')
        axes[0].set(ylabel='Graph-unwrapped CFO (kHz)');axes[1].set(ylabel='Core polynomial residual (Hz)');axes[1].axhline(0,c='gray');axes[2].set(ylabel='Persisted polynomial leverage',ylim=(0,1.02))
        for ax in axes:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2)
        axes[0].legend(fontsize=8);axes[1].legend(fontsize=8)
        fig.suptitle(case+' · high-leverage endpoint is a diagnostic, not proof of false curvature\nDegree2-only test fails, but degree4 curvature survives deletion in whole source and core; no points removed')
        fig.savefig(OUT/'figures'/(case+'_curvature_degree_control.png'),dpi=145);plt.close(fig)
    return rows


def main():
    binding.configure('paths');graph.RAW=RAW
    for folder in ['figures','tables','evidence','source/tools','source/tests']:(OUT/folder).mkdir(parents=True,exist_ok=True)
    for module in [figures,common,diagnostics,paths_report,restarts]:module.RAW=RAW;module.OUT=OUT
    figures.setup=runner.engine.current_setup;paths_report.paths=paths
    for name in ['batch_execution.json','independent_iteration_audit.json','recovery_endpoint_audit.json','recovery_independent_audit_binding.json']:assert read(RAW/name)['all_passed']
    rows=[];trials=[];gates=[];controls=[];families=[];residuals=[];following=[];path_rows=[];rounds=[];shapes=[];ceilings={}
    cases=read(RAW/'protocol.json')['cases']
    for case in cases:
        original=runner.engine.current_setup(case);initial=read(RAW/case/'inventory.json')['arms'];data,cov,kind,selected=paths.parent(case)
        for arm,saved in original['arms'].items():original['arms'][arm]=reported_fit(runner.engine.baseline.build(original,arm,saved['phase_reference']),saved)
        td,tcov=temporal(case,data,cov);extra=read(RAW/'point_rich_extra_curve'/(case+'.json'))['selected'];xd,xcov=data,cov
        if extra is not None:
            xcov=next(r['coverage'] for r in read(RAW/'recovery_endpoint_audit.json')['memberships'] if r['case']==case and r['kind']=='extra')
            xd=dict(original,node=extra['node'],keep=np.asarray(extra['mask'],bool),means=np.asarray(extra['means']),entries=extra['entries'],arms=extra['arms'])
        n=initial['fitted_c']['total_GLRT'];g=n-initial['fitted_c']['outside_graph_points'];ceilings[case]=dict(total_GLRT=n,graph_points=g,percent=100*g/n,minimum_outside_for90=max(0,int(np.ceil(.9*n))-g))
        for name,dd,coverage in [('Incumbent',original,initial),('Graph recovery',data,cov),('Persistent temporal',td,tcov),('Extra curve',xd,xcov)]:
            for arm,saved in dd['arms'].items():rows.append(result_row(case,name,arm,saved,coverage[arm],initial[arm]))
            for associated in [True,False]:figures.glrt_figure(dd,coverage['fitted_c'],name.lower().replace(' ','_'),associated)
        controls.extend(dict(case=case,**r) for r in figures.current_dbg_figures(case));rounds.extend(restarts.restart_figure(case));families.extend(figures.family_rows(case,original))
        residuals.extend(figures.residual_figures(case,original,dict(baseline_arms=original['arms'],policy_arms=data['arms'],selected=selected),None));following.extend(diagnostics.track_diagnostics(case,original));path_rows.extend(paths_report.path_figures(case,data,kind));shapes.extend(source_figures(case))
        collections=[('Default graph',read(RAW/'single_curve_reentry'/(case+'_positions.json'))['trials']),('Support graph',read(RAW/'support_aware_reentry'/(case+'.json'))['trials']),('Extra curve',read(RAW/'point_rich_extra_curve'/(case+'.json'))['trials'])]
        collections.extend((m,[v]) for m,v in read(RAW/'graph_seeded_paths'/(case+'.json'))['methods'].items() if 'arms' in v)
        ft=read(RAW/'temporal_feasibility'/(case+'.json'))
        if 'arms' in ft:collections.append(('Constrained temporal',[ft]))
        for label,collection in collections:
            for i,trial in enumerate(collection):
                gates.extend(common.gate_rows(case,label+':'+str(i),trial))
                for arm,saved in trial['arms'].items():trials.append(dict(case=case,method=label,trial=i,arm=arm,paired_valid=trial['paired_valid'],accepted=trial.get('accepted',trial['paired_valid']),new_curved_points=trial.get('added_curved_points',0),new_predictive_points=trial.get('new_points',0),position_error_km=position_error(saved['endpoint_latlon']),RMS_hz=saved['RMS_hz'],final_phase_change_s=saved['final_phase_change_s']))
    overview(rows,ceilings)
    for name,data in [('position_and_association',rows),('prototype_trials',trials),('all_curved_gates',gates),('all_interventions',controls),('family_ablations',families),('residual_diagnostics',residuals),('following_TLE_profiles',following),('temporal_paths',path_rows),('restart_phase_rounds',rounds),('source_degree_control',shapes)]:
        if data:figures.csv_write(OUT/'tables'/(name+'.csv'),data)
    write(OUT/'evidence/evaluation.json',dict(rows=rows,trials=trials,graph_ceilings=ceilings,no_full_DS23_or_new_location_validation=True,new_ALGO_release=False))
    for name in ['protocol.json','batch_execution.json','independent_iteration_audit.json','RF_restart_selection.json','recovery_endpoint_audit.json','recovery_independent_audit_binding.json']:shutil.copyfile(RAW/name,OUT/'evidence'/name)
    for name in ['run_ds23_dbg01_iteration_016.py','probe_ds23_iteration016_recovery.py','audit_ds23_iteration016_recovery.py','ds23_distributed_polynomial_curvature.py',Path(__file__).name]:shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    for name in ['test_ds23_dbg01_iteration_016.py','test_ds23_iteration016_recovery.py','test_ds23_iteration016_audit.py','test_ds23_distributed_polynomial_curvature.py']:shutil.copyfile(ROOT/'tests/analysis'/name,OUT/'source/tests'/name)
    common.archive(cases);common.gallery()
    gallery=OUT/'FIGURES.md';gallery.write_text(gallery.read_text().replace('# Iteration011 figure inventory','# Iteration016 figure inventory',1))
    write(OUT/'evidence/source_hashes.json',{str(p.relative_to(OUT)):sha(p) for p in (OUT/'source').rglob('*.py')})
    print('016 report',len(list((OUT/'figures').glob('*.png'))),'figures',len(list((OUT/'tables').glob('*.csv'))),'tables',flush=True)


if __name__=='__main__':main()
