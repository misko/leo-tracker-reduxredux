"""Inventory compact owned artifacts; leave immutable old corpus as hash-bound inputs."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    published=[dict(path=str(p),relative_path=str(p.relative_to(HERE)),sha256=sha(p),bytes=p.stat().st_size)
        for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='lean_publication.json'
        and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts]
    local={e['path'] for e in published};external={}
    for protocol in (HERE/'protocol.json',HERE/'single_application/protocol.json'):
        for path,digest in json.loads(protocol.read_text())['files'].items():
            p=Path(path)
            if sha(p)!=digest:raise ValueError('frozen dependency changed: '+path)
            if path not in local:external[path]=dict(path=path,sha256=digest,bytes=p.stat().st_size,
                reason='immutable external input, original numerical source or preserved preparation log')
    payload=dict(schema='candidate-continuity-lean-publication/v1',published=published,
        external=list(external.values()),published_files=len(published),
        published_bytes=sum(e['bytes'] for e in published),
        replay_limitation='Exact original exports and repository graph dependencies remain hash-bound external inputs; no detector or recorded IQ is needed for path replay.')
    (HERE/'lean_publication.json').write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps(dict(files=payload['published_files'],bytes=payload['published_bytes'],external=len(external))))


if __name__=='__main__':main()
