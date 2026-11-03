"""DBG01 report: curved recovery, native temporal paths and a duration ablation."""

from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import run_ds23_dbg01_iteration_008 as runner
import probe_ds23_graph_seeded_paths as paths
import report_ds23_dbg01_iteration_001 as figures
import report_ds23_dbg01_iteration_002 as curves
import report_ds23_dbg01_iteration_004 as graph
import report_ds23_dbg01_iteration_006 as archives
import report_ds23_dbg01_iteration_007 as diagnostics
from report_ds23_dbg01_iteration_005 import result_row
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from ds23_supported_curvature import curvature_evidence
from ds23_curved_core_view import curved_core_view
from ds23_predictive_subsets import realize_predictive_subsets
from plot_ds23_worst_association_bottleneck import raw_track_values
from run_algo01_ds23_sample import ROOT,read,write,sha
from report_algo02_ds23 import position_error

RAW=runner.RAW
OUT=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_008'


def save(fig,name):
    fig.savefig(OUT/'figures'/name,dpi=145);plt.close(fig)


def path_figures(case,d,kind):
    record=read(paths.OUT/(case+'.json'));rows=[];graph_ids={o for t in d['scan'].tracks for o in t['observation_ids']}
    for method,t in record['methods'].items():
        if 'arms' not in t:continue
        selected=read(paths.OUT/(case+'_'+method+'_selection.json'))['selected'];basis=paths.native.receiver_basis(d['scan'])
        scan,entries=paths.native.append_native_paths(d['scan'],d['entries'],selected,basis)
        dd=dict(d,scan=scan,entries=entries);r=t['arms']['fitted_c'];p=paths.build(dd,kind,'fitted_c',r['phase_reference'])
        c=p.calculate(np.asarray(r['endpoint_east_north_km']));byid={o['observation_id']:o for o in d['observations']}
        if method=='persistent5s' and t['accepted']:
            for associated in [True,False]:figures.glrt_figure(dd,t['coverage']['fitted_c'],'temporal_policy',associated)
        for start in range(0,len(selected),6):
            offered=selected[start:start+6];fig,axes=plt.subplots(len(offered),2,figsize=(14,3*len(offered)),squeeze=False,layout='constrained')
            for k,f in enumerate(offered):
                slot=len(d['entries'])+start+k;sl=p.linear_slices[slot];t0=np.asarray(f['times']);residual=c['linear_raw_prediction_residual_hz'][sl]
                raw=np.array([byid[o]['measured_cfo_hz'] for o in f['observation_ids']])
                axes[k,0].scatter(t0,raw/1000,c='black',s=14,label='Original winning GLRT')
                cuts=np.flatnonzero((abs(np.diff(raw))>100000)|(np.diff(t0)>10))+1
                for run in np.split(np.arange(len(t0)),cuts):axes[k,0].plot(t0[run],(raw-residual)[run]/1000,c='C0')
                axes[k,0].set(title=f"RX{f['receiver']} CH{f['channel']} · {f['norad']} · {len(t0)} points",ylabel='Native CFO (kHz)')
                axes[k,1].plot(t0,residual,'.-',c='C0');axes[k,1].axhline(0,c='gray');axes[k,1].axhline(np.mean(residual),c='C1',ls='--')
                axes[k,1].set(ylabel='Fixed-radio prediction residual (Hz)',title=f"Path gate {'passes' if r['linear_gates'][slot]['compatible'] else 'fails'}; full trial {'accepted' if t['accepted'] else 'rejected'}")
                for ax in axes[k]:ax.set_xlabel('Time in scan (s)');ax.grid(alpha=.2)
                rows.append(dict(case=case,method=method,component=f['key'],norad=f['norad'],receiver=f['receiver'],channel=f['channel'],
                    points=len(t0),span_s=float(np.ptp(t0)),outside_original_graph=sum(o not in graph_ids for o in f['observation_ids']),
                    trial_accepted=t['accepted'],whole_path_gate=r['linear_gates'][slot]['compatible']))
            fig.suptitle(case+' · '+method+' · all screened offered paths · fitted c\nOrbit + graph-parent curved calibration; all native observations retained')
            save(fig,f'{case}_{method}_paths_{start//6+1}.png')
    return rows


def curvature_figure(d,kind):
    case=d['scan'].case;raw_record=read(RAW/'native_curvature_consistency.json');t=d['scan'].tracks[6]
    f=next(f for f in read(paths.OUT/(case+'_persistent5s_selection.json'))['selected'] if f['norad']==64261)
    use=np.array([o in set(f['observation_ids']) for o in t['observation_ids']]);core=dict(t,times=t['times'][use],values=t['values'][use])
    evidence=curvature_evidence(core);write(OUT/'evidence/core_curvature_evidence.json',evidence)
    r=d['arms']['fitted_c'];p=paths.build(d,kind,'fitted_c',r['phase_reference']);x=np.asarray(r['endpoint_east_north_km']);c=p.calculate(x)
    view,values,*_=linear_geometry(p,[dict(track_index=6,candidate_index=f['candidate_index'],alias=0)])
    geometry=geometry_features(view,x,0.);mean=view.q*geometry['intercept']+geometry['features']@c['coefficient']
    alias=int(np.rint(np.mean(mean-values)/paths.temporal.PERIOD));residual=values+alias*paths.temporal.PERIOD-mean
    byid={o['observation_id']:o for o in d['observations']};times,raw=raw_track_values(t,range(len(t['times'])),byid)
    fig,axes=plt.subplots(2,2,figsize=(14,10),layout='constrained')
    axes[0,0].scatter(times[use],raw[use]/1000,c='C2',label='21 points recovered by frozen HMM')
    axes[0,0].scatter(times[~use],raw[~use]/1000,c='crimson',marker='x',s=70,label='Isolated original endpoint; remains unused')
    cuts=np.flatnonzero(abs(np.diff(raw-values))>1e-5)+1
    for k,run in enumerate(np.split(np.arange(len(times)),cuts)):
        axes[0,0].plot(times[run],(raw-residual)[run]/1000,c='C0',marker='.' if len(run)==1 else None,
            label='64261 from independent CH4 graph recovery' if k==0 else None)
    axes[0,0].set(xlabel='Time (s)',ylabel='Native CFO (kHz)');axes[0,0].legend(fontsize=8)
    axes[0,1].plot(times,residual,'.-');axes[0,1].axhline(0,c='gray');axes[0,1].set(xlabel='Time (s)',ylabel='Fixed-parent satellite residual (Hz)')
    comparisons=raw_record['comparisons'];values=[comparisons['full']['False']['BIC_shared_minus_independent'],
        comparisons['full']['True']['BIC_shared_minus_independent'],comparisons['HMM_core']['False']['BIC_shared_minus_independent']]
    axes[1,0].bar(range(3),values,color=['C3','C3','C2']);axes[1,0].axhline(0,c='gray')
    axes[1,0].set_xticks(range(3),['Full: all times\nN=46','Full: overlap only\nN=39','HMM core: all times\nN=45'])
    axes[1,0].set(ylabel='BIC(shared curvature) − BIC(independent)')
    axes[1,1].plot(range(len(evidence['rows'])),[r['quadratic_BIC_gain'] for r in evidence['rows']],'.-')
    axes[1,1].axhline(10,c='crimson',ls='--');axes[1,1].set(xlabel='Full core, then each single-point deletion',ylabel='Quadratic gain over a line (BIC)')
    for ax in axes.flat:ax.grid(alpha=.2)
    fig.suptitle('DS23-0207 RX2 CH1 T000 · endpoint join and duration-classification diagnosis\nCore is only 13.93 s but remains actively curved; same-RX curvature test uses neither GPS nor a TLE')
    save(fig,'DS23-0207_endpoint_and_shared_curvature.png')
    rows=[]
    for population,groups in comparisons.items():
        for overlap,r in groups.items():
            for fit in r['rows']:rows.append(dict(population=population,overlap_only=overlap,points=len(r['times']),
                method=fit['method'],degree=fit['degree'],parameters=fit['parameters'],RMS_hz=fit['RMS_hz'],BIC=fit['BIC']))
    figures.csv_write(OUT/'tables/curvature_consistency.csv',rows)


def overview(rows,ceilings):
    methods=['Incumbent','Graph recovery','Temporal policy','Curved-core policy'];fig,axes=plt.subplots(1,3,figsize=(17,5),layout='constrained')
    for k,case in enumerate(ceilings):
        for j,method in enumerate(methods):
            r=next(r for r in rows if r['case']==case and r['arm']=='fitted_c' and r['method']==method);x=k+(j-1.5)*.19
            axes[0].bar(x,r['associated_percent'],width=.18,color=f'C{j}',label=method if k==0 else None)
            axes[1].bar(x,r['position_error_km'],width=.18,color=f'C{j}')
            axes[1].text(x,r['position_error_km']+.05,f"{r['position_error_km']:.3f}",ha='center',fontsize=7)
        axes[2].bar(k,ceilings[case]['percent'],color='0.6');axes[2].text(k,ceilings[case]['percent']+1,f"{ceilings[case]['percent']:.2f}%",ha='center')
    axes[0].set(ylabel='Original GLRT associated (%)',ylim=(0,100));axes[0].axhline(90,c='crimson',ls='--');axes[0].legend(fontsize=7)
    axes[1].set(ylabel='Position error (km)');axes[1].axhline(.5,c='green',ls='--');axes[2].set(ylabel='Original graph-only ceiling (%)',ylim=(0,100));axes[2].axhline(90,c='crimson',ls='--')
    for ax in axes:ax.set_xticks(range(2),list(ceilings));ax.grid(axis='y',alpha=.2)
    fig.suptitle('DBG01 iteration008 · bounded development · fitted c\n0157 temporal trial rejected; policies use graph fallback. No full-DS23 promotion')
    save(fig,'iteration_summary.png')


def main():
    runner.configure();graph.RAW=RAW;figures.RAW=RAW;figures.OUT=OUT;figures.setup=runner.engine.current_setup
    curves.RAW=RAW;curves.OUT=OUT;diagnostics.RAW=RAW;diagnostics.OUT=OUT
    for folder in ['figures','tables','evidence','source/tools','source/tests']:(OUT/folder).mkdir(parents=True,exist_ok=True)
    assert read(RAW/'independent_iteration_audit.json')['all_passed']
    cases=read(RAW/'protocol.json')['cases'];rows=[];trial_rows=[];families=[];controls=[];residuals=[];following=[];path_rows=[];ceilings={};alternatives=[]
    for case in cases:
        original=runner.engine.current_setup(case);initial=read(RAW/case/'inventory.json')['arms'];d,cov,kind,selected=paths.parent(case)
        n=initial['fitted_c']['total_GLRT'];g=n-initial['fitted_c']['outside_graph_points'];ceilings[case]=dict(total=n,graph_points=g,percent=100*g/n,
            unused_graph=initial['fitted_c']['unassociated_graph_points'],outside_graph=n-g,minimum_outside_points_for90=max(0,int(np.ceil(.9*n))-g))
        for method,arms,coverage,prefix in [('Incumbent',original['arms'],initial,'published'),('Graph recovery',d['arms'],cov,'graph_recovery')]:
            for a,r in arms.items():rows.append(result_row(case,method,a,r,coverage[a],initial[a]))
            for associated in [True,False]:figures.glrt_figure(d,coverage['fitted_c'],prefix,associated)
        controls.extend(dict(case=case,**r) for r in figures.current_dbg_figures(case));families.extend(figures.family_rows(case,original))
        residuals.extend(figures.residual_figures(case,original,dict(baseline_arms=original['arms'],policy_arms=d['arms'],selected=selected),None))
        following.extend(diagnostics.track_diagnostics(case,original));path_rows.extend(path_figures(case,d,kind))
        if selected:
            old=runner.engine.baseline.build
            if kind=='support':runner.engine.baseline.build=lambda changed,a,reference:runner.engine.support.build(original,changed['node'],changed['keep'],a,reference,changed['means'])
            try:curves.recovered_curves(case,original,selected)
            finally:runner.engine.baseline.build=old
        temporal=read(paths.OUT/(case+'.json'))
        for method,t in temporal['methods'].items():
            if 'arms' in t:
                for a,r in t['arms'].items():trial_rows.append(dict(result_row(case,'Temporal trial '+method,a,r,t['coverage'][a],initial[a]),accepted=t['accepted'],paired_valid=t['paired_valid']))
        primary=temporal['methods']['persistent5s'];arms=primary['arms'] if primary['accepted'] else d['arms'];coverage=primary['coverage'] if primary['accepted'] else cov
        for a,r in arms.items():rows.append(result_row(case,'Temporal policy',a,r,coverage[a],initial[a]))
        core=read(RAW/'supported_temporal_core'/(case+'.json'));accepted=None
        for trial in core['trials']:
            for a,r in trial['arms'].items():trial_rows.append(dict(result_row(case,trial['method'],a,r,trial['coverage'][a],initial[a]),accepted=trial['accepted'],paired_valid=trial['paired_valid']))
            if trial['method']=='core_curved' and trial['accepted']:accepted=trial
        arms=accepted['arms'] if accepted else d['arms'];coverage=accepted['coverage'] if accepted else cov
        for a,r in arms.items():rows.append(result_row(case,'Curved-core policy',a,r,coverage[a],initial[a]))
        if accepted:
            curvature_figure(d,kind)
            p=paths.build(d,kind,'c0',d['arms']['c0']['phase_reference']);changed,_,_=curved_core_view(d,p,accepted['offer']['fragment'],accepted['offer']['source_index'])
            for associated in [True,False]:figures.glrt_figure(changed,coverage['fitted_c'],'curved_core',associated)
        for group in read(RAW/'same_mask_alternatives'/(case+'.json'))['groups']:
            for trial in group['trials']:
                for a,r in trial['arms'].items():alternatives.append(dict(case=case,component=group['component'],norad=trial['norad'],arm=a,
                    selected_norad=group['selected_norad'],paired_valid=trial['paired_valid'],error_km=position_error(r['endpoint_latlon']),corrected_RF_loss=trial['corrected_loss'][a]))
    overview(rows,ceilings)
    for name,data in [('position_and_association',rows),('prototype_trials',trial_rows),('family_ablations',families),('all_interventions',controls),
        ('residual_diagnostics',residuals),('following_TLE_profiles',following),('temporal_paths',path_rows),('same_mask_alternatives',alternatives)]:figures.csv_write(OUT/'tables'/(name+'.csv'),data)
    write(OUT/'evidence/evaluation.json',dict(rows=rows,trials=trial_rows,graph_ceilings=ceilings,no_full_DS23_or_new_ALGO_gain_claim=True))
    archives.RAW=RAW;archives.OUT=OUT;archives.archives(cases)
    for name in ['protocol.json','batch_execution.json','independent_iteration_audit.json','RF_restart_selection.json','native_curvature_consistency.json']:
        shutil.copyfile(RAW/name,OUT/'evidence'/name)
    for name in ['run_ds23_dbg01_iteration_008.py','diagnose_ds23_iteration008_tracks.py','diagnose_ds23_iteration007_tracks.py',
        'ds23_graph_seeded_path_recovery.py','probe_ds23_graph_seeded_paths.py','ds23_receiver_curve_consistency.py','ds23_curved_core_view.py',
        'probe_ds23_curved_temporal_core.py','probe_ds23_supported_temporal_core.py','ds23_supported_curvature.py',
        'probe_ds23_iteration008_alternatives.py',Path(__file__).name]:shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    for name in ['test_ds23_dbg01_iteration_008.py','test_ds23_graph_seeded_path_recovery.py','test_ds23_receiver_curve_consistency.py',
        'test_ds23_curved_core_view.py','test_ds23_supported_curvature.py']:shutil.copyfile(ROOT/'tests/analysis'/name,OUT/'source/tests'/name)
    print('Iteration008 assets generated',flush=True)


if __name__=='__main__':main()
