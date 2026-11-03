"""Report bounded graph/temporal/short-curvature tests and20-scan confirmation."""

from pathlib import Path
import shutil
import re
import tarfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import run_ds23_dbg01_iteration_010 as runner
import probe_ds23_iteration010_paths as binding
import report_ds23_dbg01_iteration_001 as figures
import report_ds23_dbg01_iteration_006 as archives
import report_ds23_dbg01_iteration_007 as diagnostics
import report_ds23_dbg01_iteration_008 as path_figures
import report_ds23_dbg01_iteration_009 as restart_figures
from evaluate_ds23_iteration010_short_confirmation import reported_fit
from ds23_short_whole_curve_view import promote
from report_ds23_dbg01_iteration_005 import result_row
from report_algo02_ds23 import position_error
from plot_ds23_worst_association_bottleneck import raw_track_values
from run_algo01_ds23_sample import ROOT,read,write,sha

RAW=runner.RAW
OUT=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_010'


def save(fig,name):
    fig.savefig(OUT/'figures'/name,dpi=145);plt.close(fig)


def partitioned_archives(cases):
    groups={}
    for p in RAW.rglob('*'):
        if not p.is_file() or p.suffix not in ['.json','.csv','.py']:continue
        name=str(p.relative_to(RAW));match=re.search(r'DS23-\d{4}',name)
        if match and match.group() in cases:
            group=match.group()+('_restarts' if '/DBG01/restart_' in name else '_other')
        elif match:group='confirmation_'+match.group()
        else:group='shared'
        groups.setdefault(group,[]).append(p)
    for group,paths in groups.items():
        with tarfile.open(OUT/'evidence'/('raw_'+group+'.tar.gz'),'w:gz') as archive:
            for p in sorted(paths):archive.add(p,arcname=str(p.relative_to(RAW)),recursive=False)


def short_policy(case,d,cov,kind):
    record=read(RAW/'short_whole_curves'/(case+'.json'));t=record['selected']
    if t is None:return d,cov,kind,None
    p=binding.paths.build(d,kind,'c0',d['arms']['c0']['phase_reference']);changed,_=promote(d,p,t['offers'])
    return dict(changed,arms=t['arms'],original_protected=set(record['original_protected'])),t['coverage'],'support',t


def temporal_policy(case,d,cov,kind):
    original=read(binding.OUT/(case+'.json'))['methods']['persistent5s'];refined=read(RAW/'temporal_feasibility'/(case+'.json'))
    t=refined if refined.get('accepted') else original if original.get('accepted') else None
    if t is None:return d,cov,None
    fragments=t.get('selected_paths') or read(binding.OUT/(case+'_persistent5s_selection.json'))['selected']
    scan,entries=binding.paths.native.append_native_paths(d['scan'],d['entries'],fragments,binding.paths.native.receiver_basis(d['scan']))
    return dict(d,scan=scan,entries=entries,arms=t['arms']),t['coverage'],t


def short_figures(case,d,kind):
    nom=read(RAW/'short_whole_curves'/(case+'_nominations.json'))['targets']
    selected=read(RAW/'short_whole_curves'/(case+'.json'))['selected'];changed,cov,method,_=short_policy(case,d,{},kind)
    fig,axes=plt.subplots(len(nom),2,figsize=(15,4*len(nom)),squeeze=False,layout='constrained');rows=[]
    p=binding.paths.build(changed,method,'fitted_c',selected['arms']['fitted_c']['phase_reference']) if selected else None
    calculated=p.calculate(np.asarray(selected['arms']['fitted_c']['endpoint_east_north_km'])) if p else None
    byid={o['observation_id']:o for o in d['observations']}
    for k,row in enumerate(nom):
        t=d['scan'].tracks[row['target']['track_index']];tt,raw=raw_track_values(t,range(len(t['times'])),byid)
        best=row['arms']['c0'][0];r=np.asarray(best['residual_hz']);label=f"Causal conditional nomination {best['norad']}"
        if p:
            slot=next(i for i,r in enumerate(p.rows) if r['component']==t['key']);r=calculated['conditional_residual_hz'][p.slices[slot]];label=f"Accepted joint fit {best['norad']}"
        axes[k,0].scatter(tt,raw/1000,c='black',s=20,label='Original winning GLRT')
        for run in np.split(np.arange(len(tt)),np.flatnonzero(abs(np.diff(raw-t['values']))>1e-5)+1):axes[k,0].plot(tt[run],(raw-r)[run]/1000,c='C0')
        q=row['target']['curvature'];axes[k,0].set(title=t['key'].split('-RF')[0]+f" · {len(tt)} points / {np.ptp(tt):.2f}s",ylabel='Native CFO (kHz)')
        axes[k,1].plot(tt,r,'.-',label=label);axes[k,1].axhline(0,c='gray')
        axes[k,1].set(title=f"Jackknife min linear RMS{q['minimum_linear_RMS_hz']:.1f}Hz, BIC gain{q['minimum_quadratic_BIC_gain']:.1f}",ylabel='Residual (Hz)')
        for ax in axes[k]:ax.set_xlabel('Time (s)');ax.grid(alpha=.2);ax.legend(fontsize=7)
        rows.append(dict(case=case,component=t['key'],points=len(tt),span_s=float(np.ptp(tt)),minimum_linear_RMS_hz=q['minimum_linear_RMS_hz'],
            minimum_quadratic_BIC_gain=q['minimum_quadratic_BIC_gain'],nominee=best['norad'],nomination_RMS_hz=best['conditional_RMS_hz'],
            offered=row['offer'] is not None,selected_in_passing_policy=selected is not None))
    fig.suptitle(case+' · whole short sources · no point trimming or new polynomial fragments\nExisting10s jackknife rule; original20s classifier unchanged. Conditional nomination is not identity truth')
    save(fig,case+'_short_curves.png');return rows


def confirmation_figures():
    data=read(RAW/'short_confirmation20_evaluation/evaluation.json');cases=data['cases'];rows=[r for record in data['records'] for r in record['rows']]
    fig,axes=plt.subplots(2,2,figsize=(16,10),layout='constrained')
    for k,arm in enumerate(['c0','fitted_c']):
        old=[next(r for r in rows if r['case']==c and r['arm']==arm and r['method']=='Incumbent') for c in cases]
        new=[next(r for r in rows if r['case']==c and r['arm']==arm and r['method']!='Incumbent') for c in cases]
        a=np.array([r['position_error_km'] for r in old]);b=np.array([r['position_error_km'] for r in new])
        axes[k,0].plot(range(20),a,'o-',label='Incumbent');axes[k,0].plot(range(20),b,'x-',label='Short whole-curve policy')
        axes[k,0].set_xticks(range(20),[c.replace('DS23-','') for c in cases],rotation=65);axes[k,0].set(title=arm,ylabel='Position error (km)');axes[k,0].legend(fontsize=8)
        axes[k,1].scatter(100*(np.array([r['associated_points'] for r in new])-np.array([r['associated_points'] for r in old]))/np.array([r['all_GLRT'] for r in old]),1000*(b-a),c=['C0' if r['selected_recovery'] else 'gray' for r in new])
        axes[k,1].axhline(0,c='gray');axes[k,1].set(xlabel='Association gain (percentage points)',ylabel='Position error change (m; positive worse)')
    for ax in axes.flat:ax.grid(alpha=.2)
    fig.suptitle('20 scan-disjoint same-site cases · all cases and exact fallbacks retained\n+394 curved observations; higher association does not improve both accuracy metrics. No full-DS23 promotion')
    save(fig,'confirmation20_positions_and_coverage.png')
    figures.csv_write(OUT/'tables/confirmation20_positions.csv',rows);figures.csv_write(OUT/'tables/confirmation20_summary.csv',data['summary'])


def overview(rows,ceilings):
    methods=['Incumbent','Graph recovery','Temporal policy','Short-curve policy'];fig,axes=plt.subplots(1,3,figsize=(17,5),layout='constrained')
    for k,case in enumerate(ceilings):
        for j,m in enumerate(methods):
            r=next(r for r in rows if r['case']==case and r['arm']=='fitted_c' and r['method']==m);x=k+(j-1.5)*.19
            axes[0].bar(x,r['associated_percent'],width=.18,color=f'C{j}',label=m if k==0 else None)
            axes[1].bar(x,r['position_error_km'],width=.18,color=f'C{j}');axes[1].text(x,r['position_error_km']+.04,f"{r['position_error_km']:.3f}",ha='center',fontsize=7)
        axes[2].bar(k,ceilings[case]['percent'],color='gray');axes[2].text(k,ceilings[case]['percent']+1,f"{ceilings[case]['percent']:.2f}%",ha='center')
    axes[0].set(ylabel='Original GLRT associated (%)',ylim=(0,100));axes[0].axhline(90,c='crimson',ls='--');axes[0].legend(fontsize=7)
    axes[1].set(ylabel='Position error (km)');axes[1].axhline(.5,c='green',ls='--');axes[2].set(ylabel='Original graph-only ceiling (%)',ylim=(0,100));axes[2].axhline(90,c='crimson',ls='--')
    for ax in axes:ax.set_xticks(range(2),list(ceilings));ax.grid(axis='y',alpha=.2)
    fig.suptitle('DBG01 iteration010 · separate bounded policies, no GPS selection\n0080 constrained temporal reaches80.83% but no fitted-c gain;0257 short curves improve locally, not in20-case mean')
    save(fig,'iteration_summary.png')


def main():
    binding.configure();figures.RAW=RAW;figures.OUT=OUT;figures.setup=runner.engine.current_setup
    diagnostics.RAW=RAW;diagnostics.OUT=OUT;path_figures.RAW=RAW;path_figures.OUT=OUT
    restart_figures.RAW=RAW;restart_figures.OUT=OUT
    for folder in ['figures','tables','evidence','source/tools','source/tests']:(OUT/folder).mkdir(parents=True,exist_ok=True)
    assert read(RAW/'batch_resume_execution.json')['all_passed'];assert read(RAW/'independent_iteration_audit.json')['all_passed']
    cases=read(RAW/'protocol.json')['cases'];rows=[];trials=[];families=[];controls=[];residuals=[];following=[];paths=[];short=[];rounds=[];ceilings={}
    for case in cases:
        original=runner.engine.current_setup(case);initial=read(RAW/case/'inventory.json')['arms'];d,cov,kind,selected=binding.paths.parent(case)
        for a,s in original['arms'].items():
            p=runner.engine.baseline.build(original,a,s['phase_reference']);original['arms'][a]=reported_fit(p,s)
        n=initial['fitted_c']['total_GLRT'];g=n-initial['fitted_c']['outside_graph_points'];ceilings[case]=dict(total_GLRT=n,graph_points=g,percent=100*g/n,minimum_outside_for90=max(0,int(np.ceil(.9*n))-g))
        td,tcov,t=temporal_policy(case,d,cov,kind);sd,scov,skind,s=short_policy(case,d,cov,kind)
        for name,data,coverage in [('Incumbent',original,initial),('Graph recovery',d,cov),('Temporal policy',td,tcov),('Short-curve policy',sd,scov)]:
            for a,r in data['arms'].items():
                if 'final_phase_change_s' not in r:r=reported_fit(binding.paths.build(data,skind if name=='Short-curve policy' else kind,a,r['phase_reference']),r)
                rows.append(result_row(case,name,a,r,coverage[a],initial[a]))
            if name!='Short-curve policy' or s:
                for associated in [True,False]:figures.glrt_figure(data,coverage['fitted_c'],name.lower().replace(' ','_'),associated)
        controls.extend(dict(case=case,**r) for r in figures.current_dbg_figures(case));rounds.extend(restart_figures.restart_figure(case));families.extend(figures.family_rows(case,original))
        residuals.extend(figures.residual_figures(case,original,dict(baseline_arms=original['arms'],policy_arms=d['arms'],selected=selected),None))
        following.extend(diagnostics.track_diagnostics(case,original));paths.extend(path_figures.path_figures(case,d,kind));short.extend(short_figures(case,d,kind))
        collections=[('Default reentry',read(RAW/'single_curve_reentry'/(case+'_positions.json'))['trials']),
            ('Support reentry',read(RAW/'support_aware_reentry'/(case+'.json'))['trials']),
            ('Short whole-curve',read(RAW/'short_whole_curves'/(case+'.json'))['trials'])]
        h=read(binding.OUT/(case+'.json'))['methods'];collections.extend(('HMM '+m,[v]) for m,v in h.items() if 'arms' in v)
        constrained=read(RAW/'temporal_feasibility'/(case+'.json'))
        if 'arms' in constrained:collections.append(('Constrained HMM',[constrained]))
        for method,collection in collections:
            for i,trial in enumerate(collection):
                for a,r in trial['arms'].items():trials.append(dict(case=case,method=method,trial=i,arm=a,paired_valid=trial['paired_valid'],accepted=trial.get('accepted',trial['paired_valid']),
                    new_curved_points=trial.get('added_curved_points',0),new_predictive_points=trial.get('new_points',0),position_error_km=position_error(r['endpoint_latlon']),RMS_hz=r['RMS_hz'],final_phase_change_s=r['final_phase_change_s']))
    overview(rows,ceilings);confirmation_figures()
    for name,data in [('position_and_association',rows),('prototype_trials',trials),('family_ablations',families),('all_interventions',controls),
                      ('residual_diagnostics',residuals),('following_TLE_profiles',following),('temporal_paths',paths),('short_curvature',short),('restart_phase_rounds',rounds)]:
        if data:figures.csv_write(OUT/'tables'/(name+'.csv'),data)
    write(OUT/'evidence/evaluation.json',dict(rows=rows,trials=trials,graph_ceilings=ceilings,no_full_DS23_or_new_ALGO_gain_claim=True))
    partitioned_archives(cases)
    for name in ['protocol.json','batch_execution.json','batch_resume_execution.json','independent_iteration_audit.json','RF_restart_selection.json']:
        shutil.copyfile(RAW/name,OUT/'evidence'/name)
    shutil.copyfile(RAW/'short_confirmation20_evaluation/evaluation.json',OUT/'evidence/confirmation20_evaluation.json')
    names=['run_ds23_dbg01_iteration_010.py','repair_ds23_iteration010_bank.py','diagnose_ds23_iteration010_tracks.py','probe_ds23_iteration010_paths.py',
        'ds23_short_whole_curve_view.py','probe_ds23_iteration010_short_curves.py','probe_ds23_iteration010_path_feasibility.py',
        'confirm_ds23_iteration010_short_curves.py','repair_ds23_iteration010_empty_prediction.py','evaluate_ds23_iteration010_short_confirmation.py',
        'diagnose_ds23_iteration010_shared_shapes.py',Path(__file__).name]
    for name in names:shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    tests=['test_ds23_dbg01_iteration_010.py','test_ds23_iteration010_prototypes.py','test_ds23_iteration010_bank.py','test_ds23_short_whole_curve_view.py',
        'test_ds23_iteration010_path_feasibility.py','test_ds23_iteration010_confirmation.py','test_ds23_iteration010_empty_prediction.py','test_ds23_iteration010_evaluation.py']
    for name in tests:shutil.copyfile(ROOT/'tests/analysis'/name,OUT/'source/tests'/name)
    write(OUT/'evidence/source_hashes.json',{str(p.relative_to(OUT)):sha(p) for p in (OUT/'source').rglob('*.py')})
    print('Iteration010 report assets complete',flush=True)


if __name__=='__main__':main()
