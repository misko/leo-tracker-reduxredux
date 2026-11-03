"""Bounded sequential subset searches; reuse the identical full-fraction case.

At most one scan, nine distinct reduced subsets and 25 minutes per invocation.
Completed summaries are retained; the numerical driver verifies checkpoint
signatures on incomplete cases. No acquisition or locked-test unblinding.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent


def cases(rankings,fractions):
    if not rankings or not fractions or any(r not in ('rms','support','glrt') for r in rankings):
        raise ValueError('invalid rankings')
    if any(f not in (.25,.5,.75,1.) for f in fractions):raise ValueError('invalid fractions')
    return list(dict.fromkeys(('support' if f==1. else r,f) for r in rankings for f in fractions))


def check_scan(cohort,label,frozen=False):
    scan=next((r for r in cohort['scans'] if r['label']==label),None)
    if scan is None:raise ValueError('unknown scan')
    if scan['split']=='locked_test' and not frozen:raise ValueError('locked-test settings not frozen')


def selection_file(name):
    if Path(name).name!=name or not name.startswith('selection-') or not name.endswith('.json'):
        raise ValueError('selection must be a local selection JSON filename')
    return name


def position_namespace(permit_calibration_warning=False):
    return 'position-fisher-v2-calibration-warning' if permit_calibration_warning else 'position-fisher-v2'


def run(inputs,label,rankings,fractions,selection='selection-p10-g600-t1.json',permit_calibration_warning=False):
    selection=selection_file(selection)
    cohort=json.loads((HERE/'cohort-v2.json').read_text())
    check_scan(cohort,label,(HERE/'final-settings.json').exists())
    if next(r for r in cohort['scans'] if r['label']==label)['split']=='locked_test':
        from freeze_final_settings import read_freeze
        if selection!=read_freeze(HERE)['configuration']['selection']:
            raise ValueError('locked-test selection differs from frozen settings')
    directory=inputs/label/'seed-timing-v6'
    deadline=time.monotonic()+1500
    results=[]
    for ranking,fraction in cases(rankings,fractions):
        stem=f'alternatives-{ranking}-{int(100*fraction)}'
        summary=directory/position_namespace(permit_calibration_warning)/Path(selection).stem/stem/'summary.json'
        if summary.exists():
            print('SUBSET existing (consumer must validate)',label,stem,flush=True)
            continue
        remaining=deadline-time.monotonic()
        if remaining<30:break
        log=directory/f'subset-{stem}-{time.time_ns()}.log'
        args=[sys.executable,str(HERE/'run_fisher_positions.py'),str(directory),'--ranking',ranking,'--fraction',str(fraction),'--selection',selection]
        if permit_calibration_warning:args.append('--permit-calibration-warning')
        with log.open('x') as stream:
            process=subprocess.Popen(args,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                process.wait(timeout=min(1200,remaining));status='complete' if process.returncode==0 else 'failed'
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
                status='terminated_at_budget_checkpoint_retained'
        result=dict(scan=label,case=stem,selection=selection,status=status,returncode=process.returncode,log=str(log))
        results.append(result);print(json.dumps(result),flush=True)
        if status!='complete':break
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('inputs',type=Path);p.add_argument('--label',required=True)
    p.add_argument('--rankings',nargs='+',default=['rms','support','glrt']);p.add_argument('--fractions',nargs='+',type=float,default=[.25,.5,.75,1.])
    p.add_argument('--selection',default='selection-p10-g600-t1.json')
    p.add_argument('--permit-calibration-warning',action='store_true',help='Diagnostic namespace only; never treats failed calibration as valid')
    a=p.parse_args();run(a.inputs,a.label,a.rankings,a.fractions,a.selection,a.permit_calibration_warning)
