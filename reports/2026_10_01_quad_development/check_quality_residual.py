"""Bounded exact retained-quality joins and fixed-state residual diagnostics."""
import fcntl
import json
import os
from pathlib import Path
import sys
import numpy as np
from run_window import prepare_window
from check_shared_scale import UNITS
from check_receiver_curvature import save
from screen_seed_prefix import sealed,digest
from regression_batch import execute,verify_sources
from failure_composition_checks import process_ok
from quality_residual_stats import summarize

HERE=Path(__file__).resolve().parent


def worker(unit,directory):
    inputs={}
    def read(path):
        value=sealed(path);inputs[str(path)]=digest(path);return value
    parent_dir=HERE/'one-start-blas-cold-v1'/unit/'blas'
    parent=read(parent_dir/(unit+'.json'));freeze=read(parent_dir/'sources.json')
    audit=read(parent_dir/'evaluation.json')
    assert audit['rows'][0]['accepted'] and audit['rows'][0]['receipt_sha256']==digest(parent_dir/(unit+'.json'))
    assert process_ok(read(parent_dir/(unit+'.launch.json')))
    sources=dict(freeze['source_sha256']);inputs.update(freeze['inputs'])
    overlay=read(HERE/'quality-overlay-v4/overlay.json')
    verify_sources(overlay['sources']);verify_sources(overlay['inputs'])
    sources.update(overlay['sources']);inputs.update(overlay['inputs'])
    verify_sources(sources);verify_sources(inputs)
    binding,scans,columns,precision,ports=prepare_window(unit)
    assert binding==parent['binding'] and parent['observations']==[list(p.observation_ids) for p in ports]
    scan,height,locals_=scans[0]
    quality=next(r for r in overlay['results'] if r['unit']==scan.unit_id)
    assert quality['status']=='bound'
    assert digest(quality['observation_path'])==quality['observation_sha256']
    inputs[quality['observation_path']]=quality['observation_sha256']
    obs=json.loads(Path(quality['observation_path']).read_text())
    by_track={r['track_id']:r for r in quality['tracks']}
    state=np.asarray(parent['best']['mean']);rows=[];background=[];used=set()
    for index,((track_id,track),local,p,label) in enumerate(zip(scan.tracks,locals_,ports,parent['best']['associations'],strict=True)):
        points=by_track[track_id]['points'];by_id={}
        for point in points:
            key=f"{scan.session_id}:rx{point['receiver_id']}:channel{point['channel']}:visit{point['visit_index']}"
            assert key not in by_id;by_id[key]=point
        full_indices={key:i for i,key in enumerate(track.observation_ids)}
        retained=[]
        for key in local.observation_ids:
            assert key not in used;used.add(key)
            point=by_id[key];i=full_indices[key]
            assert point['normalized_dealiased_cfo_hz']==track.frequencies_hz[i]
            assert (point['support_center_utc_ns']-obs['start_utc_ns'])/1e9==track.times_s[i]
            retained.append(point)
        row=dict(track_index=index,track_id=track_id,observation_ids=list(local.observation_ids),
                 candidate_ids=[p['candidate_id'] for p in retained],
                 median_margin=float(np.median([p['margin'] for p in retained])),
                 retained_count=len(retained),receiver_id=retained[0]['receiver_id'])
        if label==p.candidate_count:
            background.append(row);continue
        prediction=p.predict_selected(state,label);assert prediction.eligible
        residual=p.observation-prediction.mean
        whitened=np.linalg.solve(np.linalg.cholesky(prediction.covariance),residual)
        energy=float(whitened@whitened);d=len(whitened)
        row.update(norad=int(scan.bank.norad_ids[label]),dimension=d,energy=energy,energy_per_dimension=energy/d)
        rows.append(row)
    sources.update({str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])})
    for name in ('QUALITY_RESIDUAL_PLAN.md','test_quality_residual_stats.py'):sources[str(HERE/name)]=digest(HERE/name)
    verify_sources(sources);verify_sources(inputs)
    save(directory/'sources.json',dict(source_sha256=sources,inputs=inputs))
    result=dict(unit=unit,signal_tracks=rows,background_tracks=background,retained_observations=len(used),
                summary=summarize(rows),qualification='Fixed fitted state and labels used these observations; in-sample descriptive gate only, no GPS or fits.')
    save(directory/'result.json',result);print(json.dumps(dict(unit=unit,summary=result['summary'])),flush=True)


def main():
    if len(sys.argv)==3:worker(sys.argv[1],Path(sys.argv[2]));return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        root=HERE/'quality-residual-v1';root.mkdir(exist_ok=False)
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(HERE.parents[1]/'src'))
        for unit in UNITS:
            directory=root/unit;directory.mkdir()
            launch=execute([sys.executable,str(Path(__file__).resolve()),unit,str(directory)],directory,unit,timeout_s=90,env=env)
            save(directory/'launch.json',launch);print(unit,launch['returncode'],flush=True)
            assert process_ok(launch)


if __name__=='__main__':main()
