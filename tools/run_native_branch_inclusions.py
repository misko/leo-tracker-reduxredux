"""Test every supported annotation in one frozen native-branch batch."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import sys
from debug_fast_graph_unassociated import read,write
from stress_joint_attachment import supervise
from leo.analysis.research.grouped_prediction import identity_consensus


def run(args):
    jobs=[]
    for j in read(args.annotations/'protocol.json')['jobs']:
        r=read(args.annotations/j['branch']['branch_id']/'result.json')
        a=identity_consensus(r['folds'],score_name=r['identity_score_name'])
        if a['status']=='conditionally_supported_identity':jobs.append(dict(j,annotation=a))
    if len(jobs)>8:raise ValueError('one bounded batch, at most eight inclusion trials')
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(jobs=jobs,annotations=str(args.annotations),
        selection='All supported identities in the frozen annotation batch',workers=8,seconds_per_case=600,
        original_model_and_noise=True,GPS_used=False,matched_c_arms=True))
    def work(j):
        bid=j['branch']['branch_id'];cmd=[sys.executable,str(Path(__file__).with_name('include_predictive_annotations.py')),
            '--inventory',j['job']['inventory'],'--validation',str(args.annotations/bid),
            '--native-branches',j['source'],'--output',str(args.output/bid)]
        r=dict(job=j,command=cmd,**supervise(cmd,args.output/(bid+'.log'),600))
        write(args.output/(bid+'-terminal.json'),r);return j['job']['label'],r['status']
    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):print(f.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--annotations',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args())
