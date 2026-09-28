"""Targeted retrospective diagnosis; no production or geographic search changes."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
from scipy.special import logsumexp

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_26_ds5_probabilistic'))
from run_ds5 import (AdaptiveTlePositionStoreV2,ScannerTrackingInputStore,TleArchiveReader,
    prepare_adaptive_tle_position_inputs,build_prediction_banks,RegionalTrackPredictionEvaluator,point_factory)
from probabilistic_core import fit_profiles,evaluate,scale_at,prior_weights,summarize_grid
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories,PersistentHopTrajectoryConfig,persistent_hop_tracklet_graph
from leo.contracts.digests import canonical_digest
from joint_selection import select_joint

SID='scan-fw-dc1153010e57ac76'


def coarse_score(measured,predicted,train):
    """Candidate x tau training-only centered RMS, with no evaluation access."""
    residual=measured[np.asarray(train,bool)][None,None,:]-predicted[:,:,np.asarray(train,bool)]
    residual-=residual.mean(axis=2,keepdims=True)
    return np.sqrt(np.mean(residual**2,axis=2))


def provenance(source,p,targets):
    candidates=project_scanner_candidates(source)
    trajectory=reconstruct_persistent_hop_trajectories(candidates,config=PersistentHopTrajectoryConfig(minimum_span_s=3.0,minimum_support=6))
    assert trajectory.config_digest==p.trajectory_digest
    graphs={}
    for h in trajectory.hypotheses:
        for tid in h.tracklet_ids:
            if tid in targets:graphs[tid]=persistent_hop_tracklet_graph(h,tid)
    source_groups={}
    for c in candidates:source_groups.setdefault(c.source_group_id,[]).append(c)
    out={}
    for t in p.tracks:
        if t.track_id not in targets:continue
        observations={o.observation_id:o for o in graphs[t.track_id].observations}
        assert set(observations)==set(t.observation_ids)
        aliases=[];points=[]
        for oid in t.observation_ids:
            obs=observations[oid];matches=[]
            for c in source_groups[obs.source_group_id]:
                scale=11_200_000_000./c.actual_rf_hz
                alias=round((c.measured_cfo_hz*scale-obs.measured_cfo_hz)/((1/4.4e-6)*scale))
                binding=canonical_digest({'candidate_id':c.candidate_id,'actual_rf_hz':c.actual_rf_hz,'canonical_rf_hz':11_200_000_000.,'relative_alias_index':alias,'fractional_epoch_used':True})
                if binding==obs.source_binding_digest:matches.append((c,alias))
            assert len(matches)==1
            c,alias=matches[0];points.append(c);aliases.append(alias)
        lane=points[0].lane_key;assert all(c.lane_key==lane for c in points)
        out[t.track_id]={'channel':lane[0],'edge':lane[1].value,'receiver':lane[2],'actual_rf_hz':lane[3],
            'start_s':float(t.times_s.min()),'stop_s':float(t.times_s.max()),'span_s':float(np.ptp(t.times_s)),
            'observations':len(t.times_s),'train_count':int(t.training_mask.sum()),
            'times_s':t.times_s.tolist(),'measured_hz':t.measured_hz.tolist(),'training_mask':t.training_mask.tolist(),
            'source_groups':[c.source_group_id for c in points],'alias_indices':aliases,
            'alias_changes':sum(a!=b for a,b in zip(aliases,aliases[1:])),
            'maximum_observation_gap_s':float(np.diff(t.times_s).max())}
    return out


def group_audit(rows,taus,scales):
    out=[]
    for cid in sorted({r['satellite_id'] for r in rows}):
        group=[r for r in rows if r['satellite_id']==cid]
        lp=prior_weights(taus,scales[cid])+sum(r['train'] for r in group)
        logp=lp-logsumexp(lp)
        score=float(logsumexp(logp+sum(r['test'] for r in group)))
        out.append({'satellite_id':cid,'tracks':[r['track_id'] for r in group],
            'test_count':sum(r['n_test'] for r in group),'conditional_predictive_log_score':score,
            'timing':summarize_grid(taus,logp)})
    return out


def main():
    ds5=json.loads((REPORTS/'2026_09_26_ds5_probabilistic/results.json').read_text())
    previous=next(s for s in ds5['scans'] if s['session_id']==SID)
    sites=previous['sites'];frozen=previous['fixed_identities']
    root=Path('/srv/bulk/leo');store=ScannerTrackingInputStore(root)
    try:
        source=store.load(SID)
        p=prepare_adaptive_tle_position_inputs(SID,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
    finally:store.close()
    assert p.evidence_sha256==previous['evidence_sha256'] and p.snapshot_digest==previous['snapshot_digest']
    target_ids={tid for tid,r in frozen['reference'].items() if r['candidate_id'] in ('64068','53139')}
    targets=[t for t in p.tracks if t.track_id in target_ids]
    detail=provenance(source,p,target_ids)
    coarse=np.arange(-30.,31.,3.)
    candidates={s:{t.track_id:[] for t in targets} for s in sites}
    reuse_coarse='--reuse-coarse' in sys.argv
    if reuse_coarse:candidates=json.loads((HERE/'coarse_candidates.json').read_text())
    for start in ([] if reuse_coarse else range(0,len(p.candidate_indices),256)):
        indices=p.candidate_indices[start:start+256]
        banks,_=build_prediction_banks(p.catalogue,indices,p.start_utc_ns,targets,taus_s=coarse)
        for site,location in sites.items():
            for b in RegionalTrackPredictionEvaluator(banks,point_factory(location['latitude_deg'],location['longitude_deg']),taus_s=coarse)(0,0):
                rms=coarse_score(b.measured_hz,b.predictions_hz,b.training_mask)
                for i,cid in enumerate(b.candidate_ids):
                    if not b.visible[i]:continue
                    j=int(np.argmin(rms[i]))
                    candidates[site][b.track_id].append({'candidate_id':str(cid),'train_rms_hz':float(rms[i,j]),'tau_s':float(coarse[j])})
        if start%2048==0:print('coarse catalogue',start,'/',len(p.candidate_indices),flush=True)
    for site in sites:
        for tid,rows in candidates[site].items():
            candidates[site][tid]=sorted(rows,key=lambda r:(r['train_rms_hz'],int(r['candidate_id'])))[:6]
    (HERE/'coarse_candidates.json').write_text(json.dumps(candidates,indent=2)+'\n')
    history=json.loads((REPORTS/'2026_09_26_reno_track_audit/probabilistic_history.json').read_text())
    lookup={str(n):i for i,n in enumerate(p.catalogue.satellite_numbers)};epochs=p.catalogue.element_epoch_utc_ns()
    taus=np.round(np.arange(-600,601)/10,1);ages={};scales={}
    base={s:[] for s in sites};reassigned={s:[] for s in sites};alternatives={s:{} for s in sites}
    option_profiles={s:{} for s in sites}
    for num,t in enumerate(p.tracks):
        allowed={s:{r['candidate_id'] for r in candidates[s].get(t.track_id,[])}|{frozen[s][t.track_id]['candidate_id']} for s in sites}
        ids=set().union(*allowed.values())
        banks,_=build_prediction_banks(p.catalogue,[lookup[c] for c in sorted(ids)],p.start_utc_ns,[t],taus_s=taus)
        for cid in ids:
            ages[cid]=(p.start_utc_ns-epochs[lookup[cid]])/3.6e12
            scales[cid]=scale_at(ages[cid],history['bins'])
        for site,loc in sites.items():
            options=[]
            for b in RegionalTrackPredictionEvaluator(banks,point_factory(loc['latitude_deg'],loc['longitude_deg']),taus_s=taus)(0,0):
                for i,cidraw in enumerate(b.candidate_ids):
                    cid=str(cidraw)
                    if cid not in allowed[site] or not b.visible[i]:continue
                    prof=fit_profiles(b.measured_hz,b.predictions_hz[i],b.training_mask,100.)
                    row=dict(track_id=t.track_id,satellite_id=cid,weight_s=len(np.unique(np.floor(t.times_s))),**prof)
                    lp=prior_weights(taus,scales[cid])+prof['train'];z=float(logsumexp(lp));logp=lp-z
                    j=int(np.argmax(logp));res=b.measured_hz-b.predictions_hz[i,j]-prof['offset'][j]
                    options.append((z,row,{'candidate_id':cid,'training_log_integrated_profile_likelihood':z,
                        'timing':summarize_grid(taus,logp),'eval_rms_at_training_map_hz':float(np.sqrt(prof['test_mse'][j])),
                        'train_rms_at_training_map_hz':float(np.sqrt(np.mean(res[b.training_mask]**2))),
                        'max_adjacent_residual_jump_hz':float(np.max(np.abs(np.diff(res)))),
                        'residual_hz_at_training_map':res.tolist() if t.track_id in target_ids else None}))
                    if cid==frozen[site][t.track_id]['candidate_id']:base[site].append(row)
            options.sort(key=lambda r:(-r[0],int(r[1]['satellite_id'])))
            assert options
            option_profiles[site][t.track_id]={o[1]['satellite_id']:o[1] for o in options}
            reassigned[site].append(options[0][1])
            if t.track_id in target_ids:alternatives[site][t.track_id]=[o[2] for o in options]
        if num%10==0:print('fine tracks',num+1,'/',len(p.tracks),flush=True)
    results={}
    joint={};joint_receipts={}
    for site in sites:
        chosen,receipt=select_joint(option_profiles[site],{tid:r['candidate_id'] for tid,r in frozen[site].items()},
            {cid:prior_weights(taus,scale) for cid,scale in scales.items()})
        joint[site]=[option_profiles[site][tid][cid] for tid,cid in chosen['ids'].items()]
        joint_receipts[site]={'selected':chosen,'search':receipt}
    for label,rows in [('frozen',base),('targeted_reassignment',reassigned),('joint_training_reassignment',joint)]:
        results[label]={}
        for site,rr in rows.items():
            assert len(rr)==len(p.tracks)
            value=evaluate(rr,taus,taus,np.array([0.]),None,scales)
            results[label][site]=value
            print(label,site,value['negative_log_score_per_test_observation'],value['uncapped_posterior_expected_weighted_rms_hz'],flush=True)
    old=next(e for e in previous['experiments'] if e['noise_scale_hz']==100 and e['mode']=='age_satellite')
    for site in sites:assert abs(results['frozen'][site]['negative_log_score_per_test_observation']-old['sites'][site]['negative_log_score_per_test_observation'])<1e-8
    out={'session_id':SID,'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,
         'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'joint_core_sha256':hashlib.sha256((HERE/'joint_selection.py').read_bytes()).hexdigest(),
         'coarse_candidates_sha256':hashlib.sha256((HERE/'coarse_candidates.json').read_bytes()).hexdigest(),
         'protocol':{'selection':'8 reference-group tracks chosen for diagnosis; all3sites searched independently; fullcatalogue coarse tau +/-30 step3 training RMS top6 plus original candidate; fine +/-60 step0.1 candidate selection training integrated t4 age score, pertrack; shared timing rescored after IDs freeze',
                     'joint_arm':'multi-start training-only coordinate ascent over the same per-site candidate sets, integrating one timing latent per assigned satellite including the 31 unchanged tracks; selection never reads evaluation scores',
                     'limitations':'target selection is retrospective; shortlist not exhaustive fine search; independent arm selects IDs before sharing; joint arm is approximate assignment optimization, not global inference or identity marginalization; old evaluation masks reused; no geography or production changes'},
         'target_tracks':detail,'alternatives':alternatives,'age_hours':ages,'results':results,
         'joint_training_selection':joint_receipts,
         'frozen_group_contributions':{s:group_audit(rr,taus,scales) for s,rr in base.items()},
         'new_group_contributions':{s:group_audit(rr,taus,scales) for s,rr in reassigned.items()},
         'joint_group_contributions':{s:group_audit(rr,taus,scales) for s,rr in joint.items()},
         'timing_authority':source.timing.model_dump(mode='json')}
    (HERE/'results.json').write_text(json.dumps(out,indent=2)+'\n')


if __name__=='__main__':main()
