import concurrent.futures
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PYTHON='/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python'


def read(p):
    return json.loads(p.read_text())


def export_dataset(ds):
    plan=read(HERE/'manifest.json')
    for item in [s for s in plan['scans'] if s['real_dataset']==ds and not s['reused']]:
        try:
            p=subprocess.run(['sudo','-n','env','OPENBLAS_NUM_THREADS=1',PYTHON,str(HERE/'export.py'),item['dataset']],capture_output=True,text=True,timeout=60)
            receipt=dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr)
        except subprocess.TimeoutExpired:
            receipt=dict(exit_code=None,timed_out=True)
        with (HERE/f"{item['dataset']}.receipt.json").open('x') as out:
            json.dump(receipt,out,indent=2)
        print(item['dataset'],receipt,flush=True)


def prepare():
    pool=read(HERE.parent/'2026_09_29_scan_budget/manifest.json')
    hashes=read(HERE.parent/'2026_09_29_source_consistent_pilot/manifest.json')['hashes']
    paths=[*HERE.glob('*.py'),HERE/'PROTOCOL.md',HERE.parent/'2026_09_29_quality_metadata_corrected/export.py',HERE.parent/'2026_09_28_full_manifest_inputs/environment.json',HERE.parent/'2026_09_29_source_consistent_pilot/selection.py']
    scans=[]
    for ds in ('DS7','DS8','DS9'):
        baseline_path=HERE.parent/f'2026_09_29_time_balanced_scans/grid_{ds}_balanced_0.json'
        baseline=read(baseline_path);paths.append(baseline_path)
        source=next(s for s in pool['sets'] if s['dataset']==ds and s['count']==24)
        for i,sid in enumerate(baseline['sessions']):
            s=next(s for s in source['scans'] if s['session_id']==sid)
            artifact=next(a for a in s['input']['artifacts'] if a['kind']=='observations')
            p=Path(artifact['path'])
            assert 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()==artifact['sha256']
            paths.append(p)
            quality=HERE.parent/f'2026_09_29_quality_metadata_corrected/{ds}.json' if i==0 else HERE/f'{ds}_{i}.json'
            if i==0:
                assert read(quality)['session_id']==sid;paths.append(quality)
            scans.append(dict(dataset=f'{ds}_{i}',real_dataset=ds,session_id=sid,observations=str(p),quality_path=str(quality),reused=i==0,input=s['input']))
    for p in paths:
        hashes[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    with (HERE/'manifest.json').open('x') as out:
        json.dump(dict(scans=scans,config=pool['config'],hashes=hashes),out,indent=2)


def seal():
    plan=read(HERE/'manifest.json');hashes={}
    for s in plan['scans']:
        if not s['reused']:
            assert read(HERE/f"{s['dataset']}.receipt.json")['exit_code']==0
        p=Path(s['quality_path']);data=read(p)
        assert data['session_id']==s['session_id']
        assert data['baseline_sha256']==hashlib.sha256(Path(s['observations']).read_bytes()).hexdigest()
        hashes[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    with (HERE/'quality-seal.json').open('x') as out:
        json.dump(dict(hashes=hashes),out,indent=2)
    print('Sealed',len(hashes),'quality sidecars')


if __name__=='__main__':
    if sys.argv[1]=='prepare':
        prepare()
    elif sys.argv[1]=='export':
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(export_dataset,('DS7','DS8','DS9')))
    elif sys.argv[1]=='seal':
        seal()
