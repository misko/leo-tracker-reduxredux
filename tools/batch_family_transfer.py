"""Apply the same random-family transfer test to every completed new-family trial."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import sys
from debug_fast_graph_unassociated import read,write
from stress_joint_attachment import supervise


def run(args):
    args.output.mkdir(parents=True,exist_ok=False)
    known={read(p.parent/'protocol.json')['source_trial']:str(p) for p in args.study.glob('family-transfer-*-v1/result.json')}
    sources=sorted(args.study.glob('new-family-inclusion-*-v1/new_family.json'))+sorted((args.study/'new-family-cohort-v1').glob('*/inclusion/new_family.json'))
    jobs=[]
    for path in sources:
        pr=read(path.parent/'protocol.json')
        if str(path.parent) in known:continue
        jobs.append(dict(trial=str(path.parent),job_id=pr['job']['job_id'],label=pr['job']['label'],norad=pr['targets'][0]['norad']))
    write(args.output/'protocol.json',dict(jobs=jobs,known_results=known,selection='every completed new-family proposal, including rejected trials',seed=20261029,workers=4,seconds_per_case=600,GPS_used=False))
    def work(job):
        name=job['job_id']+'-'+str(job['norad'])
        cmd=[sys.executable,str(Path(__file__).with_name('validate_family_position_transfer.py')),'--study',str(args.study),
             '--trial',job['trial'],'--output',str(args.output/name)]
        return dict(job=job,**supervise(cmd,args.output/(name+'.log'),600))
    results=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):
            r=f.result();results.append(r);j=r['job'];write(args.output/(j['job_id']+'-'+str(j['norad'])+'-terminal.json'),r)
            print(j['label'],j['norad'],r['status'],flush=True)
    write(args.output/'execution.json',results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
