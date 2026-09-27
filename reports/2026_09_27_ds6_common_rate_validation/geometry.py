"""Exploratory candidate-geometry test at a previously CFO-derived observer.

This does not use pose coordinates or search for a position. Different RF
channels keep separate response offsets. Only baseline sign and scan time
are shared across the disjoint source pairs.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.special import logsumexp
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states,REFERENCE_RF_HZ,LIGHT_KM_S
from leo.sky.propagation import parse_element_sets
from leo.sky.frames import geodetic_to_ecef_km

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'2026_09_27_ds6_exact_timing'))
from robust import robust_scores
sys.path.insert(0,str(ROOT/'2026_09_27_ds6_orbit_phase'))
from run import phase_evidence


def score_banks(banks,geometry=True):
    training=[];phase_all=[];cfo_all=[]
    for b in banks:
        prediction=b['geometry'] if geometry else np.zeros_like(b['geometry'])
        fit=np.stack([phase_evidence(b['y'][b['mask']],sign*prediction[...,b['mask']],np.ones(b['mask'].sum())) for sign in [-1,1]])
        all_=np.stack([phase_evidence(b['y'],sign*prediction,np.ones(len(b['y']))) for sign in [-1,1]])
        training.append(logsumexp(b['cfo_train']+fit,axis=-1))
        phase_all.append(logsumexp(b['cfo_train']+all_,axis=-1))
        cfo_all.append(logsumexp(b['cfo_joint']+fit,axis=-1))
    total=sum(training);z=logsumexp(total)
    cfo_train=sum(logsumexp(b['cfo_train'],axis=-1) for b in banks)
    cfo_joint=sum(logsumexp(b['cfo_joint'],axis=-1) for b in banks)
    return dict(training_log_evidence=float(z-np.log(total.size)),
                held_phase_log_predictive=float(logsumexp(sum(phase_all))-z),
                held_cfo_log_predictive=float(logsumexp(sum(cfo_all))-z),
                cfo_only_held_log_predictive=float(logsumexp(cfo_joint)-logsumexp(cfo_train)))


def main():
    protocol=json.loads((HERE/'protocol.json').read_text())
    observer_path=ROOT/'2026_09_27_ds6_exact_timing/robust-extended/results.json'
    observer=json.loads(observer_path.read_text())['best']['quarter']['cfo']
    lat,lon=observer['latitude'],observer['longitude'];la,lo=np.radians([lat,lon])
    receiver=geodetic_to_ecef_km(lat,lon,0);east=np.array([-np.sin(lo),np.cos(lo),0.]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)])
    taus=np.arange(-5.,6.);archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    out=dict(observer_from_other_scan_cfo=[lat,lon],observer_sha256=hashlib.sha256(observer_path.read_bytes()).hexdigest(),
             protocol_sha256=hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest(),
             scope='Post-validation exploratory geometry test; one-degree-of-freedom response offset per pair; no position search',
             phase_pipeline='Frozen shared-rate extraction on original qualified windows',
             baseline_m=[-.08,.08],timing_s=taus.tolist(),phase_kappa=1.,cfo_scale_hz=100.,
             candidates='All causal labelled Starlink except labelled debris and propagation failures; training-only top six per track/time retained',scans=[])
    for record in protocol['selected']:
        sid=record['session_id'];plan=json.loads((HERE/(sid+'-plan.json')).read_text());replay=json.loads((HERE/(sid+'-replay.json')).read_text())
        assert replay['complete'] and replay['plan_sha256']==hashlib.sha256((HERE/(sid+'-plan.json')).read_bytes()).hexdigest()
        if not plan['selected_groups']:
            out['scans'].append(dict(session_id=sid,evaluable=False,reason='No selected phase group'));continue
        snapshot=archive.select_latest_before(plan['start_utc_ns']-505_000_000_000)
        assert snapshot.digest==plan['snapshot_digest']
        payload,_=exclude_labelled_starlink_debris(archive.read(snapshot));cat=parse_element_sets(payload)
        indices=np.array([i for i,n in enumerate(cat.names) if n.upper().startswith('STARLINK')])
        tracks={t['track_id']:t for t in plan['tracks']};banks=[];groups=[];used=set()
        for group in plan['selected_groups']:
            visits=[v for v in plan['selected'] if v['group']==group['group']];obs=[]
            for v in visits:
                rr=[r for r in replay['rows'] if r['group']==v['group'] and r['visit']==v['visit'] and r['original']['both_qualified']]
                if not rr:continue
                obs.append(dict(visit=v['visit'],time_s=float(np.mean([r['time_s'] for r in rr])),
                    phase=float(np.angle(np.mean([np.exp(1j*r['shared']['evaluation_dd']) for r in rr]))),
                    train=v['partition']=='train',windows=len(rr)))
            if not any(o['train'] for o in obs) or not any(not o['train'] for o in obs):continue
            states=[];ids=[m['rx0_track_id'] for m in visits[0]['modes']]
            assert not used&set(ids);used.update(ids)
            for tid in ids:
                track=tracks[tid];times=np.array(track['times_s']);mask=np.array(track['training_mask']);scores=[];joint=[];valid_all=[]
                for first in range(0,len(indices),256):
                    p,v,valid=propagate_candidate_states(cat,indices[first:first+256],plan['start_utc_ns'],times,taus)
                    direction=p-receiver;direction/=np.linalg.norm(direction,axis=-1)[...,None]
                    predicted=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(direction*v,axis=-1)
                    visible=np.any((direction@up)[...,mask]>=0,axis=-1)
                    a,b=robust_scores(np.array(track['measured_hz'])[None,None,:]-predicted,mask)
                    scores.append(np.where(visible,a,-np.inf));joint.append(np.where(visible,b,-np.inf));valid_all.extend(valid.tolist())
                a=np.concatenate(scores);b=np.concatenate(joint);valid_all=np.array(valid_all)
                chosen=np.argsort(a,axis=0)[-6:,:]
                assert np.all(np.isfinite(np.take_along_axis(a,chosen,axis=0)))
                union=np.unique(valid_all[chosen])
                p,_,valid=propagate_candidate_states(cat,union,plan['start_utc_ns'],np.array([o['time_s'] for o in obs]),taus)
                assert np.array_equal(valid,union)
                direction=p-receiver;direction/=np.linalg.norm(direction,axis=-1)[...,None]
                lookup={int(v):i for i,v in enumerate(valid)}
                projection=np.array([(direction[[lookup[int(v)] for v in valid_all[chosen[:,ti]]],ti]@east) for ti in range(len(taus))])
                state=dict(train=np.take_along_axis(a,chosen,axis=0).T-np.log(len(indices)),
                           joint=np.take_along_axis(b,chosen,axis=0).T-np.log(len(indices)),projection=projection,
                           satellite_numbers=np.asarray(cat.satellite_numbers)[valid_all[chosen]].T.tolist())
                states.append(state)
                print(sid,tid[:20],'observations',len(times),'catalogue',len(indices),'scored',len(valid_all),flush=True)
            a,b=states;scale=2*np.pi*.08*visits[0]['rf_center_hz']/299792458.
            bank=dict(y=np.array([o['phase'] for o in obs]),mask=np.array([o['train'] for o in obs]),
                geometry=(scale*(b['projection'][:,None,:,:]-a['projection'][:,:,None,:])).reshape(len(taus),36,len(obs)),
                cfo_train=(a['train'][:,:,None]+b['train'][:,None,:]).reshape(len(taus),36),
                cfo_joint=(a['joint'][:,:,None]+b['joint'][:,None,:]).reshape(len(taus),36))
            banks.append(bank);groups.append(dict(group=group['group'],channel=visits[0]['channel'],rf_hz=visits[0]['rf_center_hz'],
                observations=obs,track_ids=ids,shortlists=[s['satellite_numbers'] for s in states]))
        row=dict(session_id=sid,evaluable=bool(banks),groups=groups)
        if banks:
            row.update(geometry=score_banks(banks),response_only=score_banks(banks,False))
            row['geometry_minus_response_only_held_phase']=row['geometry']['held_phase_log_predictive']-row['response_only']['held_phase_log_predictive']
            row['phase_minus_cfo_only_held_cfo']=row['geometry']['held_cfo_log_predictive']-row['geometry']['cfo_only_held_log_predictive']
            (HERE/(sid+'-geometry-banks.json')).write_text(json.dumps(banks,default=lambda v:v.tolist())+'\n')
        out['scans'].append(row)
        (HERE/'geometry-results.json').write_text(json.dumps(out,indent=2)+'\n')
    (HERE/'geometry-results.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps([{k:v for k,v in s.items() if k!='groups'} for s in out['scans']],indent=2))


if __name__=='__main__':main()
