"""Report frozen full-population prediction and bounded DBG01 development.

This tool evaluates and plots saved RF-only outcomes. It never fits a position
or selects a satellite using the evaluation GPS. Full inference is immutable.
"""

from pathlib import Path
import shutil
import tarfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import run_ds23_dbg01_iteration_007 as runner
import report_ds23_dbg01_iteration_001 as figures
import probe_ds23_new_family_prediction as model
import evaluate_ds23_new_family_prediction as evaluation
from ds23_predictive_subsets import realize_predictive_subsets
from plot_ds23_worst_association_bottleneck import raw_track_values
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import ROOT,DATASET,read,write,sha

RAW=runner.RAW
OUT=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_007'
METHODS=['incumbent','phase_only','physical_prior']
LABELS=['Incumbent','New family: phase only','New family: physical prior']


def save(fig,name):
    fig.savefig(OUT/'figures'/name,dpi=150)
    plt.close(fig)


def new_family_ablation_figures(full):
    root=RAW/'new_family_ablation_diagnostic';cases=read(root/'protocol.json')['cases'];rows=[]
    assert read(root/'execution.json')['all_terminal']
    fig,axes=plt.subplots(1,len(cases),figsize=(16,5),layout='constrained')
    for ax,case in zip(axes,cases,strict=True):
        original=next(r for r in full['rows'] if r['case']==case and r['arm']=='fitted_c' and r['method']=='incumbent')
        primary=next(r for r in full['rows'] if r['case']==case and r['arm']=='fitted_c' and r['method']=='physical_prior')
        values=[original['position_error_km'],primary['position_error_km']];labels=['Incumbent','All new']
        for trial in read(root/(case+'.json'))['trials']:
            for arm,r in trial['arms'].items():rows.append(dict(case=case,arm=arm,excluded_norad=trial['excluded_norad'],
                paired_valid=trial['paired_valid'],error_km=trial['errors_km'][arm],remaining_new_points=sum(e['points'] for e in trial['entries']),
                diagnostic_only_never_used_as_RF_policy=True))
            values.append(trial['errors_km']['fitted_c']);labels.append('Drop\n'+str(trial['excluded_norad']))
        ax.bar(range(len(values)),values,color=['C0','C2']+['0.6']*(len(values)-2))
        ax.set_xticks(range(len(values)),labels,rotation=25);ax.set(title=case,ylabel='Position error (km)');ax.grid(axis='y',alpha=.2)
    fig.suptitle('Remove-one-new-family diagnosis · fitted c · no ablation adopted\nThree largest regressions and largest improvement selected for explanation after full evaluation')
    save(fig,'new_family_ablation_diagnostic.png')
    figures.csv_write(OUT/'tables/new_family_ablations.csv',rows)
    with tarfile.open(OUT/'evidence/new_family_ablations.tar.gz','w:gz') as archive:
        for p in sorted(root.glob('*.json')):archive.add(p,arcname=p.name,recursive=False)


def summarize(rows,group):
    result=[]
    for arm in ['c0','fitted_c']:
        for method in METHODS:
            rr=[r for r in rows if r['arm']==arm and r['method']==method]
            errors=np.array([r['position_error_km'] for r in rr]);n=sum(r['total_GLRT'] for r in rr)
            points=sum(r['associated_points'] for r in rr);fragments=sum(r['associated_fragments'] for r in rr)
            result.append(dict(group=group,arm=arm,method=method,cases=len(rr),mean_error_km=float(errors.mean()),
                median_error_km=float(np.median(errors)),p95_error_km=float(np.quantile(errors,.95)),
                associated_points=points,total_GLRT=n,associated_percent=100*points/n,
                associated_fragments=fragments,points_per_fragment=points/fragments,
                mean_frequency_RMS_hz=float(np.mean([r['frequency_RMS_hz'] for r in rr]))))
    return result


def population_figures(record):
    rows=record['rows'];summaries=record['summary'];fitted=[r for r in rows if r['arm']=='fitted_c']
    old={r['case']:r for r in fitted if r['method']=='incumbent'}
    primary=[r for r in fitted if r['method']=='physical_prior']
    fig,axes=plt.subplots(1,3,figsize=(16,5),layout='constrained')
    for k,method in enumerate(METHODS):
        r=next(r for r in summaries if r['arm']=='fitted_c' and r['method']==method)
        axes[0].bar(k-.16,r['mean_error_km'],width=.3,color='C0',label='Mean' if k==0 else None)
        axes[0].bar(k+.16,r['median_error_km'],width=.3,color='C1',label='Median' if k==0 else None)
        axes[1].bar(k,r['associated_percent'],color=f'C{k}')
        axes[1].text(k,r['associated_percent']+.35,f"{r['associated_percent']:.2f}%",ha='center')
        group=[r['position_error_km'] for r in fitted if r['method']==method]
        axes[2].plot(np.sort(group),np.arange(1,len(group)+1)/len(group),label=LABELS[k])
    for ax in axes[:2]:ax.set_xticks(range(3),['Incumbent','Phase only','Physical prior']);ax.grid(axis='y',alpha=.2)
    axes[0].set(ylabel='Position error (km)');axes[0].axhline(.5,c='gray',ls='--');axes[0].legend()
    axes[1].set(ylabel='Original winning GLRT associated (%)',ylim=(0,100));axes[1].axhline(90,c='crimson',ls='--')
    axes[2].set(xlabel='Position error (km)',ylabel='Fraction of410 available scans',xlim=(0,5));axes[2].legend(fontsize=8);axes[2].grid(alpha=.2)
    fig.suptitle('Full DS23 · fitted c · 410/413 available · causal inference\nSmall mean gain, essentially unchanged median; no new ALGO release')
    save(fig,'full_DS23_summary.png')
    fig,axes=plt.subplots(1,3,figsize=(16,5),layout='constrained')
    x=np.array([old[r['case']]['position_error_km'] for r in primary]);y=np.array([r['position_error_km'] for r in primary])
    gain=x-y;dp=np.array([r['associated_percent']-old[r['case']]['associated_percent'] for r in primary])
    axes[0].scatter(x,y,c=dp,cmap='viridis',s=15);axes[0].plot([0,18],[0,18],c='gray',lw=1)
    axes[0].set(xlabel='Incumbent error (km)',ylabel='Physical-prior prototype error (km)',aspect='equal')
    axes[1].scatter(dp,gain,s=15,alpha=.65);axes[1].axhline(0,c='gray');axes[1].set(xlabel='Change in associated GLRT (percentage points)',ylabel='Position improvement (km; positive is better)')
    axes[2].hist(gain,bins=np.linspace(-.65,2.2,40),color='C2');axes[2].axvline(0,c='gray');axes[2].set(xlabel='Position improvement (km)',ylabel='Scans')
    for r,g in zip(primary,gain,strict=True):
        if g<-.5 or g>1:axes[1].annotate(r['case'].replace('DS23-',''),(r['associated_percent']-old[r['case']]['associated_percent'],g),fontsize=7)
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('Full DS23 · every available scan retained · fitted c\nMore associated points do not consistently imply better location')
    save(fig,'full_DS23_regressions_and_coverage.png')
    fig,axes=plt.subplots(2,1,figsize=(17,8),layout='constrained',sharex=True)
    ordered=sorted(primary,key=lambda r:r['case']);xx=np.arange(len(ordered))
    axes[0].plot(xx,[old[r['case']]['position_error_km'] for r in ordered],'.-',ms=2,lw=.7,label='Incumbent')
    axes[0].plot(xx,[r['position_error_km'] for r in ordered],'.-',ms=2,lw=.7,label='Physical prior')
    axes[1].plot(xx,[r['associated_percent'] for r in ordered],'.',ms=3,label='Physical prior')
    axes[1].plot(xx,[old[r['case']]['associated_percent'] for r in ordered],'.',ms=2,label='Incumbent')
    axes[0].set(ylabel='Position error (km)');axes[0].axhline(.5,c='gray',ls='--');axes[1].set(ylabel='GLRT associated (%)',xlabel='DS23 scan');axes[1].axhline(90,c='crimson',ls='--')
    axes[1].set_xticks(xx[::20],[r['case'].replace('DS23-','') for r in ordered[::20]],rotation=60)
    for ax in axes:ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.suptitle('Full DS23 · all410 available scans in scan order · fitted c')
    save(fig,'full_DS23_by_scan.png')
    changes=[dict(case=r['case'],incumbent_error_km=old[r['case']]['position_error_km'],
        prototype_error_km=r['position_error_km'],improvement_km=old[r['case']]['position_error_km']-r['position_error_km'],
        new_family_norads=r['new_family_norads'],new_predictive_points=r['new_prediction_points'],
        associated_percent=r['associated_percent'],lost_postfit_IDs=r['original_accepted_points_lost']) for r in primary]
    figures.csv_write(OUT/'tables/full_DS23_positions.csv',rows)
    figures.csv_write(OUT/'tables/full_DS23_summary.csv',summaries)
    figures.csv_write(OUT/'tables/full_DS23_changes.csv',sorted(changes,key=lambda r:r['improvement_km']))
    members={m['dataset_label']:m for m in read(DATASET/'manifest.json')['members']}
    subgroups=[]
    for mode,name in [('short_window_iq_recording','fast'),('starlink_adaptive_hop_iq','adaptive')]:
        subgroups.extend(summarize([r for r in rows if members[r['case']]['recording_format']==mode],name))
    cohort=read(RAW/'new_family_confirmation20/protocol.json')['cases']
    subgroups.extend(summarize([r for r in rows if r['case'] in cohort],'random20'))
    figures.csv_write(OUT/'tables/subgroup_summary.csv',subgroups)
    write(OUT/'evidence/full_DS23_evaluation.json',record)
    return subgroups


def group_figure(case,d,trial):
    saved=trial['arms']['fitted_c'];entries=trial['entries'];x=np.asarray(saved['endpoint_east_north_km'])
    p=model.build(d,'fitted_c',saved['phase_reference'],saved['new_reference'],entries,True)
    c=p.calculate(x);byid={o['observation_id']:o for o in d['observations']}
    fig,axes=plt.subplots(len(entries),2,figsize=(14,3*len(entries)),squeeze=False,layout='constrained')
    for k,(entry,sl) in enumerate(zip(entries,p.new_slices,strict=True)):
        track=p.scan.tracks[entry['track_index']];t=np.asarray(track['times']);raw=np.array([byid[o]['measured_cfo_hz'] for o in entry['observation_ids']])
        residual=c['new_raw_prediction_residual_hz'][sl]
        axes[k,0].scatter(t,raw/1000,c='black',s=18,label='Original winning GLRT')
        axes[k,0].plot(t,(raw-residual)/1000,c='C0',label='Orbit + original curved radio mean')
        axes[k,0].set(title=f"RX{track['receiver']} CH{track['channel']} · satellite {entry['norad']} · {len(t)} points",ylabel='Native CFO (kHz)')
        axes[k,1].plot(t,residual,'.-',label='Fixed-radio prediction residual')
        axes[k,1].axhline(np.mean(residual),c='C1',ls='--',label='Descriptive mean')
        axes[k,1].axhline(0,c='black',lw=.6);axes[k,1].set(ylabel='Residual (Hz)')
        for ax in axes[k]:ax.set_xlabel('Time in scan (s)');ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle(case+' · shared new-family prediction · fitted c\nPer-family phase and physical correction; no predictive update to receiver calibration')
    save(fig,case+'_new_family_predictions.png')


def track_diagnostics(case,d):
    data=read(RAW/'all_track_diagnostics'/(case+'.json'));byid={o['observation_id']:o for o in d['observations']};rows=[]
    fig,axes=plt.subplots(len(data['rows']),2,figsize=(14,10),squeeze=False,layout='constrained')
    for k,row in enumerate(data['rows']):
        track=d['scan'].tracks[row['target']['track_index']];t,raw=raw_track_values(track,range(len(track['times'])),byid)
        axes[k,0].scatter(t,raw/1000,c='black',s=18,label='Original GLRT')
        for s,(grid,y) in enumerate(figures.polynomial_segments(track,range(len(t)),byid)):
            axes[k,0].plot(grid,y/1000,c='C2',label='Persisted graph polynomial' if s==0 else None)
        axes[k,0].set(title=track['key'].split('-RF')[0],ylabel='Native CFO (kHz)')
        best=row['candidates'][0]
        for name,profile in best['profiles'].items():
            axes[k,1].plot(t,profile['residual_hz'],'.-',label=f"{name}: RMS{profile['conditional_RMS_hz']:.1f} Hz")
        axes[k,1].axhline(0,c='gray');axes[k,1].set(title=f"Hypothesis {best['norad']} · matched phase-only profile",ylabel='Conditional residual (Hz)')
        for candidate in row['candidates']:
            rows.append(dict(case=case,component=track['key'],points=len(t),hypothesis_norad=candidate['norad'],
                graph_RMS_hz=row['graph_RMS_hz'],causal_profile_RMS_hz=candidate['profiles']['causal']['conditional_RMS_hz'],
                following_profile_RMS_hz=candidate['profiles'].get('following',{}).get('conditional_RMS_hz'),
                following_used_for_inference=False))
        for ax in axes[k]:ax.set_xlabel('Time in scan (s)');ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.suptitle(case+' · three longest wholly unused graph tracks, including linear tracks\nFollowing TLEs are diagnostic only; small single-line RMS does not establish identity')
    save(fig,case+'_unused_track_TLE_diagnostics.png')
    return rows


def endpoint_figure(d):
    diagnostic=read(RAW/'endpoint_group_diagnostic/DS23-0227.json')['rows'][0]
    offer=diagnostic['offer'];track=d['scan'].tracks[offer['track_index']];t=np.asarray(track['times']);v=np.asarray(track['values']);keep=np.asarray(offer['indices'])
    byid={o['observation_id']:o for o in d['observations']};_,raw=raw_track_values(track,range(len(t)),byid)
    piece=track['pieces'][0];grid=np.linspace(min(t),max(t),400)
    quartic=np.polynomial.legendre.legval((grid-piece['reference_time_s'])/piece['time_scale_s'],piece['coefficients_hz'])+np.median(raw-v)
    z=(t-t.mean())/np.ptp(t);design=np.polynomial.legendre.legvander(z,offer['core_degree'])
    coefficient=np.linalg.lstsq(design[keep],v[keep],rcond=None)[0]
    core=np.polynomial.legendre.legval((grid-t.mean())/np.ptp(t),coefficient)+np.median(raw-v)
    best=next(r for r in diagnostic['arms']['fitted_c'] if r['norad']==67025)
    residual=np.asarray(best['raw_residual_hz']);leverage=read(RAW/'fragment_leverage_diagnostic.json')['quartic_leverage']
    fig,axes=plt.subplots(2,2,figsize=(14,10),layout='constrained')
    for ax in [axes[0,0],axes[0,1]]:
        ax.scatter(t,raw/1000,c='black',s=24,label='Original20 GLRT points')
        ax.scatter(t[0],raw[0]/1000,c='crimson',s=70,marker='x',label='Isolated endpoint; remains unused')
        ax.plot(grid,quartic/1000,c='C2',label='Persisted degree4 polynomial')
        ax.plot(grid,core/1000,c='C1',ls='--',label='Degree2 fit of19-point core')
        ax.plot(t,(raw-residual)/1000,c='C0',label='67025 predicted from independent group')
        ax.set(xlabel='Time in scan (s)',ylabel='Native CFO (kHz)');ax.legend(fontsize=7)
    axes[0,1].set_xlim(t[keep].min()-.2,t[keep].max()+.2)
    visible=(grid>=t[keep].min())&(grid<=t[keep].max());axes[0,1].set_ylim(min(raw[keep].min(),core[visible].min())/1000-1,max(raw[keep].max(),core[visible].max())/1000+1)
    axes[1,0].stem(t,leverage,basefmt=' ');axes[1,0].set(xlabel='Time (s)',ylabel='Quartic point leverage',ylim=(0,1.1));axes[1,0].axhline(.98,c='crimson',ls='--')
    axes[1,1].plot(t,residual,'.-',label='Independent67025 residual');axes[1,1].axhline(0,c='gray')
    axes[1,1].set(xlabel='Time (s)',ylabel='Prediction residual (Hz)');axes[1,1].legend(fontsize=8)
    for ax in axes.flat:ax.grid(alpha=.2)
    fig.suptitle('DS23-0227 RX1 CH1 T002 · false-join evidence\nEndpoint leverage 0.99991 after 9.99 s gap; independent family supports 19-point core')
    save(fig,'DS23-0227_endpoint_leverage.png')


def archive_and_sources(cases):
    # Publish complete selected science records, avoiding >10GB of duplicate
    # coarse catalogue residual arrays. The local raw hash inventory names all
    # omitted assets; original raw input corpora remain outside Git.
    full=RAW/'new_family_full_DS23';manifest=[]
    for case in read(full/'protocol.json')['cases']:
        for f in [full/case/'inventory.json',full/case/'selection.json',full/case/'result.json',
                  full/'linear_family_groups'/(case+'.json'),RAW/'new_family_evaluation/cases'/(case+'.json')]:
            manifest.append(dict(path=str(f.relative_to(RAW)),bytes=f.stat().st_size,sha256=sha(f)))
    write(OUT/'evidence/full_raw_sha256.json',dict(files=manifest,bulk_raw_directory=str(RAW.resolve()),
        omitted_full_nomination_residual_arrays_not_required_to_recompute_published_summary=True))
    for group,start in enumerate(range(0,410,50)):
        case_list=read(full/'protocol.json')['cases'][start:start+50]
        with tarfile.open(OUT/'evidence'/f'full_results_{group:02d}.tar.gz','w:gz',dereference=True) as archive:
            for case in case_list:
                for name in ['result.json','selection.json']:
                    archive.add(full/case/name,arcname=f'{case}/{name}',recursive=False)
    for case in cases:
        for label,paths in [
            ('DBG01',sorted((RAW/case/'DBG01').glob('*.json'))),
            ('development',[p for folder in ['linear_family_groups','new_family_prediction','new_family_prediction_v2','all_track_diagnostics','endpoint_group_diagnostic','endpoint_predictive_view'] for p in (RAW/folder).glob(case+'*.json')])]:
            with tarfile.open(OUT/'evidence'/f'{case}_{label}.tar.gz','w:gz') as archive:
                for p in paths:archive.add(p,arcname=str(p.relative_to(RAW)),recursive=False)
    for source,target in [('protocol.json','iteration_protocol.json'),('independent_iteration_audit.json','independent_DBG01_audit.json'),
        ('new_family_full_DS23/protocol.json','full_protocol.json'),('new_family_full_DS23/execution.json','full_execution.json'),
        ('new_family_evaluation/protocol.json','coverage_evaluation_protocol.json'),('new_family_confirmation20/protocol.json','random20_protocol.json'),
        ('new_family_confirmation20/initial_position_evaluation.json','random20_position_evaluation.json'),
        ('new_family_prediction_v2/protocol.json','corrected_development_protocol.json'),
        ('endpoint_group_diagnostic/protocol.json','endpoint_diagnostic_protocol.json'),('endpoint_predictive_view/protocol.json','endpoint_child_protocol.json'),
        ('fragment_leverage_diagnostic.json','fragment_leverage_diagnostic.json')]:shutil.copyfile(RAW/source,OUT/'evidence'/target)
    for p in (RAW/'new_family_prediction/source_v1').glob('*'):
        dest=OUT/'evidence/invalid_v1_source'/p.name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(p,dest)
    tool_names=['run_ds23_dbg01_iteration_007.py','run_ds23_dbg01_iteration_002.py','probe_ds23_linear_family_groups.py',
        'probe_ds23_new_family_prediction.py','ds23_new_family_prediction.py','confirm_ds23_new_family_prediction.py',
        'run_ds23_new_family_full.py','evaluate_ds23_new_family_prediction.py','probe_ds23_endpoint_group_diagnostic.py',
        'probe_ds23_endpoint_predictive_view.py','diagnose_ds23_iteration007_tracks.py','prepare_ds23_dbg01_following.py',
        'ds23_predictive_subsets.py','ablate_ds23_new_family_prediction.py',Path(__file__).name]
    test_names=['test_ds23_dbg01_iteration_007.py','test_ds23_linear_family_groups.py','test_ds23_new_family_prediction.py',
        'test_ds23_endpoint_group_diagnostic.py','test_ds23_predictive_subsets.py','test_ds23_new_family_evaluation.py','test_ds23_new_family_ablation.py']
    for name in tool_names:shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    for name in test_names:shutil.copyfile(ROOT/'tests/analysis'/name,OUT/'source/tests'/name)


def main():
    runner.configure();figures.OUT=OUT;figures.RAW=RAW;figures.setup=runner.engine.current_setup
    for folder in ['figures','tables','evidence','source/tools','source/tests']:(OUT/folder).mkdir(parents=True,exist_ok=True)
    full=read(RAW/'new_family_evaluation/evaluation.json');assert full['full_incumbent_error_reproduction_verified'] and len(full['rows'])==2460
    assert read(RAW/'independent_iteration_audit.json')['all_passed']
    population_figures(full);new_family_ablation_figures(full)
    cases=read(RAW/'protocol.json')['cases'];development=[];families=[];controls=[];residuals=[];diagnostics=[];ceilings={}
    for case in cases:
        d=runner.engine.current_setup(case);inventory=read(RAW/case/'inventory.json')['arms'];case_eval=read(RAW/'new_family_evaluation/cases'/(case+'.json'))
        cov=case_eval['coverage'];trial=read(RAW/'new_family_prediction_v2'/(case+'.json'))['trials']['physical_prior']
        development.extend(r for r in full['rows'] if r['case']==case)
        for prefix,coverage in [('published',inventory['fitted_c']),('new_family',cov['fitted_c_physical_prior'])]:
            for associated in [True,False]:figures.glrt_figure(d,coverage,prefix,associated)
        controls.extend(dict(case=case,**r) for r in figures.current_dbg_figures(case));families.extend(figures.family_rows(case,d))
        residuals.extend(figures.residual_figures(case,d,dict(baseline_arms=d['arms'],policy_arms=None,selected=None),None))
        diagnostics.extend(track_diagnostics(case,d));group_figure(case,d,trial)
        original=inventory['fitted_c'];g=original['total_GLRT']-original['outside_graph_points'];ceilings[case]=dict(
            total_GLRT=original['total_GLRT'],associated=original['associated'],unused_inside_graph=original['unassociated_graph_points'],
            outside_graph=original['outside_graph_points'],graph_only_ceiling_percent=100*g/original['total_GLRT'],
            outside_points_needed_for90=max(0,int(np.ceil(.9*original['total_GLRT']))-g))
        child=read(RAW/'endpoint_predictive_view'/(case+'.json'))
        if child['accepted']:
            endpoint_figure(d)
            for arm,r in child['arms'].items():
                coverage=evaluation.coverage(d,arm,r,child['entries']);old=inventory[arm]
                development.append(dict(case=case,arm=arm,method='endpoint_core_development_only',accepted=True,
                    position_error_km=position_error(r['endpoint_latlon']),east_km=r['endpoint_east_north_km'][0],north_km=r['endpoint_east_north_km'][1],
                    frequency_RMS_hz=r['RMS_hz'],associated_points=coverage['associated'],total_GLRT=coverage['total_GLRT'],
                    associated_percent=coverage['percent'],associated_fragments=coverage['associated_tracks'],points_per_fragment=coverage['associated']/coverage['associated_tracks'],
                    active_curved_points=old['active_curved_points'],predictive_points=old['predictive_points']+sum(e['points'] for e in child['entries']),
                    new_prediction_points=sum(e['points'] for e in child['entries']),original_accepted_points_lost=len(set(old['accepted_observation_ids'])-set(coverage['accepted_observation_ids']))))
                write(OUT/'evidence'/(case+'_endpoint_'+arm+'_coverage.json'),coverage)
                if arm=='fitted_c':
                    derived=[e for e in child['entries'] if e.get('source_component')];subsets=[dict(e,track_index=next(i for i,t in enumerate(d['scan'].tracks) if t['key']==e['source_component']),component=e['source_component']) for e in derived]
                    scan,realized,_=realize_predictive_subsets(d['scan'],subsets)
                    assert [e['component'] for e in realized]==[e['component'] for e in derived]
                    for associated in [True,False]:figures.glrt_figure(dict(d,scan=scan),coverage,'endpoint_core_development',associated)
    for name,rows in [('development_positions',development),('family_ablations',families),('all_interventions',controls),('residual_diagnostics',residuals),('unused_track_TLE_profiles',diagnostics)]:figures.csv_write(OUT/'tables'/(name+'.csv'),rows)
    write(OUT/'evidence/development_evaluation.json',dict(rows=development,ceilings=ceilings,no_ALGO_release=True,endpoint_child_not_in_full_population_method=True))
    archive_and_sources(cases)
    write(OUT/'evidence/asset_receipt.json',dict(files=[dict(path=str(p.relative_to(OUT)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='asset_receipt.json']))
    print('Iteration007 figures, tables and receipts generated',flush=True)


if __name__=='__main__':main()
