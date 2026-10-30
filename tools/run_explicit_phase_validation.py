"""Six bounded fold jobs for two predeclared contrasting native cases."""
import argparse,hashlib,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from debug_fast_graph_unassociated import read,write
from stress_joint_attachment import supervise


def run(args):
    if len(args.diagnostics)>2 or not 1<=args.workers<=4:raise ValueError('bounded to two cases and four workers')
    args.output.mkdir(parents=True,exist_ok=False);jobs=[];sources={}
    for directory in args.diagnostics:
        path=directory/'protocol.json';pr=read(path);annotation_path=Path(pr['validation'])/'result.json';annotation=read(annotation_path)
        inv=read(Path(pr['inventory']));label=inv['job']['label']
        for p in (path,annotation_path):sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        for fold in annotation['folds']:
            jobs.append(dict(name=f"{label}-{fold['seed']}",scan=label,seed=fold['seed'],diagnostic=str(directory)))
    if len(jobs)!=6:raise ValueError('exactly two cases and three frozen partitions each required')
    write(args.output/'protocol.json',dict(jobs=jobs,sources=sources,workers=args.workers,seconds_per_job=360,
        matched_c=True,GPS_used=False,future_TLE=False,weight_policy=args.weight_policy,
        selection='previous successful DS24-0093 and adverse DS24-0063 full-data trials'))
    def work(job):
        command=[sys.executable,str(Path(__file__).with_name('validate_explicit_phase_position.py')),
            '--diagnostic',job['diagnostic'],'--seed',str(job['seed']),'--output',str(args.output/job['name']),
            '--weight-policy',args.weight_policy]
        row=dict(job,command=command,**supervise(command,args.output/(job['name']+'.log'),360))
        write(args.output/(job['name']+'-terminal.json'),row);return row
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):print(f.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--diagnostics',nargs='+',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=4)
    p.add_argument('--weight-policy',choices=['unit','training_support'],default='unit');run(p.parse_args())
