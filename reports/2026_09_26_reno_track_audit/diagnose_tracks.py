"""Bounded reference-conditioned diagnosis of five preselected tracks."""
import json,sys,hashlib
from pathlib import Path
from dataclasses import asdict
import numpy as np
from compare_scan_clock import (ScannerTrackingInputStore,prepare_adaptive_tle_position_inputs,TleArchiveReader,
    build_prediction_banks,RegionalTrackPredictionEvaluator,point_factory,AdaptiveTlePositionStoreV2)
from nuisance_core import fit_profiles,select_fit
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories,PersistentHopTrajectoryConfig,persistent_hop_tracklet_graph
from leo.contracts.digests import canonical_digest

HERE=Path(__file__).resolve().parent
PREFIXES=('ad00e08d','d4446f2d','46b5f08c','f34dd5e9','7f350671')


def main():
    old=json.loads((HERE/'results.json').read_text()); root=Path('/srv/bulk/leo'); sid=old['session_id']
    selected={r['track_id']:r for r in old['tracks'] if r['track_id'][7:15] in PREFIXES}
    store=ScannerTrackingInputStore(root)
    try:
        source=store.load(sid)
        p=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
    finally:store.close()
    assert p.evidence_sha256==old['evidence_sha256'] and p.snapshot_digest==old['snapshot_digest']
    doc=AdaptiveTlePositionStoreV2(root).status(sid).manifest.document.model_dump(mode='json')
    candidates=project_scanner_candidates(source)
    trajectory=reconstruct_persistent_hop_trajectories(candidates,config=PersistentHopTrajectoryConfig(minimum_span_s=3.0,minimum_support=6))
    assert trajectory.config_digest==p.trajectory_digest
    graphs={}
    for h in trajectory.hypotheses:
        for tid in h.tracklet_ids:
            if tid in selected:graphs[tid]=persistent_hop_tracklet_graph(h,tid)
    source_groups={}
    for c in candidates:source_groups.setdefault(c.source_group_id,[]).append(c)
    tracks=[t for t in p.tracks if t.track_id in selected]
    ids={r['id'] for x in selected.values() for r in x['reference_top3']}
    indices=[i for i in p.candidate_indices if str(p.catalogue.satellite_numbers[i]) in ids]
    taus=np.round(np.arange(-150,151)/10,1)
    banks,_=build_prediction_banks(p.catalogue,indices,p.start_utc_ns,tracks,taus_s=taus)
    site=doc['diagnostics']['reference_evaluation_only']
    raw={t.track_id:{} for t in tracks}
    for b in RegionalTrackPredictionEvaluator(banks,point_factory(site['latitude_deg'],site['longitude_deg']),taus_s=taus)(0,0):
        for i,cid in enumerate(b.candidate_ids):
            if str(cid) in {r['id'] for r in selected[b.track_id]['reference_top3']} and b.visible[i]:
                raw[b.track_id][str(cid)]=np.asarray(b.predictions_hz[i])
    epochs=p.catalogue.element_epoch_utc_ns()
    satellite_metadata={str(p.catalogue.satellite_numbers[i]):{'name':p.catalogue.names[i],
                        'element_epoch_utc_ns':epochs[i],'element_age_hours':(p.start_utc_ns-epochs[i])/3.6e12} for i in indices}
    output={'session_id':sid,'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,
            'start_utc_ns':p.start_utc_ns,'snapshot_age_hours':(p.start_utc_ns-p.snapshot_collected_utc_ns)/3.6e12,
            'timing':source.timing.model_dump(mode='json'),'satellites':satellite_metadata,
            'protocol':{'track_prefixes':PREFIXES,'candidate_inventory':'each track original reference top3 only; not full catalogue',
                        'tau_grid':[-15,15,.1],'random_bin_split_seed':20260926,'random_bin_split_count':32,
                        'scope':'diagnostic sensitivity, not independent validation; reference only; no geographic inference',
                        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},'tracks':[]}
    for t in tracks:
        observations={o.observation_id:o for o in graphs[t.track_id].observations}
        assert set(observations)==set(t.observation_ids)
        points=[];aliases=[]
        for oid in t.observation_ids:
            obs=observations[oid];matches=[]
            for c in source_groups[obs.source_group_id]:
                scale=11_200_000_000./c.actual_rf_hz
                alias=round((c.measured_cfo_hz*scale-obs.measured_cfo_hz)/((1/4.4e-6)*scale))
                binding=canonical_digest({'candidate_id':c.candidate_id,'actual_rf_hz':c.actual_rf_hz,'canonical_rf_hz':11_200_000_000.,'relative_alias_index':alias,'fractional_epoch_used':True})
                if binding==obs.source_binding_digest:matches.append((c,alias))
            assert len(matches)==1
            c,alias=matches[0];points.append(c);aliases.append(alias)
        lane=points[0].lane_key
        assert all(c.lane_key==lane for c in points)
        original=selected[t.track_id]
        alternatives=[]
        for cid,pred in raw[t.track_id].items():
            profile,centered=fit_profiles(t.times_s,t.measured_hz,pred,t.training_mask,taus)
            fit=select_fit(profile,centered,t.times_s,t.training_mask,15)
            j=int(np.argmin(profile['train_rms_hz']))
            # A drift extension is diagnostic only; tau held at no-drift optimum.
            splits=[];bins=np.floor(t.times_s).astype(int); groups=np.unique(bins)
            rng=np.random.default_rng(20260926)
            for _ in range(32):
                chosen=rng.choice(groups,size=max(1,min(len(groups)-1,round(.6*len(groups)))),replace=False)
                mask=np.isin(bins,chosen)
                pp,rr=fit_profiles(t.times_s,t.measured_hz,pred,mask,taus)
                ff=select_fit(pp,rr,t.times_s,mask,15)
                splits.append({'train_bins':sorted(map(int,chosen)),'tau_s':ff['tau_s'],'score_rms_hz':ff['score_rms_hz']})
            res=centered[j]
            gap=np.diff(t.times_s)
            alternatives.append({'satellite_id':cid,'fit':fit,'split_sensitivity':splits,
                'residual_hz':res.tolist(),'max_adjacent_residual_jump_hz':float(np.max(np.abs(np.diff(res)))),
                'median_abs_adjacent_residual_jump_hz':float(np.median(np.abs(np.diff(res)))),
                'train_profile_rms_hz':profile['train_rms_hz'],'score_profile_rms_hz':profile['score_rms_hz']})
        output['tracks'].append({'track_id':t.track_id,'span_s':original['span_s'],'original_reference':original['reference_top3'][0],
            'lane':{'channel':lane[0],'edge':lane[1].value,'receiver_id':lane[2],'actual_rf_hz':lane[3]},
            'alias_indices':sorted(set(aliases)),
            'alias_change_count':sum(a!=b for a,b in zip(aliases,aliases[1:])),
            'candidate_rank_counts':{str(k):sum(c.candidate_rank==k for c in points) for k in sorted(set(c.candidate_rank for c in points))},
            'source_groups':[c.source_group_id for c in points],
            'times_s':t.times_s.tolist(),'measured_hz':t.measured_hz.tolist(),'training_mask':t.training_mask.tolist(),
            'max_gap_s':float(np.max(np.diff(t.times_s))), 'alternatives':sorted(alternatives,key=lambda x:x['fit']['train_rms_hz'])})
    print(json.dumps(output,indent=2))


if __name__=='__main__':main()
