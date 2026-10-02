"""Read-only bounded moment effect on the fitted three-single signal tracks."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from run_window import prepare_window
from check_shared_scale import UNITS
from check_receiver_curvature import save
from screen_seed_prefix import sealed,digest
from regression_batch import execute,verify_sources
from failure_composition_checks import process_ok
from physics import enu_state_ecef_km,hermite_interpolate,helmert_contrasts,LIGHT_KM_S
from support_moment_effect import correction

HERE=Path(__file__).resolve().parent


def worker(unit,directory):
    inputs={}
    def read(path):
        value=sealed(path);inputs[str(path)]=digest(path);return value
    previous=HERE/'quality-residual-v1'/unit
    q=read(previous/'result.json');freeze=read(previous/'sources.json')
    assert process_ok(read(previous/'launch.json'))
    sources=dict(freeze['source_sha256']);inputs.update(freeze['inputs'])
    verify_sources(sources);verify_sources(inputs)
    read(directory.parent/'geometry-source.json')
    parent=read(HERE/'one-start-blas-cold-v1'/unit/'blas'/(unit+'.json'))
    overlay=read(HERE/'quality-overlay-v4/overlay.json')
    binding,scans,columns,precision,ports=prepare_window(unit)
    assert binding==parent['binding'] and parent['observations']==[list(p.observation_ids) for p in ports]
    scan,height,local=scans[0];x=np.asarray(parent['best']['mean']);state=x[columns[0]]
    receiver=enu_state_ecef_km(state[0],state[1],height(*state[:2]),scan.config.prior_center_lat_deg,scan.config.prior_center_lon_deg)
    quality=next(r for r in overlay['results'] if r['unit']==scan.unit_id)
    candidates={p['candidate_id']:p for t in quality['tracks'] for p in t['points']}
    rows=[]
    for row in q['signal_tracks']:
        index=row['track_index'];track=scan.tracks[index][1];p=ports[index];label=parent['best']['associations'][index]
        assert scan.tracks[index][0]==row['track_id']
        selected=[track.observation_ids.index(k) for k in row['observation_ids']]
        times=track.times_s[selected];rx=track.receiver_indices[selected];C=helmert_contrasts(rx)
        assert row['observation_ids']==list(p.observation_ids)
        def doppler(t):
            pos,vel,_=hermite_interpolate(scan.bank.times_s,scan.bank.positions_ecef_km[label],scan.bank.velocities_ecef_km_s[label],t+state[2]+state[5+label])
            line=pos-receiver
            return float(scan.config.doppler_sign*scan.config.reference_frequency_hz/LIGHT_KM_S*(vel@line)/np.linalg.norm(line))
        central=np.array([doppler(t) for t in times])
        drift=state[3+rx]*(scan.config.reference_frequency_hz/track.rf_hz)*(times-times.mean())
        pred=p.predict_selected(x,label);assert pred.eligible
        parity=float(np.max(np.abs(C@(central+drift)-pred.mean)))
        assert parity<1e-6,parity
        estimates=[];spans=[]
        for h in (.02,.04):
            estimate=[]
            for t,cid in zip(times,row['candidate_ids'],strict=True):
                point=candidates[cid]
                estimate.append(correction([doppler(t+k*h) for k in (-2,-1,0,1,2)],h,point['factorial_support_moments_s']))
            estimates.append(np.array(estimate))
        spans=[(candidates[cid]['support_end_utc_ns']-candidates[cid]['support_start_utc_ns'])/1e9 for cid in row['candidate_ids']]
        delta=estimates[0];difference=float(np.max(abs(delta-estimates[1])))
        stable=difference<=max(1e-6,.1*float(np.max(abs(delta))))
        L=np.linalg.cholesky(pred.covariance);z=np.linalg.solve(L,p.observation-pred.mean);shift=np.linalg.solve(L,C@delta)
        rows.append(dict(track_id=row['track_id'],norad=row['norad'],samples=len(times),support_span_s=spans,
            correction_hz=delta.tolist(),step_difference_hz=difference,step_stable=stable,
            point_prediction_parity_hz=parity,whitened_correction_norm=float(np.linalg.norm(shift)),
            energy_change=float((z-shift)@(z-shift)-z@z)))
    sources.update({str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])})
    for name in ('SUPPORT_EFFECT_PLAN.md','test_support_moment_effect.py'):sources[str(HERE/name)]=digest(HERE/name)
    verify_sources(sources);verify_sources(inputs)
    save(directory/'sources.json',dict(source_sha256=sources,inputs=inputs))
    result=dict(unit=unit,tracks=rows,maximum_correction_hz=max(abs(v) for r in rows for v in r['correction_hz']),
        maximum_whitened_norm=max(r['whitened_correction_norm'] for r in rows),all_steps_stable=all(r['step_stable'] for r in rows),
        expansion_gate=any(r['step_stable'] and r['whitened_correction_norm']>.01 for r in rows),
        qualification='Cubic symbol-center moment approximation at fitted states; not exact detector response, remainder bound, refit or geography.')
    save(directory/'result.json',result);print({k:v for k,v in result.items() if k!='tracks'},flush=True)


def main():
    if len(sys.argv)==3:worker(sys.argv[1],Path(sys.argv[2]));return
    from prepare_block import verify_reader,RUNTIME
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        root=HERE/'support-effect-v1';root.mkdir(exist_ok=False)
        before=verify_reader()
        code='import inspect,json,hashlib; from pathlib import Path; from leo.application.scanner_trajectory import fractional_glrt64_support_geometry as f; p=Path(inspect.getfile(f)); print(json.dumps(dict(source=inspect.getsource(f),module_path=str(p),module_sha256="sha256:"+hashlib.sha256(p.read_bytes()).hexdigest())))'
        call=subprocess.run(['sudo','-n','-u','leo',RUNTIME,'-c',code],capture_output=True,text=True,check=True,timeout=30)
        save(root/'geometry-source.json',dict(reader_before=before,reader_after=verify_reader(),geometry=json.loads(call.stdout)))
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(HERE.parents[1]/'src'))
        for unit in UNITS:
            directory=root/unit;directory.mkdir()
            launch=execute([sys.executable,str(Path(__file__).resolve()),unit,str(directory)],directory,unit,timeout_s=90,env=env)
            save(directory/'launch.json',launch);print(unit,launch['returncode'],flush=True);assert process_ok(launch)


if __name__=='__main__':main()
