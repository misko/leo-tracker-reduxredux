"""Exhaust all visible pairs under the robust differential-CFO likelihood.

Block streaming limits memory; a checked 1-D circular integral lookup avoids
repeating a 129-point concentration integral for every satellite pair.
"""
import json
import argparse
import hashlib
import time
from pathlib import Path

import numpy as np
from scipy.special import logsumexp,gammaln
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states,REFERENCE_RF_HZ,LIGHT_KM_S
from leo.sky.frames import geodetic_to_ecef_km
from run import dd,u
from collapsed import PhaseIntegral,combine

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent


def zero_offset_scores(residual,mask,sigma):
    z=residual/sigma
    density=gammaln(2.5)-gammaln(2)-.5*np.log(4*np.pi)-np.log(sigma)-2.5*np.log1p(z*z/4)
    return density[...,mask].sum(axis=-1),density.sum(axis=-1)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--offset',choices=['free','zero'],default='free');args=parser.parse_args()
    prefix='full' if args.offset=='free' else 'zero-offset'
    started=time.monotonic();proposal_path=HERE/'results.json';proposal=json.loads(proposal_path.read_text())
    source=json.loads((ROOT/'2026_09_27_ds6_differential_cfo/results.json').read_text())
    protocol=json.loads((HERE/'protocol.json').read_text());lat,lon=protocol['observer_from_other_scan_cfo'];la,lo=np.radians([lat,lon])
    receiver=geodetic_to_ecef_km(lat,lon,0);east=np.array([-np.sin(lo),np.cos(lo),0.]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)])
    times=np.array(protocol['timing_s']);kappa=np.geomspace(.1,1e4,129);weights=np.ones(129);weights[[0,-1]]=.5;weights/=weights.sum();luts={}
    for n in [2,4]:
        lut=PhaseIntegral(n,kappa,weights);assert lut.audit()<1e-5;luts[n]=lut
    frozen=dict(proposal_results_sha256=hashlib.sha256(proposal_path.read_bytes()).hexdigest(),
        scope='All training-visible Cartesian pairs at fixed observer and integer timing; frozen differential scales and phase model; no position search',
        block_size_left=16,phase_integral='16386-point adaptive deficit grid for each resultant length; audit all interpolation midpoints against 129-point concentration quadrature',
        phase_lookup_error={str(n):lut.audit() for n,lut in luts.items()},
        visibility='Each source must be above the local horizon at one or more training observations; no held measurements select visibility')
    if args.offset=='zero':
        frozen['offset_model']='No constant differential offset is fitted. Assumes nominal common RF carrier and negligible transmitter/branch offsets after receiver cancellation; sensitivity arm, not established calibration.'
    fp=HERE/(prefix+'-protocol.json')
    if fp.exists():assert json.loads(fp.read_text())==frozen
    else:fp.write_text(json.dumps(frozen,indent=2)+'\n')
    results=[]
    for scan,prop_scan in zip(source['scans'],proposal['scans']):
        sid=scan['session_id'];assert sid==prop_scan['session_id']
        plan=json.loads((ROOT/'2026_09_27_ds6_common_rate_validation'/(sid+'-plan.json')).read_text());tracks={t['track_id']:t for t in plan['tracks']}
        cat=u.load_catalogue(plan);numbers=np.asarray(cat.satellite_numbers);indices=np.array([i for i,n in enumerate(cat.names) if n.upper().startswith('STARLINK')]);logprior=-2*np.log(len(indices));group_results=[]
        for gi,(group,prop_group) in enumerate(zip(scan['groups'],prop_scan['groups'])):
            assert group['group']==prop_group['group']
            paired=dd.paired_observations(*[tracks[i] for i in group['track_ids']]);mask=paired['mask'];n=len(mask);delta=paired['measured'][1]-paired['measured'][0]
            obs=group['phase_observations'];y=np.array([o['phase'] for o in obs]);phase_mask=np.array([o['train'] for o in obs]);phase_times=np.array([o['time_s'] for o in obs]);states=[]
            for mode in [0,1]:
                pred=[];projection=[];visible=[];valid_all=[]
                for first in range(0,len(indices),256):
                    p,v,valid=propagate_candidate_states(cat,indices[first:first+256],plan['start_utc_ns'],np.r_[paired['source_times'][mode],phase_times],times)
                    direction=p-receiver;direction/=np.linalg.norm(direction,axis=-1)[...,None]
                    pred.append(-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(direction[:,:,:n]*v[:,:,:n],axis=-1));projection.append(direction[:,:,n:]@east)
                    visible.append(np.any((direction[:,:,:n]@up)[...,mask]>=0,axis=-1));valid_all.extend(valid.tolist())
                states.append(dict(pred=np.concatenate(pred),projection=np.concatenate(projection),visible=np.concatenate(visible),numbers=numbers[np.array(valid_all)]))
            a,b=states;rf=tracks[group['track_ids'][0]]['rf_hz'];scale=2*np.pi*.08*rf/299792458.
            stats=dict(train=np.full((2,len(times)),-np.inf),phase_all=np.full((2,len(times)),-np.inf),cfo_all=np.full((2,len(times)),-np.inf),
                cfo_train=np.full(len(times),-np.inf),cfo_joint=np.full(len(times),-np.inf));moments=np.zeros(len(times));maxima=[]
            retained={str(k):np.full(len(times),-np.inf) for k in [256,512,1024]};counts=[]
            fit_lut=luts[int(phase_mask.sum())];all_lut=luts[len(y)]
            for ti in range(len(times)):
                ia=np.flatnonzero(a['visible'][:,ti]);ib=np.flatnonzero(b['visible'][:,ti]);counts.append(len(ia)*len(ib));best=(-np.inf,None)
                pair_sets={str(k):{tuple(x) for x in prop_group['candidate_pairs'][str(k)][ti]} for k in [256,512,1024]}
                # Catalogue numbers encoded injectively; maxima here are far below 2**32.
                encoded={k:np.array(sorted((int(x)<<32)|int(z) for x,z in ss),dtype=np.uint64) for k,ss in pair_sets.items()}
                for first in range(0,len(ia),16):
                    aa=ia[first:first+16];pa=a['pred'][aa,ti];pb=b['pred'][ib,ti]
                    residual=(delta[None,None,:]-(pb[None,:,:]-pa[:,None,:])).reshape(-1,n)
                    scorer=u.robust_scores if args.offset=='free' else zero_offset_scores
                    ct,cj=scorer(residual,mask,sigma=group['differential_scale_hz']);ct+=logprior;cj+=logprior
                    batch_z=logsumexp(ct);new_z=np.logaddexp(stats['cfo_train'][ti],batch_z)
                    moments[ti]=np.exp(stats['cfo_train'][ti]-new_z)*moments[ti]+np.exp(batch_z-new_z)*float(np.exp(ct-batch_z)@ct)
                    stats['cfo_train'][ti]=new_z;stats['cfo_joint'][ti]=np.logaddexp(stats['cfo_joint'][ti],logsumexp(cj))
                    encoded_pairs=((a['numbers'][aa].astype(np.uint64)[:,None]<<np.uint64(32))|b['numbers'][ib].astype(np.uint64)[None,:]).ravel()
                    for k,keys in encoded.items():
                        use=np.isin(encoded_pairs,keys,assume_unique=True)
                        if use.any():retained[k][ti]=np.logaddexp(retained[k][ti],logsumexp(ct[use]))
                    i=int(np.argmax(ct))
                    if ct[i]>best[0]:best=(float(ct[i]),[int(a['numbers'][aa[i//len(ib)]]),int(b['numbers'][ib[i%len(ib)]])])
                    geometry=(scale*(b['projection'][ib,ti][None,:,:]-a['projection'][aa,ti][:,None,:])).reshape(-1,len(y))
                    for si,sign in enumerate([-1,1]):
                        fit=fit_lut.score(y[phase_mask],sign*geometry[:,phase_mask]);all_=all_lut.score(y,sign*geometry)
                        for field,value in [('train',ct+fit),('phase_all',ct+all_),('cfo_all',cj+fit)]:
                            stats[field][si,ti]=np.logaddexp(stats[field][si,ti],logsumexp(value))
                maxima.append(dict(time_s=float(times[ti]),pair=best[1],max_probability=float(np.exp(best[0]-stats['cfo_train'][ti])),
                                   effective_pairs=float(np.exp(stats['cfo_train'][ti]-moments[ti]))))
                print(sid,'group',gi,'tau',times[ti],'pairs',counts[-1],'elapsed',round(time.monotonic()-started,1),flush=True)
            # Geometry-zero response evidence factors out of all CFO hypotheses.
            flat_train=float(fit_lut.score(y[phase_mask],np.zeros((1,int(phase_mask.sum()))))[0]);flat_all=float(all_lut.score(y,np.zeros((1,len(y))))[0])
            null=dict(train=np.repeat((stats['cfo_train']+flat_train)[None,:],2,axis=0),
                phase_all=np.repeat((stats['cfo_train']+flat_all)[None,:],2,axis=0),cfo_all=np.repeat((stats['cfo_joint']+flat_train)[None,:],2,axis=0),
                cfo_train=stats['cfo_train'],cfo_joint=stats['cfo_joint'])
            group_results.append(dict(group=group['group'],pair_counts=counts,geometry=stats,response_only=null,retained_log_mass=retained,maxima=maxima))
        row=dict(session_id=sid,groups=group_results,geometry=combine([g['geometry'] for g in group_results]),response_only=combine([g['response_only'] for g in group_results]))
        posterior=np.array(row['geometry']['cfo_time_posterior']);ti=int(np.argmax(posterior))
        row['retention']=[dict(group=g['group'],mass={k:float(posterior@np.exp(v-g['geometry']['cfo_train'])) for k,v in g['retained_log_mass'].items()},map=g['maxima'][ti]) for g in group_results]
        results.append(row)
        (HERE/(prefix+'-results.json')).write_text(json.dumps(dict(protocol_sha256=hashlib.sha256(fp.read_bytes()).hexdigest(),complete=False,scans=results),default=lambda v:v.tolist(),indent=2)+'\n')
    (HERE/(prefix+'-results.json')).write_text(json.dumps(dict(protocol_sha256=hashlib.sha256(fp.read_bytes()).hexdigest(),complete=True,elapsed_s=time.monotonic()-started,scans=results),default=lambda v:v.tolist(),indent=2)+'\n')
    for row in results:print(row['session_id'],row['geometry'],row['retention'],flush=True)


if __name__=='__main__':main()
