"""Freeze a qualified candidate's expected outputs for repeatability checks.

This never substitutes for the original-D identity/decision/truth gate: the
candidate must pass that gate first. Legacy -D filenames satisfy the existing
receipt reader; the stored method and manifest identify the actual candidate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def prepare_reference(candidate, here=HERE):
    if not re.fullmatch('[a-z0-9_]+',candidate):raise ValueError('candidate')
    root=here/'work'/candidate;source=root/'arm-check'
    completion=json.loads((source/'completion.json').read_text())
    assessments=json.loads((source/'assessments.json').read_text())
    build=json.loads((root/'arm.build.json').read_text())
    manifest=json.loads((source/'manifest.json').read_text())
    if not completion.get('complete') or not completion.get('passed') or not assessments or not all(x.get('passed') for x in assessments):
        raise ValueError('original-D scientific gate failed')
    if build.get('binary_sha256')!=manifest.get('sha256') or sha(root/'arm')!=manifest.get('sha256'):
        raise ValueError('candidate binary mismatch')
    selected=json.loads((here.parent/'concurrent/selected-cases.json').read_text())
    if not isinstance(selected,list) or not selected: raise ValueError('selected cases')
    qualified=[]
    for case in selected:
        cid=case.get('case_id') if isinstance(case,dict) else None
        if not isinstance(cid,str): raise ValueError('selected case')
        f=source/(cid+'.json');got=json.loads(f.read_text())
        if got.get('method')!=candidate or not any(x.get('case_id')==cid and x.get('passed') for x in assessments):
            raise ValueError('case not qualified')
        qualified.append((cid,f))
    out=here/'persistent/references'/candidate;out.mkdir(parents=True,exist_ok=False)
    hashes={}
    for cid,f in qualified:
        shutil.copyfile(f,out/(cid+'-D.json'));hashes[cid]=sha(f)
    (out/'qualification.json').write_text(json.dumps({
        'candidate':candidate,'candidate_binary_sha256':manifest['sha256'],
        'original_D_assessments':str(source/'assessments.json'),
        'original_D_assessments_sha256':sha(source/'assessments.json'),
        'original_D_scientific_gate_passed':True,'expected_output_hashes':hashes,
        'purpose':'exact repeatability against qualified candidate; not exact equality to original D',
    },indent=2)+'\n')
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args()
    print(prepare_reference(a.candidate))

if __name__=='__main__':main()
