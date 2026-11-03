"""Independent Monte Carlo gate calibration and power; GPS absent from inference."""

import argparse
import time
from pathlib import Path
import numpy as np
from ds23_gate_null import GateState,calibration_cutoff,injection,gate_score,profiled
from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_height import context
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_predictive_linear import OUT as GAUSSIAN
from probe_ds23_robust_predictive_linear import OUT as HISTORY
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.retained_track_likelihood import PERIOD

OUT=ROOT/'reports/2026_10_19_ds23_gate_calibration'
SIZES=dict(calibration=1024,evaluation=1024,power=256,full_Gamma=64)
KINDS=('slope','quadratic','step','receiver_quadratic','satellite_quadratic')
AMPLITUDES=(50.,100.,200.)


def build(scan,node,keep,powers,means,model,arm,entries,position):
    x=np.asarray(position,float);reference=np.zeros(len(means));change=0.
    for _ in range(5):
        p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
        c=p.calculate(x);next_phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        change=float(max(abs(next_phase-reference)));reference=next_phase
    u=c['features'][keep];n,w=u.shape;g=p.noise_groups[keep]
    mean=np.zeros(w);start=p.hardware.shape[1]+p.smooth.shape[1];mean[start:start+len(p.labels)]=means/p.phase_sigma
    curved=[];cursor=0
    for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
        active=keep[sl];count=int(active.sum())
        if not count:continue
        t=scan.tracks[i]
        curved.append(dict(component=t['key'],slice=slice(cursor,cursor+count),times=t['times'][active],
            member_index=k,receiver=t['receiver'],channel=t['channel'],candidate_index=row['candidate_index'],
            observation_ids=np.asarray(t['observation_ids'])[active]))
        cursor+=count
    assert cursor==n
    if entries:
        view,values,sigma_l,groups_l,slices=linear_geometry(p,entries)
        geo=geometry_features(view,x,0.);ul=geo['features'];yl=values-view.q*geo['intercept'];el=geo['elevation']
        linear=[dict(component=e['component'],slice=sl,times=scan.tracks[e['track_index']]['times'],
            receiver=scan.tracks[e['track_index']]['receiver'],candidate_index=e['candidate_index'],
            observation_ids=e['observation_ids']) for e,sl in zip(entries,slices,strict=True)]
    else:
        ul=np.zeros((0,w));yl=np.zeros(0);el=np.zeros(0);sigma_l=np.zeros(0);linear=[]
    state=GateState(u,c['coefficient_prior_precision'],powers[g]*c['noise_precision'][g]/p.point_noise[keep]**2,
        mean,c['coefficient'],curved,ul,linear,w-len(p.members),len(p.members))
    state.sigma=p.point_noise[keep]/np.sqrt(c['noise_precision'][g]);state.sigma_l=sigma_l*np.sqrt(2)
    state.nominal_sigma=p.point_noise[keep];state.groups=g;state.powers=powers
    state.phase_start=start;state.families=len(p.labels);state.model=model
    state.raw=(p.values-p.q*c['intercept'])[keep];state.raw_l=yl
    state.elevation=c['elevation'][keep];state.elevation_l=el;state.phase_change=change
    state.position=x;state.supported=p.supported
    return state


def real_checks(state,cutoff):
    rc=state.raw-state.features@state.coefficient
    rl=state.raw_l-state.linear_features@state.coefficient
    rows=[];scores=[]
    for kind,tracks,values,elev in [('curved',state.curved,rc,state.elevation),('linear',state.linear,rl,state.elevation_l)]:
        for track in tracks:
            sl=track['slice'];r=values[sl];sigma=1000. if kind=='curved' else 300.
            raw=r+(1000.*state.coefficient[state.constant_start+track['member_index']] if kind=='curved' else 0.)
            bias=float(sum(raw)/(len(raw)+150.**2/sigma**2));profile_residual=raw-bias
            score=float(gate_score(profile_residual[:,None],track['times'])[0])
            if kind=='curved':score=max(score,float(gate_score(r[:,None],track['times'])[0]))
            alias_delta=int(np.rint(-float(raw.mean())/PERIOD))
            hard=(np.sqrt(np.mean(profile_residual**2))<=450 and abs(bias)<=3000 and alias_delta==0 and min(elev[sl])>=0)
            if kind=='curved':hard=hard and np.sqrt(np.mean(r*r))<=450
            rows.append(dict(component=track['component'],kind=kind,candidate_index=track['candidate_index'],
                points=len(r),observation_ids=track['observation_ids'],hard_bounds_pass=bool(hard),statistic_ratio=score,
                compatible=bool(hard and score<=cutoff),receiver=track['receiver'],channel=track.get('channel'),
                profile_RMS_hz=float(np.sqrt(np.mean(profile_residual**2))),bias_hz=bias,alias_delta=alias_delta))
            scores.append(score)
    # Linear tracks never contribute independent owners for physical modes.
    while True:
        owners={j:{(r['receiver'],r['channel']) for r in rows if r['kind']=='curved' and r['candidate_index']==j and r['compatible']} for j in state.supported}
        changed=False
        for r in rows:
            if r['kind']=='curved' and r['compatible'] and r['candidate_index'] in owners and len(owners[r['candidate_index']])<2:
                r['compatible']=False;changed=True
        if not changed:break
    return dict(tracks=rows,maximum_statistic_ratio=max(scores),
        phase_reference_qualified=state.phase_change<=.01,
        compatible=all(r['compatible'] for r in rows) and state.phase_change<=.01)


def standard_draws(states,count,seed):
    rng=np.random.default_rng(seed);s=states['c0']
    nc=len(s.features);nl=len(s.linear_features)
    ec=rng.normal(size=(nc,count))*s.sigma[:,None]
    el=rng.normal(size=(nl,count))*s.sigma_l[:,None]
    bias=np.zeros((nl,count))
    for t in s.linear:bias[t['slice']]=300.*rng.normal(size=count)[None,:]
    return ec,el,bias


def paired_scores(states,draws,mode,kind=None,amplitude=0.):
    values=[]
    for state in states.values():
        dc,dl=(None,None) if kind is None else injection(state,kind)
        values.append(state.scores(*draws,mode=mode,injection=None if dc is None else amplitude*dc,
            linear_injection=None if dl is None else amplitude*dl))
    return np.maximum.reduce(values)


def full_Gamma_scores(states,draws):
    result=[]
    for k in range(draws[0].shape[1]):
        scores=[]
        for state in states.values():
            width=len(state.mean);scale=np.ones(width);scale[-state.original_members:]=.3
            prior=np.full(width,-1,int)
            if state.model['nu'] is not None:
                prior[state.phase_start:state.phase_start+state.families]=np.arange(state.families)
            present=np.unique(state.groups)
            b=hierarchical_bound(draws[0][:,k],state.features*scale,state.nominal_sigma,state.groups,
                powers=state.powers[present],prior_groups=prior,prior_nu=4 if state.model['nu'] is None else state.model['nu'])
            fit=b['coefficient']*scale+state.mean
            rc=draws[0][:,k]+state.features@(state.mean-fit)
            rl=draws[1][:,k]+state.linear_features@(state.mean-fit)+draws[2][:,k]
            scores.append(state.score_residuals(rc[:,None],rl[:,None],fit[:,None])[0])
        result.append(max(scores))
    return np.array(result)


def run(case):
    started=time.monotonic();OUT.mkdir(parents=True,exist_ok=True)
    destination=OUT/(case+'.json')
    if destination.exists():raise FileExistsError('preserve scientific outputs')
    scan,node,keep,powers,means,model,_,_=context(case,'archived')
    original=read(GAUSSIAN/(case+'.json'));v=original['results']['all_linear'];entries=v['entries'] if v['paired_valid'] else []
    states={arm:build(scan,node,keep,powers,means,model,arm,entries,v['policy_arms'][arm]['endpoint_east_north_km']) for arm in ('c0','fitted_c')}
    for s in states.values():assert real_checks(s,1.)['compatible'],'individual null replay must pass original gates'
    seed=2026101904+int(case.split('-')[1])*10
    train=paired_scores(states,standard_draws(states,SIZES['calibration'],seed+1),'fitted_centered')
    cutoff=calibration_cutoff(train,.05)
    draws=standard_draws(states,SIZES['evaluation'],seed+2)
    null={m:paired_scores(states,draws,m) for m in ('white','fitted_centered','fitted_plugin')}
    power=[];draws_power=standard_draws(states,SIZES['power'],seed+3)
    for kind in KINDS:
        for amplitude in AMPLITUDES:
            score=paired_scores(states,draws_power,'fitted_centered',kind,amplitude)
            power.append(dict(kind=kind,amplitude_RMS_hz=amplitude,scores=score,
                legacy_detection_fraction=float(np.mean(score>1)),calibrated_detection_fraction=float(np.mean(score>cutoff))))
    gamma=None
    if case in ('DS23-0074','DS23-0217'):
        print(case,'full Gamma validation',flush=True)
        gamma=full_Gamma_scores(states,standard_draws(states,SIZES['full_Gamma'],seed+4))
    saved=next(r for r in read(HISTORY/'history_gate_replay.json')['records'] if r['case']==case)
    actual={}
    for name in ('individual_null','stationary_prefix'):
        actual[name]={}
        for arm in ('c0','fitted_c'):
            state=states[arm] if name=='individual_null' else build(scan,node,keep,powers,means,model,arm,entries,saved['controls'][name]['arms'][arm]['endpoint_east_north_km'])
            old=real_checks(state,1.);new=real_checks(state,cutoff)
            assert old['compatible']==saved['controls'][name]['arms'][arm]['compatible'],'legacy gate replay must match'
            actual[name][arm]=dict(position_east_north_km=state.position,legacy=old,calibrated=new)
    write(destination,dict(case=case,cutoff=cutoff,alpha=.05,sizes=SIZES,calibration_scores=train,null_scores=null,power=power,
        full_Gamma_validation_scores=gamma,actual=actual,original_arms=v['policy_arms'],no_GPS_used=True,no_IQ_reread=True,
        same_c0_noise_draws_for_both_c_arms=True,curved_calibration_and_labels_masks_aliases_unchanged=True,
        fixed_Gaussian_approximation_not_full_pipeline_bootstrap=True,
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_gate_null.py'),
        gaussian_input_sha256=sha(GAUSSIAN/(case+'.json')),history_input_sha256=sha(HISTORY/'history_gate_replay.json'),
        seconds=time.monotonic()-started))
    print(case,'complete cutoff',cutoff,'old/new FPR',float(np.mean(null['fitted_centered']>1)),float(np.mean(null['fitted_centered']>cutoff)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
