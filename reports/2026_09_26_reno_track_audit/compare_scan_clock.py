"""Fixed-location clock ablation; never pools geographic proposals."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_26_joint_location_prototype'))
from run_prototype import point_factory
from joint_core import TrackPrediction,profile_track,score_profiled_location
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStoreV2
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.adaptive_tle_prediction import build_prediction_banks,RegionalTrackPredictionEvaluator


def compare(compact,sid):
    free=score_profiled_location([(sid,compact)],0)
    shared=score_profiled_location([(sid,compact)],0,hard_shared=True)
    a,b=free['scans'][0]['tracks'],shared['scans'][0]['tracks']
    return {'per_track':free,'one_per_scan':shared,
            'changed_identities':sum(x is not None and y is not None and x['candidate_id']!=y['candidate_id'] for x,y in zip(a,b))}


def fixed_ids(nuisance):
    output={}
    for name,tracks in nuisance['branches'].items():
        output[name]={}
        for bound in (5,30):
            compact=[]
            for t in tracks:
                p=t['profile']; ix=[i for i,v in enumerate(p['tau_s']) if abs(v)<=bound]
                rows=[{'track_id':t['track_id'],'candidate_id':t['satellite_id'],'tau_s':p['tau_s'][i],
                       'cfo_hz':p['offset_hz'][i],'training_rms_hz':p['train_rms_hz'][i],'reserved_rms_hz':p['score_rms_hz'][i]} for i in ix]
                compact.append((t['weight_s'],np.array([p['tau_s'][i] for i in ix]),rows))
            output[name][str(bound)]=compare(compact,nuisance['session_id'])
    return output


def main():
    prior=json.loads((HERE/'results.json').read_text())
    nuisance=json.loads((HERE/'nuisance_results.json').read_text())
    sid=prior['session_id']; root=Path('/srv/bulk/leo')
    manifest=AdaptiveTlePositionStoreV2(root).status(sid).manifest
    assert manifest.document_sha256==prior['document_sha256']
    doc=manifest.document.model_dump(mode='json')
    store=ScannerTrackingInputStore(root)
    try: p=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
    finally: store.close()
    assert p.evidence_sha256==prior['evidence_sha256'] and p.snapshot_digest==prior['snapshot_digest']
    banks,_=build_prediction_banks(p.catalogue,p.candidate_indices,p.start_utc_ns,p.tracks)
    sites={'reference':doc['diagnostics']['reference_evaluation_only'],
           'reno':next(x['selected'] for x in doc['priors'] if x['name']=='reno')}
    output={'session_id':sid,'document_sha256':manifest.document_sha256,'evidence_sha256':p.evidence_sha256,
            'snapshot_digest':p.snapshot_digest,'protocol':{'scope':'two fixed diagnostic locations; no geographic search or candidate sharing',
            'full_catalogue_tau_seconds':[-5,5,1],'timing_and_identity_selection':'training-only in both free and shared arms',
            'shared_clock':'one tau across 46 tracks within this one scan; one independent constant frequency offset per track',
            'weights':'occupied-second weights, same fixed denominator, 800 Hz cap',
            'validation':'original reused evaluation observations; not independent validation',
            'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            'fixed_identity_sensitivity':fixed_ids(nuisance),'full_catalogue':{}}
    for name,site in sites.items():
        merged={}; legacy={}
        for b in RegionalTrackPredictionEvaluator(banks,point_factory(site['latitude_deg'],site['longitude_deg']))(0,0):
            weight=len(np.unique(np.floor(b.times_s)))
            track=TrackPrediction(b.track_id,weight,tuple(map(str,b.candidate_ids)),b.taus_s,b.measured_hz,b.predictions_hz,b.training_mask,b.visible)
            rows=profile_track(track)
            if b.track_id not in merged: merged[b.track_id]=(weight,b.taus_s,rows)
            else:
                previous=merged[b.track_id][2]
                for i,row in enumerate(rows):
                    if row is not None and (previous[i] is None or (row['training_rms_hz'],int(row['candidate_id']))<(previous[i]['training_rms_hz'],int(previous[i]['candidate_id']))): previous[i]=row
            residual=b.measured_hz[None,None,:]-b.predictions_hz
            train=np.asarray(b.training_mask,dtype=bool)
            offset=residual[:,:,train].mean(axis=2)
            centered=residual-offset[:,:,None]
            tr=np.sqrt(np.mean(centered[:,:,train]**2,axis=2))
            te=np.sqrt(np.mean(centered[:,:,~train]**2,axis=2))
            visible=np.asarray(b.visible)
            if visible.ndim==1: visible=visible[:,None]
            tr=np.where(visible,tr,np.inf)
            for i,cid in enumerate(b.candidate_ids):
                j=int(np.argmin(tr[i]))
                if not np.isfinite(tr[i,j]): continue
                row={'track_id':b.track_id,'candidate_id':str(cid),'tau_s':float(b.taus_s[j]),'training_rms_hz':float(tr[i,j]),'reserved_rms_hz':float(te[i,j]),'weight_s':weight}
                key=lambda r:(r['reserved_rms_hz'],r['training_rms_hz'],int(r['candidate_id']))
                if b.track_id not in legacy or key(row)<key(legacy[b.track_id]): legacy[b.track_id]=row
        compact=[merged[t.track_id] for t in p.tracks]
        assert len(compact)==46
        compared=compare(compact,sid)
        denom=sum(x[0] for x in compact)
        baseline=np.sqrt(sum(merged[tid][0]*min(800,row['reserved_rms_hz'])**2 for tid,row in legacy.items())/denom)
        expected=next(x['selected']['capped_weighted_rmse_hz'] for x in doc['priors'] if x['name']=='reno') if name=='reno' else np.sqrt(sum(t['occupied_seconds']*min(800,t['reference_top3'][0]['score_hz'])**2 for t in prior['tracks'])/denom)
        assert abs(baseline-expected)<1e-6
        compared['legacy_evaluation_selected_rms_hz']=float(baseline)
        compared['legacy_parity_difference_hz']=float(baseline-expected)
        compared['changed_from_legacy']=sum(row is not None and row['candidate_id']!=legacy[row['track_id']]['candidate_id'] for row in compared['one_per_scan']['scans'][0]['tracks'])
        output['full_catalogue'][name]=compared
    print(json.dumps(output,indent=2))


if __name__=='__main__': main()
