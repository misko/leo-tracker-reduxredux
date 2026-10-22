"""Frozen iteration009 reporting; geographic errors are evaluation only."""

from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import repair_ds23_iteration009_targets as repair
import report_ds23_dbg01_iteration_001 as figures
import report_ds23_dbg01_iteration_006 as archive
import report_ds23_dbg01_iteration_007 as diagnostics
from report_ds23_dbg01_iteration_005 import result_row
from report_algo02_ds23 import position_error
from ds23_target_radio_covariance import make_target_problem
from compare_dsx01_frame_joint import conditional_gate
from plot_ds23_worst_association_bottleneck import raw_track_values
from run_algo01_ds23_sample import ROOT,read,write,sha

RAW=repair.runner.RAW
OUT=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_009'


def save(fig,name):
    fig.savefig(OUT/'figures'/name,dpi=145);plt.close(fig)


def trial_records(case):
    for folder,suffix in [('single_curve_reentry_v2','_positions'),('support_aware_reentry',''),
                          ('point_priority_support',''),('point_rich_extra_curve',''),('partial_mask_restoration','')]:
        record=read(RAW/folder/(case+suffix+'.json'))
        for i,t in enumerate(record['trials']):yield folder+':'+str(i),t
    for path in sorted((RAW/'target_radio_covariance_v2').glob(case+'_*.json')):
        yield 'covariance:'+path.stem.removeprefix(case+'_'),read(path)


def trial_tables(case):
    rows=[];gates=[]
    for name,t in trial_records(case):
        for arm,r in t['arms'].items():
            rows.append(dict(case=case,method=name,arm=arm,paired_valid=t['paired_valid'],
                offered_curved_points=t.get('added_curved_points',26 if 'mask' in t and 'component' in t else 0),
                position_error_km=position_error(r['endpoint_latlon']),RMS_hz=r['RMS_hz'],
                active_points=r['active_points'],predictive_points=r.get('predictive_points',0),
                final_phase_change_s=r['final_phase_change_s'],
                rejected_trial_never_adopted=True))
            for gate in r['gates']['tracks']:
                q=gate['conditional_residual_gate'];a=q.get('raw_diagnostics',q['diagnostics'])
                gates.append(dict(case=case,method=name,arm=arm,component=gate['component'],norad=gate['norad'],
                    points=gate['points'],compatible=gate['compatible'],conditional_RMS_hz=q['rms_hz'],
                    mean_z=a['mean_z'],slope_z=a['slope_z'],quadratic_BIC_gain=a['quadratic_bic_gain'],
                    maximum_step_z=a['maximum_step_z'],lag1_autocorrelation=a['lag1_acf'],
                    raw_ACF_limit=4/np.sqrt(gate['points']),covariance_aware=gate.get('covariance_aware_component',False)))
    return rows,gates


def restart_figure(case):
    """Separate intermediate phase-round states from final numerical endpoints."""
    from matplotlib.patches import Circle
    import report_dbg01_algo02_ds23_0268 as old
    records=[read(RAW/case/'DBG01'/f'restart_{i:02d}.json') for i in range(81)];rows=[]
    fig,axes=plt.subplots(1,2,figsize=(16,8),layout='constrained')
    for ax,arm in zip(axes,['c0','fitted_c'],strict=True):
        for n,r in enumerate(records):
            a=r['arms'][arm];start=np.asarray(r['start'])
            ax.scatter(*start,s=20,c='firebrick',edgecolor='black',lw=.4,zorder=4,label='81 starting positions' if n==0 else None)
            ax.annotate(str(r['start_id']),start,xytext=(3,3),textcoords='offset points',fontsize=5)
            for k,h in enumerate(a['history']):
                trace=np.asarray([v['point'] for v in h['descent']['trace']]);end=np.asarray(h['descent']['parameters'])
                if len(trace):ax.plot(trace[:,0],trace[:,1],c='C0',alpha=.13,lw=.6)
                if k<len(a['history'])-1:ax.scatter(*end,marker='D',s=14,facecolors='none',edgecolors='purple',alpha=.3,
                    label='Intermediate phase-round endpoints' if n==0 and k==0 else None)
                rows.append(dict(case=case,arm=arm,start_id=r['start_id'],phase_round=k+1,
                    east_km=end[0],north_km=end[1],is_final_round=k==len(a['history'])-1,
                    final_east_km=a['endpoint_east_north_km'][0],final_north_km=a['endpoint_east_north_km'][1]))
        endpoints=np.array([r['arms'][arm]['endpoint_east_north_km'] for r in records])
        ax.scatter(endpoints[:,0],endpoints[:,1],marker='X',s=100,c='C1',edgecolor='black',lw=.7,zorder=7,label='Final after five phase rounds')
        ax.scatter(*old.REFERENCE_XY,marker='*',s=200,c='limegreen',edgecolor='black',zorder=8,label='GPS: evaluation only')
        center=np.median(endpoints,axis=0)
        ax.annotate(f'Final: E{center[0]:.3f}, N{center[1]:.3f} km',center,xytext=(-160,-60),textcoords='offset points',
                    arrowprops=dict(arrowstyle='->',color='black'),bbox=dict(facecolor='white',alpha=.85,edgecolor='gray'),fontsize=8)
        ax.add_patch(Circle((0,0),10,fill=False,ls='--',color='gray'))
        ax.set(xlim=(-12.6,12.6),ylim=(-12.6,12.6),aspect='equal',title=arm,
               xlabel='East from regional center (km)',ylabel='North from regional center (km)');ax.legend(fontsize=7,loc='upper left');ax.grid(alpha=.2)
    fig.suptitle(case+' · 81 independent starts, five phase-refresh rounds\nCurved labels/aliases may switch per c0 step in the bounded bank; fitted c follows its schedule; predictive labels fixed')
    save(fig,case+'_convergence_10km.png')
    return rows


def partial_figures(d):
    case=d['scan'].case;target=read(RAW/'partial_tail_diagnostic'/(case+'.json'))['rows'][0]
    saved=d['arms']['fitted_c'];p=repair.engine.baseline.build(d,'fitted_c',saved['phase_reference'])
    x=np.asarray(saved['endpoint_east_north_km']);i=target['source_track_index'];track=d['scan'].tracks[i]
    sl=p.slices[target['source_row']];active=p.keep[sl];times=np.asarray(track['times'])
    residual=p.calculate(x)['conditional_residual_hz'][sl]
    _,raw=raw_track_values(track,range(len(times)),{o['observation_id']:o for o in d['observations']})
    fig,axes=plt.subplots(2,2,figsize=(15,10),layout='constrained')
    axes[0,0].scatter(times[active],raw[active]/1000,c='C0',s=20,label='51 original calibration points')
    axes[0,0].scatter(times[~active],raw[~active]/1000,c='crimson',s=20,label='26 unused original points')
    for k,run in enumerate(np.split(np.arange(len(times)),np.flatnonzero(abs(np.diff(raw-track['values']))>1e-5)+1)):
        axes[0,0].plot(times[run],(raw-residual)[run]/1000,c='C2',label='57434 + frozen fitted radio' if k==0 else None)
    for piece in track['pieces']:axes[0,0].axvline(piece['start_s'],c='gray',ls=':',alpha=.7)
    axes[0,0].set(xlabel='Time (s)',ylabel='Native GLRT CFO (kHz)',title='One original source component, two persisted polynomial pieces')
    axes[0,0].legend(fontsize=7)
    rows=[]
    for name,use in [('Prefix51',active),('Unused26',~active),('Whole77',np.ones(len(active),bool))]:
        q=conditional_gate(residual[use],times[use]);a=q['diagnostics']
        rows.append(dict(population=name,points=int(use.sum()),RMS_hz=q['rms_hz'],compatible=q['compatible'],
            mean_z=a['mean_z'],slope_z=a['slope_z'],quadratic_BIC_gain=a['quadratic_bic_gain'],step_z=a['maximum_step_z'],
            lag1=a['lag1_acf'],ACF_limit=4/np.sqrt(use.sum())))
        axes[0,1].plot(times[use],residual[use],'.-',label=name)
    axes[0,1].axhline(0,c='gray');axes[0,1].set(xlabel='Time (s)',ylabel='Frozen incumbent residual (Hz)');axes[0,1].legend()
    for j,r in enumerate(rows):
        axes[1,0].bar(j,r['lag1'],color='C0' if r['compatible'] else 'crimson')
        axes[1,0].scatter(j,r['ACF_limit'],c='black',marker='_',s=150)
    axes[1,0].set_xticks(range(3),[r['population'] for r in rows]);axes[1,0].set(ylabel='Lag-one correlation; black = 4 / sqrt(N)',title='Passing subsets do not imply a passing full source')
    for c in target['candidates'][:4]:axes[1,1].plot(target['times'],c['residual_hz'],'.-',label=f"{c['norad']}: {c['conditional_RMS_hz']:.1f} Hz")
    axes[1,1].axhline(0,c='gray');axes[1,1].set(xlabel='Time (s)',ylabel='Conditional suffix residual (Hz)',title='Causal catalogue prediction at fixed c0 RF endpoint');axes[1,1].legend(fontsize=7)
    for ax in axes.flat:ax.grid(alpha=.2)
    fig.suptitle('DS23-0028 RX1 CH1 T000 · partial-mask recovery diagnosis\nNative points unchanged; no arbitrary split at the calibration boundary; identities remain hypotheses')
    save(fig,'DS23-0028_partial_tail.png');figures.csv_write(OUT/'tables/partial_mask_frozen_checks.csv',rows)

    fig,axes=plt.subplots(3,2,figsize=(15,11),layout='constrained')
    restored=read(RAW/'partial_mask_restoration'/(case+'.json'))['trials'][0]
    models=[('White restoration',restored),('Covariance shape only',read(RAW/'target_radio_covariance_v2'/(case+'_shape_only.json'))),
            ('Covariance training scale',read(RAW/'target_radio_covariance_v2'/(case+'_training_scaled.json')))]
    noise_rows=[]
    for k,(name,t) in enumerate(models):
        r=t['arms']['fitted_c'];dd=dict(d,keep=np.asarray(t['mask'],bool))
        if 'covariance' in t:
            m=t['covariance'];pp=make_target_problem(dd,'fitted_c',r['phase_reference'],t['component'],m['alpha'],m['tau_s'],t['noise_scale'])
        else:pp=repair.engine.baseline.build(dd,'fitted_c',r['phase_reference'])
        rr=pp.calculate(np.asarray(r['endpoint_east_north_km']))['conditional_residual_hz'][sl]
        axes[k,0].plot(times,rr,'.-');axes[k,0].axhline(0,c='gray');axes[k,0].set(ylabel='Raw residual (Hz)',title=name+f" · rejected · error {position_error(r['endpoint_latlon']):.3f} km")
        g=next(g for g in r['gates']['tracks'] if g['component']==target['component']);q=g['conditional_residual_gate']
        raw_stats=q.get('raw_diagnostics',q['diagnostics']);white=q['diagnostics']
        keys=['mean_z','slope_z','maximum_step_z','lag1_acf'];limits=np.array([3,3,4,4/np.sqrt(77)])
        axes[k,1].bar(np.arange(4)-.16,np.array([raw_stats[a] for a in keys])/limits,width=.3,label='Raw')
        if 'covariance' in t:axes[k,1].bar(np.arange(4)+.16,np.array([white[a] for a in keys])/limits,width=.3,label='White innovations (correct Hz mapping)')
        axes[k,1].axhline(1,c='crimson',ls='--');axes[k,1].set_xticks(range(4),['Mean','Slope','Step','ACF']);axes[k,1].set(ylabel='Statistic / original threshold');axes[k,1].legend(fontsize=7)
        for a in ['c0','fitted_c']:
            gg=next(g for g in t['arms'][a]['gates']['tracks'] if g['component']==target['component']);qq=gg['conditional_residual_gate']
            noise_rows.append(dict(method=name,arm=a,compatible=gg['compatible'],raw=qq.get('raw_diagnostics',qq['diagnostics']),innovation=qq['diagnostics']))
    for ax in axes.flat:ax.grid(alpha=.2)
    fig.suptitle('Same restored77 observations · no new nuisance coordinates · fitted c\nCovariance fixes correlation but fails retained raw slope/step checks. No trial is adopted')
    save(fig,'DS23-0028_covariance_position_checks.png');write(OUT/'evidence/covariance_gate_comparison.json',noise_rows)

    record=read(RAW/'other_track_radio_noise'/(case+'.json'))['rows'][0];model=record['model']
    costs=np.array([[next(q['cost'] for q in model['candidates'] if q['alpha']==a and q['tau_s']==tau) for tau in [1,3,10,30,100]] for a in [.1,.3,.6,.9]])
    fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained');im=axes[0].imshow(model['baseline_cost']-costs,aspect='auto',origin='lower')
    axes[0].set_xticks(range(5),[1,3,10,30,100]);axes[0].set_yticks(range(4),[.1,.3,.6,.9]);axes[0].set(xlabel='Tau (s)',ylabel='Correlation alpha',title='Other same-RX polynomial contrasts');fig.colorbar(im,ax=axes[0],label='REML gain over white')
    axes[1].bar([0,1,2],[model['radio_REML_gain'],model['complexity_penalty'],record['target_validation']['radio_REML_gain']],color=['C0','gray','C1'])
    axes[1].set_xticks([0,1,2],['Other-track gain','Training penalty','Target gain']);axes[1].set(ylabel='REML contrast score',title='Shape qualified; target does not set the amplitude');axes[1].grid(axis='y',alpha=.2)
    fig.suptitle('RF-only noise shape: 60 training pieces,1738 contrasts; target77 IDs excluded\nInherited native sigma may use target RF. This is not independent position or identity validation')
    save(fig,'DS23-0028_other_track_noise.png')
    future=read(RAW/'partial_tail_following'/(case+'.json'))['rows'][0];following=[]
    fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained')
    for ax,c in zip(axes,future['candidates'],strict=True):
        for name,q in c['profiles'].items():
            ax.plot(future['times'],q['residual_hz'],'.-',label=f"{name}: {q['conditional_RMS_hz']:.1f} Hz")
            following.append(dict(case=case,component=future['component'],norad=c['norad'],element=name,RMS_hz=q['conditional_RMS_hz'],phase_s=q['phase_s'],used_in_inference=False))
        ax.axhline(0,c='gray');ax.set(xlabel='Time (s)',ylabel='Matched phase-only residual (Hz)',title=f"Partial suffix hypothesis {c['norad']}");ax.legend();ax.grid(alpha=.2)
    fig.suptitle('Causal versus earliest real following TLE · same c0 RF endpoint and posterior\nFollowing epochs and collection are after scan end, within48h; diagnostic only')
    save(fig,'DS23-0028_tail_following_TLE.png');figures.csv_write(OUT/'tables/partial_tail_following_TLE.csv',following)


def overview(rows,ceilings,trials):
    fig,axes=plt.subplots(1,3,figsize=(16,5),layout='constrained')
    for k,case in enumerate(ceilings):
        r=next(r for r in rows if r['case']==case and r['arm']=='fitted_c')
        axes[0].bar(k,r['associated_percent']);axes[0].text(k,r['associated_percent']+1,f"{r['associated_points']}/{r['all_GLRT']}\n{r['associated_percent']:.2f}%",ha='center')
        axes[1].scatter(k,r['position_error_km'],s=100,c='C0',label='Retained incumbent' if k==0 else None)
        sample=[t for t in trials if t['case']==case and t['arm']=='fitted_c']
        axes[1].scatter(np.full(len(sample),k)+np.linspace(-.2,.2,len(sample)),[t['position_error_km'] for t in sample],marker='x',c='crimson',s=30,label='Rejected prototype' if k==0 else None)
        axes[2].bar(k,ceilings[case]['percent'],color='gray');axes[2].text(k,ceilings[case]['percent']+1,f"{ceilings[case]['percent']:.2f}%",ha='center')
    axes[0].set(ylabel='Original GLRT associated (%)',ylim=(0,100));axes[0].axhline(90,c='crimson',ls='--')
    axes[1].set(ylabel='Position error (km)');axes[1].axhline(.5,c='green',ls='--');axes[1].legend(fontsize=7)
    axes[2].set(ylabel='Ceiling inside original graph (%)',ylim=(0,100));axes[2].axhline(90,c='crimson',ls='--')
    for ax in axes:ax.set_xticks(range(2),list(ceilings));ax.grid(axis='y',alpha=.2)
    fig.suptitle('DBG01 iteration009 · bounded negative controls · no accepted change\nRejected endpoints are diagnostics, not new algorithm accuracy. Full-DS23 reference remains unchanged')
    save(fig,'iteration_summary.png')


def main():
    repair.configure();figures.RAW=RAW;figures.OUT=OUT;figures.setup=repair.engine.current_setup
    diagnostics.RAW=RAW;diagnostics.OUT=OUT
    for part in ['figures','tables','evidence','source/tools','source/tests']:(OUT/part).mkdir(parents=True,exist_ok=True)
    assert read(RAW/'independent_iteration_audit.json')['all_passed']
    assert read(RAW/'batch_resume_execution.json')['all_terminal']
    cases=read(RAW/'protocol.json')['cases'];rows=[];families=[];controls=[];residuals=[];following=[];trials=[];gates=[];ceilings={};rounds=[]
    for case in cases:
        d=repair.engine.current_setup(case);initial=read(RAW/case/'inventory.json')['arms'];inv=initial['fitted_c']
        n=inv['total_GLRT'];g=n-inv['outside_graph_points'];ceilings[case]=dict(total_GLRT=n,graph_points=g,percent=100*g/n,
            unused_graph_points=inv['unassociated_graph_points'],outside_graph_points=n-g,minimum_outside_for90=max(0,int(np.ceil(.9*n))-g))
        for a,r in d['arms'].items():rows.append(result_row(case,'Retained incumbent',a,r,initial[a],initial[a]))
        for associated in [True,False]:figures.glrt_figure(d,inv,'retained',associated)
        controls.extend(dict(case=case,**r) for r in figures.current_dbg_figures(case));families.extend(figures.family_rows(case,d));rounds.extend(restart_figure(case))
        residuals.extend(figures.residual_figures(case,d,dict(baseline_arms=d['arms'],selected=None),None));following.extend(diagnostics.track_diagnostics(case,d))
        t,q=trial_tables(case);trials.extend(t);gates.extend(q)
        if case=='DS23-0028':partial_figures(d)
    overview(rows,ceilings,trials)
    for name,data in [('position_and_association',rows),('prototype_trials',trials),('prototype_track_gates',gates),
                      ('family_ablations',families),('all_interventions',controls),('residual_diagnostics',residuals),('following_TLE_profiles',following),('restart_phase_rounds',rounds)]:
        if data:figures.csv_write(OUT/'tables'/(name+'.csv'),data)
    write(OUT/'evidence/evaluation.json',dict(rows=rows,trials=trials,graph_ceilings=ceilings,no_accepted_change=True,
        all_new_trials_rejected=all(not r['paired_valid'] for r in trials),no_full_DS23_or_ALGO_gain_claim=True))
    archive.RAW=RAW;archive.OUT=OUT;archive.archives(cases)
    for name in ['protocol.json','batch_execution.json','batch_resume_execution.json','independent_iteration_audit.json','RF_restart_selection.json']:
        shutil.copyfile(RAW/name,OUT/'evidence'/name)
    names=['run_ds23_dbg01_iteration_009.py','repair_ds23_iteration009_targets.py','diagnose_ds23_iteration009_tracks.py',
        'probe_ds23_point_priority_support.py','probe_ds23_point_rich_extra_curve.py','diagnose_ds23_partial_curved_tail.py',
        'diagnose_ds23_partial_tail_following.py','probe_ds23_partial_mask_restoration.py','ds23_other_track_noise.py',
        'qualify_ds23_partial_radio_noise.py','ds23_target_radio_covariance.py','probe_ds23_target_radio_covariance.py',
        'audit_ds23_target_covariance_innovations.py',Path(__file__).name]
    for name in names:shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    tests=['test_ds23_dbg01_iteration_009.py','test_ds23_iteration009_target_guard.py','test_ds23_priority_partial_diagnostics.py',
        'test_ds23_partial_mask_restoration.py','test_ds23_other_track_noise.py','test_ds23_target_radio_covariance.py']
    for name in tests:shutil.copyfile(ROOT/'tests/analysis'/name,OUT/'source/tests'/name)
    write(OUT/'evidence/source_hashes.json',{str(p.relative_to(OUT)):sha(p) for p in (OUT/'source').rglob('*.py')})
    print('Iteration009 assets complete',flush=True)


if __name__=='__main__':main()
