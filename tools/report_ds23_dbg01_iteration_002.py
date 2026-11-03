"""Report frozen, independently audited iteration002; GPS is evaluation only."""

import csv
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.text import Text
import numpy as np
from sgp4.api import Satrec

from analyze_dsx01_fixed_site import ecef_states
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.sky.propagation import ElementSetCatalogue
from plot_ds23_worst_association_bottleneck import raw_track_values
from probe_ds23_single_curved_reentry import predictive_track_data
from prototype_dsx01_continuous_position import latlon
from report_algo02_ds23 import position_error
import report_ds23_dbg01_iteration_001 as figures
import run_ds23_dbg01_iteration_002 as iteration
from run_algo01_ds23_sample import ROOT, read, write, sha

RAW = iteration.RAW
OUT = ROOT/'reports/2026_10_22_ds23_dbg01_iteration_002'


def baseline_or_trial(data, trial):
    if trial is None:
        return data, data['arms']
    return dict(data, node=trial['node'], keep=np.asarray(trial['mask'], bool),
        entries=trial['entries'], means=np.asarray(trial['means']), arms=trial['arms']), trial['arms']


def native_runs(times, raw, canonical):
    shift=np.asarray(raw)-np.asarray(canonical)
    cuts=np.flatnonzero((abs(np.diff(shift))>1e-5)|(np.diff(times)>10.))+1
    return np.split(np.arange(len(times)),cuts)


def candidate_diagnostics(case, data):
    by_id = {o['observation_id']:o for o in data['observations']}
    diagnostics = read(RAW/'curve_diagnostics'/(case+'.json'))['targets']
    nominations = read(RAW/'single_curve_reentry'/(case+'_nominations.json'))['targets']
    trials = read(RAW/'single_curve_reentry'/(case+'_positions.json'))['trials']
    fig, axes = plt.subplots(len(diagnostics), 2, figsize=(14, 3.5*len(diagnostics)), squeeze=False, layout='constrained')
    rows = []
    for k, target in enumerate(diagnostics):
        track = next(t for t in data['scan'].tracks if t['key'] == target['component'])
        t, raw = raw_track_values(track, range(len(track['times'])), by_id)
        axes[k,0].plot(t, raw/1000, '.', c='black', label='Original GLRT')
        for segment,(grid,curve) in enumerate(figures.polynomial_segments(track,range(len(t)),by_id)):
            axes[k,0].plot(grid,curve/1000,c='tab:green',label='Persisted graph polynomial' if segment==0 else None)
        axes[k,0].set(title=target['component'].split('-RF')[0], ylabel='Raw CFO (kHz)')
        trial = next(r for r in trials if len(r['additions']) == 1 and r['additions'][0]['component'] == target['component'])
        dd, arms = baseline_or_trial(data, trial)
        saved = arms['c0']; p = iteration.baseline.build(dd, 'c0', saved['phase_reference'])
        x = np.asarray(saved['endpoint_east_north_km'])
        slot = next(i for i,r in enumerate(p.rows) if r['component'] == target['component'])
        residual = p.calculate(x)['conditional_residual_hz'][p.slices[slot]]
        axes[k,1].plot(t, target['graph_residual_hz'], '.-', c='tab:green', alpha=.65,
                       label=f"Graph RMS {target['graph_RMS_hz']:.1f} Hz")
        axes[k,1].plot(t, residual, '.-', c='tab:blue', label=f"Joint satellite fit RMS {np.sqrt(np.mean(residual**2)):.1f} Hz")
        axes[k,1].axhline(0, c='black', lw=.7)
        axes[k,1].set(ylabel='Residual (Hz)', title=f"Candidate {trial['additions'][0]['norad']}; paired fit {'passes' if trial['paired_valid'] else 'fails'}")
        for ax in axes[k]:
            ax.set_xlabel('Device time (s)');ax.grid(alpha=.2);ax.legend(fontsize=7)
        leading = target['candidates'][0]
        rows.append(dict(case=case, component=target['component'], points=target['points'],
            graph_RMS_hz=target['graph_RMS_hz'], leading_candidate=leading['norad'],
            causal_profile_RMS_hz=leading['arms']['causal'].get('conditional_RMS_hz'),
            following_profile_RMS_hz=leading['arms'].get('following', {}).get('conditional_RMS_hz'),
            real_following_element=leading['real_following_version']))
    fig.suptitle(case+' · long unused curves; lower graph RMS is not satellite identity evidence\n'
                 'One original polynomial piece per target; right panel is an audited regional joint-fit diagnostic')
    fig.savefig(OUT/'figures'/(case+'_long_curve_residuals.png'), dpi=150);plt.close(fig)
    p0 = iteration.baseline.build(data, 'c0', data['arms']['c0']['phase_reference'])
    x0 = np.asarray(data['arms']['c0']['endpoint_east_north_km'])
    fig, axes = plt.subplots(len(diagnostics), 2, figsize=(14, 3.5*len(diagnostics)), squeeze=False, layout='constrained')
    for k, (target, nomination) in enumerate(zip(diagnostics, nominations, strict=True)):
        proposed = target['candidates'][0]
        datum = predictive_track_data(data, p0, x0, nomination['row_index'])
        j = next(i for i,n in enumerate(data['scan'].norads) if n == proposed['norad'])
        times = datum['times']
        corrected = datum['values']+proposed['aliases'][0]/4.4e-6-datum['radio']@datum['coefficient'][:datum['radio_width']]
        axes[k,0].scatter(times, corrected/1000, c='black', s=14, label='Causal receiver-corrected GLRT')
        bank = dict(time_s=data['scan'].sky['time_s'], position_km=data['scan'].sky['position_km'][[j]],
                    velocity_km_s=data['scan'].sky['velocity_km_s'][[j]])
        for arm, color in [('causal','tab:blue'), ('following','tab:orange')]:
            r = proposed['arms'].get(arm)
            if r is None or not r['visible']:
                continue
            used = bank
            if arm == 'following':
                version = proposed['following_provenance']
                catalogue = ElementSetCatalogue((str(proposed['norad']),), (proposed['norad'],),
                    (Satrec.twoline2rv(*version['lines']),))
                position, velocity, good = ecef_states(catalogue, data['scan'].receipt['origin_utc_ns'], bank['time_s'])
                if not good.all():raise ValueError('following propagation changed')
                used = dict(bank, position_km=position, velocity_km_s=velocity)
            f, _ = phase_frequency_grid(used, times, *latlon(x0), phase_seconds=r['phase_s'])
            axes[k,0].plot(times, datum['q']*f[0]/1000, c=color, label=f'{arm} orbital Doppler')
            axes[k,1].plot(times, r['residual_hz'], '.-', c=color,
                label=f"{arm}: {r['conditional_RMS_hz']:.1f} Hz")
        axes[k,0].set(title=target['component'].split('-RF')[0]+f" · {proposed['norad']}", ylabel='Corrected CFO / orbit (kHz)')
        axes[k,1].set(ylabel='Conditional residual (Hz)');axes[k,1].axhline(0, c='black', lw=.7)
        for ax in axes[k]:
            ax.set_xlabel('Device time (s)');ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle(case+' · following TLE diagnostic only; frozen causal RF endpoint and receiver calibration\n'
        'Matched phase profiles within ±15 s, no phase prior or orbital-shape modes in either diagnostic; no position adoption')
    fig.savefig(OUT/'figures'/(case+'_following_TLE_profiles.png'), dpi=150);plt.close(fig)
    return rows


def recovered_curves(case, data, selected):
    if selected is None:return
    dd, arms = baseline_or_trial(data, selected)
    saved = arms['fitted_c'];p = iteration.baseline.build(dd, 'fitted_c', saved['phase_reference'])
    x = np.asarray(saved['endpoint_east_north_km']);residual = p.calculate(x)['conditional_residual_hz']
    by_id = {o['observation_id']:o for o in data['observations']}
    additions = selected['additions']
    fig, axes = plt.subplots(len(additions), 2, figsize=(13, 3.6*len(additions)), squeeze=False, layout='constrained')
    for k, addition in enumerate(additions):
        slot = next(i for i,r in enumerate(p.rows) if r['component'] == addition['component'])
        track = data['scan'].tracks[p.members[slot]]
        times, raw = raw_track_values(track, range(len(track['times'])), by_id)
        r = residual[p.slices[slot]]
        axes[k,0].scatter(times, raw/1000, c='black', s=17, label='Original GLRT')
        for segment,run in enumerate(native_runs(times,raw,track['values'])):
            axes[k,0].plot(times[run],(raw-r)[run]/1000,c='tab:blue',
                label='Expected orbit + inferred radio / fragment terms' if segment==0 else None)
        axes[k,0].set(ylabel='Raw CFO (kHz)', title=addition['component'].split('-RF')[0]+f" · hypothesis {addition['norad']}")
        axes[k,1].plot(times, r, '.-', label=f"Conditional RMS {np.sqrt(np.mean(r*r)):.1f} Hz")
        axes[k,1].axhline(0, c='black', lw=.7);axes[k,1].set(ylabel='Residual (Hz)')
        for ax in axes[k]:ax.set_xlabel('Device time (s)');ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle(case+' · recovered evidence · fitted c · original gates pass in both c arms')
    fig.savefig(OUT/'figures'/(case+'_recovered_curves.png'), dpi=155);plt.close(fig)


def summary(rows, ceilings):
    cases = list(ceilings)
    fig, axes = plt.subplots(1,3,figsize=(15,5),layout='constrained')
    for k, case in enumerate(cases):
        for j, method in enumerate(['Published incumbent', 'RF-selected growth']):
            row = next(r for r in rows if r['case']==case and r['method']==method and r['arm']=='fitted_c')
            x=k+(j-.5)*.25
            axes[0].bar(x,row['associated_percent'],width=.23,color=['tab:blue','tab:orange'][j],label=method if k==0 else None)
            axes[1].bar(x,row['position_error_km'],width=.23,color=['tab:blue','tab:orange'][j])
            axes[0].text(x,row['associated_percent']+1,f"{row['associated_percent']:.1f}%",ha='center',fontsize=8)
            axes[1].text(x,row['position_error_km']+.1,f"{row['position_error_km']:.2f}",ha='center',fontsize=8)
        axes[2].bar(k,ceilings[case]['percent'],color='tab:green')
        axes[2].text(k,ceilings[case]['percent']+1,f"{ceilings[case]['percent']:.1f}%",ha='center')
    axes[0].axhline(90,ls='--',c='crimson');axes[2].axhline(90,ls='--',c='crimson');axes[1].axhline(.5,ls='--',c='green')
    axes[0].set(ylabel='Associated original GLRT (%)',ylim=(0,100));axes[0].legend(fontsize=8)
    axes[1].set(ylabel='Position error (km)')
    axes[2].set(ylabel='Maximum association within current graph (%)',ylim=(0,100))
    for ax in axes:ax.set_xticks(range(len(cases)),cases);ax.grid(axis='y',alpha=.2)
    fig.suptitle('DBG01 iteration 002 · conditional two-scan gains; no new ALGO release or full-DS23 accuracy claim')
    fig.savefig(OUT/'figures/iteration_summary.png',dpi=165);plt.close(fig)


def family_identity_controls():
    case='DS23-0035';d=iteration.current_setup(case)
    growth=read(RAW/'family_seeded_growth'/(case+'.json'))
    alternative=read(RAW/'family_alternatives'/(case+'.json'))
    baseline=growth['selected']['arms']['c0']['corrected_selection_loss']
    rows=[]
    for trial in [growth['selected']]+alternative['trials']:
        family=trial['additions'][0]['norad']
        for arm,fit in trial['arms'].items():
            rows.append(dict(case=case,family=family,arm=arm,paired_valid=trial['paired_valid'],
                corrected_selection_loss=fit['corrected_selection_loss'],RMS_hz=fit['RMS_hz'],
                position_error_km=position_error(fit['endpoint_latlon']),
                selected_by_RF=family==growth['selected']['additions'][0]['norad']))
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    families=list(dict.fromkeys(r['family'] for r in rows))
    for k,family in enumerate(families):
        r=next(r for r in rows if r['family']==family and r['arm']=='c0')
        axes[0].bar(k,r['corrected_selection_loss']-baseline,color='tab:blue' if r['paired_valid'] else 'crimson')
        for offset,arm,color in [(-.12,'c0','tab:blue'),(.12,'fitted_c','tab:orange')]:
            r=next(r for r in rows if r['family']==family and r['arm']==arm)
            axes[1].scatter(k+offset,r['position_error_km'],c=color,marker='o' if r['paired_valid'] else 'x')
    for ax in axes:ax.set_xticks(range(len(families)),families);ax.grid(axis='y',alpha=.2)
    axes[0].set(ylabel='Corrected c0 RF loss minus accepted 68060')
    axes[1].set(ylabel='Position error (km)',title='Blue c0; orange fitted c; × fails original gates')
    fig.suptitle('0035 · same 52 recovered points, competing shared family identities\n'
                 '69943 improves geographic error but has worse RF evidence; it is not GPS-selected')
    fig.savefig(OUT/'figures/family_identity_controls.png',dpi=165);plt.close(fig)
    dd,arms=baseline_or_trial(d,growth['extension'])
    fig,axes=plt.subplots(1,2,figsize=(14,4.5),layout='constrained')
    for ax,arm in zip(axes,['c0','fitted_c'],strict=True):
        fit=arms[arm];p=iteration.baseline.build(dd,arm,fit['phase_reference'])
        residual=p.calculate(np.asarray(fit['endpoint_east_north_km']))['conditional_residual_hz']
        for addition in growth['extension']['additions']:
            k=next(k for k,r in enumerate(p.rows) if r['component']==addition['component'])
            track=d['scan'].tracks[p.members[k]]
            ax.plot(track['times'],residual[p.slices[k]],'.-',label=addition['component'].split('-RF')[0].replace(case+'-',''))
        ax.axhline(0,c='black',lw=.7);ax.set(title=arm,xlabel='Device time (s)',ylabel='Conditional residual (Hz)');ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('0035 · rejected 99-point union under one shared 68060 correction\n'
                 'Long RX1 curve conflicts with the two RX2 curves; same leading candidate is not shared identity proof')
    fig.savefig(OUT/'figures/family_consistency_conflict.png',dpi=165);plt.close(fig)
    return rows


def main():
    iteration.configure()
    assert read(RAW/'independent_iteration_audit.json')['all_passed']
    assert read(RAW/'family_seeded_growth/execution.json')['all_passed']
    assert read(RAW/'remaining_curves/independent_nomination_audit.json')['all_passed']
    assert read(RAW/'curve_diagnostics/execution.json')['all_passed']
    assert read(RAW/'family_alternatives/execution.json')['all_passed']
    assert read(RAW/'curved_promotion/execution.json')['all_passed']
    for name in ['figures','tables','evidence','source/tools','source/tests']:(OUT/name).mkdir(parents=True,exist_ok=True)
    figures.OUT, figures.RAW = OUT, RAW
    figures.REENTRY, figures.SUPPORT = RAW/'single_curve_reentry', RAW/'support_aware_reentry'
    figures.setup = iteration.current_setup
    rows, families, controls, residuals, diagnostics, failures, ceilings = [], [], [], [], [], [], {}
    original_save=Figure.savefig
    def labeled_save(fig,*args,**kwargs):
        for item in fig.findobj(Text):item.set_text(item.get_text().replace('Single-curve prototype','RF-selected growth'))
        return original_save(fig,*args,**kwargs)
    Figure.savefig=labeled_save
    try:
        for case in read(RAW/'protocol.json')['cases']:
            d=iteration.current_setup(case);original=read(RAW/case/'inventory.json')['arms']
            growth=read(RAW/'family_seeded_growth'/(case+'.json'))
            final=read(RAW/'curved_promotion'/(case+'.json'));dd,arms=baseline_or_trial(d,final['selected'])
            _,growth_arms=baseline_or_trial(d,growth['selected'])
            ceilings[case]=dict(points=original['fitted_c']['total_GLRT']-original['fitted_c']['outside_graph_points'],
                percent=100*(1-original['fitted_c']['outside_graph_points']/original['fitted_c']['total_GLRT']))
            for method, pair, coverage in [('Published incumbent',d['arms'],original),
                                           ('Graph recovery',growth_arms,growth['coverage']),
                                           ('RF-selected growth',arms,final['coverage'])]:
                for arm,fit in pair.items():
                    cov=coverage[arm]
                    rows.append(dict(case=case,method=method,arm=arm,position_error_km=position_error(fit['endpoint_latlon']),
                        associated_points=cov['associated'],all_GLRT=cov['total_GLRT'],associated_percent=cov['percent'],
                        curved_position_points=fit['active_points'],predictive_points=fit.get('predictive_points',sum(e['points'] for e in d['entries'])),
                        position_used_percent=100*(fit['active_points']+sum(e['points'] for e in d['entries']))/cov['total_GLRT'],
                        associated_graph_fragments=cov['associated_tracks'],points_per_associated_fragment=cov['associated']/cov['associated_tracks'],
                        RMS_hz=fit['RMS_hz'],original_accepted_points_lost=len(set(original[arm]['accepted_observation_ids'])-set(cov['accepted_observation_ids'])),
                        selected_by_GPS=False))
                if method!='Graph recovery':
                    for associated in [True,False]:figures.glrt_figure(d,coverage['fitted_c'],'published' if method=='Published incumbent' else 'growth',associated)
            residuals.extend(figures.residual_figures(case,d,dict(baseline_arms=d['arms'],policy_arms=arms,selected=final['selected']),None))
            controls.extend(dict(case=case,**r) for r in figures.current_dbg_figures(case))
            families.extend(figures.family_rows(case,d))
            diagnostics.extend(candidate_diagnostics(case,d));recovered_curves(case,d,final['selected'])
            for folder in ['single_curve_reentry','remaining_curves']:
                for trial in read(RAW/folder/(case+'_positions.json'))['trials']:
                    for arm,fit in trial['arms'].items():
                        failures.append(dict(case=case,stage=folder,arm=arm,
                            additions=str([a['norad'] for a in trial['additions']]),paired_valid=trial['paired_valid'],
                            failing_tracks=str([g for g in fit['gates']['tracks'] if not g['compatible']]),
                            failing_predictive=str([g for g in fit['linear_gates'] if not g['compatible']])))
            target=OUT/'evidence'/case;target.mkdir(exist_ok=True)
            for name in ['inventory.json','screen.json']:shutil.copyfile(RAW/case/name,target/name)
            for name in ['audit.json','protocol.json','request.json','surface_values.json','hypothesis_bank.json','restart_comparison.csv','restart_summary.json','interventions.csv','RF_restart_selection.json']:
                shutil.copyfile(RAW/case/'DBG01'/name,target/('DBG01_'+name))
            for folder in ['single_curve_reentry','remaining_curves']:
                for suffix in ['nominations','positions','audit']:shutil.copyfile(RAW/folder/(case+'_'+suffix+'.json'),target/(folder+'_'+suffix+'.json'))
            for folder in ['family_seeded_growth','curve_diagnostics']:
                shutil.copyfile(RAW/folder/(case+'.json'),target/(folder+'.json'))
            shutil.copyfile(RAW/'family_alternatives'/(case+'.json'),target/'family_alternatives.json')
            shutil.copyfile(RAW/'curved_promotion'/(case+'.json'),target/'curved_promotion.json')
            shutil.copyfile(RAW/(case+'_following_elements.json'),target/'following_elements.json')
            shutil.copyfile(RAW/'support_aware_reentry'/(case+'_audited.json'),target/'support_aware_audit.json')
    finally:Figure.savefig=original_save
    for name,records in [('position_and_association',rows),('family_ablations',families),('all_interventions',controls),
                         ('residual_diagnostics',residuals),('following_TLE_profiles',diagnostics),('trial_gates',failures)]:
        figures.csv_write(OUT/'tables'/(name+'.csv'),records)
    summary(rows,ceilings)
    figures.csv_write(OUT/'tables/family_identity_controls.csv',family_identity_controls())
    write(OUT/'evidence/evaluation.json',dict(rows=rows,graph_ceilings=ceilings,no_full_DS23_accuracy_claim=True,
        no_ALGO_release=True,no_production_defaults_changed=True,frequency_fit_separate_from_position=True))
    for name in ['protocol.json','current_context_correction.json','context_nomination_null.json','independent_iteration_audit.json',
                 'RF_restart_selection.json','DBG01_analysis_execution.json','DBG01_audit_discover_execution.json']:
        shutil.copyfile(RAW/name,OUT/'evidence'/name)
    for folder in ['remaining_curves','family_seeded_growth','curve_diagnostics','support_aware_reentry','family_alternatives','curved_promotion']:
        for name in ['protocol.json','extension_protocol.json','execution.json','independent_nomination_audit.json','finalization_audit.json']:
            if (RAW/folder/name).exists():shutil.copyfile(RAW/folder/name,OUT/'evidence'/(folder+'_'+name))
    shutil.copytree(RAW/'context_v1',OUT/'evidence/context_v1',ignore=shutil.ignore_patterns('single_curve_reentry'),dirs_exist_ok=True)
    tools=['run_ds23_dbg01_iteration_002.py','ds23_current_assignment_context.py','probe_ds23_dbg01_iteration002_extra_curves.py',
           'diagnose_ds23_iteration002_curves.py','finalize_ds23_iteration002_growth.py',
           'probe_ds23_iteration002_family_alternatives.py','probe_ds23_iteration002_curved_promotion.py',Path(__file__).name]
    for name in tools:shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    for name in ['test_ds23_dbg01_iteration_002.py','test_ds23_remaining_curves.py',
                 'test_report_ds23_dbg01_iteration_002.py']:shutil.copyfile(ROOT/'tests/analysis'/name,OUT/'source/tests'/name)
    write(OUT/'evidence/artifact_hashes.json',{str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='artifact_hashes.json' and p.suffix!='.log'})
    print('Iteration002 figures/tables generated',OUT,flush=True)


if __name__=='__main__':main()
