"""Bounded recovery replay of a frozen, RF-selected unused recording panel."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from pathlib import Path
import sys

from debug_fast_graph_unassociated import read, write
from stress_joint_attachment import supervise


def run(args):
    args.output.mkdir(parents=True,exist_ok=False)
    inventory=read(args.inventory);jobs=inventory['selected'];tool=Path(__file__).parent
    for job in jobs:
        if not job['report_scalar_metadata']['recording_name'].startswith('fast8-auto-'):
            raise ValueError('panel must have confirmed fast recording names')
        p=Path(job['artifact']['path'])
        if 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()!=job['artifact']['sha256']:
            raise ValueError('frozen completed baseline changed')
    write(args.output/'protocol.json',dict(jobs=jobs,inventory_sha256=hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
          budgets_s=dict(reentry=240,attachment=240),workers=2,production_unchanged=True,
          no_GPS_in_inference=True,no_future_TLE=True,matched_c_arms=True,
          qualification='unused in prior 29-recording attachment experiment, not new-site validation',
          source_sha256={n:hashlib.sha256((tool/n).read_bytes()).hexdigest() for n in
                        ('run_joint_attachment_validation.py','test_joint_high_channel_recovery.py','combined_family_reentry.py')}))
    def one(job):
        folder=args.output/job['job_id'];folder.mkdir();rows=[]
        for name,command in (
            ('reentry',[sys.executable,str(tool/'combined_family_reentry.py'),'case','--root',job['root'],'--case','SCAN','--output',str(folder/'reentry')]),
            ('attachment',[sys.executable,str(tool/'test_joint_high_channel_recovery.py'),'case','--root',job['root'],'--case','SCAN','--source',str(folder/'reentry'),'--output',str(folder/'attachment')])):
            result=dict(stage=name,**supervise(command,folder/(name+'.log'),240));rows.append(result)
            if result['status']!='complete':break
        result=dict(job_id=job['job_id'],stages=rows,status=rows[-1]['status'])
        write(folder/'terminal.json',result);return result
    rows=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(one,j) for j in jobs]):
            r=f.result();rows.append(r);print(r,flush=True)
    write(args.output/'execution.json',rows)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inventory',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);run(p.parse_args())
