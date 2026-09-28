"""Bounded saved-IQ qualification and timing of an isolated optimization."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile
import time
from build import HERE,BASE
from check import compare
sys.path.insert(0,str(HERE.parent/'concurrent'))
from run_phase import SSH, ROOT


def main():
    p=argparse.ArgumentParser();p.add_argument('name');p.add_argument('--root',type=Path)
    p.add_argument('--all',action='store_true');p.add_argument('--output-name',default='arm-check');a=p.parse_args()
    if not re.fullmatch('[a-z0-9_]+',a.name):raise ValueError('name')
    if not re.fullmatch('[a-z0-9_-]+',a.output_name):raise ValueError('output name')
    root=a.root or HERE/'work'/a.name;out=root/a.output_name;out.mkdir(exist_ok=False)
    binary=root/'arm';digest=hashlib.sha256(binary.read_bytes()).hexdigest()
    target='opt-'+a.name;stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as t:t.add(binary,arcname=target)
    subprocess.run([*SSH,'tar xf - -C '+ROOT],input=stream.getvalue(),capture_output=True,check=True,timeout=20)
    remote_hash=subprocess.check_output([*SSH,'sha256sum '+ROOT+'/'+target],timeout=10).decode().split()[0]
    if remote_hash!=digest:raise ValueError('target binary hash')
    m=json.loads((BASE/'manifest.json').read_text());selected=json.loads((HERE.parent/'concurrent/selected-cases.json').read_text())
    ids={c['case_id'] for c in selected};cases=[c for c in m['cases'] if a.all or c['case_id'] in ids or (c['split']=='control' and c['rate_hz']==2500000)]
    (out/'manifest.json').write_text(json.dumps({'cases':cases,'sha256':digest,'mode':'saved-IQ no RF'},indent=2)+'\n')
    assessments=[];started=time.monotonic()
    for c in cases:
        if time.monotonic()-started>360:raise TimeoutError('bounded ARM block')
        t=m['templates'][c['template_key']]
        command='cd '+ROOT+' && '+shlex.join(['./'+target,c['raw_file'],t['exact'],t['control'],str(c['rate_hz']),c['edge'],c['case_id']])
        r=subprocess.run([*SSH,command],capture_output=True,timeout=22)
        (out/(c['case_id']+'.stderr')).write_bytes(r.stderr);(out/(c['case_id']+'.json')).write_bytes(r.stdout);r.check_returncode()
        ref=HERE.parent/'target_run_01'/(c['case_id']+'-D.json')
        if not ref.exists(): ref=HERE.parent/'target_run_02_10m'/(c['case_id']+'-D.json')
        row=compare(c,json.loads(ref.read_text()),json.loads(r.stdout),a.name);assessments.append(row)
        (out/'assessments.json').write_text(json.dumps(assessments,indent=2)+'\n')
        print(c['case_id'],row['passed'],round(row['reference_cost']['total_cpu_ms'],2),round(row['candidate_cost']['total_cpu_ms'],2),flush=True)
    (out/'completion.json').write_text(json.dumps({'complete':True,'cases':len(cases),'passed':all(x['passed'] for x in assessments),'seconds':time.monotonic()-started},indent=2)+'\n')
    if not all(x['passed'] for x in assessments):raise RuntimeError('scientific gate failed')


if __name__=='__main__':main()
