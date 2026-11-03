"""Rerun masked coarse acquisition, refinement and GLRT on saved IQ."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from features import HERE, INPUTS, ORACLE, sha


def mask_for(proposal,method,threshold):
    if method=='full' or (method=='guard5' and proposal['sqrt_confidence']<=threshold):return 2047
    ranking=proposal['ranking'] if method=='log9' else proposal['sqrt_ranking']
    k={'sqrt3':3,'sqrt5':5,'log9':9,'guard5':5}[method]
    return sum(1<<f for f in ranking[:k])


def run(features,binary,output,method,workers):
    feature_manifest=json.loads((features/'manifest.json').read_text());assert feature_manifest['complete']
    selected=feature_manifest['native_selected'];root=INPUTS[feature_manifest['dataset']]
    records={(r['context']['session_id'],r['context']['visit_index']):r for r in
             map(json.loads,(features/'rows.jsonl').read_text().splitlines())}
    choice=json.loads((HERE/'method-selection.json').read_text());threshold=choice['threshold']
    templates={}
    for c in json.loads((ORACLE/'oracle.json').read_text())['cases']:
        templates[(c['context']['rate_hz'],c['context']['target']['edge'])]=c['templates']
    receipt=json.loads((binary.parent/'build.json').read_text());assert sha(binary)==receipt['binary_sha256'][binary.name]
    output.mkdir(parents=True,exist_ok=False)
    manifest=dict(selected=selected,complete=False,method=method,binary_sha256=sha(binary),
        build_receipt_sha256=sha(binary.parent/'build.json'),feature_rows_sha256=sha(features/'rows.jsonl'),
        method_selection_sha256=sha(HERE/'method-selection.json'),threshold=threshold,
        timing_scope='Native GLRT only; PSD proposal cost excluded',processed_dwells=0)
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    def worker(ctx):
        record=records[(ctx['session_id'],ctx['visit_index'])]
        assert record['context']['sha256']==ctx['sha256']
        source=root/ctx['file'];assert sha(source)==ctx['sha256']
        masks=[mask_for(w['proposal'],method,threshold) for w in record['windows']]
        assert [(w['probe_index'],w['receiver_id']) for w in record['windows']]==[(p,r) for p in range(11) for r in range(2)]
        t=templates[(ctx['rate_hz'],ctx['target']['edge'])]
        for item in t.values():assert sha(ORACLE/item['file'])==item['sha256']
        with tempfile.TemporaryDirectory(prefix='psd-mask-') as tmp:
            tmp=Path(tmp);raw=tmp/'iq.ci16';maskfile=tmp/'masks.txt'
            np.asarray(np.load(source,allow_pickle=False),dtype='<i2').tofile(raw)
            maskfile.write_text('\n'.join(map(str,masks))+'\n')
            command=[str(binary),str(ctx['rate_hz']),str(ORACLE/t['exact']['file']),str(ORACLE/t['control']['file']),str(raw),str(maskfile)]
            proc=subprocess.run(command,text=True,capture_output=True,timeout=120)
        windows=[json.loads(line) for line in proc.stdout.splitlines()]
        if proc.returncode or proc.stderr or len(windows)!=22:raise RuntimeError((ctx,proc.returncode,proc.stderr))
        assert [w['coarse_mask'] for w in windows]==masks
        return dict(context=ctx,returncode=0,stderr='',rows=windows)
    with ThreadPoolExecutor(max_workers=workers) as pool,(output/'rows.jsonl').open('x') as stream:
        for r in pool.map(worker,selected):
            stream.write(json.dumps(r,allow_nan=False)+'\n');stream.flush();manifest['processed_dwells']+=1
    manifest.update(complete=True,rows_sha256=sha(output/'rows.jsonl'))
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(method=method,dataset=feature_manifest['dataset'],completed=manifest['processed_dwells'])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--features',type=Path,required=True)
    p.add_argument('--binary',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--method',choices=('full','sqrt3','sqrt5','log9','guard5'),required=True)
    p.add_argument('--workers',type=int,default=8);a=p.parse_args();run(a.features,a.binary.resolve(),a.output,a.method,a.workers)
