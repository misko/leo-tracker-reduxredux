"""Verify frozen provenance and coverage before any DS10 geographic fit."""
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    plan=json.loads((HERE/'plan.json').read_text())
    frozen=json.loads((HERE/'fit-implementation.json').read_text())
    for name,h in frozen.items():assert digest(HERE/name)==h,name
    for name,h in plan['hashes'].items():assert digest(Path(name))==h,name
    records=[];missing=[]
    for row in plan['captures']:
        analysis=Path(row['analysis_path'])
        assert 'sha256:'+digest(analysis)==row['analysis_evidence_sha256']
        path=HERE/'exports'/row['unit_id']/'validated.json'
        if not path.exists():
            missing.append(row['unit_id']);continue
        result=json.loads(path.read_text())
        assert result['source_sha256']==frozen['export_one.py']
        assert result['input']['session_id']==row['session_id']
        assert result['input']['manifest_sha256']==row['manifest_sha256']
        for a in result['input']['artifacts']:
            assert 'sha256:'+digest(Path(a['path']))==a['sha256']
        obs_path=next(Path(a['path']) for a in result['input']['artifacts'] if a['kind']=='observations')
        obs=json.loads(obs_path.read_text())
        assert obs['analysis_manifest_sha256']==json.loads(analysis.read_text())['glrt']['metrics_manifest_sha256']
        assert obs['sample_rate_hz']==row['sample_rate_hz']
        records.append(dict(unit=row['unit_id'],session_id=row['session_id'],sample_rate_hz=obs['sample_rate_hz'],tracks=result['tracks'],observations=result['observations'],validated_sha256=digest(path)))
    assert len({r['session_id'] for r in records})==len(records)
    output=dict(complete=len(records)==24 and not missing,validated=len(records),missing=missing,
                tracks=sum(r['tracks'] for r in records),observations=sum(r['observations'] for r in records),
                sample_rate_counts=dict(Counter(r['sample_rate_hz'] for r in records)),records=records,
                plan_sha256=digest(HERE/'plan.json'),implementation_sha256=digest(HERE/'fit-implementation.json'))
    (HERE/'input-audit.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({k:v for k,v in output.items() if k!='records'},indent=2))


if __name__=='__main__':main()
