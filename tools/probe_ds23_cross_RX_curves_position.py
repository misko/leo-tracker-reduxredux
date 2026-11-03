"""Paired cold position trials of independently curved opposite-RX native peaks.

Existing labels, masks, noise, replication powers and physical orbit support
are frozen. Extra curves have300Hz constant priors and fixed power.6. Separate
receiver errors are assumed independent; this remains a research hypothesis.
"""

import copy
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np
from inventory_ds23_cross_RX_curves import OUT as INVENTORY
from ds23_frequency_events import make_event_problem
from probe_ds23_frequency_events import refit
from probe_ds23_sign_carrier_position import context_signed
from prototype_dsx01_continuous_position import latlon
from run_ds23_combined_recovery_full import ARMS,valid
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis,whitening,PERIOD

OUT=ROOT/'reports/2026_10_21_ds23_cross_RX_curves_position_v2'
BULK=Path('/srv/bulk/leo/research/ds23-cross-RX-curves-position-v2-20261021')


def add_native_noise(noise,observation_ids,sigma_hz):
    if not np.isfinite(sigma_hz) or sigma_hz<40:raise ValueError('native noise must preserve the40Hz contract floor')
    # Recovered canonical winners retain their original radio uncertainty,
    # including dormant copies in the old graph. Only new native IDs get a SD.
    for oid in observation_ids:noise['per_observation_noise_sigma_hz'].setdefault(oid,float(sigma_hz))


def augment(scan,node,mask,powers,means,hyper,signed,inventory):
    p=make_event_problem(scan,node,mask,'c0',np.asarray(signed['policy_arms']['c0']['phase_reference']),powers,means,hyper,[])
    x=np.array(signed['policy_arms']['c0']['endpoint_east_north_km']);state=p.state(x)
    changed=copy.copy(scan);newnode=copy.deepcopy(node)
    for name in ['tracks','curved','rx_basis','white','index']:setattr(changed,name,list(getattr(scan,name)))
    changed.fixed_window_noise=copy.deepcopy(scan.fixed_window_noise);noise=changed.fixed_window_noise
    if noise['extra_parameter_BIC_gain']<=0:
        noise['per_observation_noise_sigma_hz']={o:scan.radio_sigma_hz for t in scan.tracks for o in t['observation_ids']}
        noise['extra_parameter_BIC_gain']=1.
    added=[];ids=set();occupied=set(inventory['original_occupied_ids'])
    for k,fragment in enumerate(inventory['fragments']):
        family,rx,ch,rf=fragment['group'];rows=fragment['points'];time_s=np.array([r['time_s'] for r in rows]);values=np.array([r['value'] for r in rows])
        newids=[r['observation_id'] for r in rows]
        if occupied.intersection(newids) or ids.intersection(newids) or len(set(newids))!=len(newids):raise ValueError('native point would enter twice')
        ids.update(newids)
        key=inventory['case']+f'-native_paired_RX{rx}_CH{ch}_{k:03d}'
        track=dict(key=key,receiver=rx,channel=ch,rf_hz=rf,times=time_s,values=values,observation_ids=newids,
            pieces=[],indices=[],start_s=float(time_s[0]),end_s=float(time_s[-1]),bank='research',quality_status='research_independent_native_curvature')
        index=len(changed.tracks);changed.tracks.append(track);changed.curved.append(index)
        basis=projected_receiver_basis(time_s);changed.rx_basis.append(basis);changed.white.append(whitening(time_s))
        right=np.clip(np.searchsorted(scan.times,time_s),0,len(scan.times)-1);left=np.maximum(right-1,0)
        ix=np.where(abs(scan.times[right]-time_s)<abs(scan.times[left]-time_s),right,left)
        if np.max(abs(scan.times[ix]-time_s))>1e-6:raise ValueError('native peak missing from original probe time grid')
        changed.index.append(ix)
        f,_=paired_phase_frequency(scan.sky,time_s,np.full(len(time_s),family,int),state['phases'],*latlon(x))
        q=rf/11.5e9;expected=q*f+scan.hardware(track,state['beta'])+q*basis@state['smooth'][rx-1]
        alias=int(np.rint(np.mean(expected-values)/PERIOD))
        newnode['seed']['rows'].append(dict(component=key,active_curvature=True,candidate_index=family,candidate_norad=int(scan.norads[family])))
        newnode['aliases'].append(alias)
        add_native_noise(noise,newids,fragment['sigma_hz'])
        added.append(dict(component=key,track_index=index,points=len(rows),norad=int(scan.norads[family]),candidate_index=family,
            kinds={kind:sum(r['kind']==kind for r in rows) for kind in ['unretained_original','additional_native_peak']},
            observation_ids=newids,curvature=fragment['curvature'],sigma_hz=fragment['sigma_hz'],alias=alias))
    newmask=np.r_[mask,np.ones(sum(r['points'] for r in added),bool)];newpowers=np.r_[powers,np.full(len(added),.6)]
    audit=make_event_problem(changed,newnode,newmask,'c0',np.zeros(len(means)),newpowers,means,hyper,[])
    if audit.labels!=p.labels or audit.supported!=p.supported:raise ValueError('new curves changed phase or physical orbit-mode prior support')
    np.testing.assert_allclose(audit.point_noise[:len(mask)],p.point_noise,rtol=0,atol=0)
    old_values=p.values[mask];new_values=audit.values[:len(mask)][mask]
    np.testing.assert_allclose(old_values,new_values,rtol=0,atol=0)
    return changed,newnode,newmask,newpowers,added


def one(inventory):
    case=inventory['case'];path=BULK/(case+'.json')
    if path.exists():return read(path)
    started=time.monotonic()
    def timeout(*_):raise TimeoutError('180 second opposite RX curve position cap exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(180)
    try:
        scan,node,mask,powers,means,hyper,entries,signed,binding=context_signed(case)
        if sha(binding)!=inventory['signed_incumbent_sha256']:raise ValueError('inventory signed incumbent changed')
        changed,newnode,newmask,newpowers,added=augment(scan,node,mask,powers,means,hyper,signed,inventory)
        arms={a:refit(changed,newnode,newmask,a,newpowers,means,hyper,[],entries) for a in ARMS}
        accepted=valid(arms)
        result=dict(case=case,status='complete',arms=arms,accepted=accepted,paired_valid=accepted,
            policy_arms=arms if accepted else signed['policy_arms'],incumbent_arms=signed['policy_arms'],
            original_mask=mask,new_mask=newmask,original_powers=powers,new_powers=newpowers,added=added,
            independently_curved_native_points=sum(r['points'] for r in added),
            recovered_original_points=sum(r['kinds']['unretained_original'] for r in added),
            same_old_point_values_masks_noise_powers_labels_aliases_and_orbit_support_verified=True,
            no_raw_objective_comparison_between_different_observation_sets=True,
            signed_incumbent_sha256=sha(binding),no_GPS_or_future_TLE_or_new_RF_collection=True,
            cross_RX_noise_independence_is_an_unvalidated_covariance_assumption=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(path,result);print(case,result['status'],result.get('accepted'),result.get('error'),flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True);source=INVENTORY/'inventory.json'
    rows=[r for r in read(source)['rows'] if r['fragments']]
    protocol=dict(cases=sorted(r['case'] for r in rows),workers=6,per_case_seconds=180,
        source_inventory_sha256=sha(source),all_native_curvature_qualified_offers_used=True,
        existing_phase_and_orbit_shape_prior_support_unchanged=True,extra_curve_bias_sigma_hz=300.,new_curve_power=.6,
        cross_RX_measurement_noise_treated_independent=True,
        new_noise_sigma='original radio noise for every canonical ID; only additional native IDs use max(150Hz, original radio-only constant)',
        selection='all old and added original gates in both c arms; exact incumbent fallback on failure',
        no_extra_point_or_label_removal_or_GPS_or_future_TLE_or_new_RF=True,
        matched_c0_fitted_c_observations_priors_and_budgets=True,
        cold_regional_start_km=[0,0],regional_width_km=25.,phase_rounds=5,iterations=48,
        source_sha256=sha(Path(__file__)))
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('frozen opposite RX curve position protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:result=[f.result() for f in as_completed([pool.submit(one,r) for r in rows])]
    write(OUT/'execution.json',dict(rows=result,all_terminal=True,failures=[r for r in result if r['status']!='complete']))


if __name__=='__main__':main()
