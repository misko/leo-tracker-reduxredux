"""Source-bound fractional frame phases and approximate causal orbital ranges."""
import inspect
import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy.special import logsumexp

HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(PARENT))
sys.path.insert(0,str(ROOT))
from doppler_pilot import fast,read,digest


def phase_us(counter_delta, probe_start_ms, integer_epoch, fraction, sample_rate, frame_rate):
    assert float(sample_rate).is_integer() and float(frame_rate).is_integer()
    # Integer arithmetic first: absolute device counter size cannot erase phase.
    whole=int(counter_delta)+int(integer_epoch)
    residue=(whole*int(frame_rate))%int(sample_rate)
    return ((residue/frame_rate+probe_start_ms*sample_rate/1000+fraction)%(sample_rate/frame_rate))/sample_rate*1e6


def main(index):
    from tools.rx_paired_opportunities import export_input,projected_candidates
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.analysis.persistent_hop_trajectory import PersistentHopTrajectoryConfig,reconstruct_persistent_hop_trajectories
    from leo.application import persistent_hop_trajectory
    started=time.monotonic()
    donor_path=PARENT/f'acquisition_calibration/donor-{index:02d}.json'
    geometry_path=PARENT/'causal-calibration-geometry.polished.json'
    plan_path=ROOT/'reports/2026_09_30_ds10_scale_weighting/plan.json'
    donor,geometry,plan=map(read,(donor_path,geometry_path,plan_path))
    for p,h in donor['sources'].items():assert digest(p)==h,p
    entry=plan['inputs'][index]
    doc=fast.load_documents(dict(config=geometry['config'],inputs=[entry]))[0]
    engine=fast.Stationary(doc,geometry['config'])
    x=np.array(donor['fixed_geometry_x'])
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:raw=store.load(donor['session_id'])
    finally:store.close()
    assert raw.qualified and raw.timing.qualified
    assert raw.input_manifest_sha256==entry['manifest_sha256']
    assert raw.analysis_manifest_sha256==doc['analysis_manifest_sha256']
    projected=projected_candidates(raw)
    by_id={c.candidate_id:c for c in projected.values()}
    graph=reconstruct_persistent_hop_trajectories(list(projected.values()),config=PersistentHopTrajectoryConfig(minimum_span_s=3.,minimum_support=6))
    tracks={t.tracklet_id:t for t in graph.tracklets}
    opportunities,_=export_input(raw,split=donor['role'],cache_sha256='public-input:'+raw.input_manifest_sha256+':'+raw.analysis_manifest_sha256,projected=projected)
    observations={}
    frame_rate=persistent_hop_trajectory.FRAME_RATE_HZ
    for o in opportunities:
        fs=o['source_window']['sample_rate_hz']
        delta=o['valid_start_counter']-o['session_start_device_sample_counter']
        for rx in o['receivers'].values():
            for c in rx['candidates']:
                cid=c['projected_candidate_id']
                if cid is None:continue
                samples=delta+o['probe_start_ms']*fs/1000+c['integer_epoch_sample']+c['fractional_epoch_offset_samples']
                t=(o['first_sample_estimate_utc_ns']-doc['start_utc_ns'])/1e9+samples/fs
                observations[cid]=dict(frame_time_s=t,phase_us=phase_us(delta,o['probe_start_ms'],c['integer_epoch_sample'],c['fractional_epoch_offset_samples'],fs,frame_rate))
    selections={t:lane['norad'] for lane in donor['lanes'] for t in lane['tracks']}
    receiver,_=fast.baseline.site(*engine.coordinates(x))
    hi=int(np.searchsorted(engine.taus,x[2],side='right'));lo=hi-1
    weight=(x[2]-engine.taus[lo])/(engine.taus[hi]-engine.taus[lo])
    rows=[]
    for track in doc['tracks']:
        tid=track['track_id']
        if tid not in selections:continue
        prediction,visible=engine.prediction(track,x)
        score,_,audits,_=fast.profile(track['y'][None]-prediction,track['mask'])
        assert all(a['converged'] for a in audits)
        score=np.where(visible,score,-np.inf)
        slot=int(np.argmax(score));confidence=float(np.exp(score[slot]-logsumexp(score)))
        assert confidence>=.9
        points=tracks[tid].points
        assert len(points)==len(track['times_s'])
        values=[]
        for j,point in enumerate(points):
            c=by_id[point.candidate_id]
            assert abs((c.support_center_utc_ns-doc['start_utc_ns'])/1e9-track['times_s'][j])<1e-9
            obs=observations[point.candidate_id]
            position=track['candidate_position_km'][slot,lo,j]*(1-weight)+track['candidate_position_km'][slot,hi,j]*weight
            velocity=track['candidate_velocity_km_s'][slot,lo,j]*(1-weight)+track['candidate_velocity_km_s'][slot,hi,j]*weight
            position=position+velocity*(obs['frame_time_s']-track['times_s'][j])
            values.append(dict(**obs,training=bool(track['mask'][j]),candidate_id=point.candidate_id,range_delay_us=float(np.linalg.norm(position-receiver)/299792.458*1e6)))
        rows.append(dict(track_id=tid,norad=selections[tid],receiver=track['receiver_id'],rf_hz=track['rf_hz'],confidence=confidence,points=values))
    paths=[Path(__file__),HERE/'PROTOCOL.md',donor_path,geometry_path,plan_path]
    paths+=[Path(inspect.getfile(f)) for f in (fast,fast.baseline,export_input,ScannerTrackingInputStore,reconstruct_persistent_hop_trajectories,persistent_hop_trajectory)]
    result=dict(index=index,session_id=donor['session_id'],frame_period_us=1e6/frame_rate,rows=rows,inferred_labels=True,approximate_simultaneous_range=True,sources={str(p):digest(p) for p in paths},elapsed_s=time.monotonic()-started)
    with (HERE/f'input-{index:02d}.json').open('x') as f:json.dump(result,f,allow_nan=False)
    print(json.dumps(dict(index=index,tracks=len(rows),elapsed_s=result['elapsed_s'])),flush=True)


if __name__=='__main__':main(int(sys.argv[1]))
