"""Train-only CFO scale audit and conditional phase uncertainty experiment.

Uses saved numerical observations and causal TLEs; no IQ or pose truth reads.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.special import i0e,logsumexp
from scipy.stats import t as student_t
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states,REFERENCE_RF_HZ,LIGHT_KM_S
from leo.sky.propagation import parse_element_sets
from leo.sky.frames import geodetic_to_ecef_km

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
PREV=ROOT/'2026_09_27_ds6_common_rate_validation'
sys.path.insert(0,str(ROOT/'2026_09_27_ds6_exact_timing'))
from robust import robust_scores,fit_offset


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def log_i0(x):
    return np.log(i0e(x))+np.abs(x)


def estimate_scale(train_residual):
    """MAD matched to a Student-t4 scale, not a Gaussian RMS estimate."""
    median=np.median(train_residual)
    return float(max(10.,np.median(abs(train_residual-median))/student_t.ppf(.75,4)))


def phase_score(y,prediction,kappa):
    """Integrate one uniform circular response intercept; density / uniform."""
    resultant=abs(np.exp(1j*(y-prediction)).sum(axis=-1))
    return log_i0(kappa[:,None,None]*resultant[None,...])-len(y)*log_i0(kappa)[:,None,None]


def score_banks(banks,kappa,weights,geometry=True):
    train=[];phase_all=[];cfo_all=[];concentrations=[]
    for b in banks:
        p=b['geometry'] if geometry else np.zeros_like(b['geometry'])
        # shape: sign, kappa, time, source-pair
        pt=np.stack([phase_score(b['y'][b['mask']],sign*p[...,b['mask']],kappa) for sign in [-1,1]])
        pa=np.stack([phase_score(b['y'],sign*p,kappa) for sign in [-1,1]])
        prior=np.log(weights)[None,:,None,None]
        train.append(logsumexp(logsumexp(b['cfo_train'][None,None,...]+pt+prior,axis=-1),axis=1))
        phase_all.append(logsumexp(logsumexp(b['cfo_train'][None,None,...]+pa+prior,axis=-1),axis=1))
        cfo_all.append(logsumexp(logsumexp(b['cfo_joint'][None,None,...]+pt+prior,axis=-1),axis=1))
        concentrations.append(logsumexp(b['cfo_train'][None,None,...]+pt+prior,axis=-1))
    total=sum(train);z=logsumexp(total)
    cfo_train=sum(logsumexp(b['cfo_train'],axis=-1) for b in banks)
    cfo_joint=sum(logsumexp(b['cfo_joint'],axis=-1) for b in banks)
    answer=dict(training_log_evidence=float(z-np.log(total.size)),
                held_phase_log_predictive=float(logsumexp(sum(phase_all))-z),
                held_cfo_log_predictive=float(logsumexp(sum(cfo_all))-z),
                cfo_only_held_log_predictive=float(logsumexp(cfo_joint)-logsumexp(cfo_train)),
                cfo_only_time_posterior=np.exp(cfo_train-logsumexp(cfo_train)).tolist(),
                phase_time_posterior=np.exp(logsumexp(total,axis=0)-z).tolist(),kappa_posteriors=[])
    for index,conditional in enumerate(concentrations):
        other=sum(train[:index]+train[index+1:]) if len(train)>1 else np.zeros_like(train[0])
        posterior=np.exp(logsumexp(conditional+other[:,None,:],axis=(0,2))-z)
        answer['kappa_posteriors'].append(posterior.tolist())
    return answer


def load_catalogue(plan):
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    snapshot=archive.select_latest_before(plan['start_utc_ns']-505_000_000_000)
    assert snapshot.digest==plan['snapshot_digest']
    payload,_=exclude_labelled_starlink_debris(archive.read(snapshot))
    return parse_element_sets(payload)


def main():
    HERE.mkdir(exist_ok=True)
    source_path=PREV/'geometry-results.json';source=json.loads(source_path.read_text());audit_path=PREV/'geometry-audit.json';audit=json.loads(audit_path.read_text())
    lat,lon=source['observer_from_other_scan_cfo'];la,lo=np.radians([lat,lon]);receiver=geodetic_to_ecef_km(lat,lon,0)
    east=np.array([-np.sin(lo),np.cos(lo),0.]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)])
    coarse=np.arange(-5.,6.);fine=np.arange(-5.,5.001,.25);kappa=np.geomspace(.1,1e4,129);weights=np.ones(len(kappa));weights[[0,-1]]=.5;weights/=weights.sum()
    protocol=dict(source_geometry_sha256=sha(source_path),source_audit_sha256=sha(audit_path),observer_from_other_scan_cfo=[lat,lon],
        scope='Conditional development audit of two scans, eight phase-linked tracks; no geographic search, new IQ, or coordinate truth',
        cfo_scale_rule='Median absolute training residual / t4.ppf(.75), floor 10 Hz; residuals from previous training-selected candidate and integer scan timing; scale frozen before candidate rescoring',
        cfo_model='Student-t4; profile constant offset on training only; fixed 100 Hz versus learned per-track scale; same measurement partitions',
        candidates='All causal labelled Starlink scored on integer timing for both scale arms; union of each arm top 12 per time refined at quarter seconds; fine-grid top six per source/time retained',
        fine_timing_s=fine.tolist(),kappa_grid=kappa.tolist(),kappa_prior='Independent per pair, log-uniform 0.1 to 10000, trapezoid quadrature; uniform response offset integrated analytically',
        comparison='Fixed kappa=1 and marginalized kappa, each with orbital geometry and response-only null; all predictions freeze training nuisances',
        limitations=['Shortlist coverage is conditional on coarse training selection','Independent residual likelihood may overstate information from correlated visits','Only two phase-training visits per pair','Baseline nominal east-west 80 mm; RF phase centers uncalibrated'])
    protocol_path=HERE/'protocol.json'
    if protocol_path.exists():assert json.loads(protocol_path.read_text())==protocol
    else:protocol_path.write_text(json.dumps(protocol,indent=2)+'\n')
    results=[]
    for previous in source['scans']:
        if not previous['evaluable']:continue
        sid=previous['session_id'];plan_path=PREV/(sid+'-plan.json');plan=json.loads(plan_path.read_text());tracks={t['track_id']:t for t in plan['tracks']}
        prior=next(s for s in audit['scans'] if s['session_id']==sid)
        cat=load_catalogue(plan);numbers=np.asarray(cat.satellite_numbers);lookup={str(n):i for i,n in enumerate(numbers)}
        indices=np.array([i for i,name in enumerate(cat.names) if name.upper().startswith('STARLINK')])
        banks={'fixed':[],'learned':[]};track_audits=[];group_audits=[]
        for group,old_group in zip(previous['groups'],prior['groups']):
            assert group['group']==old_group['group']
            phase_times=np.array([o['time_s'] for o in group['observations']]);states={'fixed':[],'learned':[]}
            for tid,old_sat in zip(group['track_ids'],old_group['illustrative_satellite_numbers']):
                tr=tracks[tid];times=np.array(tr['times_s']);mask=np.array(tr['training_mask']);measured=np.array(tr['measured_hz'])
                def predict(chosen,taus,all_times):
                    p,v,valid=propagate_candidate_states(cat,chosen,plan['start_utc_ns'],all_times,taus)
                    u=p-receiver;u/=np.linalg.norm(u,axis=-1)[...,None]
                    return -REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(u*v,axis=-1),u,valid
                pred,_,_=predict([lookup[str(old_sat)]],np.array([prior['illustrative_timing_s']]),times)
                residual=measured-pred[0,0];learned=estimate_scale(residual[mask]);old_offset=float(fit_offset(residual[mask]))
                centered=residual-old_offset
                scales={'fixed':100.,'learned':learned};coarse_scores={arm:[] for arm in scales};valid_all=[]
                for first in range(0,len(indices),256):
                    pred,u,valid=predict(indices[first:first+256],coarse,times)
                    visible=np.any((u@up)[...,mask]>=0,axis=-1)
                    for arm,scale in scales.items():
                        a,_=robust_scores(measured[None,None,:]-pred,mask,sigma=scale)
                        coarse_scores[arm].append(np.where(visible,a,-np.inf))
                    valid_all.extend(valid.tolist())
                valid_all=np.array(valid_all);union=[]
                for arm in scales:
                    a=np.concatenate(coarse_scores[arm]);union.extend(valid_all[np.argsort(a,axis=0)[-12:,:]].ravel().tolist())
                union=np.array(sorted(set(union)))
                pred,u,valid=predict(union,fine,np.r_[times,phase_times]);n=len(times)
                visible=np.any((u[:,:,:n]@up)[...,mask]>=0,axis=-1)
                audit_track=dict(track_id=tid,old_satellite=old_sat,learned_student_t_scale_hz=learned,
                    training_count=int(mask.sum()),held_count=int((~mask).sum()),
                    old_train_rms_hz=float(np.sqrt(np.mean(centered[mask]**2))),old_held_rms_hz=float(np.sqrt(np.mean(centered[~mask]**2))),
                    times_s=times.tolist(),training_mask=mask.tolist(),old_residual_hz=centered.tolist(),
                    refined_catalogue_union_size=len(union),refined_catalogue_valid_size=len(valid))
                for arm,scale in scales.items():
                    a,b=robust_scores(measured[None,None,:]-pred[:,:,:n],mask,sigma=scale);a=np.where(visible,a,-np.inf);b=np.where(visible,b,-np.inf)
                    chosen=np.argsort(a,axis=0)[-6:,:];assert np.all(np.isfinite(np.take_along_axis(a,chosen,axis=0)))
                    projection=np.array([(u[chosen[:,ti],ti,n:]@east) for ti in range(len(fine))])
                    states[arm].append(dict(train=np.take_along_axis(a,chosen,axis=0).T-np.log(len(indices)),
                        joint=np.take_along_axis(b,chosen,axis=0).T-np.log(len(indices)),projection=projection,
                        satellite_numbers=numbers[valid[chosen]].T.tolist()))
                track_audits.append(audit_track)
                print(sid,tid[:20],'learned scale',round(learned,1),'refined candidates',len(union),flush=True)
            for arm in scales:
                a,b=states[arm];scale=2*np.pi*.08*group['rf_hz']/299792458.
                banks[arm].append(dict(y=np.array([o['phase'] for o in group['observations']]),mask=np.array([o['train'] for o in group['observations']]),
                    geometry=(scale*(b['projection'][:,None,:,:]-a['projection'][:,:,None,:])).reshape(len(fine),36,len(phase_times)),
                    cfo_train=(a['train'][:,:,None]+b['train'][:,None,:]).reshape(len(fine),36),
                    cfo_joint=(a['joint'][:,:,None]+b['joint'][:,None,:]).reshape(len(fine),36)))
            group_audits.append(dict(group=group['group'],track_ids=group['track_ids'],observations=group['observations'],
                shortlists={arm:[s['satellite_numbers'] for s in states[arm]] for arm in states}))
        row=dict(session_id=sid,source_plan_sha256=sha(plan_path),track_audits=track_audits,groups=group_audits,arms={})
        for scale_arm,bb in banks.items():
            row['arms'][scale_arm]={}
            for phase_arm,kk,ww in [('fixed_kappa',np.array([1.]),np.array([1.])),('learned_kappa',kappa,weights)]:
                row['arms'][scale_arm][phase_arm]={label:score_banks(bb,kk,ww,geometry=use) for label,use in [('geometry',True),('response_only',False)]}
        (HERE/(sid+'-banks.json')).write_text(json.dumps(banks,default=lambda v:v.tolist())+'\n')
        results.append(row)
        (HERE/'results.json').write_text(json.dumps(dict(protocol_sha256=sha(protocol_path),scans=results),indent=2)+'\n')
    print(json.dumps([{s['session_id']:{c:{p:{g:{k:v for k,v in stats.items() if not k.endswith('posterior') and k!='kappa_posteriors'} for g,stats in arms.items()} for p,arms in ar.items()} for c,ar in s['arms'].items()}} for s in results],indent=2))


if __name__=='__main__':main()
