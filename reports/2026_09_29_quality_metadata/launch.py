import hashlib
import json
import subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PYTHON='/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python'


if __name__=='__main__':
    pool_path=HERE.parent/'2026_09_29_scan_budget/manifest.json'
    pool=json.loads(pool_path.read_text())
    scans=[]
    paths=[*HERE.glob('*.py'),HERE/'PROTOCOL.md',pool_path,HERE.parent/'2026_09_28_full_manifest_inputs/environment.json']
    for ds in ('DS7','DS8','DS9'):
        s=next(s for s in pool['sets'] if s['dataset']==ds and s['count']==24)
        first=min(s['scans'],key=lambda x:(x['start_utc_ns'],x['session_id']))
        artifact=next(a for a in first['input']['artifacts'] if a['kind']=='observations')
        p=Path(artifact['path'])
        assert 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()==artifact['sha256']
        scans.append(dict(dataset=ds,session_id=first['session_id'],observations=str(p)))
        paths.append(p)
    with (HERE/'manifest.json').open('x') as out:
        json.dump(dict(scans=scans,hashes={str(p.relative_to(ROOT)) if p.is_absolute() else str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}),out,indent=2)
    for ds in ('DS7','DS8','DS9'):
        try:
            p=subprocess.run(['sudo','-n','env','OPENBLAS_NUM_THREADS=1',PYTHON,str(HERE/'export.py'),ds],capture_output=True,text=True,timeout=60)
            receipt=dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr)
        except subprocess.TimeoutExpired:
            receipt=dict(exit_code=None,timed_out=True)
        with (HERE/f'{ds}.receipt.json').open('x') as out:
            json.dump(receipt,out,indent=2)
        print(ds,receipt,flush=True)
