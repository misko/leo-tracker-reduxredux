"""Verify new assets and exact R1 dependencies; optionally restore logical trees.

Uses only the Python standard library. Does not run inference or fetch files.
"""

import argparse
import hashlib
import json
from pathlib import Path
import tarfile

HERE = Path(__file__).resolve().parent


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', required=True, type=Path, help='Directory containing the three new release assets')
    parser.add_argument('--prior-assets', required=True, type=Path, help='Directory containing five exact referenced R1 assets')
    parser.add_argument('--prior-report', required=True, type=Path, help='Exact R1 report directory at the recorded immutable commit')
    parser.add_argument('--restore', type=Path, help='Optional new directory for logical restored data/source trees')
    args = parser.parse_args()
    if args.restore:
        args.restore.mkdir(parents=True, exist_ok=False)
    index = json.loads((HERE/'publication_index.json').read_text())
    dependencies = json.loads((HERE/'audit/publication_dependencies.json').read_text())
    source = json.loads((HERE/'audit/runtime_closure.json').read_text())
    for row in index['direct_files']:
        path = HERE/row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], path
    needed = {}
    for row in dependencies['input_files']+source['files']:
        if row['delivery'] == 'prior_release_asset_member':
            needed.setdefault(row['asset'], {})[row['member']] = row
    assets_checked = members_checked = member_bytes = 0
    for asset in index['assets']+index['reused_release_assets']:
        prior = asset in index['reused_release_assets']
        archive = (args.prior_assets if prior else args.assets)/asset['asset']
        assert archive.stat().st_size == asset['bytes'], archive
        assert sha(archive) == asset['sha256'], archive
        expected = needed[asset['asset']] if prior else {v['member']:v for v in asset['members']}
        with tarfile.open(archive, 'r:gz') as tar:
            lookup = {m.name:m for m in tar.getmembers()}
            if not prior:
                assert set(lookup) == set(expected)
            for name, row in expected.items():
                member = lookup[name]
                assert member.isfile() and not name.startswith('/') and '..' not in Path(name).parts
                data = tar.extractfile(member).read()
                assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
                if args.restore:
                    destination = args.restore/('prior_r1' if prior else 'current')/name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(data)
                members_checked += 1
                member_bytes += len(data)
        assets_checked += 1
    immutable = {}
    for row in index['immutable_R1_files']:
        relative = Path(row['member']).relative_to('reports/2026_10_25_ds24_movement_policy')
        path = args.prior_report/relative
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], path
        immutable[str(relative)] = row['sha256']
        if args.restore:
            destination = args.restore/'prior_r1'/relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
    receipt = dict(all_passed=True, no_inference=True, assets_checked=assets_checked,
        new_assets=len(index['assets']), reused_assets=len(index['reused_release_assets']),
        required_archive_members_checked=members_checked, required_member_bytes=member_bytes,
        direct_report_files_checked=len(index['direct_files']), immutable_R1_files_checked=len(immutable),
        restored_logical_tree=str(args.restore) if args.restore else None,
        index_sha256=sha(HERE/'publication_index.json'))
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
