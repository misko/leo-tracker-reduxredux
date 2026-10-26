"""Bind compact publication files while retaining large original artifacts locally."""
import json
from pathlib import Path
import geometry_cache as gc

HERE=Path(__file__).resolve().parent


def main():
    published=[];external=[]
    for path in sorted(HERE.rglob('*')):
        if not path.is_file() or any(part in ('.pytest_cache','__pycache__') for part in path.parts):continue
        relative=path.relative_to(HERE)
        if path.name=='lean_publication.json':continue
        large=relative.parts[0]=='cache' or path.name=='gates.json' or path.stat().st_size>1024*1024
        row=dict(path=str(path),relative_path=str(relative),bytes=path.stat().st_size,sha256=gc.sha(path))
        (external if large else published).append(row)
    body=dict(schema='position-lean-publication/v1',published=published,external_hash_bound=external,
        published_bytes=sum(row['bytes'] for row in published),external_bytes=sum(row['bytes'] for row in external),
        replay_limit='Satellite states and repetitive full parent/gate ledgers remain at their original absolute paths. Protocol/RF manifests preserve external dependency hashes; full calibration replay requires the local corpus.',
        manifest_self_hash_excluded=True)
    with (HERE/'lean_publication.json').open('x') as stream:json.dump(body,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(published_files=len(published),published_bytes=body['published_bytes'],external_files=len(external),external_bytes=body['external_bytes'])))


if __name__=='__main__':main()
