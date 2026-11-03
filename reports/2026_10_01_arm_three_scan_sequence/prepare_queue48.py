"""Bounded capacity-only retry; original failed experiment is preserved."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
from render_arm_chain import render

report=Path(__file__).resolve().parent;before=report/'arm-sequence-v1';after=report/'arm-sequence-v2'
old='/mnt/glrtbench/three-distinct-cadence-v1';new='/mnt/glrtbench/three-distinct-cadence-v2'
def relocate(value):
    if isinstance(value,str):return value.replace(old,new)
    if isinstance(value,list):return [relocate(v) for v in value]
    if isinstance(value,dict):return {relocate(k):relocate(v) for k,v in value.items()}
    return value
protocol=relocate(json.loads((before/'protocol.json').read_text()));after.mkdir()
for name,path in [('controller',before/'controller'),('detector',Path('/var/tmp/leo-recorded-queue48-v1'))]:
    shutil.copy2(path,after/name);protocol['payloads'][new+'/'+name]=hashlib.sha256(path.read_bytes()).hexdigest()
for i,scan in enumerate(protocol['scans']):
    path=after/f'scan-{i}/chain.sh';path.parent.mkdir()
    path.write_text(render(scan['chain'],protocol['payloads']))
    protocol['payloads'][new+f'/scan-{i}/chain.sh']=hashlib.sha256(path.read_bytes()).hexdigest()
rows=[line.replace(old,new).split('\t') for line in (before/'plan.tsv').read_text().splitlines()]
for row in rows:
    if row[0]=='detector':
        assert row[7]=='32';row[7]='48'
(after/'plan.tsv').write_text('\n'.join('\t'.join(row) for row in rows)+'\n')
protocol['payloads'][new+'/plan.tsv']=hashlib.sha256((after/'plan.tsv').read_bytes()).hexdigest()
protocol['scope']+='; explicit 48-dwell queue retry after measured 32-dwell overflow; science unchanged'
(after/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
policy=json.loads((before/'acceptance-policy.json').read_text())
policy.update(queue_capacity=48,maximum_iq_buffers=50,maximum_iq_buffer_bytes=120000000,
    maximum_dwell_latency_ms=5000,loaded_downstream_acceptance_s=300)
(after/'acceptance-policy.json').write_text(json.dumps(policy,indent=2)+'\n')
sources=['native/adaptive/bench/recorded_paced.cpp','native/adaptive/runtime/runtime.cpp',
         'native/adaptive/runtime/projection.cpp','native/adaptive/runtime/projection.hpp',
         'native/adaptive/runtime/detector_projection.hpp','tests/native_adaptive/bench/test_recorded_paced.py']
for name in sources:
    target=after/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
(after/'source-sha256.json').write_text(json.dumps({name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},indent=2)+'\n')
print(after)
