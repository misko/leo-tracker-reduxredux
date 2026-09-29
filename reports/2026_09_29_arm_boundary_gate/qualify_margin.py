#!/usr/bin/env python3
"""Compile and record the native boundary-margin component test."""
import hashlib, importlib.util, json, shutil, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PRIOR=ROOT.parent/'2026_09_29_arm_fused_pipeline'
SOURCE='test_boundary_margin_allowed.c'

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def builder():
    spec=importlib.util.spec_from_file_location('fused_build',PRIOR/'build_v4.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def one(label):
    module=builder();root=ROOT/'variants'/label
    for target in ('host','sanitizer','arm'):
        out=root/'builds-v4'/target;shutil.copy2(root/'sources'/SOURCE,out/SOURCE)
        name=f'test_boundary_margin_allowed_{target}'
        command=module.command(out,target,[SOURCE],name,target=='sanitizer',0)
        complete=subprocess.run(command,text=True,capture_output=True,check=True)
        receipt_path=out/'build-receipt.json';receipt=json.loads(receipt_path.read_text())
        receipt['commands']=[r for r in receipt['commands'] if not any(name in str(v) for v in r.get('command',[]))]
        receipt['commands'].append({'command':command,'stdout':complete.stdout,'stderr':complete.stderr})
        receipt['binaries'][name]=sha(out/name)
        receipt['sources'][SOURCE]=sha(out/SOURCE)
        receipt['boundary_margin_component_test']={'source':SOURCE,'binary':name,'threshold':float(label)/1000 if label=='025' else float(label)/1000,
            'checks':['finite above/below','equal threshold','nextafter below/above','NaN and infinities preserve fallback']}
        receipt['units']=[r for r in receipt['units'] if r.get('binary')!=name]
        if target!='arm':
            result=subprocess.run([str(out/name)],text=True,capture_output=True,check=True)
            receipt['units'].append({'binary':name,'executed':True,'stdout':result.stdout,'stderr':result.stderr})
        receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    one('025');one('100')
