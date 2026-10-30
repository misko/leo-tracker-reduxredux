"""Refine phase quadrature for every identity near the fixed competition threshold."""
import argparse
import hashlib
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from debug_fast_graph_unassociated import read, write
from stress_joint_attachment import supervise


def near_threshold(annotation):
    margin = annotation.get('minimum_margin')
    return margin is not None and 8. <= margin <= 12.


def matched_geometry(original, refined):
    if original['track_id'] != refined['track_id']:
        raise ValueError('different target')
    old = {f['seed']: f for f in original['folds']}
    new = {f['seed']: f for f in refined['folds']}
    if len(old) != len(original['folds']) or len(new) != len(refined['folds']) or set(old) != set(new):
        raise ValueError('different folds')
    for seed, before in old.items():
        after = new[seed]
        if before['split'] != after['split']:
            raise ValueError('different physical split')
        op = {p['norad']: p for p in before['proposals']}
        np = {p['norad']: p for p in after['proposals']}
        if set(op) != set(np):
            raise ValueError('different candidate sets')
        for norad, p in op.items():
            q = np[norad]
            if p['alias'] != q['alias'] or set(p['arms']) != set(q['arms']):
                raise ValueError('different aliases or c arms')
            for arm in p['arms']:
                for key in ('endpoint_east_north_km', 'training_objective', 'history'):
                    if p['arms'][arm][key] != q['arms'][arm][key]:
                        raise ValueError('training calibration changed')
    return True


def run(args):
    root=args.review;out=args.output;execution=read(root/'execution.json')
    if any(r['status']!='complete' for r in execution):raise ValueError('review must be terminal complete')
    jobs=[];hashes={};sources=[root/'protocol.json',root/'execution.json']
    for rec in execution:
        tid=rec['job']['track_id'];source=root/tid/'result.json';r=read(source);sources.append(source)
        if not near_threshold(r['annotation']):continue
        for step in (.05,.025):
            jobs.append(dict(track_id=tid,label=rec['job']['label'],step=step,source=str(source),command=rec['command']))
    if len(jobs)>16:raise ValueError('at most eight curves in this bounded audit')
    out.mkdir(parents=True,exist_ok=False)
    write(out/'protocol.json',dict(jobs=jobs,source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        selection='every expanded identity with minimum margin in [8,12], around existing threshold 10; both sides included',
        phase_steps_s=[.05,.025],seconds_per_case=600,workers=8,GPS_used=False,future_TLE=False))
    def work(job):
        name=job['track_id']+'-'+str(job['step']);folder=out/name;cmd=job['command'].copy();cmd[0]=sys.executable
        cmd[cmd.index('--output')+1]=str(folder)
        if '--phase-step' in cmd:raise ValueError('source already overrides phase spacing')
        cmd+=['--phase-step',str(job['step'])]
        result=dict(job=job,command=cmd,**supervise(cmd,out/(name+'.log'),600))
        if result['status']=='complete':result['matched_geometry']=matched_geometry(read(Path(job['source'])),read(folder/'result.json'))
        write(out/(name+'-terminal.json'),result);print(job['label'],job['step'],result['status'],flush=True);return result
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(work,jobs))
    write(out/'execution.json',results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('review','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
