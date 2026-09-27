"""Bounded, training-only joint orbit/position/phase development experiment."""
import json,sys,hashlib
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'2026_09_26_ds5_phase_integration'))
from phase_factor import phase_evidence
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.sky.propagation import parse_element_sets
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.sky.frames import geodetic_to_ecef_km
C=299792458.

def cfo_evidence(residual,sigma=100.):
    n=residual.shape[-1];mean=residual.mean(axis=-1);v=sigma**2;prior=1e12
    return -.5*(n*np.log(2*np.pi)+(n-1)*np.log(v)+np.log(v+n*prior)+np.sum((residual-mean[...,None])**2,axis=-1)/v+n*mean**2/(v+n*prior))

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--first-visit',type=int,default=1568);args=parser.parse_args()
    sid='scan-fw-4c56320fb5ca6994';start_visit=args.first_visit
    output=HERE if start_visit==1568 else HERE/f'pair-{start_visit}';output.mkdir(exist_ok=True)
    plan_path=ROOT/'2026_09_27_latest_ten_phase/plan.json';phase_path=ROOT/'2026_09_27_latest_ten_phase'/f'{sid}.json'
    scan=next(s for s in json.loads(plan_path.read_text())['scans'] if s['session_id']==sid)
    member=next(r for r in json.loads((ROOT/'2026_09_27_ds6_roof/manifest.json').read_text())['captures'] if r['session_id']==sid)
    assert member['manifest_sha256']==scan['capture_digest']
    key=next(v['group'] for v in scan['selected'] if v['visit']==start_visit)
    visits=[v for v in scan['selected'] if v['group']==key];data=json.loads(phase_path.read_text())['rows'];obs=[]
    for v in visits:
        rows=[r for r in data if r['visit']==v['visit'] and r['both_qualified']]
        if not rows:continue
        dd=np.array([r['modes'][1]['evaluation']['phase_rad']-r['modes'][0]['evaluation']['phase_rad'] for r in rows])
        obs.append(dict(visit=v['visit'],time_s=float(np.mean([r['time_s'] for r in rows])),phase=float(np.angle(np.mean(np.exp(1j*dd)))),cfo=[m['seeds'][0]['cfo_hz'] for m in v['modes']],train=v['partition']=='train',qualified_windows=len(rows),rf_hz=v['rf_center_hz']))
    times=np.array([r['time_s'] for r in obs]);y=np.array([r['phase'] for r in obs]);train=np.array([r['train'] for r in obs]);cfo=np.array([r['cfo'] for r in obs]).T
    assert train.sum()>=2 and (~train).sum()>=2
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));snapshot=archive.select_latest_before(scan['capture_utc_ns']-505_000_000_000)
    payload,_=exclude_labelled_starlink_debris(archive.read(snapshot));catalogue=parse_element_sets(payload);taus=np.arange(-5.,6.)
    protocol=dict(session_id=sid,selection='Existing six-visit recurring pair beginning at visit 1568; chosen as a previously observed positive phase example; development only',observations=obs,source_manifest_sha256=scan['capture_digest'],plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),phase_sha256=hashlib.sha256(phase_path.read_bytes()).hexdigest(),snapshot_digest=snapshot.digest,cfo_sigma_hz=100.,cfo_offset_prior_std_hz=1e6,phase_kappa_per_dwell=1.,nominal_baseline_m=[-.08,.08],baseline_axis='east-west, sign equally marginalized; uncalibrated nominal fixture',rf='channel center approximation',timing_offsets_s=taus.tolist(),candidates_per_source_per_tau=6,position_grid='latitude 36.8..40.0, longitude -124..-120; 9x9 grid; no coordinate truth supplied',phase_offset='one shared pair offset integrated uniformly',evaluation='Existing random whole-dwell train/held assignments; candidates and position rank from train only',limitations=['CFO GLRT seeds and phase are acquisition-conditioned; product likelihood not independently calibrated','One pair over a few seconds cannot establish dataset-wide location accuracy','Same-time two-source CFO may include common oscillator drift','Top-six catalogue truncation is approximate','Satellite identities and nominal baseline are unverified'])
    protocol['selection']=f'Existing recurring pair beginning at visit {start_visit}; both recurring pairs in this previously studied scan are development examples, not independent confirmation'
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    pos,vel,indices=propagate_candidate_states(catalogue,np.arange(len(catalogue.satellite_numbers)),scan['capture_utc_ns'],times,taus)
    numbers=np.array(catalogue.satellite_numbers)[indices];print('propagated',len(indices),'candidates',flush=True)
    rows=[]
    for lat in np.linspace(36.8,40.,9):
      for lon in np.linspace(-124.,-120.,9):
        receiver=geodetic_to_ecef_km(lat,lon,0);la,lo=np.radians([lat,lon]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]);east=np.array([-np.sin(lo),np.cos(lo),0.])
        dr=pos-receiver;distance=np.linalg.norm(dr,axis=-1);unit=dr/distance[...,None]
        rf=obs[0]['rf_hz'];prediction=-rf/(C/1000)*np.sum(unit*vel,axis=-1)
        visible=np.all(np.sum(unit[:,:,train]*up,axis=-1)>0,axis=-1)
        residual=cfo[:,None,None,:]-prediction[None,:,:,:]
        ct=cfo_evidence(residual[...,train]);cj=cfo_evidence(residual)
        train_base=[];joint_base=[];train_phase=[];joint_phase=[];identities=[]
        for ti,tau in enumerate(taus):
            eligible=np.flatnonzero(visible[:,ti])
            if len(eligible)<6:continue
            chosen=[eligible[np.argsort(ct[m,eligible,ti])[-6:]] for m in [0,1]]
            for ia in chosen[0]:
              for ib in chosen[1]:
                a=ct[0,ia,ti]+ct[1,ib,ti];b=cj[0,ia,ti]+cj[1,ib,ti]
                g=2*np.pi*.08*rf/C*(unit[ib,ti]@east-unit[ia,ti]@east)
                gt=np.array([phase_evidence(y[train],sign*g[train],np.ones(train.sum())) for sign in [-1,1]])
                gj=np.array([phase_evidence(y,sign*g,np.ones(len(y))) for sign in [-1,1]])
                train_base.append(a);joint_base.append(b);train_phase.append(a+logsumexp(gt)-np.log(2));joint_phase.append(b+logsumexp(gj)-np.log(2));identities.append([str(numbers[ia]),str(numbers[ib]),float(tau)])
        normalization=np.log(len(indices)**2*len(taus))
        row=dict(latitude=float(lat),longitude=float(lon),cfo_train=float(logsumexp(train_base)-normalization),joint_train=float(logsumexp(train_phase)-normalization),cfo_held=float(logsumexp(joint_base)-logsumexp(train_base)),joint_held=float(logsumexp(joint_phase)-logsumexp(train_phase)),cfo_map=identities[int(np.argmax(train_base))],joint_map=identities[int(np.argmax(train_phase))])
        rows.append(row)
      print('latitude',lat,'nodes',len(rows),flush=True)
    best_cfo=max(rows,key=lambda r:r['cfo_train']);best_joint=max(rows,key=lambda r:r['joint_train'])
    (output/'results.json').write_text(json.dumps(dict(rows=rows,best_cfo=best_cfo,best_joint=best_joint,valid_catalogue_candidates=len(indices),phase_span_s=float(times[-1]-times[0])),indent=2)+'\n')
    print(json.dumps(dict(best_cfo=best_cfo,best_joint=best_joint)),flush=True)
if __name__=='__main__':main()
