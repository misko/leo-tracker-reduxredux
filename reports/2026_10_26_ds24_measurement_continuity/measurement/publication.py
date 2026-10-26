"""Create the compact publication inventory without rewriting scientific artifacts."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def entry(path, relative):
    return dict(path=str(path), relative_path=str(relative), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main():
    published = [entry(p, p.relative_to(HERE)) for p in sorted(HERE.rglob('*'))
                 if p.is_file() and p.name != 'lean_publication.json'
                 and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts]
    external = []
    protocol = json.loads((HERE/'protocol.json').read_text())
    local = {e['path'] for e in published}
    for path, digest in protocol['files'].items():
        if path not in local:
            p = Path(path)
            if hashlib.sha256(p.read_bytes()).hexdigest() != digest:
                raise ValueError('external frozen input changed: '+path)
            external.append(dict(path=path, sha256=digest, bytes=p.stat().st_size,
                                 reason='external immutable authority or preparation log'))
    payload = dict(schema='measurement-lean-publication/v1', published=published, external=external,
        published_files=len(published), published_bytes=sum(e['bytes'] for e in published),
        replay_limitation='Historical deployed interpreter/source, original fixture and external exact inputs remain required; no recorded IQ is required or read.')
    (HERE/'lean_publication.json').write_text(json.dumps(payload, indent=2)+'\n')
    print(json.dumps(dict(files=payload['published_files'], bytes=payload['published_bytes'], external=len(external))))


if __name__ == '__main__':
    main()
