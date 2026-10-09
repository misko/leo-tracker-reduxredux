"""Metadata and public-get integrity check; no numerical model evaluations."""
import hashlib
import json
from pathlib import Path
from source_adapters import failure_point,read_sanitized

HERE=Path(__file__).resolve().parent


def main():
    path=HERE/'source-plan.json';plan=json.loads(path.read_text());rows=plan['members']
    assert len(rows)==193 and len({m['member']['session_id'] for m in rows})==193
    documents=0;bootstraps=0
    for member in rows:
        for source in member['sources']:read_sanitized(source);documents+=1
        for failure in member.get('failure_checkpoint_bindings',[]):failure_point(member,failure);bootstraps+=1
    assert bootstraps==49
    result=dict(plan_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),members=193,sanitized_documents_verified=documents,historical_failure_bootstrap_receipts_verified=bootstraps,
                status='Metadata/hash/get-port verified; physical-model objective checks deferred to frozen numerical driver',
                source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE/'source_plan.py',HERE/'source_adapters.py',HERE/'source_preflight.py']})
    (HERE/'source-preflight.json').write_text(json.dumps(result,indent=2)+'\n');print(result)


if __name__=='__main__':main()
