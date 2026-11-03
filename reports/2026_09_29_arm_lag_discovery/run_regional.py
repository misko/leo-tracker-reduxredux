"""Actual IQ-to-GLRT rerun using only current-IQ timing proposals."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import argparse
import numpy as np
import evaluate

HERE=Path(__file__).resolve().parent
a=evaluate.a

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--full',action='store_true')
    parser.add_argument('--features',default='ds7-32-v1');parser.add_argument('--output')
    parser.add_argument('--inputs',type=Path);args=parser.parse_args()
    full=args.full
    if args.inputs:a.INPUTS=args.inputs
    out=HERE/(args.output or ('regional-control32-v1' if full else 'regional32-v1'));out.mkdir(exist_ok=False)
    feature=HERE/args.features
    summary=json.loads((feature/'summary.json').read_text());assert summary['complete']
    records={}
    for row in map(json.loads,(feature/'rows.jsonl').read_text().splitlines()):
        c=row['context'];records[(c['session_id'],c['visit_index'],row['window'],row['rx'])]=row
    oracle=json.loads((a.ORACLE/'oracle.json').read_text())
    templates={(c['context']['rate_hz'],c['context']['target']['edge']):c['templates'] for c in oracle['cases']}
    binary=HERE/'regional-builds/host-v1/cohort_regional'
    receipt=json.loads((binary.parent/'regional-build.json').read_text());assert a.sha(binary)==receipt['binary_sha256']
    manifest={'complete':False,'selected':summary['selected'],'processed_dwells':0,
        'method':'full timing control' if full else 'combined top4 timing peaks +/-4 samples, full CFO/fine/boundary GLRT',
        'feature_rows_sha256':a.sha(feature/'rows.jsonl'),'binary_sha256':a.sha(binary),
        'build_sha256':a.sha(binary.parent/'regional-build.json'),
        'timing_scope':'Native search only; proposal cost excluded'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    def worker(ctx):
        source=a.INPUTS/ctx['file'];assert a.sha(source)==ctx['sha256']
        n=round(ctx['rate_hz']/750);lists=[]
        for w in range(11):
            for rx in range(2):
                rec=records[(ctx['session_id'],ctx['visit_index'],w,rx)]
                epochs=list(range(n)) if full else sorted({x for c in rec['ranked_epochs']['combined'][:4]
                    for x in range(max(0,c-4),min(n,c+5))})
                lists.append(str(len(epochs))+' '+ ' '.join(map(str,epochs)))
        t=templates[(ctx['rate_hz'],ctx['target']['edge'])]
        for item in t.values():assert a.sha(a.ORACLE/item['file'])==item['sha256']
        with tempfile.TemporaryDirectory(prefix='lag-regional-') as tmp:
            tmp=Path(tmp);raw=tmp/'input.ci16';np.load(source,allow_pickle=False).tofile(raw)
            regions=tmp/'regions.txt';regions.write_text('\n'.join(lists)+'\n')
            cmd=[str(binary),str(ctx['rate_hz']),str(a.ORACLE/t['exact']['file']),
                str(a.ORACLE/t['control']['file']),str(raw),str(regions)]
            result=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
        assert result.returncode==0 and not result.stderr
        rows=[json.loads(s) for s in result.stdout.splitlines()];assert len(rows)==22
        return {'context':ctx,'returncode':0,'stderr':'','rows':rows}
    with ThreadPoolExecutor(max_workers=4) as pool,(out/'rows.jsonl').open('x') as stream:
        for row in pool.map(worker,summary['selected']):
            stream.write(json.dumps(row,allow_nan=False)+'\n');stream.flush();manifest['processed_dwells']+=1
            print(manifest['processed_dwells'],flush=True)
    manifest.update(complete=True,rows_sha256=a.sha(out/'rows.jsonl'))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':main()
