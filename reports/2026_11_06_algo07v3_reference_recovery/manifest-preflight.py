"""Verify the unmodified historical manifests under exact private overlays."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def main(args):
    fixture = Path('/srv/bulk/leo/research/algo07-star-20261104/iteration000')
    if args.inside:
        from leo.cli.algo07_profile import verify
        result = {name: verify(fixture / name)
                  for name in ('frozen-r2.json', 'presentation-frozen.json')}
        assert all(row['verified'] for row in result.values()), result
        with args.output.open('x') as stream:
            json.dump(dict(manifests=result, original_manifests_unchanged=True,
                           bindings_sha256=hashlib.sha256(args.bindings.read_bytes()).hexdigest()),
                      stream, indent=2)
            stream.write('\n')
        print(json.dumps(result), flush=True)
        return
    rows = json.loads(args.bindings.read_bytes())
    assert rows and len({r['target'] for r in rows}) == len(rows)
    for row in rows:
        assert hashlib.sha256(Path(row['source']).read_bytes()).hexdigest() == row['sha256']
        assert Path(row['target']).is_file()
    before = os.readlink('/proc/self/ns/mnt')
    os.unshare(os.CLONE_NEWNS | os.CLONE_NEWNET)
    assert os.readlink('/proc/self/ns/mnt') != before
    subprocess.run(['mount', '--make-rprivate', '/'], check=True)
    for row in rows:
        subprocess.run(['mount', '--bind', row['source'], row['target']], check=True)
        subprocess.run(['mount', '-o', 'remount,bind,ro', row['target']], check=True)
        assert hashlib.sha256(Path(row['target']).read_bytes()).hexdigest() == row['sha256']
    command = [sys.executable, '-B', 'tools/algo07_star_archive.py', 'exec', '--view',
               str(fixture / 'tle-view'), '--manifest', str(fixture / 'frozen.json'), '--',
               sys.executable, '-B', str(Path(__file__).resolve()), '--inside',
               '--bindings', str(args.bindings), '--output', str(args.output)]
    os.execvpe(command[0], command, os.environ)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bindings', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inside', action='store_true')
    main(parser.parse_args())
