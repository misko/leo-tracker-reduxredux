"""Discover omitted native GLRT branches without orbits, receiver models or GPS."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from dataclasses import asdict
import hashlib
from pathlib import Path
import sys,time
import numpy as np
from debug_fast_graph_unassociated import read,write
from leo.analysis.graph_tracklets import fit_lane as graph_fit
from leo.analysis.hough_tracklets import fit_lane as hough_fit
from leo.analysis.polynomial_tracklets import TrackConfig
from stress_joint_attachment import supervise

CONFIG=TrackConfig(max_slope_hz_s=8000)


def discover(rows,job_id,*,method,config=CONFIG,scramble_seed=None):
    if len({r['observation_id'] for r in rows})!=len(rows):raise ValueError('duplicate native observation identity')
    fitter={'graph':graph_fit,'hough':hough_fit}[method];results=[];lanes=[];rng=np.random.default_rng(scramble_seed)
    for lane in sorted({(r['receiver'],r['channel'],r['actual_rf_hz']) for r in rows}):
        selected=sorted([r for r in rows if (r['receiver'],r['channel'],r['actual_rf_hz'])==lane],key=lambda r:(r['time_s'],r['observation_id']))
        t=np.array([r['time_s'] for r in selected]);y=np.array([r['measured_cfo_hz'] for r in selected]);offsets={}
        if scramble_seed is not None:
            blocks=np.floor(t/12).astype(int);offsets={int(b):float(rng.uniform(-config.alias_spacing_hz/2,config.alias_spacing_hz/2)) for b in np.unique(blocks)}
            y=y+np.array([offsets[int(b)] for b in blocks])
        fitted=fitter(t,y,config);owners=set()
        for track in fitted['tracks']:
            ix=np.asarray(track['indices'],int);ix=ix[np.argsort(t[ix],kind='stable')];ids=[selected[i]['observation_id'] for i in ix]
            if owners.intersection(ids):raise ValueError('discovery duplicated point ownership')
            owners.update(ids);tid=hashlib.sha256((job_id+'\n'+'\n'.join(sorted(ids))).encode()).hexdigest()[:20]
            results.append(dict(branch_id=tid,method=method,receiver=lane[0],channel=lane[1],rf_hz=lane[2],observation_ids=ids,
                times_s=t[ix],raw_CFO_hz=np.array([selected[i]['measured_cfo_hz'] for i in ix]),values_hz=y[ix]+fitted['alias_lifts'][ix]*config.alias_spacing_hz,
                alias_lifts=fitted['alias_lifts'][ix],points=len(ix),span_s=float(np.ptp(t[ix])),start_s=float(t[ix].min()),end_s=float(t[ix].max()),
                RMS_hz=track['residual_rms_hz'],quality_status=track['diagnostics']['quality_status'],quality_flags=track['diagnostics']['quality_flags'],
                pieces=track['pieces'],large=bool(len(ix)>=20 and np.ptp(t[ix])>=20),accepted_association=False))
        lanes.append(dict(receiver=lane[0],channel=lane[1],rf_hz=lane[2],points=len(selected),discovered=len(owners),
            unresolved_ids=[r['observation_id'] for r in selected if r['observation_id'] not in owners],diagnostics=fitted['diagnostics'],null_block_offsets_hz=offsets))
    return dict(branches=results,lanes=lanes,discovery_only=True,scramble_seed=scramble_seed)


def one(args):
    began=time.monotonic();args.output.mkdir(parents=True,exist_ok=False);inv=read(args.inventory);job=inv['job'];root=Path(job['root'])/job['case']
    obs=read(root/'observations.json');tracks=read(root/'tracks.json');graph={o for t in tracks for o in t['observation_ids']}
    associated=set().union(*(set(r['proposed_associated_ids']) for r in inv['policy'].values()))
    rows=[r for r in obs if r['observation_id'] not in graph|associated]
    protocol=dict(job=job,input_observations=len(obs),original_graph_points=len(graph),omitted_unassociated_in_both_arms=len(rows),
        excluded_outside_graph_associated_in_either_arm=len(associated-graph),config=asdict(CONFIG),scramble_seed=args.scramble_seed,
        input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.inventory,root/'observations.json',root/'tracks.json']},
        actual_RF_lanes_separate=True,GPS_used=False,TLE_used=False,original_graph_unchanged=True)
    write(args.output/'protocol.json',protocol);results={}
    for method in ['graph','hough']:
        start=time.monotonic();result=discover(rows,job['job_id'],method=method,scramble_seed=args.scramble_seed);result['seconds']=time.monotonic()-start
        write(args.output/(method+'.json'),result);results[method]=result
    union={o for r in results.values() for t in r['branches'] for o in t['observation_ids']}
    write(args.output/'summary.json',dict(job=job,input_points=len(rows),unique_proposed_points=len(union),
        methods={m:dict(branches=len(r['branches']),points=sum(t['points'] for t in r['branches']),large=sum(t['large'] for t in r['branches']),
            large_points=sum(t['points'] for t in r['branches'] if t['large']),seconds=r['seconds']) for m,r in results.items()},
        seconds=time.monotonic()-began,accepted_associations=0,scramble_seed=args.scramble_seed))


def batch(args):
    args.output.mkdir(exist_ok=False);inventory=args.study/'all-large-track-recovery';alljobs=read(inventory/'protocol.json')['jobs']
    jobs=[dict(job_id=j['job_id'],label=j['label'],inventory=str(inventory/j['job_id']/'inventory.json')) for j in alljobs if 'DS24' in j['scopes']]
    write(args.output/'protocol.json',dict(jobs=jobs,workers=8,seconds_per_scan=120,config=asdict(CONFIG),scope='all 93 available frozen DS24 exports',
        discovery_on_original_graph_omissions=True,no_satellite_or_position_filter=True,accepted_associations=0))
    def work(job):
        name=job['job_id'];cmd=[sys.executable,str(Path(__file__)),'one','--inventory',job['inventory'],'--output',str(args.output/name)]
        result=dict(job=job,command=cmd,**supervise(cmd,args.output/(name+'.log'),120));write(args.output/(name+'-terminal.json'),result);return name,result['status']
    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):print(f.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['one','batch'])
    for k in ['study','inventory','output']:p.add_argument('--'+k,type=Path,required=k=='output')
    p.add_argument('--scramble-seed',type=int);a=p.parse_args();batch(a) if a.mode=='batch' else one(a)
