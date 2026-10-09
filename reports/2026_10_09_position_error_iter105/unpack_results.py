"""Verify result archive and restore safely; never overwrite differing files."""
import hashlib
import json
import sys
import tarfile
import tempfile
from pathlib import Path,PurePosixPath

HERE=Path(__file__).resolve().parent


def restore(destination):
    destination=Path(destination)
    if destination.is_symlink():raise ValueError('Symlink destination forbidden')
    manifest=json.loads((HERE/'results-receipts-manifest.json').read_text());archive=HERE/'results-receipts.tar.gz'
    temporary=None
    if not archive.exists():
        temporary=tempfile.NamedTemporaryFile(prefix='leo105-results-',suffix='.tar.gz')
        for part in manifest['parts']:
            name=PurePosixPath(part['name']);assert len(name.parts)==1 and not name.is_absolute()
            data=(HERE/part['name']).read_bytes()
            assert len(data)==part['bytes'] and hashlib.sha256(data).hexdigest()==part['sha256']
            temporary.write(data)
        temporary.flush();archive=Path(temporary.name)
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==manifest['archive_sha256']
    payload={}
    with tarfile.open(archive,'r:gz') as tar:
        assert len(tar.getmembers())==len(manifest['files'])
        for member in tar.getmembers():
            name=PurePosixPath(member.name)
            assert member.isfile() and not name.is_absolute() and '..' not in name.parts
            assert len(name.parts)>=3 and name.parts[0]=='results' and name.suffix=='.json'
            assert member.name in manifest['files'] and member.name not in payload
            data=tar.extractfile(member).read();expected=manifest['files'][member.name]
            assert len(data)==expected['bytes'] and hashlib.sha256(data).hexdigest()==expected['sha256']
            target=destination/member.name
            for parent in [target,*target.parents]:
                if parent==destination.parent:break
                if parent.is_symlink():raise ValueError('Symlink path forbidden')
            if target.exists():assert target.is_file() and target.read_bytes()==data,'Existing file differs'
            payload[member.name]=data
    destination.mkdir(parents=True,exist_ok=True)
    for name,data in payload.items():
        target=destination/name
        if target.exists():continue
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(data)
    if temporary is not None:temporary.close()
    return len(payload)


if __name__=='__main__':print('Verified/restored',restore(sys.argv[1]),'files')
