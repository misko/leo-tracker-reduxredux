"""Drain sealed fast recordings from optional NVMe staging to permanent RAID."""

import argparse
import json
from pathlib import Path
import time

from leo.storage.raid_archive import VerifiedDirectoryArchive


def eligible_names(root: Path, *, include_incomplete: bool = False) -> list[str]:
    result = []
    for path in sorted(root.iterdir()):
        if path.name.startswith('.') or path.is_symlink() or not path.is_dir():
            continue
        checkpoint = path / 'run.json'
        if not checkpoint.is_file():
            continue
        document = json.loads(checkpoint.read_bytes())
        if document.get('run_id') != path.name:
            raise ValueError("recording checkpoint identity changed")
        if document.get('state') in ('stopped', 'failed') or include_incomplete:
            result.append(path.name)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--archive-root', type=Path, required=True)
    parser.add_argument('--name', action='append', help='Explicit quiescent directory; may be repeated.')
    parser.add_argument('--include-incomplete', action='store_true', help='Operator recovery of quiescent captures only.')
    parser.add_argument('--maximum-recordings', type=int, default=8)
    parser.add_argument('--maximum-seconds', type=float, default=300)
    args = parser.parse_args()
    if args.maximum_recordings < 1 or args.maximum_seconds <= 0:
        parser.error('archive limits must be positive')
    last_report = [0.0]
    def progress(event):
        if event['state'] == 'complete' or time.monotonic() - last_report[0] >= 10:
            print(json.dumps(event), flush=True)
            last_report[0] = time.monotonic()
    archive = VerifiedDirectoryArchive(args.source_root, args.archive_root, progress=progress)
    names = args.name or list(dict.fromkeys(archive.pending_names() + eligible_names(
        args.source_root, include_incomplete=args.include_incomplete)))
    started = time.monotonic()
    completed = []
    for name in names[:args.maximum_recordings]:
        if time.monotonic() - started >= args.maximum_seconds:
            break
        receipt = archive.archive(name)
        completed.append({'name': name, 'bytes': receipt['bytes']})
    print(json.dumps({'state': 'batch_complete', 'archived': completed,
                      'remaining_candidates': len(names) - len(completed),
                      'elapsed_seconds': time.monotonic() - started}), flush=True)


if __name__ == '__main__':
    main()
