"""Falsify a receiver-wide step using other curved families; no position fit."""

from pathlib import Path
import numpy as np

import run_ds23_dbg01_iteration_013 as runner
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'step_transfer_diagnostic'


def affine_eliminated_step(times,residual,sigma,tau):
    t,r,s=map(np.asarray,(times,residual,sigma));w=1/s
    a=np.column_stack((np.ones(len(t)),t-t.mean()))*w[:,None]
    z=r*w;u=(t>=tau)*300*w
    z=z-a@np.linalg.lstsq(a,z,rcond=None)[0];u=u-a@np.linalg.lstsq(a,u,rcond=None)[0]
    information=float(u@u);rhs=float(u@z)
    return dict(amplitude_hz=300*rhs/(1+information),posterior_SD_hz=300/np.sqrt(1+information),
        gain=rhs*rhs/(1+information)-np.log1p(information),information=information)


def only_step_fails(g):
    q=g['conditional_residual_gate'];a=q['diagnostics']
    return bool(q['rms_hz']<=450 and a['mean_z']<=3 and a['slope_z']<=3 and a['quadratic_bic_gain']<=10
        and abs(a['lag1_acf'])<=4/np.sqrt(g['points']) and a['maximum_step_z']>4)


def one(case):
    d=runner.engine.current_setup(case);source=read(runner.RAW/'single_curve_reentry'/(case+'_positions.json'));targets=[]
    saved=d['arms']['c0'];base=runner.engine.baseline.build(d,'c0',saved['phase_reference']);original_residual=base.calculate(np.asarray(saved['endpoint_east_north_km']))['conditional_residual_hz']
    for trial in source['trials']:
        if len(trial['additions'])!=1:continue
        component=trial['additions'][0]['component'];gates=[next(g for g in r['gates']['tracks'] if g['component']==component) for r in trial['arms'].values()]
        if not all(only_step_fails(g) for g in gates):continue
        target=next(t for t in d['scan'].tracks if t['key']==component);arm=trial['arms']['c0'];dd=dict(d,node=trial['node'],keep=np.asarray(trial['mask'],bool),means=np.asarray(trial['means']),entries=trial['entries'])
        p=runner.engine.baseline.build(dd,'c0',arm['phase_reference']);sl=next(sl for r,sl in zip(p.rows,p.slices,strict=True) if r['component']==component);residual=p.calculate(np.asarray(arm['endpoint_east_north_km']))['conditional_residual_hz'][sl]
        n=len(residual);splits=np.arange(4,n-3);sums=np.cumsum(residual)[splits-1];jump=sums/splits-(residual.sum()-sums)/(n-splits)
        z=abs(jump)/(max(np.std(residual,ddof=1),75)*np.sqrt(1/splits+1/(n-splits)));split=int(splits[np.argmax(z)]);tau=float(np.mean(target['times'][split-1:split+1]));controls=[]
        for k,(r,i,sl) in enumerate(zip(base.rows,base.members,base.slices,strict=True)):
            t=d['scan'].tracks[i];use=base.keep[sl];tt=t['times'][use]
            if t['receiver']!=target['receiver'] or r['candidate_norad']==gates[0]['norad'] or sum(tt<tau)<4 or sum(tt>=tau)<4:continue
            rr=original_residual[sl][use];sigma=base.point_noise[sl][use]/np.sqrt(d['powers'][k]);control=affine_eliminated_step(tt,rr,sigma,tau)
            controls.append(dict(component=t['key'],norad=r['candidate_norad'],channel=t['channel'],times=tt,residual_hz=rr,sigma_hz=sigma,**control))
        targets.append(dict(component=component,norad=gates[0]['norad'],receiver=target['receiver'],channel=target['channel'],times=target['times'],residual_hz=residual,
            split_index=split,time_s=tau,observed_step_z=float(max(z)),mean_difference_hz=float(jump[np.argmax(z)]),independent_original_parent_curves=controls))
    write(OUT/(case+'.json'),dict(case=case,targets=targets,diagnostic_only_no_inference_or_threshold_change=True,
        source_result_sha256=sha(runner.RAW/'single_curve_reentry'/(case+'_positions.json'))))
    print(case,'isolated step targets',[(r['time_s'],len(r['independent_original_parent_curves'])) for r in targets],flush=True)


def main():
    runner.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve step falsification diagnostic')
    write(OUT/'protocol.json',dict(source_sha256=sha(Path(__file__)),cases=read(runner.RAW/'protocol.json')['cases'],
        target='single-source trial that fails only the residual step screen in both arms',
        original_gate_threshold4_unchanged=True,event_time='midpoint at maximum original CUSUM split',
        transfer='original-parent curved observations from other satellite families on same receiver, at least4points each side',
        per_curve_affine_removed_only_for_diagnostic_not_calibration=True,event_amplitude_SD_hz=300,
        original_event_proposal_math_reused_no_new_position_fit=True,
        correlated_parent_residuals_not_independent_identity_probabilities=True,
        no_GPS_future_TLE_new_RF_or_point_trimming=True))
    for case in read(runner.RAW/'protocol.json')['cases']:one(case)
    write(OUT/'execution.json',dict(all_terminal=True,all_passed=True))


if __name__=='__main__':main()
