"""Complete comparisons only after the physical controller and download finish."""
import json
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
REPORT=Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0,str(ROOT/'tools'))
from evaluate_loaded_cadence import evaluate

parser=argparse.ArgumentParser();parser.add_argument('--sequence',default='arm-sequence-v1');args=parser.parse_args()
SEQUENCE=REPORT/args.sequence


def command(argv,name,timeout=600):
    with (REPORT/name).open('x') as log:
        subprocess.run([sys.executable,*map(str,argv)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=timeout)


deadline=time.monotonic()+1800
while not (SEQUENCE/'retrieved-products.json').exists():
    if time.monotonic()>deadline:raise TimeoutError('replay products not complete; do not restart hardware')
    time.sleep(2)
execution=json.loads((SEQUENCE/'execution.json').read_text())
if execution['exit_code']!=0:raise ValueError('ARM sequence failed; inspect preserved partial products')
print('Complete ARM products retrieved; evaluating stages',flush=True)
command(['tools/evaluate_three_recorded_scans.py',REPORT,'--sequence',args.sequence],'stage-comparison.log')
command(['tools/evaluate_cadence_schedule.py',SEQUENCE],'schedule-comparison.log')
print('Stage and schedule comparisons complete; physical independent controls next',flush=True)
command(['tools/qualify_three_association_controls.py','--sequence',args.sequence],'physical-association-controls.log')
for scan in json.loads((REPORT/'selection.json').read_text())['scans']:
    directory=REPORT/scan['session_id']
    command(['tools/qualify_native_orbit.py',directory/'location-authority',
        directory/('orbit-arm-'+scan['session_id'].removeprefix('scan-fw-')),'--device'],
        scan['session_id']+'-orbit-arm.log')
command(['tools/plot_three_recorded_scans.py','--sequence',args.sequence],'plots.log')
schedule=json.loads((SEQUENCE/'schedule-evaluation.json').read_text())
stages=json.loads((REPORT/'stage-comparison.json').read_text())
throughput=evaluate(schedule,300,minimum_loaded=2)
policy=json.loads((SEQUENCE/'acceptance-policy.json').read_text())
capacity=all(r['queue']['rejected']==r['queue']['failed']==0 and r['queue']['queue_high_water']<=policy['queue_capacity']
             and r['queue']['iq_buffer_allocations']<=policy['maximum_iq_buffers'] and r['queue']['maximum_dwell_latency_ms']<=5000 for r in stages)
result={'execution_complete':True,'all_native_same_checkpoint_controls_passed':all(r['native_stage_controls_passed'] for r in stages),
        'queue_and_latency_passed':capacity,'loaded_throughput':throughput,'schedule':schedule,
        'independent_native_full_chain_search_passed':all(r['native_end_to_end']['search']['passed'] for r in stages),
        'scope':'Three distinct recorded captures with original science times at fixed replay cadence; not live RF qualification'}
(REPORT/'qualification-summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
