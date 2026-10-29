"""Run the frozen joint-attachment experiment in four bounded processes."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from debug_fast_graph_unassociated import read,write


def main(args):
    root=Path(__file__).parents[1];out=args.output;out.mkdir(parents=True,exist_ok=False)
    parent=args.study;source=read(parent/'combined-reentry/protocol.json');cases=[]
    for c in sorted(source['primary_cases']+source['remaining_cases']):
        cases.append(dict(case=c,root=source['root'],source=str(parent/'combined-reentry'/c)))
    separate=read(parent/'separate-fast-validation/protocol.json')
    for c in separate['cases']:
        cases.append(dict(case=c,root=separate['root'],source=str(parent/'separate-fast-validation/recovery'/c)))
    names=['tools/test_joint_high_channel_recovery.py','tools/probe_high_channel_correlated_noise.py',
           'src/leo/analysis/research/covariance_structure.py','tools/run_joint_high_channel_recovery.py']
    write(out/'protocol.json',dict(cases=cases,workers=4,case_seconds=240,source_revision='1e519670b',
        source_sha256={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},
        target_rule='largest wholly unassociated same-RX overlapping CH7/8 pair; otherwise largest single CH7/8; >=20 points,24s,20s overlap',
        candidate_rule='original nominees plus active and whole-causal-catalogue winners in both arms; only families represented in prior design',
        identity_rule='same winner both arms, >=10 score margin; common family no worse than separate identities after 2 ln K penalty',
        unmatched='reject option, not a calibrated clutter likelihood',
        tests='GLS mean/slope/quadratic/searched-step, physical neighbor covariance, chi-square energy; full and randomized held contexts',
        alpha=.01,calibration_seed=82137,calibration_draws=4096,validation_seeds=[20261029,0,1,2,3,4,5,6,7],
        covariance='independent noncandidate-family training; existing fixed grid, complexity penalty, positive aggregate held-density gain in both arms',
        budgets=dict(phase_rounds=5,iterations=48,starts=[0,0]),
        variants=['white_existing','covariance_existing','covariance_physical'],
        original_gates_unchanged=True,keep_all_old_ids=True,GPS_in_inference=False,postscan_TLE=False,production_changed=False,
        synthetic_calibration=str(parent/'joint-attachment-synthetic/synthetic.json')))
    def run(c):
        began=time.monotonic();status='complete';reason=None
        cmd=[sys.executable,str(root/'tools/test_joint_high_channel_recovery.py'),'case','--case',c['case'],
             '--root',c['root'],'--source',c['source'],'--output',str(out/c['case'])]
        with (out/(c['case']+'.log')).open('x') as f:
            process=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                code=process.wait(timeout=240)
                if code:status='failed';reason=f'exit {code}'
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                status='timeout';reason='240-second cap'
        r=dict(case=c['case'],status=status,reason=reason,seconds=time.monotonic()-began)
        write(out/(c['case']+'-terminal.json'),r);return r
    rows=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(run,c) for c in cases]):
            r=f.result();rows.append(r);print(r,flush=True)
    write(out/'execution.json',rows)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
