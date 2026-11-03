"""Reuse existing track/bank exporters after donor availability qualification."""
import hashlib
import json
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor
import subprocess
import time

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT))
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def worker(stage,index):
    from tools.ds7_export_baseline import export,export_banks
    ap=HERE/'availability.json';availability=json.loads(ap.read_text());assert availability['passed']
    for p,h in availability['sources'].items():assert digest(p)==h,p
    doc=json.loads((HERE/f'capture-{index:02d}.json').read_text());capture=doc['capture_metadata']
    folder=HERE/f'numeric-{index:02d}'
    if stage=='tracks':
        result=export(capture,folder/'tracks.json',Path('/srv/bulk/leo'),Path('/var/lib/leo/tle'))
        assert result['analysis_manifest_sha256']==doc['analysis_manifest_sha256']
        assert result['snapshot_sha256']==availability['rows'][index]['baseline_snapshot_sha256']
        print(json.dumps(dict(index=index,stage=stage,tracks=len(result['tracks']),elapsed_seconds=result['elapsed_seconds'])),flush=True)
    elif stage=='banks':
        result=export_banks(capture,folder/'tracks.json',folder/'banks',Path('/srv/bulk/leo'),Path('/var/lib/leo/tle'))
        print(json.dumps(dict(index=index,stage=stage,result=result)),flush=True)
    else:raise ValueError(stage)


def launch(stage,index):
    begin=time.monotonic();stem=HERE/f'{stage}-{index:02d}'
    with stem.with_suffix('.log').open('x') as log:
        r=subprocess.run(['timeout','--kill-after=5s','90s',sys.executable,str(Path(__file__)),'worker',stage,str(index)],stdout=log,stderr=subprocess.STDOUT)
    sources={str(p):digest(p) for p in (Path(__file__),HERE/'availability.json',HERE/f'capture-{index:02d}.json',ROOT/'tools/ds7_export_baseline.py',stem.with_suffix('.log'))}
    result=dict(stage=stage,index=index,exit_code=r.returncode,elapsed_s=time.monotonic()-begin,sources=sources)
    with stem.with_suffix('.receipt.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='sources'}),flush=True)


if __name__=='__main__':
    if sys.argv[1]=='worker':worker(sys.argv[2],int(sys.argv[3]))
    else:
        with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(lambda i:launch(sys.argv[1],i),range(4)))
