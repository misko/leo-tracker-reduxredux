"""Prepare a small exact manifest; no scientific computation or source copying."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    published=[]
    for path in sorted(HERE.rglob('*')):
        if not path.is_file() or path.name=='lean_publication.json' or any(
                x in path.parts for x in ('__pycache__','.pytest_cache')):continue
        published.append(dict(path=str(path),relative_path=str(path.relative_to(HERE)),
                              sha256=sha(path),bytes=path.stat().st_size))
    protocol=json.loads((HERE/'protocol.json').read_text());external=[]
    for value,digest in protocol['files'].items():
        path=Path(value)
        if path.is_relative_to(HERE):continue
        if sha(path)!=digest:raise ValueError('external input changed: '+value)
        external.append(dict(path=value,sha256=digest,bytes=path.stat().st_size,
                             status='external_hash_bound_original_input'))
    for value in ('audit/measurement_preflight.json','audit/measurement_terminal.json'):
        path=HERE.parent/value
        external.append(dict(path=str(path),sha256=sha(path),bytes=path.stat().st_size,
                             status='independent_audit_published_by_coordinator'))
    result=dict(schema='detector-response-lean-publication/v1',published=published,
                total_published_bytes=sum(p['bytes'] for p in published),external_files=external,
                excluded_raw_IQ='Not persisted; deterministic generation and exact IQ hashes retained.',
                replay_limitation='Driver requires original absolute input paths and immutable historical interpreter. Correlations/results and saved-only report are portable with path remapping; no detector identity substitution is valid.')
    target=HERE/'lean_publication.json';target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(files=len(published),bytes=result['total_published_bytes'],external=len(external),
                         manifest_sha256=sha(target))))


if __name__=='__main__':main()
