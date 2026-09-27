"""Matched-visit absolute versus differential CFO candidate weighting."""
import importlib.util
import json
import hashlib
from pathlib import Path

import numpy as np
from scipy.special import logsumexp
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states,REFERENCE_RF_HZ,LIGHT_KM_S
from leo.sky.frames import geodetic_to_ecef_km

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
PREV=ROOT/'2026_09_27_ds6_uncertainty_audit'
BASE=ROOT/'2026_09_27_ds6_common_rate_validation'
spec=importlib.util.spec_from_file_location('uncertainty',PREV/'run.py')
uncertainty=importlib.util.module_from_spec(spec);spec.loader.exec_module(uncertainty)


def paired_observations(left,right):
    """Join same-visit observations with centroids within one pilot period.

    Their orbital predictions retain their own epochs. Only a constant common
    receiver offset cancels exactly when the centroids are not identical.
    """
    assert left['receiver_id']==right['receiver_id']==0
    assert left['rf_hz']==right['rf_hz'] and left['channel']==right['channel']
    assert len(set(left['visits']))==len(left['visits'])
    assert len(set(right['visits']))==len(right['visits'])
    a={v:i for i,v in enumerate(left['visits'])};b={v:i for i,v in enumerate(right['visits'])}
    common=sorted(set(a)&set(b));ia=[a[v] for v in common];ib=[b[v] for v in common]
    times=np.array(left['times_s'])[ia];other_times=np.array(right['times_s'])[ib]
    assert np.all(abs(times-other_times)<=1/750),'Centroids differ by more than one pilot period'
    mask=np.array(left['training_mask'])[ia]
    np.testing.assert_array_equal(mask,np.array(right['training_mask'])[ib])
    return dict(visits=common,times=(times+other_times)/2,source_times=np.array([times,other_times]),mask=mask,
                measured=np.array([np.array(left['measured_hz'])[ia],np.array(right['measured_hz'])[ib]]))


def difference_residual(measured,prediction_left,prediction_right):
    # Input predictions: candidate, time, observation. Output: time,pair,observation.
    difference=(prediction_right[None,...]-prediction_left[:,None,...]).transpose(2,0,1,3)
    difference=difference.reshape(difference.shape[0],-1,difference.shape[-1])
    return measured[1]-measured[0]-difference


def main():
    source_path=PREV/'results.json';source=json.loads(source_path.read_text())
    previous_protocol=json.loads((PREV/'protocol.json').read_text());old=json.loads((BASE/'geometry-audit.json').read_text())
    lat,lon=previous_protocol['observer_from_other_scan_cfo'];la,lo=np.radians([lat,lon])
    receiver=geodetic_to_ecef_km(lat,lon,0);east=np.array([-np.sin(lo),np.cos(lo),0.]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)])
    times=np.array(previous_protocol['fine_timing_s']);kappa=np.array(previous_protocol['kappa_grid']);weights=np.ones(len(kappa));weights[[0,-1]]=.5;weights/=weights.sum()
    protocol=dict(source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),observer_from_other_scan_cfo=[lat,lon],timing_s=times.tolist(),
        comparison='Both arms use only same-visit RX0 observations with centroids within one 750 Hz pilot period; each source prediction retains its own epoch. Same candidate union, phase observations and splits. Absolute arm fits each source offset; difference arm fits one B-A offset.',
        timing_correction='Initial protocol incorrectly required identical support centres and failed before scoring. Source-dependent pilot centroids differ by up to 0.936 ms. Common constant offset cancels exactly; nonconstant drift leaves its change between source centroids.',
        differential_scale='Student-t4 MAD scale estimated from training-only B-A residuals at the previous training-selected candidate/time, floor 10 Hz; frozen for all hypotheses',
        candidate_scope='Union of previous fixed/learned CFO top-six quarter-second shortlists per source. All Cartesian pairs retained; no distinct-satellite constraint.',
        phase='Previous common-rate DD observations, independent uniform pair offsets, per-pair log-uniform concentration 0.1 to 10000; baseline sign and scan timing shared',
        interpretation='Conditional exploratory test; held phase scores share the same target across arms, but absolute and differential held CFO scores have different dimensions and cannot be directly compared.',
        no_geographic_search=True)
    path=HERE/'protocol-v2.json'
    if path.exists():assert json.loads(path.read_text())==protocol
    else:path.write_text(json.dumps(protocol,indent=2)+'\n')
    results=[]
    for scan in source['scans']:
        sid=scan['session_id'];plan_path=BASE/(sid+'-plan.json');plan=json.loads(plan_path.read_text());tracks={t['track_id']:t for t in plan['tracks']}
        cat=uncertainty.load_catalogue(plan);numbers=np.asarray(cat.satellite_numbers);lookup={str(n):i for i,n in enumerate(numbers)}
        prior=next(s for s in old['scans'] if s['session_id']==sid);old_t=times.tolist().index(prior['illustrative_timing_s'])
        scale_by_id={a['track_id']:a['learned_student_t_scale_hz'] for a in scan['track_audits']}
        old_sat_by_id={a['track_id']:a['old_satellite'] for a in scan['track_audits']}
        banks={'absolute':[],'differential':[]};groups=[]
        for group in scan['groups']:
            ids=group['track_ids'];paired=paired_observations(*[tracks[i] for i in ids]);n=len(paired['times']);mask=paired['mask']
            assert mask.sum()>=2 and (~mask).sum()>=2
            phase_times=np.array([o['time_s'] for o in group['observations']]);states=[];candidates=[]
            for mode,tid in enumerate(ids):
                selected=sorted({int(v) for arm in group['shortlists'].values() for row in arm[mode] for v in row})
                chosen=[lookup[str(v)] for v in selected]
                p,v,valid=propagate_candidate_states(cat,chosen,plan['start_utc_ns'],np.r_[paired['source_times'][mode],phase_times],times)
                assert np.array_equal(valid,chosen)
                direction=p-receiver;direction/=np.linalg.norm(direction,axis=-1)[...,None]
                pred=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(direction[:,:,:n]*v[:,:,:n],axis=-1)
                visible=np.any((direction[:,:,:n]@up)[...,mask]>=0,axis=-1)
                a,b=uncertainty.robust_scores(paired['measured'][mode][None,None,:]-pred,mask,sigma=scale_by_id[tid])
                states.append(dict(prediction=pred,train=np.where(visible,a,-np.inf),joint=np.where(visible,b,-np.inf),projection=direction[:,:,n:]@east,visible=visible))
                candidates.append(selected)
            a,b=states;na,nb=len(candidates[0]),len(candidates[1]);residual=difference_residual(paired['measured'],a['prediction'],b['prediction'])
            old_index=candidates[0].index(old_sat_by_id[ids[0]])*nb+candidates[1].index(old_sat_by_id[ids[1]])
            seed_residual=residual[old_t,old_index]
            sigma=uncertainty.estimate_scale(seed_residual[mask])
            dt,dj=uncertainty.robust_scores(residual,mask,sigma=sigma)
            visible=(a['visible'][:,None,:]&b['visible'][None,:,:]).transpose(2,0,1).reshape(len(times),-1)
            dt=np.where(visible,dt,-np.inf);dj=np.where(visible,dj,-np.inf)
            at=(a['train'][:,None,:]+b['train'][None,:,:]).transpose(2,0,1).reshape(len(times),-1)
            aj=(a['joint'][:,None,:]+b['joint'][None,:,:]).transpose(2,0,1).reshape(len(times),-1)
            rf=tracks[ids[0]]['rf_hz'];geometry=(2*np.pi*.08*rf/299792458.*(b['projection'][None,...]-a['projection'][:,None,...])).transpose(2,0,1,3).reshape(len(times),na*nb,len(phase_times))
            common=dict(y=np.array([o['phase'] for o in group['observations']]),mask=np.array([o['train'] for o in group['observations']]),geometry=geometry)
            # Equal candidate priors conditional on the common union.
            banks['absolute'].append(dict(common,cfo_train=at-np.log(na*nb),cfo_joint=aj-np.log(na*nb)))
            banks['differential'].append(dict(common,cfo_train=dt-np.log(na*nb),cfo_joint=dj-np.log(na*nb)))
            groups.append(dict(group=group['group'],track_ids=ids,candidates=candidates,visits=paired['visits'],times_s=paired['times'].tolist(),source_times_s=paired['source_times'].tolist(),training_mask=mask.tolist(),
                max_centroid_separation_s=float(np.max(abs(paired['source_times'][1]-paired['source_times'][0]))),
                measured_difference_hz=(paired['measured'][1]-paired['measured'][0]).tolist(),seed_residual_hz=seed_residual.tolist(),differential_scale_hz=sigma,
                source_scales_hz=[scale_by_id[i] for i in ids],candidate_pairs=na*nb,phase_observations=group['observations']))
            print(sid,'paired visits',n,'candidate pairs',na*nb,'DD scale',round(sigma,1),flush=True)
        row=dict(session_id=sid,source_plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),groups=groups,arms={})
        for arm,data in banks.items():
            row['arms'][arm]={label:uncertainty.score_banks(data,kappa,weights,geometry=use) for label,use in [('geometry',True),('response_only',False)]}
            row['arms'][arm]['candidate_audit']=[]
            time_probability=np.array(row['arms'][arm]['geometry']['cfo_only_time_posterior']);ti=int(np.argmax(time_probability))
            for g,bank in zip(groups,data):
                scores=bank['cfo_train'];post=np.exp(scores-logsumexp(scores,axis=-1)[:,None]);pi=int(np.argmax(scores[ti]));nb=len(g['candidates'][1])
                row['arms'][arm]['candidate_audit'].append(dict(map_time_s=float(times[ti]),map_satellites=[g['candidates'][0][pi//nb],g['candidates'][1][pi%nb]],max_pair_probability=float(post[ti].max()),
                    effective_pairs_at_map_time=float(np.exp(-np.sum(post[ti]*np.log(np.maximum(post[ti],1e-300)))))))
        (HERE/(sid+'-banks.json')).write_text(json.dumps(banks,default=lambda v:v.tolist())+'\n')
        results.append(row)
        (HERE/'results.json').write_text(json.dumps(dict(protocol_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),scans=results),indent=2)+'\n')
    for s in results:
        print(s['session_id'])
        for arm,r in s['arms'].items():
            print(arm,'held phase geometry/null',r['geometry']['held_phase_log_predictive'],r['response_only']['held_phase_log_predictive'],
                  'phase gain in own CFO target',r['geometry']['held_cfo_log_predictive']-r['geometry']['cfo_only_held_log_predictive'],r['candidate_audit'])


if __name__=='__main__':main()
