"""Zero-time-offset full-catalogue diagnostic at two frozen locations."""
import hashlib
import json
from pathlib import Path
import numpy as np
from compare_scan_clock import (
    AdaptiveTlePositionStoreV2,ScannerTrackingInputStore,
    prepare_adaptive_tle_position_inputs,TleArchiveReader,
    build_prediction_banks,RegionalTrackPredictionEvaluator,point_factory,
    TrackPrediction,profile_track,score_profiled_location,
)

HERE=Path(__file__).resolve().parent


def best_row(old,new):
    if new is None: return old
    if old is None: return new
    key=lambda r:(r['training_rms_hz'],int(r['candidate_id']))
    return min((old,new),key=key)


def main():
    prior=json.loads((HERE/'results.json').read_text())
    previous=json.loads((HERE/'scan_clock_results.json').read_text())
    nuisance=json.loads((HERE/'nuisance_results.json').read_text())
    sid=prior['session_id']; root=Path('/srv/bulk/leo')
    manifest=AdaptiveTlePositionStoreV2(root).status(sid).manifest
    assert manifest.document_sha256==prior['document_sha256']==previous['document_sha256']
    doc=manifest.document.model_dump(mode='json')
    store=ScannerTrackingInputStore(root)
    try: prepared=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
    finally: store.close()
    assert prepared.evidence_sha256==prior['evidence_sha256']==previous['evidence_sha256']
    assert prepared.snapshot_digest==prior['snapshot_digest']==previous['snapshot_digest']
    taus=np.array([0.])
    banks,receipt=build_prediction_banks(prepared.catalogue,prepared.candidate_indices,prepared.start_utc_ns,prepared.tracks,taus_s=taus)
    sites={'reference':doc['diagnostics']['reference_evaluation_only'],
           'reno':next(x['selected'] for x in doc['priors'] if x['name']=='reno')}
    result={'session_id':sid,'document_sha256':manifest.document_sha256,'evidence_sha256':prepared.evidence_sha256,
            'snapshot_digest':prepared.snapshot_digest,'protocol':{'tau_seconds':[0],
            'selection':'satellite identity and constant frequency offset fitted on training only',
            'weighting':'same occupied-second weights; fixed denominator; 800 Hz cap',
            'scope':'two fixed diagnostic locations, no geographic search or Sacramento proposals',
            'visibility':'evaluated at zero-offset epochs',
            'validation':'reused evaluation observations, one selected failure; not independent validation',
            'candidate_count':receipt.candidate_count,
            'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'previous_results_sha256':hashlib.sha256((HERE/'scan_clock_results.json').read_bytes()).hexdigest()},'sites':{}}
    for name,site in sites.items():
        weights={t.track_id:len(np.unique(np.floor(t.times_s))) for t in prepared.tracks}
        rows={tid:None for tid in weights}
        for b in RegionalTrackPredictionEvaluator(banks,point_factory(site['latitude_deg'],site['longitude_deg']),taus_s=taus)(0,0):
            track=TrackPrediction(b.track_id,weights[b.track_id],tuple(map(str,b.candidate_ids)),b.taus_s,b.measured_hz,b.predictions_hz,b.training_mask,b.visible)
            rows[b.track_id]=best_row(rows[b.track_id],profile_track(track)[0])
        compact=[(weights[tid],taus,[row]) for tid,row in rows.items()]
        fit=score_profiled_location([(sid,compact)],0,hard_shared=True)
        chosen=fit['scans'][0]['tracks']
        assert all(r is None or r['tau_s']==0 for r in chosen)
        fit['unmatched_count']=sum(r is None for r in chosen)
        fit['above_cap_count']=sum(r is not None and r['reserved_rms_hz']>800 for r in chosen)
        fit['uncapped_evaluation_rms_hz']=float(np.sqrt(sum(weights[r['track_id']]*r['reserved_rms_hz']**2 for r in chosen)/sum(weights.values()))) if all(r is not None for r in chosen) else None
        fit['identity_changes']={}
        for arm in ('per_track','one_per_scan'):
            old={r['track_id']:r for r in previous['full_catalogue'][name][arm]['scans'][0]['tracks'] if r is not None}
            fit['identity_changes'][arm]=sum(r is not None and r['candidate_id']!=old[r['track_id']]['candidate_id'] for r in chosen)
        fixed=[]
        for t in nuisance['branches'][name]:
            p=t['profile']; j=p['tau_s'].index(0.)
            fixed.append((t['weight_s'],taus,[{'track_id':t['track_id'],'candidate_id':t['satellite_id'],'tau_s':0.,
                          'cfo_hz':p['offset_hz'][j],'training_rms_hz':p['train_rms_hz'][j],'reserved_rms_hz':p['score_rms_hz'][j]}]))
        fit['fixed_identity_sensitivity']=score_profiled_location([(sid,fixed)],0,hard_shared=True)
        result['sites'][name]=fit
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
