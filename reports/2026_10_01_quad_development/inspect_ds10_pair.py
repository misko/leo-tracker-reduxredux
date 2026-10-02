"""Outlier-selected fixed-state inspection; no localization fit or data removal."""
import fcntl
import os
from pathlib import Path
import sys
import numpy as np
from run_window import prepare_window
from check_receiver_curvature import save
from screen_seed_prefix import sealed,digest
from regression_batch import execute,verify_sources
from failure_composition_checks import process_ok
from physics import enu_state_ecef_km,hermite_interpolate,helmert_contrasts,LIGHT_KM_S
HERE=Path(__file__).resolve().parent
UNIT='DS10-B01-S1'


def worker(directory):
    inputs={}
    def read(p):
        d=sealed(p);inputs[str(p)]=digest(p);return d
    root=HERE/'rx-residual-v1'/UNIT
    previous=read(root/'result.json');freeze=read(root/'sources.json');assert process_ok(read(root/'launch.json'))
    selected=max(previous['groups'],key=lambda r:r['common_energy']+r['differential_energy'])
    assert selected['track_indices']==[17,16]
    sources=dict(freeze['source_sha256']);inputs.update(freeze['inputs']);verify_sources(sources);verify_sources(inputs)
    parent=read(HERE/'one-start-blas-cold-v1'/UNIT/'blas'/(UNIT+'.json'))
    overlay=read(HERE/'quality-overlay-v4/overlay.json')
    binding,scans,columns,precision,ports=prepare_window(UNIT)
    assert binding==parent['binding'] and parent['observations']==[list(p.observation_ids) for p in ports]
    scan,height,local=scans[0];state=np.asarray(parent['best']['mean'])[columns[0]]
    receiver=enu_state_ecef_km(state[0],state[1],height(*state[:2]),scan.config.prior_center_lat_deg,scan.config.prior_center_lon_deg)
    quality=next(r for r in overlay['results'] if r['unit']==scan.unit_id)
    by_track={r['track_id']:r['points'] for r in quality['tracks']};records=[]
    for index in selected['track_indices']:
        tid,track=scan.tracks[index];points=by_track[tid];label=parent['best']['associations'][index]
        assert scan.bank.norad_ids[label]==64429 and len(points)==len(track.times_s)
        times=track.times_s;rx=track.receiver_indices
        raw=[]
        for t in times:
            pos,vel,_=hermite_interpolate(scan.bank.times_s,scan.bank.positions_ecef_km[label],scan.bank.velocities_ecef_km_s[label],t+state[2]+state[5+label])
            line=pos-receiver
            raw.append(scan.config.doppler_sign*scan.config.reference_frequency_hz/LIGHT_KM_S*(vel@line)/np.linalg.norm(line))
        retained=np.array([track.observation_ids.index(k) for k in ports[index].observation_ids])
        drift=state[3+rx]*(scan.config.reference_frequency_hz/track.rf_hz)*(times-times[retained].mean())
        pred=ports[index].predict_selected(np.asarray(parent['best']['mean']),label)
        C=helmert_contrasts(rx[retained]);raw=np.asarray(raw)+drift
        np.testing.assert_allclose(C@raw[retained],pred.mean,atol=1e-6,rtol=0)
        residual=track.frequencies_hz-raw;residual-=residual[retained].mean()
        summaries={}
        for name,indices in [('full',np.arange(len(times))),('retained',retained)]:
            t=times[indices];y=residual[indices];X=np.column_stack((np.ones(len(t)),t-t.mean()))
            beta=np.linalg.lstsq(X,y,rcond=None)[0];error=y-X@beta
            summaries[name]=dict(samples=len(t),span_s=float(np.ptp(t)),slope_hz_s=float(beta[1]),
                rms_centered_hz=float(np.std(y)),rms_after_linear_hz=float(np.sqrt(np.mean(error**2))),
                largest_adjacent_change_hz=float(np.max(abs(np.diff(y)))))
        samples=[]
        for i,p in enumerate(points):
            assert p['normalized_dealiased_cfo_hz']==track.frequencies_hz[i]
            samples.append(dict(time_s=float(times[i]),visit=p['visit_index'],candidate_rank=p['candidate_rank'],margin=p['margin'],
                raw_cfo_hz=p['measured_cfo_hz'],normalized_dealiased_cfo_hz=p['normalized_dealiased_cfo_hz'],
                centered_residual_hz=float(residual[i]),retained=bool(i in retained)))
        records.append(dict(track_index=index,track_id=tid,receiver_id=int(rx[0]),summary=summaries,samples=samples))
    sources.update({str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])})
    verify_sources(sources);verify_sources(inputs);save(directory/'sources.json',dict(source_sha256=sources,inputs=inputs))
    result=dict(unit=UNIT,selected_norad=64429,tracks=records,
        qualification='Outlier-selected fixed-state inspection; linear summaries are descriptive, not a new localization fit or independent validation. Aliases are not exported and are not inferred here.')
    save(directory/'result.json',result);print([r['summary'] for r in records],flush=True)


def main():
    if len(sys.argv)==2:worker(Path(sys.argv[1]));return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        directory=HERE/'ds10-pair-inspection-v1';directory.mkdir(exist_ok=False)
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(HERE.parents[1]/'src'))
        launch=execute([sys.executable,str(Path(__file__).resolve()),str(directory)],directory,UNIT,timeout_s=90,env=env)
        save(directory/'launch.json',launch);assert process_ok(launch);print(launch,flush=True)


if __name__=='__main__':main()
