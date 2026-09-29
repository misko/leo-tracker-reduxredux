"""Complete saved-IQ endpoint-search experiment, with input/binary bindings."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_28_arm_full_optimization'))
import arm_cohort as a


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--mode',choices=['pairs-only','union','union-fallback'],required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--full',action='store_true')
    p.add_argument('--arm',action='store_true')
    args=p.parse_args()
    if args.arm:
        selection=HERE.parent/'2026_09_28_arm_boundary_fallback/arm-cohort-v1/manifest.json'
    else:
        selection=HERE.parent/'2026_09_29_arm_lag_discovery'/('ds7-704-v1' if args.full else 'ds7-32-v1')/'summary.json'
    cohort=json.loads(selection.read_text());assert cohort['complete']
    selected=cohort['selected']
    binary=args.binary.resolve();digest=a.sha(binary)
    receipt=binary.parent/'build.json';build=json.loads(receipt.read_text())
    assert build['binary_sha256'][binary.name]==digest
    for name,value in build['source_sha256'].items():assert a.sha(binary.parent/name)==value
    oracle=json.loads((a.ORACLE/'oracle.json').read_text())
    templates={(r['context']['rate_hz'],r['context']['target']['edge']):r['templates'] for r in oracle['cases']}
    out=HERE/args.output;out.mkdir(exist_ok=False)
    manifest={'complete':False,'selected':selected,'processed_dwells':0,
              'mode':args.mode,'binary_sha256':digest,'selection_sha256':a.sha(selection),
              'build_sha256':a.sha(receipt),
              'oracle_sha256':a.sha(a.ORACLE/'oracle.json'),'runner_sha256':a.sha(Path(__file__)),
              'protocol_sha256':a.sha(HERE/'PROTOCOL.md'),
              'hardware':'PLUTO+ CPU0' if args.arm else 'host',
              'scope':'complete endpoint discovery plus local searches and any blind fallback; saved IQ, no capture'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    remote='/mnt/glrtbench/endpoint-'+str(int(time.time()))
    if args.arm:
        a.remote('mkdir '+shlex.quote(remote));a.upload(binary,remote+'/endpoint')
        assert a.remote('sha256sum '+remote+'/endpoint').split()[0]==digest
        manifest['remote_directory']=remote
    def worker(ctx):
        source=a.INPUTS/ctx['file'];assert a.sha(source)==ctx['sha256']
        template=templates[(ctx['rate_hz'],ctx['target']['edge'])]
        paths=[a.ORACLE/template[k]['file'] for k in ('exact','control')]
        for key,path in zip(('exact','control'),paths):assert a.sha(path)==template[key]['sha256']
        with tempfile.TemporaryDirectory(prefix='leo-endpoint-') as tmp:
            raw=Path(tmp)/'input.ci16';np.load(source,allow_pickle=False).tofile(raw)
            if args.arm:
                dests=[]
                for path in [*paths,raw]:
                    dest=remote+'/'+path.name;a.upload(path,dest)
                    assert a.remote('sha256sum '+shlex.quote(dest)).split()[0]==a.sha(path)
                    dests.append(dest)
                output=a.remote(shlex.join([remote+'/endpoint',str(ctx['rate_hz']),*dests,args.mode]),timeout=120)
            else:
                cmd=[str(binary),str(ctx['rate_hz']),*map(str,paths),str(raw),args.mode]
                r=subprocess.run(cmd,capture_output=True,text=True,check=True,timeout=120)
                assert not r.stderr;output=r.stdout
        rows=list(map(json.loads,output.splitlines()))
        assert len(rows)==22 and {(r['receiver_id'],r['probe_index']) for r in rows}=={(rx,w) for rx in (0,1) for w in range(11)}
        return {'context':ctx,'returncode':0,'stderr':'','rows':rows}
    results=[]
    with ThreadPoolExecutor(max_workers=1 if args.arm else 4) as pool,(out/'rows.jsonl').open('x') as stream:
        for result in pool.map(worker,selected):
            stream.write(json.dumps(result,allow_nan=False)+'\n');stream.flush();results.append(result)
            manifest['processed_dwells']+=1
            print('completed',manifest['processed_dwells'],flush=True)
    manifest.update(complete=True,processed_windows=22*len(results),rows_sha256=a.sha(out/'rows.jsonl'))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('complete',len(results),args.mode,flush=True)


if __name__=='__main__':main()
