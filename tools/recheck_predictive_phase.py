"""Frozen replay of supported identities under explicit uncalibrated phase priors."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import sys
from debug_fast_graph_unassociated import read,write
from stress_joint_attachment import supervise


def run(args):
    args.output.mkdir(parents=True,exist_ok=False);jobs=[]
    known={read(p)['track_id'] for p in args.study.glob('exact-uncalibrated-annotation-*-v1/result.json')}
    queue=args.study/'systematic-annotation-v1'
    for row in read(queue/'protocol.json')['rows']:
        path=queue/row['track_id']/'result.json'
        if row['track_id'] in known or not path.exists():continue
        result=read(path);a=result.get('annotation',{})
        if result.get('inclusion_mode')!='predictive_only' or a.get('status')!='conditionally_supported_identity':continue
        kinds={q['arms']['c0']['prior']['kind'] for f in result['folds'] for q in f['proposals'] if q['norad']==a['norad']}
        if 'existing_shared_posterior' in kinds or row['label'] in ('V08','DS24-0087'):
            jobs.append(dict(row,original_norad=a['norad'],original_validation=str(path.parent)))
    write(args.output/'protocol.json',dict(jobs=jobs,selection='all remaining supported shared-family identities plus two largest new-family pilots',
        GPS_used=False,workers=4,seconds_per_case=600,uncalibrated_phase_mixture=True))
    def work(row):
        cmd=[sys.executable,str(Path(__file__).with_name('annotate_predictive_only.py')),'--inventory',row['inventory'],
            '--track',row['track_id'],'--output',str(args.output/row['track_id']),'--uncalibrated-phase-mixture']
        result=dict(track_id=row['track_id'],label=row['label'],**supervise(cmd,args.output/(row['track_id']+'.log'),600))
        write(args.output/(row['track_id']+'-terminal.json'),result);return result
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=[]
        for f in as_completed([pool.submit(work,r) for r in jobs]):
            r=f.result();results.append(r);print(r,flush=True)
    write(args.output/'execution.json',results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
