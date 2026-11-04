"""Give bounded research replays one immutable TLE view without changing workers.

Materialization reads snapshots through TleArchiveReader. Execution bind-mounts
the clone read-only in a new, private Linux mount namespace. The live host archive
and its collector are unchanged. Both paired paths must use the same manifest.
"""
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from leo.cli.algo07_profile import digest, write_new
from leo.operations.tle_archive import TleArchiveReader

ARCHIVE = Path('/var/lib/leo/tle')


def materialize(reader, manifest, target):
    target = Path(target).resolve()
    if (target.is_relative_to('/mnt/qnap01') or target.is_relative_to(reader.root.resolve())
            or reader.root.resolve().is_relative_to(target)):
        raise ValueError('New local archive clone separate from its source required')
    frozen = json.loads(Path(manifest).read_text())
    requested = set(frozen['metadata']['tle_snapshot_paths'])
    pinned = {row['path']: row['sha256'] for row in frozen['files']}
    snapshots = {str(s.path.resolve()): s for s in reader.list_snapshots()}
    if not requested or not requested <= snapshots.keys() or not requested <= pinned.keys():
        raise ValueError('Every frozen snapshot must be available and pinned')
    target.mkdir(parents=True, mode=0o700, exist_ok=False)
    files = []
    for name in sorted(requested):
        snapshot = snapshots[name]
        payload = reader.read(snapshot).encode('ascii')
        actual = hashlib.sha256(payload).hexdigest()
        if actual != pinned[name]:
            raise ValueError('Snapshot differs from frozen bytes')
        relative = snapshot.path.relative_to(reader.root)
        path = target/relative
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(payload)
        files.append(dict(path=str(relative), sha256=actual))
    receipt = dict(schema_version=1, kind='algo07-star-tle-view',
                   source_root=str(reader.root.resolve()),
                   frozen_manifest_sha256=digest(Path(manifest)), files=files)
    write_new(target/'view.json', receipt)
    return receipt


def verify_view(root, manifest):
    root = Path(root).resolve(strict=True)
    receipt = json.loads((root/'view.json').read_text())
    if (receipt['kind'] != 'algo07-star-tle-view' or
            receipt['frozen_manifest_sha256'] != digest(Path(manifest))):
        raise ValueError('Archive clone is bound to a different frozen fixture')
    frozen = json.loads(Path(manifest).read_text())
    pins = {row['path']: row['sha256'] for row in frozen['files']}
    requested = set(frozen['metadata']['tle_snapshot_paths'])
    mapped = set()
    for row in receipt['files']:
        relative = Path(row['path'])
        path = root/relative
        source = str(Path(receipt['source_root'])/relative)
        if (relative.is_absolute() or '..' in relative.parts or path.is_symlink()
                or not path.resolve(strict=True).is_relative_to(root) or source in mapped
                or source not in requested or row['sha256'] != pins[source]
                or digest(path) != pins[source]):
            raise ValueError('Archive clone bytes or identity changed')
        mapped.add(source)
    observed = {str(Path(receipt['source_root'])/s.path.relative_to(root))
                for s in TleArchiveReader(root).list_snapshots()}
    if mapped != requested or observed != requested:
        raise ValueError('Archive clone membership differs')
    return receipt


def execute(args):
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        raise ValueError('Explicit bounded replay command required')
    view = args.view.resolve(strict=True)
    receipt = verify_view(view, args.manifest)
    if receipt['source_root'] != str(ARCHIVE):
        raise ValueError('Production replay requires the original archive path')
    namespace = os.readlink('/proc/self/ns/mnt')
    os.unshare(os.CLONE_NEWNS)
    if os.readlink('/proc/self/ns/mnt') == namespace:
        raise ValueError('Refusing to mount in the parent namespace')
    subprocess.run(['/usr/bin/mount', '--make-rprivate', '/'], check=True)
    subprocess.run(['/usr/bin/mount', '--bind', str(view), str(ARCHIVE)], check=True)
    subprocess.run(['/usr/bin/mount', '-o', 'remount,bind,ro', str(ARCHIVE)], check=True)
    if not os.statvfs(ARCHIVE).f_flag & os.ST_RDONLY:
        raise ValueError('Replay archive view is not read-only')
    os.execvpe(command[0], command, os.environ)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    clone = commands.add_parser('materialize')
    clone.add_argument('--source', type=Path, default=ARCHIVE)
    clone.add_argument('--manifest', type=Path, required=True)
    clone.add_argument('--output', type=Path, required=True)
    launch = commands.add_parser('exec')
    launch.add_argument('--view', type=Path, required=True)
    launch.add_argument('--manifest', type=Path, required=True)
    launch.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.operation == 'materialize':
        result = materialize(TleArchiveReader(args.source), args.manifest, args.output)
        print(json.dumps(dict(snapshots=len(result['files']),
                              frozen_manifest_sha256=result['frozen_manifest_sha256'])))
    else:
        execute(args)
