"""Independent UTC/position replay, then report-only geographic evaluation."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ds23_bracketed_clock import clock_problem,attach_clock_prediction
from probe_ds23_fft_grid_position import setup
from run_ds23_bracketed_clock_v2 import OUT,bind,bounded_shift
from run_algo01_ds23_sample import ROOT,read,write,sha


def replay(case):
    scan,node,keep,base,old,signed,binding,model,powers,means,entries=setup(case)
    r=read(OUT/(case+'.json'));interval=r['interval'];receipts=[]
    for arm in ('c0','fitted_c'):
        saved=r['arms'][arm];shift=bounded_shift(saved['common_UTC_shift_s'],interval)
        if shift!=r['clock_curved_arms'][arm]['common_UTC_shift_s'] and abs(shift-r['clock_curved_arms'][arm]['common_UTC_shift_s'])>1e-12:
            raise ValueError('linear evidence changed the curved-only clock')
        p=clock_problem(scan,node,keep,arm,np.asarray(saved['phase_reference']),powers,means,model,interval,fixed_shift_s=shift)
        attach_clock_prediction(p,entries,powers);c=p.calculate(np.asarray(saved['endpoint_east_north_km']))
        delta=c['negative_twice_elbo']-saved['negative_twice_elbo']
        if abs(delta)>1e-3:raise ValueError('new common-clock fit does not replay')
        original=r['incumbent_arms'][arm]
        p0=clock_problem(scan,node,keep,arm,np.asarray(original['phase_reference']),powers,means,model,interval,fixed_shift_s=0.)
        attach_clock_prediction(p0,entries,powers)
        null=p0.calculate(np.asarray(original['endpoint_east_north_km']))['negative_twice_elbo']-original['negative_twice_elbo']
        if abs(null)>1e-3:raise ValueError('zero-clock fit does not replay')
        receipts.append(dict(arm=arm,RF_replay_difference=delta,zero_clock_RF_difference=null,
            common_shift_s=shift,inside_recorded_interval=True,linear_did_not_calibrate_clock=True))
    return dict(case=case,replays=receipts)


def stats(values):
    x=np.asarray(values)
    return dict(count=len(x),mean_km=float(x.mean()),median_km=float(np.median(x)),
                maximum_km=float(x.max()),below_half_km=int(np.sum(x<=.5)))


def main():
    protocol=bind();cases=protocol['development_cases']+protocol['confirmation_cases']
    for part in ('development','confirmation'):
        e=read(OUT/(part+'_execution.json'))
        if not e['all_terminal'] or len(e['receipts'])!=len(protocol[part+'_cases']) or any('error'in r for r in e['receipts']):
            raise ValueError('all original cases must finish before evaluation')
    with ProcessPoolExecutor(max_workers=12) as pool:
        replays=list(pool.map(replay,cases))
    from report_algo02_ds23 import position_error
    rows=[];summary={};fig,axes=plt.subplots(2,2,figsize=(14,9))
    for k,part in enumerate(('development','confirmation')):
        summary[part]={}
        for col,arm in enumerate(('c0','fitted_c')):
            before=[];after=[];raw=[];shifts=[];boundary=[];accepted=[]
            for case in protocol[part+'_cases']:
                r=read(OUT/(case+'.json'));old=r['incumbent_arms'][arm];trial=r['arms'][arm]
                before.append(position_error(old['endpoint_latlon']));after.append(position_error(r['policy_arms'][arm]['endpoint_latlon']))
                raw.append(position_error(trial['endpoint_latlon']));shifts.append(trial['common_UTC_shift_s'])
                boundary.append(trial['clock_at_boundary']);accepted.append(r['accepted'])
                rows.append(dict(case=case,cohort=part,arm=arm,accepted=r['accepted'],
                    incumbent_error_km=before[-1],policy_error_km=after[-1],raw_trial_error_km=raw[-1],
                    UTC_shift_s=shifts[-1],UTC_interval_width_s=r['interval']['width_s'],
                    UTC_lower_s=r['interval']['lower_s'],UTC_upper_s=r['interval']['upper_s'],clock_at_boundary=boundary[-1],
                    original_frequency_RMS_hz=old['RMS_hz'],trial_frequency_RMS_hz=trial['RMS_hz']))
            d=np.asarray(after)-before
            summary[part][arm]=dict(incumbent=stats(before),policy=stats(after),raw_trial=stats(raw),
                accepted=int(sum(accepted)),clock_boundary_count=int(sum(boundary)),
                median_abs_clock_shift_s=float(np.median(abs(np.asarray(shifts)))),
                improved_scans=int(np.sum(d< -1e-9)),worsened_scans=int(np.sum(d>1e-9)),
                mean_and_median_improve=bool(np.mean(after)<np.mean(before) and np.median(after)<np.median(before)))
            ax=axes[k,col];ax.bar(range(len(d)),1000*d,color=['#b8b8b8' if not good else '#348653' if v<0 else '#c45d67' for good,v in zip(accepted,d)])
            ax.axhline(0,color='black',lw=.8)
            ax.set(xticks=range(len(d)),xticklabels=[c.split('-')[-1] for c in protocol[part+'_cases']],
                   title=f'{part} · {arm}',xlabel='DS23 scan',ylabel='Position error change (m; negative improves)')
            ax.tick_params(axis='x',rotation=60,labelsize=7);ax.grid(axis='y',alpha=.15)
    fig.suptitle('DS23 · common UTC profiled inside recorded timing constraints\nCurved-only clock calibration, then frozen; conditional predictive covariance does not include clock-estimation uncertainty')
    fig.tight_layout(rect=(0,0,1,.92));fig.savefig(OUT/'position_error_changes.png',dpi=175);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(14,5))
    for col,arm in enumerate(('c0','fitted_c')):
        selected=[r for r in rows if r['arm']==arm]
        x=np.arange(len(selected));axes[col].bar(x,[1000*r['UTC_shift_s'] for r in selected],color=['#c45d67' if r['clock_at_boundary'] else '#317bb2' for r in selected])
        upper=np.array([1000*r['UTC_upper_s'] for r in selected]);lower=np.array([1000*r['UTC_lower_s'] for r in selected])
        axes[col].plot(x,upper,':',color='gray');axes[col].plot(x,lower,':',color='gray')
        axes[col].set(title=arm,xlabel='20 development scans, then 20 confirmation scans',ylabel='Common UTC shift (ms)')
        axes[col].axvline(19.5,color='black',lw=.8);axes[col].grid(axis='y',alpha=.15)
    fig.suptitle('Recorded timing intervals and curved-RF clock estimates\nRed: optimum reaches a timing bound; blue: interior · no GPS in clock fit')
    fig.tight_layout(rect=(0,0,1,.9));fig.savefig(OUT/'UTC_profile_bounds.png',dpi=175);plt.close(fig)
    with (OUT/'position_comparison.csv').open('w') as stream:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    primary=all(summary[p]['fitted_c']['mean_and_median_improve'] for p in summary)
    write(OUT/'replay_audit.json',dict(replays=replays,
        maximum_fit_RF_difference=max(abs(a['RF_replay_difference']) for r in replays for a in r['replays']),
        maximum_zero_clock_RF_difference=max(abs(a['zero_clock_RF_difference']) for r in replays for a in r['replays']),
        no_GPS_in_replay=True,all_clocks_in_original_intervals=True))
    write(OUT/'evaluation.json',dict(summary=summary,primary_confirmed=primary,count=40,population=413,
        all_new_jobs_terminal=True,geographic_reference_only_in_reporter=True,goal_achieved=False,
        clock_estimation_uncertainty_not_propagated_to_predictive_linear_covariance=True,
        profile_timing_prior_uniform_bounded_not_claimed_marginal_evidence=True,
        protocol_sha256=sha(OUT/'protocol.json'),source_sha256=sha(Path(__file__))))
    print(summary,flush=True);print('Primary confirmed',primary,flush=True)


if __name__=='__main__':main()
