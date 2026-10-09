"""Archive terminal pilot results without changing any raw receipt."""
import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

HERE=Path(__file__).resolve().parent


def publish_parts(archive,manifest_path):
    manifest=json.loads(manifest_path.read_text());parts=[]
    with archive.open('rb') as stream:
        index=0
        while data:=stream.read(40*1024*1024):
            name=f'results-receipts.tar.gz.part{index:03d}';path=HERE/name
            if path.exists():assert path.read_bytes()==data
            else:path.write_bytes(data)
            parts.append(dict(name=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()));index+=1
    manifest['parts']=parts
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    return parts


def main():
    protocol=json.loads((HERE/'protocol.json').read_text())
    for label in protocol['labels']:
        root=HERE/'results'/label
        baseline=json.loads((root/'baseline.json').read_text())
        assert baseline['status'] in ('complete','failed','input-failed','budget-exhausted')
        if baseline['status']=='complete':
            candidate=json.loads((root/'candidate.json').read_text())
            assert candidate['status'] in ('complete','failed','input-failed','budget-exhausted')
    paths=sorted((HERE/'results').rglob('*.json'))
    payload={str(path.relative_to(HERE)):path.read_bytes() for path in paths}
    stream=io.BytesIO()
    with gzip.GzipFile(fileobj=stream,mode='wb',filename='',mtime=0) as gz:
        with tarfile.open(fileobj=gz,mode='w',format=tarfile.PAX_FORMAT) as tar:
            for name,data in payload.items():
                info=tarfile.TarInfo(name);info.mode=0o644;info.mtime=0;info.size=len(data)
                tar.addfile(info,io.BytesIO(data))
    data=stream.getvalue();archive=HERE/'results-receipts.tar.gz'
    if archive.exists():assert archive.read_bytes()==data,'Refusing archive replacement'
    else:archive.write_bytes(data)
    with tarfile.open(archive,'r:gz') as tar:
        assert tar.getnames()==list(payload)
        for member in tar.getmembers():assert member.isfile() and tar.extractfile(member).read()==payload[member.name]
    assert all(path.read_bytes()==payload[str(path.relative_to(HERE))] for path in paths)
    manifest=dict(archive_sha256=hashlib.sha256(data).hexdigest(),protocol_sha256=hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest(),
                  files={name:dict(sha256=hashlib.sha256(value).hexdigest(),bytes=len(value)) for name,value in payload.items()},readback_verified=True,raw_local_preserved=True)
    path=HERE/'results-receipts-manifest.json';encoded=json.dumps(manifest,indent=2)+'\n'
    if path.exists():
        previous=json.loads(path.read_text());previous.pop('parts',None);assert previous==manifest
    else:path.write_text(encoded)
    publish_parts(archive,path)
    print('Archived',len(paths),'receipts;',len(data),'bytes;',manifest['archive_sha256'])


if __name__=='__main__':main()
