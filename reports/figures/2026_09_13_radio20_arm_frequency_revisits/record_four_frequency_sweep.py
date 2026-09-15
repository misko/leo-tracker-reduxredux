"""Retain verified four-visit physical scan evidence, with explicit scope limits."""
import hashlib,json,shutil
from pathlib import Path
BASE=Path(__file__).parent;root=BASE/'frequency-sweep60-v2'
out=Path('/home/mouse9911/gits/leo-radio20-reboot-publish/reports/figures/2026_09_13_radio20_arm_frequency_revisits')
load=lambda p:json.loads(p.read_text())
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
op=load(root/'operator.json');sequence=load(root/'independent-sequence-review.json')
children=[load(root/f'visit-{n}/independent-visit-review.json') for n in range(4)]
assert op['serial']=='1040005e0b100007100010000bf33a5d4d' and op['rate']==60000000 and op['visit_count']==4
assert op['before']==op['after'] and op['temporary_files_removed'] and op['exit_code']==0
assert sequence['status']=='pass' and len(sequence['visits'])==12
assert all(c['status']=='pass' and not c['native_results'] for c in children)
shutil.copyfile(root/'visits.txt',out/'sweep60-visits.txt')
shutil.copyfile(Path(__file__),out/Path(__file__).name)
result=dict(status='pass_bounded_four_visit_sweep',operator=op,sequence=sequence,children=children,
    prior_refusal=load(BASE/'frequency-sweep60-v1/operator.json'),
    native_tracking_qualified=False,physical_clean_loss_exercised=False,
    retained_artifact_bytes=sum(r['bytes'] for r in op['artifacts'].values()),
    recorder_sha256=digest(Path(__file__)))
with (out/'sweep60-evidence.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print('evidence_sha256',digest(out/'sweep60-evidence.json'),'bytes',result['retained_artifact_bytes'])
for c in children:print(c['rf_seconds'],c['max_refill_gap_ns'])
