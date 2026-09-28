"""Paired unchanged identity/decision/truth gates for optimization candidates."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from evaluate import validate, prior
from build import BASE


def compare(case,ref,got,name):
    cid=case['case_id']
    a=validate(ref,case,'D'); b=validate(got,case,name)
    rows={(cid,'D'):a,(cid,name):b}
    identity=prior.identity(rows,{cid:case},{cid},'D',name)
    decisions=all(x['positive']==y['positive'] for x,y in zip(a['science'],b['science'],strict=True))
    truth=[]
    if case['split']=='control':
        for rx,s in enumerate(b['science']):
            positive=case['truth']['kind']=='pilot'; ok=s['positive']==positive
            if positive and s['positive']:
                t=case['truth']['receivers'][rx];epoch=t['epoch_samples']+t['fractional_delay_samples']
                dt=abs(prior.circular_samples(s['epoch_samples']-epoch,case['rate_hz']))/case['rate_hz']*1e6
                ok &= dt<=2 and abs(s['tracking_cfo_hz']-t['cfo_hz'])<=8000 and s['selected_window']==t['window']
            truth.append(bool(ok))
    return {'case_id':cid,'rate_hz':case['rate_hz'],'split':case['split'],'identity':identity,
        'decision_equality':decisions,'truth':truth,'reference_cost':a['cost'],'candidate_cost':b['cost'],
        'passed':identity['all_identity_gates_pass'] and decisions and all(truth)}


def main():
    p=argparse.ArgumentParser();p.add_argument('name');p.add_argument('--root',type=Path)
    p.add_argument('--controls-only',action='store_true');a=p.parse_args()
    root=a.root or HERE/'work'/a.name;out=root/'host-check';out.mkdir(exist_ok=False)
    cached=HERE/'host-reference';cached.mkdir(exist_ok=True)
    m=json.loads((BASE/'manifest.json').read_text()); rows=[]
    for case in m['cases']:
        if a.controls_only and case['split']!='control':continue
        t=m['templates'][case['template_key']]
        args=[str(BASE/'data'/case['raw_file']),str(BASE/'data'/t['exact']),str(BASE/'data'/t['control']),
            str(case['rate_hz']),case['edge'],case['case_id']]
        refpath=cached/(case['case_id']+'.json')
        if not refpath.exists():
            ref=subprocess.run([str(BASE/'host-asan/D'),*args],capture_output=True,timeout=30)
            (cached/(case['case_id']+'.stderr')).write_bytes(ref.stderr);ref.check_returncode();refpath.write_bytes(ref.stdout)
        got=subprocess.run([str(root/'host-asan'),*args],capture_output=True,timeout=30)
        (out/(case['case_id']+'.stderr')).write_bytes(got.stderr)
        (out/(case['case_id']+'.json')).write_bytes(got.stdout);got.check_returncode()
        result=compare(case,json.loads(refpath.read_text()),json.loads(got.stdout),a.name);rows.append(result)
        (out/'assessments.json').write_text(json.dumps(rows,indent=2)+'\n')
        print(case['case_id'],result['passed'],flush=True)
    if not all(r['passed'] for r in rows):raise RuntimeError('scientific comparison failed')


if __name__=='__main__':main()
