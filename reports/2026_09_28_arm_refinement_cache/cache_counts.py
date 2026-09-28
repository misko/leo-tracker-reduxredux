"""Distinguish candidate evidence entries from actual repeated kernel work."""
import argparse
import hashlib
import json
from pathlib import Path


def summarize(folder):
    manifest=json.loads((folder/'manifest.json').read_text())
    if not manifest['complete']:raise ValueError('incomplete run')
    raw='raw_sha256' in manifest
    path=folder/('raw.jsonl' if raw else 'rows.jsonl')
    records=[json.loads(s) for s in path.read_text().splitlines()]
    windows=[r['native'] for r in records] if raw else [w for r in records for w in r['rows']]
    assert len(windows)==22*manifest['processed_dwells']
    result=dict(windows=len(windows),candidate_entries=0,refinement_cache_hits=0,glrt_cache_hits=0,
                conditioned_evaluations=0,glrt_kernel_calls=0)
    for w in windows:
        n=w['candidate_count'];a=w['refinement_cache_hits'];b=w['glrt_cache_hits']
        assert n==len(w['candidates']) and 0<=a<=n and 0<=b<=n
        result['candidate_entries']+=n;result['refinement_cache_hits']+=a;result['glrt_cache_hits']+=b
        result['conditioned_evaluations']+=n-a;result['glrt_kernel_calls']+=n-b
    result['source_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cohort',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();x=summarize(a.cohort);a.output.write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x,indent=2))
