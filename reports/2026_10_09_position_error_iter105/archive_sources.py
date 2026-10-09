"""Deterministic source archive with verified readback; preserve raw files."""
import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    paths=[HERE/'source-snapshot.json',HERE/'source-preflight.json']+sorted((HERE/'source-values').glob('*.json'))
    payload={str(p.relative_to(HERE)):p.read_bytes() for p in paths}
    output=io.BytesIO()
    with gzip.GzipFile(fileobj=output,mode='wb',mtime=0,filename='') as gz:
        with tarfile.open(fileobj=gz,mode='w',format=tarfile.USTAR_FORMAT) as tar:
            for name,data in sorted(payload.items()):
                member=tarfile.TarInfo(name);member.size=len(data);member.mode=0o644;member.mtime=0
                tar.addfile(member,io.BytesIO(data))
    data=output.getvalue();archive=HERE/'source-inputs.tar.gz'
    if archive.exists():assert archive.read_bytes()==data,'Existing archive differs; refusing overwrite'
    else:archive.write_bytes(data)
    manifest=dict(archive_sha256=hashlib.sha256(data).hexdigest(),files={n:dict(sha256=hashlib.sha256(v).hexdigest(),bytes=len(v)) for n,v in sorted(payload.items())})
    with tarfile.open(archive,'r:gz') as tar:
        assert tar.getnames()==sorted(payload)
        for member in tar.getmembers():assert member.isfile() and tar.extractfile(member).read()==payload[member.name]
    assert all(p.read_bytes()==payload[str(p.relative_to(HERE))] for p in paths)
    manifest.update(readback_verified=True,raw_local_files_preserved=True)
    path=HERE/'source-inputs-manifest.json';encoded=json.dumps(manifest,indent=2)+'\n'
    if path.exists():assert path.read_text()==encoded,'Existing manifest differs'
    else:path.write_text(encoded)
    print(len(paths),'files; archive bytes',len(data),'sha256',manifest['archive_sha256'])


if __name__=='__main__':main()
