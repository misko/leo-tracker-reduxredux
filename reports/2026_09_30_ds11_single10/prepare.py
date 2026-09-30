import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(action):
    source=HERE.parent/'2026_09_30_ds11_post_ds10/local/manifest.json'
    configpath=HERE.parent/'2026_09_30_ds10_single10/plan.json'
    manifest=json.loads(source.read_text());assert manifest['dataset_id']=='DS11' and manifest['status']=='minted'
    if action=='freeze':
        ordered=sorted(manifest['captures'],key=lambda r:(r['capture_start_utc_ns'],r['session_id']))
        assert len(ordered)>=32
        indices=[i*(len(ordered)-1)//31 for i in range(32)];rows=[]
        for index in indices:
            r=ordered[index];evidence=source.parent/'analysis'/f"{r['session_id']}.json"
            assert 'sha256:'+digest(evidence)==r['analysis_evidence_sha256']
            rows.append(dict(r,ordinal=index+1,unit_id=f'DS11-F{index+1:03d}',analysis_path=str(evidence)))
        paths=[source,configpath,HERE/'prepare.py',HERE/'export_one.py',HERE/'PROTOCOL.md']
        plan=dict(dataset='DS11',config=json.loads(configpath.read_text())['config'],captures=rows,hashes={str(p):digest(p) for p in paths})
        with (HERE/'export-plan.json').open('x') as f:json.dump(plan,f,indent=2)
        print('Frozen ordinals',[r['ordinal'] for r in rows])
    else:
        planpath=HERE/'export-plan.json';plan=json.loads(planpath.read_text());inputs=[]
        for row in plan['captures']:
            validated=json.loads((HERE/'exports'/row['unit_id']/'validated.json').read_text())
            assert validated['mint_analysis_match'] and validated['input']['session_id']==row['session_id']
            for a in validated['input']['artifacts']:assert 'sha256:'+digest(Path(a['path']))==a['sha256']
            inputs.append(validated['input'])
        assert len(inputs)==len({r['session_id'] for r in inputs})==32
        with (HERE/'plan.json').open('x') as f:json.dump(dict(config=plan['config'],inputs=inputs,source_sha256=digest(planpath)),f,indent=2)
        (HERE/'runs').mkdir(exist_ok=True)
        print('All 32 inputs verified and frozen for fitting')
if __name__=='__main__':main(sys.argv[1])
