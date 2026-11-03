import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def select(captures):
    ordered=sorted(captures,key=lambda r:(r['capture_start_utc_ns'],r['session_id']))
    if len(ordered)<24 or len({r['session_id'] for r in ordered})!=len(ordered):
        raise ValueError('Require at least 24 unique recordings')
    indices=[i*(len(ordered)-1)//23 for i in range(24)]
    return [(i,ordered[i]) for i in indices]


def main():
    source=HERE.parent/'2026_09_29_ds10_post_ds9/local/manifest.json'
    config_path=HERE.parent/'2026_09_29_scan_budget/manifest.json'
    manifest=json.loads(source.read_text());config=json.loads(config_path.read_text())['config']
    assert manifest['dataset_id']=='DS10' and manifest['status']=='minted' and len(manifest['captures'])==187
    rows=[]
    for rank,capture in select(manifest['captures']):
        evidence=source.parent/'analysis'/f"{capture['session_id']}.json"
        assert 'sha256:'+hashlib.sha256(evidence.read_bytes()).hexdigest()==capture['analysis_evidence_sha256']
        rows.append(dict(capture,ordinal=rank+1,unit_id=f'DS10-F{rank+1:03d}',analysis_path=str(evidence)))
    paths=[source,config_path,HERE/'prepare.py',HERE/'PROTOCOL.md',ROOT/'tools/ds7_export_baseline.py',ROOT/'tools/ds7_baseline_adapter.py',ROOT/'tools/ds7_fast_baseline_adapter.py',HERE.parent/'2026_09_29_scan_budget/run.py',HERE.parent/'2026_09_29_unassociated_trend/trend_mixture.py',HERE.parent/'2026_09_29_receiver_holdout/run.py']
    result=dict(dataset='DS10',config=config,captures=rows,panels={f'N8_{j}':[r['session_id'] for r in rows[j::3]] for j in range(3)},hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    result['panels']['N24']=[r['session_id'] for r in rows]
    with (HERE/'plan.json').open('x') as out:json.dump(result,out,indent=2)
    print('Frozen ordinals',[r['ordinal'] for r in rows])


if __name__=='__main__':main()
