"""Bounded read-only validation of the largest paired RF curves in two scans.

The explicit export stage alone reads declared recording ports and emits IQ to
stdout. Analysis uses a saved local panel; no satellite or GPS inputs occur.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import json
import signal
import sys
import time
import numpy as np

from ds23_conditional_pilot_components import conditional_component_prediction
from fast_local_pilot_refinement import FastPilotWorkspace
from probe_ds23_same_probe_curves import OUT as CURVES,SOURCE,CASES
from ds23_same_probe_covariance import residual_pair
from run_algo01_ds23_sample import ROOT,DATASET,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_same_probe_IQ'
PANELS=Path('/srv/bulk/leo/research/ds23-same-probe-20261020')


def prepare():
    previous=read(CURVES/'protocol.json');evaluation=read(CURVES/'evaluation.json')
    if evaluation['pending']:raise ValueError('all RF lanes must finish before selecting raw controls')
    jobs=[];selected=[]
    for case in CASES:
        rows=[r for r in evaluation['rows'] if r['case']==case and r['status']=='complete']
        candidates=[(row,pair) for row in rows for pair in row['pairs'] if all(pair['geometry_checks'].values())]
        lane,pair=max(candidates,key=lambda x:(len(x[1]['probes']),x[1]['first'],x[1]['second']))
        paths={r['key']:r for r in lane['paths']}
        job=next(j for j in previous['jobs'] if j['case']==case and j['lane']==lane['lane'])
        document=read(SOURCE/case/'tracking.json');source=document.get('source',document)
        one,two=paths[pair['first']],paths[pair['second']]
        for index,pi in enumerate(pair['probes']):
            p=source['probes'][pi]
            if p['probe_start_ms']!=0 or source['probe_ms']!=20:raise ValueError('this bounded panel requires an original complete20ms visit')
            a=one['probes'].index(pi);b=two['probes'].index(pi)
            peak1=job['candidates'][one['peak_indices'][a]];peak2=job['candidates'][two['peak_indices'][b]]
            jobs.append(dict(case=case,probe=pi,paired_index=index,lane=lane['lane'],
                visit_index=p['visit_index'],sample_counter=p['valid_start_counter'],native_receiver_id=p['receiver_id'],
                edge=p['edge'],first=peak1,second=peak2,first_lifted_value=one['values'][a],
                second_lifted_value=two['values'][b],time_s=pair['time_s'][index]))
        selected.append(dict(case=case,lane=lane['lane'],pair=pair,
            selection='largest simultaneous-probe count among geometry-qualified pairs; residual correlation not used for ranking'))
    protocol=dict(jobs=jobs,selected=selected,source_evaluation_sha256=sha(CURVES/'evaluation.json'),
        source_protocol_sha256=sha(CURVES/'protocol.json'),dataset_manifest_sha256=sha(DATASET/'manifest.json'),
        maximum_read_windows_per_case=6000,maximum_export_seconds_per_case=120,
        workers=4,maximum_analysis_seconds_per_probe=20,
        received_component_rule='rank17, each component reduces held-out SSE by>.1percent in both folds, each exact sequence beats equal-dimension rolled control by>10 profile units in both folds, both RF fits interior',
        no_new_RF_collection=True,raw_recording_adapter_read_only=True,
        no_GPS_TLE_or_satellite_ID_input=True,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_conditional_pilot_components.py',ROOT/'tools/fast_local_pilot_refinement.py']})
    OUT.mkdir(parents=True,exist_ok=True);PANELS.mkdir(parents=True,exist_ok=True);target=OUT/'protocol.json'
    if target.exists() and read(target)!=protocol:raise ValueError('same-probe IQ protocol changed')
    if not target.exists():write(target,protocol)
    return protocol


def export(case):
    from leo.storage.short_window import ShortWindowReader
    protocol=read(OUT/'protocol.json')
    if sha(DATASET/'manifest.json')!=protocol['dataset_manifest_sha256']:raise ValueError('dataset authority changed')
    jobs=[j for j in protocol['jobs'] if j['case']==case];required={j['visit_index']:j for j in jobs}
    if len(required)!=len(jobs):raise ValueError('one selected receiver/probe per visit required')
    member=next(m for m in read(DATASET/'manifest.json')['members'] if m['dataset_label']==case)
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('120 second existing-IQ export budget exhausted')))
    signal.alarm(120);arrays={};points=[];manifests=[];visited=0
    try:
        for authority in member['raw_recording']['segments']:
            path=Path(authority['path'])
            if 'sha256:'+sha(path)!=authority['sha256']:raise ValueError('recording manifest changed')
            reader=ShortWindowReader(path.parent);manifests.append(dict(path=str(path),sha256=sha(path)))
            for window in reader.windows():
                visited+=1;visit=window.index.acquisition['global_visit']
                if visit in required:
                    job=required[visit]
                    if window.index.acquisition['sample_start']!=job['sample_counter']:raise ValueError('raw support counter differs')
                    key=f'window_{visit:06d}';arrays[key]=np.array(window.samples,copy=True)
                    points.append(dict(job,window_key=key,receiver_offset=reader.manifest.receiver_ids.index(job['native_receiver_id']),
                        raw_window_sha256=window.index.iq_sha256))
                if len(points)==len(jobs) or visited>=6000:break
            if len(points)==len(jobs) or visited>=6000:break
        if len(points)!=len(jobs):raise ValueError('bounded read did not find every selected paired probe')
        metadata=dict(case=case,points=points,sample_rate_hz=reader.manifest.sample_rate_hz,
            protocol_sha256=sha(OUT/'protocol.json'),recording_manifests=manifests,raw_windows_read=visited,
            selected_raw_window_hashes_verified_by_read_only_adapter=True)
        arrays['metadata_json']=np.array(json.dumps(metadata));np.savez_compressed(sys.stdout.buffer,**arrays)
    finally:signal.alarm(0)


def analyze(job):
    path=OUT/(job['case']+f"_probe{job['probe']:06d}.json")
    if path.exists():return read(path)
    started=time.monotonic()
    def timeout(*_):raise TimeoutError('20 second conditional component budget exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(20)
    result=dict(case=job['case'],probe=job['probe'],paired_index=job['paired_index'],time_s=job['time_s'])
    try:
        with np.load(PANELS/(job['case']+'.npz'),allow_pickle=False) as z:
            meta=json.loads(str(z['metadata_json']));fs=meta['sample_rate_hz']
            p=next(p for p in meta['points'] if p['probe']==job['probe'])
            v=z[p['window_key']][:,p['receiver_offset']]
        y=v[:,0].astype(float)+1j*v[:,1].astype(float);fits=[]
        for label in ('first','second'):
            peak=job[label];workspace=FastPilotWorkspace(y,fs,job['edge'],peak['epoch'])
            fits.append(workspace.fast_joint_fit(peak['cfo_hz']))
        conditional=conditional_component_prediction(y,fs,job['edge'],job['first']['epoch'],fits[0],job['second']['epoch'],fits[1])
        interior=not any(f[k] for f in fits for k in ('frequency_search_boundary','epoch_search_boundary','code_rate_search_boundary'))
        result.update(status='complete',first_fit=fits[0],second_fit=fits[1],conditional=conditional,
            RF_fits_interior=interior,two_components_qualified=conditional['two_received_components_supported'] and interior,
            refined_first_value=job['first_lifted_value']+fits[0]['CFO_hz']-job['first']['cfo_hz'],
            refined_second_value=job['second_lifted_value']+fits[1]['CFO_hz']-job['second']['cfo_hz'])
    except Exception as exc:result.update(status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(path,result)
    print(job['case'],job['paired_index'],result['status'],result.get('error'),'qualified',result.get('two_components_qualified'),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['prepare','export','analyze'],required=True)
    parser.add_argument('--case',choices=CASES);parser.add_argument('--pilot',action='store_true');args=parser.parse_args()
    if args.stage=='prepare':
        protocol=prepare();print('SEALED_IQ_PROBES',len(protocol['jobs']));return
    if args.stage=='export':export(args.case);return
    protocol=read(OUT/'protocol.json')
    for name,expected in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name)!=expected:raise ValueError('IQ experiment source changed')
    bindings={case:sha(PANELS/(case+'.npz')) for case in CASES}
    jobs=protocol['jobs']
    if args.pilot:
        jobs=[]
        for case in CASES:
            group=[j for j in protocol['jobs'] if j['case']==case]
            jobs.extend(group[k] for k in sorted({0,len(group)//2,len(group)-1}))
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(analyze,j) for j in jobs]):f.result()
    rows=[];pending=[]
    for job in protocol['jobs']:
        path=OUT/(job['case']+f"_probe{job['probe']:06d}.json")
        if path.exists():rows.append(read(path))
        else:pending.append(dict(case=job['case'],probe=job['probe']))
    summary={}
    for selected in protocol['selected']:
        case=selected['case'];complete=sorted([r for r in rows if r['case']==case and r['status']=='complete'],key=lambda r:r['time_s'])
        summary[case]=dict(complete=len(complete),RF_qualified=sum(r['two_components_qualified'] for r in complete))
        if len(complete)>=16:
            for name,subset in [('all_refined',complete),('RF_qualified',[r for r in complete if r['two_components_qualified']])]:
                if len(subset)<16:continue
                summary[case][name]=residual_pair([r['time_s'] for r in subset],[r['refined_first_value'] for r in subset],
                    [r['refined_second_value'] for r in subset],selected['pair']['degree'])
    write(OUT/'evaluation.json',dict(rows=rows,pending=pending,summary=summary,panel_sha256=bindings,
        protocol_sha256=sha(OUT/'protocol.json'),real_DS23_accuracy_gain=False))
    print('CONDITIONAL_COMPONENT_IQ',summary,'pending',len(pending),flush=True)


if __name__=='__main__':main()
