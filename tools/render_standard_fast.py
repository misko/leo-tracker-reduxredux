"""Render the published ALGO07 endpoint; never search position or identities."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time

import numpy as np

from leo.contracts.fast_graph_position_v6 import owners, MODEL_VERSION
from leo.storage.graph_position_view_v6 import completed_view
from leo.storage.fast_graph_position_v6 import FastGraphPositionStoreV6
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore, RENDER_REVISION
from leo.presentation.fast_standard_analysis import render
from standard_orbit_lanes import calibrated_lanes


def read(path):
    return json.loads(Path(path).read_text())


def sha(value):
    return 'sha256:'+hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def replay(evidence, scratch):
    from algo07_science import engine as e
    from algo06_science.position import family_score
    from prototype_dsx01_continuous_position import latlon
    root=Path(evidence['workspace']); terminal=evidence['terminal']
    if evidence.get('replay_model')=='algo02':
        from benchmark_graph_covariance import load_case
        d=load_case(root,'SCAN');d['families']=[]
        z=dict(baseline_arms=evidence['baseline_terminal']['arms'])
    else:
        e.configure(root,root/'candidate')
        d,z,checks=e.load_case('SCAN')
    candidate=terminal['candidate']
    if candidate:
        # Reuse sealed historical exports. Any missing export raises; no archive access.
        old=candidate['old_norad'];record=candidate['record'];h=record['hypothesis']
        source=root/'candidate/SCAN'
        for name in ('incumbent_history',str(old)+'/'+h['name']+'-combined/history'):
            src=source/name
            if src.exists():shutil.copytree(src,scratch/name)
        d,_=e.complete_history(d,z,'SCAN',e.active_ids(d),scratch/'incumbent_history')
        path=scratch/str(old)/(h['name']+'-combined')/'history'
        d,_=e.complete_history(d,z,'SCAN',set(h['mapping'].values()),path)
        d=e.remap(d,z,'SCAN',h)
        for arm,row in candidate['arms'].items():
            p,_=e.build(d,z,arm,np.asarray(row['reference']))
            d['problems'][arm]=(p,np.asarray(row['endpoint_east_north_km']))
    view=completed_view(evidence['job']['run_id'],terminal)
    published=owners(terminal); all_rows={}; summaries={}; differences={}
    native={o['observation_id']:o for o in evidence['observations']}; lanes=None
    for arm,(p,x) in d['problems'].items():
        expected=candidate['arms'][arm] if candidate else z['baseline_arms'][arm]
        if not np.allclose(latlon(x),expected['endpoint_latlon'],rtol=0,atol=1e-9):
            raise ValueError('Published position changed during figure replay')
        c=p.calculate(x); objective=e.objective(p,d,x)
        target=expected.get('negative_twice_elbo',expected.get('objective'))
        delta=objective-target
        if abs(delta)>1e-4:raise ValueError(f'{arm} objective replay mismatch {delta}')
        differences[arm]=float(delta);rows={}
        def add(ids,residual,norad,component,role):
            for oid,r in zip(ids,residual,strict=True):
                if published[arm].get(oid)!=int(norad):continue
                o=native[oid]
                rows[oid]=dict(observation_id=oid,receiver=o['receiver'],channel=o['channel'],
                    time_s=o['time_s'],measured_cfo_hz=o['measured_cfo_hz'],norad=int(norad),
                    residual_hz=float(r),prediction_hz=float(o['measured_cfo_hz']-r),component=component,role=role)
        for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
            t=p.scan.tracks[i]
            add(t['observation_ids'],c['conditional_residual_hz'][sl],row['candidate_norad'],t['key'],'conditional')
        for entry,sl in zip(d['entries'],getattr(p,'linear_slices',[]),strict=True):
            t=p.scan.tracks[entry['track_index']]
            add(t['observation_ids'],c['linear_raw_prediction_residual_hz'][sl],entry['norad'],t['key'],'predictive')
        fs=d['families']
        details=([fs[0].evaluate(p,x,d['powers'],d['entries'],details=True,refine_phase=False)] if len(fs)==1
                 else family_score(fs,d,p,x,details=True)[1] if fs else [])
        for f,detail in zip(fs,details,strict=True):
            for entry,diag in zip(f.entries,detail['diagnostics'],strict=True):
                add(entry['observation_ids'],diag['raw_residual_hz'],entry['norad'],entry['component'],'phase_mixture_MAP')
        if arm=='fitted_c':
            lanes=calibrated_lanes(p,x,c,evidence['observations'],published[arm],fs,details)
        if set(rows)!=set(published[arm]):
            raise ValueError(f'{arm}: predictions missing for {len(set(published[arm])-set(rows))} published points')
        all_rows[arm]=list(rows.values())
        summaries[arm]=dict(endpoint_latlon=list(map(float,expected['endpoint_latlon'])),
            associated_points=len(published[arm]),associated_percent=100*len(published[arm])/len(native),
            tracks=len({r['component'] for r in rows.values()}),satellites=len(set(published[arm].values())),
            residual_rms_hz=float(np.sqrt(np.mean([r['residual_hz']**2 for r in rows.values()]))),
            owner_sha256=sha(published[arm]))
    return dict(observations=evidence['observations'],tracks=evidence['tracks'],rows=all_rows,orbit_lanes=lanes,
                arms=summaries,objective_replay=differences,selected_model=view['selected']['model_version'])


def publish(source, target, job):
    folder=target.folder(job['run_id']);folder.mkdir(parents=True,exist_ok=True)
    with (folder/'render.lock').open('a') as handle:
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return dict(state='rendering',artifacts=[])
        return _publish(source,target,job)


def _publish(source, target, job):
    old=target.detail(job['run_id'])
    if old['state']=='complete':
        for a in old['artifacts']:target.artifact(job['run_id'],a['name'],a['sha256'])
        return old
    began=time.monotonic();evidence=source.plot_evidence(job)
    with tempfile.TemporaryDirectory(prefix='standard-algo07-') as tmp:
        packet=replay(evidence,Path(tmp))
        acquisition=job
        while 'source_job' in acquisition and 'fast_acquisition' not in acquisition:
            acquisition=acquisition['source_job']
        title=acquisition.get('fast_acquisition',{}).get('recording_name',job['run_id'])
        pngs=render(packet,title=title)
    # Publication is bound to the exact scientific terminal, not its timestamp.
    again=source.plot_evidence(job)
    if again['terminal_receipt']!=evidence['terminal_receipt']:
        raise ValueError('ALGO07 terminal changed while rendering')
    document=dict(schema_version=1,run_id=job['run_id'],session_id=evidence['terminal']['session_id'],
        model_version=MODEL_VERSION,state='complete',decision=evidence['terminal']['decision'],
        selected_model=packet['selected_model'],reference_usage='evaluation_only',
        glrt_points=len(packet['observations']),arms=packet['arms'],objective_replay=packet['objective_replay'],
        input_sha256=job['input_sha256'],terminal_sha256=evidence['terminal_receipt']['sha256'],
        observations_sha256=evidence['observation_sha256'],tracks_sha256=evidence['tracks_sha256'],
        figures_model=MODEL_VERSION,renderer_revision=RENDER_REVISION,
        figure_frequency_frame='receiver calibration removed; wrapped at GLRT alias period',
        replay_seconds=time.monotonic()-began)
    return target.publish(job['run_id'],document,pngs)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bulk-root',type=Path,required=True)
    parser.add_argument('--run-id');parser.add_argument('--once',action='store_true')
    args=parser.parse_args();source=FastGraphPositionStoreV6(args.bulk_root);target=FastStandardAnalysisStore(args.bulk_root)
    while True:
        for job in source.completed_jobs():
            if args.run_id and job['run_id']!=args.run_id:continue
            if target.detail(job['run_id'])['state']=='complete':continue
            try:
                result=publish(source,target,job)
                print(json.dumps(dict(run_id=job['run_id'],state=result['state'],figures=len(result['artifacts']))),flush=True)
            except Exception as error:
                print(json.dumps(dict(run_id=job['run_id'],state='failed',error=str(error))),flush=True)
                if args.run_id:raise
        if args.once or args.run_id:return
        time.sleep(20)


if __name__=='__main__':main()
