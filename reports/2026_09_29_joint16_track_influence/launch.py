import concurrent.futures
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def worker(ds):
    try:
        p=subprocess.run([sys.executable,str(HERE/'run.py'),ds],capture_output=True,text=True,timeout=300)
        receipt=dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr)
    except subprocess.TimeoutExpired:
        receipt=dict(exit_code=None,timed_out=True)
    with (HERE/f'{ds}.receipt.json').open('x') as out:
        json.dump(receipt,out,indent=2)
    print(ds,receipt,flush=True)


if __name__=='__main__':
    hashes=json.loads((HERE.parent/'2026_09_29_joint16_association_control/manifest.json').read_text())['hashes']
    paths=[*HERE.glob('*.py'),HERE/'PROTOCOL.md']
    paths.extend((HERE.parent/'2026_09_29_joint16_association_control').glob('DS*_*.json'))
    for p in paths:
        hashes[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    with (HERE/'manifest.json').open('x') as out:
        json.dump(dict(hashes=hashes),out,indent=2)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(worker,('DS7','DS8','DS9')))
