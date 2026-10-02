"""Bounded matched physical-visit residual comparison, with no refitting."""
from collections import defaultdict
import fcntl
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
from physics import helmert_contrasts
from rx_residual_contrasts import compare
HERE=Path(__file__).resolve().parent


def worker(unit,directory):
    inputs={}
    def read(path):
        d=sealed(path);inputs[str(path)]=digest(path);return d
    prior=HERE/'quality-residual-v1'/unit
    quality=read(prior/'result.json');freeze=read(prior/'sources.json');assert process_ok(read(prior/'launch.json'))
    sources=dict(freeze['source_sha256']);inputs.update(freeze['inputs']);verify_sources(sources);verify_sources(inputs)
    overlay=read(HERE/'quality-overlay-v4/overlay.json')
    parent=read(HERE/'one-start-blas-cold-v1'/unit/'blas'/(unit+'.json'))
    binding,scans,columns,precision,ports=prepare_window(unit)
    assert binding==parent['binding'] and parent['observations']==[list(p.observation_ids) for p in ports]
    scan,height,local=scans[0];state=np.asarray(parent['best']['mean'])
    raw=next(r for r in overlay['results'] if r['unit']==scan.unit_id)
    by_candidate={p['candidate_id']:p for t in raw['tracks'] for p in t['points']}
    groups=defaultdict(lambda:defaultdict(list));trackdata={}
    for row in quality['signal_tracks']:
        i=row['track_index'];p=ports[i];label=parent['best']['associations'][i]
        assert list(p.observation_ids)==row['observation_ids']
        points=[by_candidate[c] for c in row['candidate_ids']]
        C=helmert_contrasts(np.array([v['receiver_id'] for v in points]))
        pred=p.predict_selected(state,label);assert pred.eligible
        residual=p.observation-pred.mean
        trackdata[i]=(C.T@residual,C.T@pred.covariance@C)
        for j,point in enumerate(points):
            groups[(row['norad'],point['channel'],point['visit_index'])][point['receiver_id']].append((i,j,point))
    pairs=defaultdict(list);counts=defaultdict(int)
    for key,rx in groups.items():
        if set(rx)!={0,1}:counts['unmatched_visits']+=1;continue
        if len(rx[0])!=1 or len(rx[1])!=1:counts['ambiguous_visits']+=1;continue
        a,b=rx[0][0],rx[1][0];pa,pb=a[2],b[2]
        dt=abs(pa['support_center_utc_ns']-pb['support_center_utc_ns'])/1e9
        if dt>.001 or max(pa['support_start_utc_ns'],pb['support_start_utc_ns'])>=min(pa['support_end_utc_ns'],pb['support_end_utc_ns']):
            counts['support_mismatch']+=1;continue
        counts['matched_visits']+=1
        pairs[(a[0],b[0])].append((key,a[1],b[1],dt))
    records=[]
    for (ia,ib),matches in sorted(pairs.items()):
        if len(matches)<2:counts['single_visit_track_pairs']+=1;continue
        matches=sorted(matches);a=np.array([r[1] for r in matches]);b=np.array([r[2] for r in matches])
        ra,Va=trackdata[ia];rb,Vb=trackdata[ib]
        value=compare(ra[a],Va[np.ix_(a,a)],rb[b],Vb[np.ix_(b,b)])
        value.update(track_indices=[ia,ib],norad=matches[0][0][0],visits=[r[0][2] for r in matches],
                     maximum_time_separation_s=max(r[3] for r in matches))
        records.append(value)
    common=sum(r['common_energy'] for r in records);diff=sum(r['differential_energy'] for r in records)
    ratio=common/diff if diff else None
    majority=sum(r['common_energy']>r['differential_energy'] for r in records)
    result=dict(unit=unit,counts=dict(counts),groups=records,dimension=sum(r['dimension'] for r in records),
        common_energy=common,differential_energy=diff,pooled_ratio=ratio,common_dominant_groups=majority,
        exploratory_gate=bool(len(records)>=3 and ratio is not None and ratio>2 and majority>len(records)/2),
        qualification='Conditional fitted states/labels, nominal independent-RX covariance, correlated groups possible; no significance, causality, or geography.')
    sources.update({str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])})
    for name in ('RX_RESIDUAL_PLAN.md','test_rx_residual_contrasts.py'):sources[str(HERE/name)]=digest(HERE/name)
    verify_sources(sources);verify_sources(inputs);save(directory/'sources.json',dict(source_sha256=sources,inputs=inputs))
    save(directory/'result.json',result);print({k:v for k,v in result.items() if k!='groups'},flush=True)


def main():
    if len(sys.argv)==3:worker(sys.argv[1],Path(sys.argv[2]));return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        root=HERE/'rx-residual-v1';root.mkdir(exist_ok=False)
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(HERE.parents[1]/'src'))
        for unit in UNITS:
            directory=root/unit;directory.mkdir()
            launch=execute([sys.executable,str(Path(__file__).resolve()),unit,str(directory)],directory,unit,timeout_s=90,env=env)
            save(directory/'launch.json',launch);print(unit,launch['returncode'],flush=True);assert process_ok(launch)


if __name__=='__main__':main()
