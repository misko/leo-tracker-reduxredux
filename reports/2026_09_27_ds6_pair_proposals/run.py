"""Differential-CFO proposals from all visible catalogue pairs, training only.

Rank all visible pairs by squared demeaned differential-CFO residual, then
score the retained proposals with the frozen robust likelihood and real phase.
"""
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path

import numpy as np
from scipy.special import logsumexp
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states,REFERENCE_RF_HZ,LIGHT_KM_S
from leo.sky.frames import geodetic_to_ecef_km

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
PREV=ROOT/'2026_09_27_ds6_differential_cfo'
spec=importlib.util.spec_from_file_location('differential',PREV/'run.py')
dd=importlib.util.module_from_spec(spec);spec.loader.exec_module(dd)
u=dd.uncertainty


def pair_squared_error(left,right,measured):
    """All-pair SSE after profiling a constant B-A offset.

    Rows are candidates, columns training observations; no held values enter.
    This avoids allocating candidate-A x candidate-B x observation residuals.
    """
    a=left-left.mean(axis=-1,keepdims=True)
    b=right-right.mean(axis=-1,keepdims=True)
    y=measured-measured.mean()
    target=a+y
    return np.maximum(np.sum(target**2,axis=-1)[:,None]+np.sum(b**2,axis=-1)[None,:]-2*target@b.T,0.)


def main():
    source_path=PREV/'results.json';source=json.loads(source_path.read_text())
    previous=json.loads((PREV/'protocol-v2.json').read_text())
    lat,lon=previous['observer_from_other_scan_cfo'];la,lo=np.radians([lat,lon])
    receiver=geodetic_to_ecef_km(lat,lon,0);east=np.array([-np.sin(lo),np.cos(lo),0.]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)])
    times=np.arange(-5.,6.);kappa=np.geomspace(.1,1e4,129);weights=np.ones(129);weights[[0,-1]]=.5;weights/=weights.sum()
    protocol=dict(source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),observer_from_other_scan_cfo=[lat,lon],
        timing_s=times.tolist(),proposal_budgets=[256,512,1024],
        proposal='At each integer scan time, enumerate every training-visible catalogue pair via an exact profiled SSE matrix. Top 1024 SSE proposals are retained, then rescored by frozen Student-t4 likelihood. This is not exhaustive robust-likelihood marginalization.',
        selection='Only paired training CFO values and training visibility select proposals. Phase and held measurements do not select candidates.',
        control='Old absolute-CFO candidate unions re-evaluated on this same integer timing grid; same paired visits, same differential scale, same phase observations',
        prior='Uniform over the full labelled-Starlink Cartesian catalogue before visibility/proposal restriction; selected-bank posterior is approximate',
        validation='Compare 256/512/1024 proposals; report retained conditional mass and held phase/differential-CFO changes without selecting a winner by held score',
        source_epochs='Each mode retains its own support-centre epochs; only common constant receiver offsets cancel exactly',
        scope='Conditional development test on two scans, not a geographic search or verified satellite identification')
    pp=HERE/'protocol.json'
    if pp.exists():assert json.loads(pp.read_text())==protocol
    else:pp.write_text(json.dumps(protocol,indent=2)+'\n')
    results=[]
    for scan in source['scans']:
        sid=scan['session_id'];plan_path=ROOT/'2026_09_27_ds6_common_rate_validation'/(sid+'-plan.json');plan=json.loads(plan_path.read_text());tracks={t['track_id']:t for t in plan['tracks']}
        cat=u.load_catalogue(plan);numbers=np.asarray(cat.satellite_numbers);indices=np.array([i for i,n in enumerate(cat.names) if n.upper().startswith('STARLINK')])
        banks={'restricted':[], '256':[], '512':[], '1024':[]};group_rows=[]
        for group in scan['groups']:
            paired=dd.paired_observations(*[tracks[t] for t in group['track_ids']]);mask=paired['mask'];n=len(mask)
            phase_times=np.array([o['time_s'] for o in group['phase_observations']]);states=[]
            for mode in [0,1]:
                predictions=[];projections=[];visibility=[];valid_all=[]
                for start in range(0,len(indices),256):
                    p,v,valid=propagate_candidate_states(cat,indices[start:start+256],plan['start_utc_ns'],np.r_[paired['source_times'][mode],phase_times],times)
                    direction=p-receiver;direction/=np.linalg.norm(direction,axis=-1)[...,None]
                    predictions.append(-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(direction[:,:,:n]*v[:,:,:n],axis=-1))
                    projections.append(direction[:,:,n:]@east)
                    visibility.append(np.any((direction[:,:,:n]@up)[...,mask]>=0,axis=-1));valid_all.extend(valid.tolist())
                valid_all=np.array(valid_all)
                states.append(dict(pred=np.concatenate(predictions),projection=np.concatenate(projections),visible=np.concatenate(visibility),
                    numbers=numbers[valid_all],lookup={int(num):i for i,num in enumerate(numbers[valid_all])}))
                print(sid,'group',len(group_rows),'mode',mode,'propagated',len(valid_all),flush=True)
            a,b=states;delta=paired['measured'][1]-paired['measured'][0];proposal=[];inventories=[]
            for ti in range(len(times)):
                ia=np.flatnonzero(a['visible'][:,ti]);ib=np.flatnonzero(b['visible'][:,ti])
                score=pair_squared_error(a['pred'][ia,ti][:,mask],b['pred'][ib,ti][:,mask],delta[mask])
                assert score.size>=1024
                chosen=np.argpartition(score.ravel(),1023)[:1024]
                chosen=chosen[np.argsort(score.ravel()[chosen],kind='stable')]
                aa,bb=np.unravel_index(chosen,score.shape);proposal.append(np.column_stack([ia[aa],ib[bb]]))
                inventories.append(dict(timing_s=float(times[ti]),visible_sources=[len(ia),len(ib)],all_visible_pairs=int(score.size),
                    proposal_sse_min=float(score.ravel()[chosen[0]]),proposal_sse_cut=float(score.ravel()[chosen[-1]])))
            proposal=np.array(proposal)
            restricted=np.array([[a['lookup'][int(x)],b['lookup'][int(y)]] for x,y in itertools.product(*group['candidates'])])
            candidate_sets={'restricted':np.repeat(restricted[None,...],len(times),axis=0)}
            candidate_sets.update({str(k):proposal[:,:k,:] for k in [256,512,1024]})
            row=dict(group=group['group'],track_ids=group['track_ids'],proposal_inventory=inventories,old_candidate_pairs=group['candidate_pairs'],
                     differential_scale_hz=group['differential_scale_hz'],phase_observations=group['phase_observations'],candidate_pairs={})
            rf=tracks[group['track_ids'][0]]['rf_hz']
            for arm,pairs in candidate_sets.items():
                ti=np.arange(len(times))[:,None];aa,bb=pairs[:,:,0],pairs[:,:,1]
                residual=delta-(b['pred'][bb,ti]-a['pred'][aa,ti])
                ct,cj=u.robust_scores(residual,mask,sigma=group['differential_scale_hz'])
                visible=a['visible'][aa,ti]&b['visible'][bb,ti]
                ct=np.where(visible,ct,-np.inf)-2*np.log(len(indices));cj=np.where(visible,cj,-np.inf)-2*np.log(len(indices))
                geometry=2*np.pi*.08*rf/299792458.*(b['projection'][bb,ti]-a['projection'][aa,ti])
                bank=dict(y=np.array([o['phase'] for o in group['phase_observations']]),mask=np.array([o['train'] for o in group['phase_observations']]),geometry=geometry,cfo_train=ct,cfo_joint=cj)
                banks[arm].append(bank)
                row['candidate_pairs'][arm]=np.stack([a['numbers'][aa],b['numbers'][bb]],axis=-1).tolist()
            group_rows.append(row)
        row=dict(session_id=sid,source_plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),groups=group_rows,arms={})
        for arm,bb in banks.items():
            row['arms'][arm]={name:u.score_banks(bb,kappa,weights,geometry=use) for name,use in [('geometry',True),('response_only',False)]}
            pr=np.array(row['arms'][arm]['geometry']['cfo_only_time_posterior']);ti=int(np.argmax(pr));audits=[]
            for group,bank in zip(group_rows,bb):
                posterior=np.exp(bank['cfo_train'][ti]-logsumexp(bank['cfo_train'][ti]));pi=int(np.argmax(posterior))
                audits.append(dict(map_time_s=float(times[ti]),map_pair=group['candidate_pairs'][arm][ti][pi],max_pair_probability=float(posterior[pi]),
                                   effective_pairs=float(np.exp(-np.sum(posterior*np.log(np.maximum(posterior,1e-300)))))))
            row['arms'][arm]['candidate_audit']=audits
        # Mass is conditional on the 1024-proposal bank, not a claim about the
        # unscored robust-likelihood tail outside the SSE proposal set.
        time_p=np.array(row['arms']['1024']['geometry']['cfo_only_time_posterior']);retention=[]
        for group,bank in zip(group_rows,banks['1024']):
            scores=bank['cfo_train'];post=np.exp(scores-logsumexp(scores,axis=-1)[:,None])
            retention.append(dict(group=group['group'],mass_first_256=float(time_p@post[:,:256].sum(axis=-1)),mass_first_512=float(time_p@post[:,:512].sum(axis=-1))))
        row['proposal_retention']=retention
        (HERE/(sid+'-banks.json')).write_text(json.dumps(banks,default=lambda v:v.tolist())+'\n')
        results.append(row)
        (HERE/'results.json').write_text(json.dumps(dict(protocol_sha256=hashlib.sha256(pp.read_bytes()).hexdigest(),scans=results),indent=2)+'\n')
    for s in results:
        print(s['session_id'])
        for arm,r in s['arms'].items():
            print(arm,'phase geometry/null',r['geometry']['held_phase_log_predictive'],r['response_only']['held_phase_log_predictive'],
                  'CFO only held',r['geometry']['cfo_only_held_log_predictive'],'phase CFO gain',r['geometry']['held_cfo_log_predictive']-r['geometry']['cfo_only_held_log_predictive'])
        print('retention',s['proposal_retention'])


if __name__=='__main__':main()
