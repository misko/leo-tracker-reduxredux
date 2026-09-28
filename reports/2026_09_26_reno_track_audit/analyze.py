import sys,json,math
from pathlib import Path
import numpy as np
sys.path.insert(0,'/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_26_joint_location_prototype')
from run_prototype import point_factory
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStoreV2
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.adaptive_tle_prediction import build_prediction_banks,RegionalTrackPredictionEvaluator
sid='scan-fw-d86e8f23c0624bac'
root=Path('/srv/bulk/leo')
manifest=AdaptiveTlePositionStoreV2(root).status(sid).manifest
doc=manifest.document.model_dump(mode='json')
store=ScannerTrackingInputStore(root)
try: p=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
finally: store.close()
assert p.evidence_sha256==doc['evidence_sha256']
assert p.snapshot_digest==doc['diagnostics']['snapshot_digest']
original={r['track_id']:r for r in doc['diagnostics']['selected_track_scores']['reno']}
evidence={r['track_id']:r for r in doc['diagnostics']['track_evidence']}
banks,receipt=build_prediction_banks(p.catalogue,p.candidate_indices,p.start_utc_ns,p.tracks)
ref=doc['diagnostics']['reference_evaluation_only']
ev=RegionalTrackPredictionEvaluator(banks,point_factory(ref['latitude_deg'],ref['longitude_deg']))
by_track={}
for b in ev(0.,0.):
    train=np.asarray(b.training_mask,dtype=bool)
    residual=np.asarray(b.measured_hz)[None,None,:]-b.predictions_hz
    offset=residual[:,:,train].mean(axis=2)
    centered=residual-offset[:,:,None]
    tr=np.sqrt(np.mean(centered[:,:,train]**2,axis=2))
    te=np.sqrt(np.mean(centered[:,:,~train]**2,axis=2))
    visible=np.asarray(b.visible,dtype=bool)
    if visible.ndim==1: visible=np.broadcast_to(visible[:,None],tr.shape)
    state=by_track.setdefault(b.track_id,{'candidates':[]})
    for i,candidate in enumerate(b.candidate_ids):
        masked=np.where(visible[i],tr[i],np.inf)
        ti=int(np.argmin(masked)) if np.isfinite(masked).any() else int(np.argmin(tr[i]))
        row={'id':str(candidate),'visible':bool(visible[i,ti]),'train_hz':float(tr[i,ti]),'score_hz':float(te[i,ti]),'tau_s':float(b.taus_s[ti]),'offset_hz':float(offset[i,ti])}
        if str(candidate)==original[b.track_id]['candidate_id']: state['reno_identity_at_reference']=row
        if row['visible']: state['candidates'].append(row)
rows=[]
for tid,state in by_track.items():
    ranked=sorted(state['candidates'],key=lambda r:(r['score_hz'],r['train_hz'],int(r['id'])))
    train_ranked=sorted(state['candidates'],key=lambda r:(r['train_hz'],int(r['id'])))
    e=evidence[tid]; times=e['times_s']; o=original[tid]
    rows.append({'track_id':tid,'span_s':max(times)-min(times),'start_s':min(times),'end_s':max(times),'occupied_seconds':o['weight_s'],'observations':len(times),'largest_gap_s':max(np.diff(times)), 'reno':{k:v for k,v in o.items() if k!='qualifying_observation_ids'},'reference_top3':ranked[:3],'reference_train_winner':train_ranked[0] if train_ranked else None,'reno_identity_at_reference':state.get('reno_identity_at_reference')})
out={'session_id':sid,'document_sha256':manifest.document_sha256,'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,'scope':'Reference-conditioned diagnosis only; not a location-search improvement or independently verified satellite identity. All candidate tau/CFO fit on original training observations, ranking on original evaluation observations.','tracks':sorted(rows,key=lambda r:-r['span_s'])}
print(json.dumps(out,indent=2))
