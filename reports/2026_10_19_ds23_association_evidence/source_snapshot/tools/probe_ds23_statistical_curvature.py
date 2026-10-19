"""Promote additional graph curves with radio-only curvature evidence, not degree."""

import argparse
import copy
from pathlib import Path
import numpy as np

from evaluate_ds23_family_weighting import OUT as WEIGHTS
from evaluate_ds23_phase_refreshed import extend_associations
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED,make_problem,refit
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile

OUT=ROOT/'reports/2026_10_19_ds23_statistical_curvature'


def active_ids(scan,node,keep):
    by_key={t['key']:t for t in scan.tracks};owned=[];offset=0
    for row in node['seed']['rows']:
        if not row['active_curvature']:continue
        ids=by_key[row['component']]['observation_ids'];stop=offset+len(ids)
        owned.extend(oid for oid,active in zip(ids,keep[offset:stop],strict=True) if active)
        offset=stop
    if offset!=len(keep) or len(owned)!=len(set(owned)):
        raise ValueError('exactly one active owner per physical GLRT observation required')
    return set(owned)


def curvature_evidence(times,values,noise):
    t,y,s=map(lambda v:np.asarray(v,float),(times,values,noise));n=len(t)
    if n<12 or np.ptp(t)<20:return dict(eligible=False,reason='short_or_sparse')
    z=(t-t.mean())/np.ptp(t);fits=[]
    for degree in range(1,min(4,n//4-1)+1):
        design=np.vander(z,degree+1,increasing=True)
        coefficient=np.linalg.lstsq(design/s[:,None],y/s,rcond=None)[0]
        prediction=design@coefficient;r=(y-prediction)/s
        fits.append(dict(degree=degree,BIC=float(r@r+(degree+1)*np.log(n)),prediction=prediction))
    best=min(fits,key=lambda r:r['BIC']);gain=fits[0]['BIC']-best['BIC']
    residual=y-best['prediction'];screen=batch_noise_screen(residual[None],t)
    uniform=bool(screen['noise_screen_pass'][0])
    return dict(eligible=best['degree']>1 and gain>=10 and uniform,degree=best['degree'],delta_BIC=gain,
        nonlinear_RMS_hz=float(np.sqrt(np.mean((best['prediction']-fits[0]['prediction'])**2))),
        residual_RMS_hz=float(np.sqrt(np.mean(residual**2))),noise_screen_pass=uniform,points=n,span_s=float(np.ptp(t)))


def replay(scan,node,keep,arm,powers,means,model,saved):
    reference=np.zeros(len(means))
    for h in saved['history']:
        p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
        x=np.array(h['fit']['parameters']);reference=np.clip(p.state(x)['phases'][p.labels],-15,15)
    assert abs(float(p.residual(x)@p.residual(x))-saved['score'])<1e-6
    return p,x


def fragment_alias(p,x,j,i):
    scan=p.scan;track=scan.tracks[i];state=p.state(x);c=p.calculate(x);local=p.labels.index(j)
    bank=dict(time_s=p.sky['time_s'],position_km=p.sky['position_km'][[local]],velocity_km_s=p.sky['velocity_km_s'][[local]])
    times=track['times'];labels=np.zeros(len(times),int);phase=np.array([state['phases'][j]])
    frequency,_=paired_phase_frequency(bank,times,labels,phase,*latlon(x))
    if j in p.supported:
        k=p.supported.index(j);begin=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)
        modes=dict(time_s=p.mode_bank['time_s'],position_km=p.mode_bank['position_km'][3*local:3*local+3],velocity_km_s=p.mode_bank['velocity_km_s'][3*local:3*local+3])
        derivative=paired_frequency_modes(bank,modes,times,labels,phase,*latlon(x))
        frequency+=derivative@c['coefficient'][begin+3*k:begin+3*k+3]
    q=track['rf_hz']/11.5e9;y=track['values']-scan.hardware(track,state['beta'])-q*scan.rx_basis[i]@state['smooth'][track['receiver']-1]
    return int(profile(y,q*frequency,*scan.white[i])['alias'][0])


def run(case):
    scan0=final_scan(case);original=read(SOURCE/case/'result.json');node0=original['final_node']
    source=read(LEARNED/(case+'.json'));assert not source['GPS_used'];primary=source['results']['mean_and_distribution']
    keep0=np.array(primary['mask'],bool);base=problem(scan0,node0,'c0',keep0)
    model=source['hyperparameters_from_pre_RF_TLE_only'];_,receipt=phase_widths(scan0,base.labels)
    means=forecast_phase_mean(receipt,model['shrinkage'])
    powers0=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    fitted={arm:replay(scan0,node0,keep0,arm,powers0,means,model,primary['arms'][arm]) for arm in ('c0','fitted_c')}
    extensions={arm:{r['component']:r for r in extend_associations(p,x,primary['arms'][arm]['gates'])['tracks'] if r['compatible']} for arm,(p,x) in fitted.items()}
    proposals=[];audit=[];existing=set(base.members)
    for i,track in enumerate(scan0.tracks):
        if i in existing:continue
        sigma=np.array([scan0.fixed_window_noise['per_observation_noise_sigma_hz'][oid] if scan0.fixed_window_noise['extra_parameter_BIC_gain']>0 else scan0.radio_sigma_hz for oid in track['observation_ids']])
        evidence=curvature_evidence(track['times'],track['values'],sigma)
        record=dict(component=track['key'],track_index=i,radio=evidence);audit.append(record)
        if not evidence['eligible']:continue
        pair=[extensions[arm].get(track['key']) for arm in ('c0','fitted_c')]
        if any(r is None for r in pair) or pair[0]['candidate_index']!=pair[1]['candidate_index']:
            record['rejection']='no_paired_frozen_family_association';continue
        j=pair[0]['candidate_index'];aliases=[fragment_alias(p,x,j,i) for p,x in fitted.values()]
        if aliases[0]!=aliases[1]:record['rejection']='alias_disagreement';continue
        weight=min(powers0[k] for k,(r,sl) in enumerate(zip(base.rows,base.slices,strict=True)) if r['candidate_index']==j and keep0[sl].any())
        record.update(candidate_index=j,norad=int(scan0.norads[j]),alias=aliases[0],power=weight)
        proposals.append(record)
    proposals.sort(key=lambda r:(-r['radio']['delta_BIC'],r['component']))
    accepted=[];trials=[];final_pair=primary['arms'];node=copy.deepcopy(node0);scan=copy.copy(scan0);keep=keep0.copy();powers=powers0.copy()
    original_ids=active_ids(scan,node,keep)
    for proposal in proposals:
        i=proposal['track_index'];trial_node=copy.deepcopy(node)
        trial_node['seed']['rows'].append(dict(component=proposal['component'],candidate_index=proposal['candidate_index'],candidate_norad=proposal['norad'],active_curvature=True))
        trial_node['aliases'].append(proposal['alias'])
        trial_scan=copy.copy(scan);trial_scan.curved=list(scan.curved)+[i]
        trial_keep=np.r_[keep,np.ones(len(scan.tracks[i]['times']),bool)];trial_powers=np.r_[powers,proposal['power']]
        assert original_ids<=active_ids(trial_scan,trial_node,trial_keep)
        assert {r['candidate_index'] for r in trial_node['seed']['rows']}==set(base.labels)
        pair={arm:refit(trial_scan,trial_node,trial_keep,arm,trial_powers,means,model['multiplier'],model['nu']) for arm in ('c0','fitted_c')}
        failed={r['component'] for arm in pair for r in pair[arm]['gates']['tracks'] if not r['compatible']}
        trials.append(dict(proposal=proposal,arms=pair,accepted=not failed,failed=sorted(failed)))
        if not failed:
            accepted.append(proposal);node,scan,keep,powers=trial_node,trial_scan,trial_keep,trial_powers;final_pair=pair
        print(case,'promotion',proposal['component'],'accepted',not failed,flush=True)
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/(case+'.json'),dict(case=case,arms=final_pair,accepted=accepted,trials=trials,radio_audit=audit,
        fixed_original_mask=keep0,final_mask=keep,final_node=node,final_powers=powers,GPS_used=False,
        original_active_observation_ids=sorted(original_ids),final_active_observation_ids=sorted(active_ids(scan,node,keep)),
        source_sha256=sha(Path(__file__)),learned_input_sha256=sha(LEARNED/(case+'.json')),
        candidate_rule='span>=20s, >=12 points, degree<=4 with >=4 points/coefficient, nonlinear deltaBIC>=10, noise screen',
        existing_family_and_alias_must_agree_in_both_c_arms=True,
        original_calibration_points_never_removed=True,greedy_addition_order_is_radio_BIC_not_GPS=True,
        no_linear_track_calibration=True,observed_values_and_original_radio_noise_unchanged=True))
    print(case,'radio eligible',sum(r['radio']['eligible'] for r in audit),'proposed',len(proposals),'accepted',len(accepted),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
