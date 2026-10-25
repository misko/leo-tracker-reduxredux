"""Standard-library verification/restoration of this wave's new artifacts."""

import argparse
import hashlib
import json
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets',type=Path,required=True)
    parser.add_argument('--restore',type=Path,help='Optional new directory for exact archived relative paths')
    args=parser.parse_args()
    if args.restore:args.restore.mkdir(parents=True,exist_ok=False)
    index=json.loads((HERE/'publication_index.json').read_text())
    for row in index['direct_files']:
        path=HERE/row['path']
        assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],path
    members=0
    for row in index['assets']:
        archive=args.assets/row['asset']
        assert archive.stat().st_size==row['bytes'] and sha(archive)==row['sha256'],archive
        expected={v['member']:v for v in row['members']}
        with tarfile.open(archive,'r:gz') as tar:
            assert set(tar.getnames())==set(expected)
            for member in tar.getmembers():
                assert member.isfile() and not member.name.startswith('/') and '..' not in Path(member.name).parts
                data=tar.extractfile(member).read();want=expected[member.name]
                assert len(data)==want['bytes'] and hashlib.sha256(data).hexdigest()==want['sha256']
                if args.restore:
                    destination=args.restore/member.name
                    destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(data)
                members+=1
    print(json.dumps(dict(all_passed=True,assets=len(index['assets']),members=members,
        direct_files=len(index['direct_files']),index_sha256=sha(HERE/'publication_index.json'),
        restored=str(args.restore) if args.restore else None,no_inference=True),indent=2))


if __name__=='__main__':
    main()
