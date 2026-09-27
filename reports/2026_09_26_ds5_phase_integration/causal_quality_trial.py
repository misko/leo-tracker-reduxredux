"""Two additional DS5 scans; first-eight-block catalogue proposals and prediction."""
from pathlib import Path
import argparse,json,time
import numpy as np
from scipy.special import logsumexp
from scipy.interpolate import CubicSpline
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories,PersistentHopTrajectoryConfig
from episode_support_audit import supported_breaks
from segment_catalogue_trial import SCALES,mixture
from timing_trial import prior_weights
from causal_quality import run_filter
import catalogue_trial as T

HERE=Path(__file__).resolve().parent
OUT=HERE/'causal-quality'
SIDS=['scan-fw-4fc9ccc9f49e637b','scan-fw-382ca32cddbfdc6a']

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',type=int,choices=[0,1],required=True);args=parser.parse_args();sid=SIDS[args.scan];OUT.mkdir(exist_ok=True);started=time.monotonic()
    protocol=dict(scans=SIDS,selection='Longest RX1 production-input track with >=24 observed second bins, tie by track ID; first64 bins maximum. Track membership and availability selected retrospectively; conditional prediction is causal.',warmup_blocks=8,proposal='Full catalogue using first8 CFO blocks only: coarse 5s orbit-time grid, retain union top8 at mixture/100Hz/400Hz; fine .2s propagated then .05s interpolation',scales_hz=SCALES,models=['stationary','generic','timing_informed'],transition='Generic scale redraw hazard 1-exp(-dt/20s); previous-block supported pilot timing flag adds independent .5 redraw probability. Shared static CFO intercept and fixed identity/orbit-time hypotheses.',timing_flag='Five past epoch points, extrapolation <=past span, 44 samples threshold at10MS/s; only prior-block flags can affect next prediction.',approximation='Gaussian moment matching of intercept conditional on each identity, orbit time and scale; not exact path enumeration',meaning='Additional scans for frozen-parameter development comparison; offline track selection and candidate membership prevent claiming end-to-end online association or identity truth')
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n');store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        source=store.load(sid);p=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
    finally:store.close()
    projected={c.candidate_id:c for c in project_scanner_candidates(source)}
    trajectory=reconstruct_persistent_hop_trajectories(tuple(projected.values()),config=PersistentHopTrajectoryConfig(minimum_span_s=3.,minimum_support=6));rawtracks={tr.tracklet_id:tr for tr in trajectory.tracklets}
    candidates=[tr for tr in p.tracks if len(np.unique(np.floor(tr.times_s)))>=24 and rawtracks[tr.track_id].lane_key[2]==1]
    if not candidates:
        (OUT/f'{sid}-ineligible.json').write_text(json.dumps(dict(protocol=protocol,reason='No RX1 production-input track with at least24 second bins',eligible_tracks=len(p.tracks)),indent=2)+'\n');print('ineligible',sid,flush=True);return
    track=sorted(candidates,key=lambda tr:(-len(np.unique(np.floor(tr.times_s))),tr.track_id))[0]
    points=sorted(rawtracks[track.track_id].points,key=lambda pt:projected[pt.candidate_id].support_center_utc_ns)
    acquisition_ids=[pt.candidate_id for pt in points]
    np.testing.assert_allclose(track.times_s,[(projected[cid].support_center_utc_ns-p.start_utc_ns)/1e9 for cid in acquisition_ids],rtol=0,atol=1e-9)
    np.testing.assert_allclose(track.measured_hz,[pt.normalized_dealiased_cfo_hz for pt in points],rtol=0,atol=1e-8)
    raw={(pr.visit_index,pr.receiver_id,pr.probe_index,c.candidate_rank):(pr,c) for pr in source.probes for c in pr.candidates}
    cycles=[]
    for cid in acquisition_ids:
        point=projected[cid];pr,c=raw[point.visit_index,point.receiver_id,point.probe_index,point.candidate_rank]
        relative=pr.valid_start_counter-source.timing.session_start_device_sample_counter+pr.probe_start_ms*source.sample_rate_hz/1000
        cycles.append(((relative+c.integer_epoch_sample+c.fractional_epoch_offset_samples)*750/source.sample_rate_hz)%1)
    ep=np.unwrap(np.array(cycles)*2*np.pi)/(2*np.pi)*source.sample_rate_hz/750
    innovations,breaks=supported_breaks(track.times_s,ep);flags=np.zeros(len(ep),bool);flags[breaks]=True
    bins=np.unique(np.floor(track.times_s).astype(int))[:64];groups=[np.floor(track.times_s).astype(int)==b for b in bins]
    times=np.array([track.times_s[g].mean() for g in groups]);measured=np.array([track.measured_hz[g].mean() for g in groups]);pilot_flags=np.array([flags[g].any() for g in groups])
    plan=dict(protocol=protocol,session_id=sid,track_id=track.track_id,candidate_ids=acquisition_ids,production_observation_ids=list(track.observation_ids),times_s=times.tolist(),measured_hz=measured.tolist(),pilot_flags=pilot_flags.tolist(),break_times_s=[float(track.times_s[i]) for i in breaks],source_sample_rate_hz=source.sample_rate_hz,evidence_sha256=p.evidence_sha256,snapshot_digest=p.snapshot_digest)
    (OUT/f'{sid}-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    site=json.loads((HERE/'catalogue-input-audit.json').read_text())['scans'][0]['sites']['reference'];receiver,up,_=T.site_vectors(site);cal=json.loads((HERE/'timing-calibration.json').read_text());epochs=p.catalogue.element_epoch_utc_ns()
    def propagate(indices,taus,ts):
        pos,vel,valid=propagate_candidate_states(p.catalogue,indices,p.start_utc_ns,ts,taus);dr=pos-receiver;unit=dr/np.linalg.norm(dr,axis=-1)[...,None]
        prediction=-11.2e9/(299792458./1000)*np.sum(unit*vel,axis=-1)
        return prediction,unit@up,valid
    def prior(index,grid,coarse=False):return prior_weights(cal,(p.start_utc_ns-epochs[index])/3.6e12,grid,coarse)
    coarse=np.arange(-120,121,5.);pool=[]
    for begin in range(0,len(p.candidate_indices),128):
        pred,el,valid=propagate(p.candidate_indices[begin:begin+128],coarse,times[:8]);residual=measured[:8]-pred;lp=np.array([prior(i,coarse,True) for i in valid]);lp=np.where(np.max(el,axis=-1)>0,lp,-np.inf)
        ev=[mixture(residual)]+[T.constant_log_evidence(residual,s) for s in (100.,400.)];scores=[logsumexp(e+lp,axis=-1) for e in ev]
        pool.extend(dict(index=int(i),scores=[float(s[j]) for s in scores]) for j,i in enumerate(valid))
    indices=sorted(set().union(*[{r['index'] for r in sorted(pool,key=lambda r:-r['scores'][j])[:8]} for j in range(3)]));fine=np.arange(-600,601)/5
    pred,el,valid=propagate(indices,fine,times);taus=np.arange(-2400,2401)/20
    # Apply prefix visibility. No future observation chooses candidate support.
    visibility=np.max(el[...,:8],axis=-1)>0
    if not visibility.all():raise ValueError('Fine interpolation requires explicit visibility handling for these proposals')
    residual=CubicSpline(fine,measured-pred,axis=1)(taus);lp=np.array([prior(i,taus) for i in valid]);ids=np.asarray(p.catalogue.satellite_numbers)[valid]
    np.savez_compressed(OUT/f'{sid}-bank.npz',residuals=residual,logprior=lp,times=times,pilot_flags=pilot_flags,candidate_ids=ids,taus=taus)
    results=[]
    for kind in protocol['models']:
        rows=run_filter(residual,lp,SCALES,times,pilot_flags,kind=kind);total=sum(r['log_predictive'] for r in rows if r['held']);results.append(dict(model=kind,held_log_predictive=total,rows=rows));print(sid,kind,'held',total,'blocks',len(times),'flags',np.flatnonzero(pilot_flags).tolist(),flush=True)
        (OUT/f'{sid}-results.json').write_text(json.dumps(dict(plan=plan,site=site,catalogue_candidate_ids=list(map(str,ids)),proposal_scores=pool,models=results,elapsed_s=time.monotonic()-started),indent=2)+'\n')

if __name__=='__main__':main()
