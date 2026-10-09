"""Validate all source members before safely restoring without overwrites."""
import hashlib
import json
import sys
import tarfile
from pathlib import Path,PurePosixPath

HERE=Path(__file__).resolve().parent


def restore(destination):
    destination=Path(destination)
    if destination.is_symlink():raise ValueError('Symlink destination forbidden')
    manifest=json.loads((HERE/'source-inputs-manifest.json').read_text());archive=HERE/'source-inputs.tar.gz'
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==manifest['archive_sha256']
    payload={}
    with tarfile.open(archive,'r:gz') as tar:
        assert len(tar.getmembers())==len(manifest['files'])
        for member in tar.getmembers():
            name=PurePosixPath(member.name)
            assert member.isfile() and not name.is_absolute() and '..' not in name.parts
            assert member.name in manifest['files'] and member.name not in payload
            assert member.name in ('source-snapshot.json','source-preflight.json') or (len(name.parts)==2 and name.parts[0]=='source-values' and name.suffix=='.json')
            data=tar.extractfile(member).read();expected=manifest['files'][member.name]
            assert len(data)==expected['bytes'] and hashlib.sha256(data).hexdigest()==expected['sha256']
            target=destination/member.name
            for parent in [target,*target.parents]:
                if parent==destination.parent:break
                if parent.is_symlink():raise ValueError('Symlink path forbidden')
            if target.exists():assert target.is_file() and target.read_bytes()==data,'Existing file differs; refusing overwrite'
            payload[member.name]=data
    destination.mkdir(parents=True,exist_ok=True)
    for name,data in payload.items():
        target=destination/name
        if target.exists():continue
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(data)
    return len(payload)


if __name__=='__main__':print('Verified/restored',restore(sys.argv[1]),'files')
