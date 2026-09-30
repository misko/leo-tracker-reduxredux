"""Audit frozen inputs, sources, all attempts and qualification gates."""
import hashlib,json,math
from pathlib import Path
from batch import METHODS
HERE=Path(__file__).resolve().parent

def main():
    plan=json.loads((HERE/'plan.json').read_text());export=json.loads((HERE/'export-plan.json').read_text())
    assert len(plan['inputs'])==len(export['captures'])==32
    assert len({r['session_id'] for r in plan['inputs']})==32
    for name,h in export['hashes'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
    for name,h in json.loads((HERE/'implementation.json').read_text())['method_sources'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
    counts=dict(attempts=0,qualified=0,starts=0,qualified_starts=0,receipt_overrides=0,launcher_retries=0,input_placeholder_overrides=0)
    failures=[]
    for i,entry in enumerate(plan['inputs']):
        assert entry['session_id']==export['captures'][i]['session_id']
        assert json.loads((HERE/'unit-plans'/f'{i:02d}.json').read_text())['inputs'][i]==entry
        for a in entry['artifacts']:assert 'sha256:'+hashlib.sha256(Path(a['path']).read_bytes()).hexdigest()==a['sha256']
        for method in METHODS:
            name=f'{i:02d}_{method}';p=HERE/'runs'/f'{name}.json';receipt=HERE/'runs'/f'{name}.receipt.json';retry=HERE/'runs'/f'{name}.retry.receipt.json'
            if retry.exists():
                counts['receipt_overrides']+=1;assert receipt.exists()
                original=json.loads(receipt.read_text())
                counts['input_placeholder_overrides' if original.get('reason')=='input_export_failed' else 'launcher_retries']+=1
                receipt=retry
            r=json.loads(receipt.read_text());assert r['index']==i and r['method']==method
            counts['attempts']+=1
            if not p.exists():failures.append(dict(index=i,method=method,exit_code=r['exit_code']));continue
            assert r['exit_code']==0
            d=json.loads(p.read_text());assert d['session']==entry['session_id'] and d['method']==method and d['index']==i
            assert len(d['starts'])==3
            for s in d['starts']:
                counts['starts']+=1;counts['qualified_starts']+=int(s['qualified'])
                assert s['qualified']==bool(s['success'] and not s['boundary'] and s['gradient']<=.01 and s['audit']<=.02)
            selected=d['selected']
            if selected:
                counts['qualified']+=1
                assert selected['qualified'] and all(math.isfinite(v) for v in selected['x'])
                assert selected['score']==max(s['score'] for s in d['starts'] if s['qualified'])
                if method in ('slope','curvature'):
                    q=d['quadrature'];assert q['score']<=.02 and q['held']<=.02 and q['gradient']<=.01
                    assert json.loads((HERE/'runs'/f'{i:02d}_q020.json').read_text())['selected']
    assert counts['attempts']==320
    summary=json.loads((HERE/'summary.json').read_text());assert len(summary['cells'])==320
    assert sum(r['qualified'] for r in summary['summary'])==counts['qualified']
    result=dict(counts=counts,execution_failures=failures,frozen_sources_verified=True,inputs_verified=32)
    (HERE/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
