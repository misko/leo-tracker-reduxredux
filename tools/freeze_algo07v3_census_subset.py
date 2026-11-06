"""Freeze a bounded DS26 subset for the recovery-work census."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from leo.analysis.localization_v3.tracks import prepare_tracks
from leo.analysis.polynomial_tracklets import TrackConfig
from leo.operations.localization_v3_job import runtime_versions, validate_request
from leo.operations.tle_archive import TleArchiveReader


def sha(data):
    return hashlib.sha256(data).hexdigest()


def causal_snapshots(snapshots, metadata):
    cutoff = metadata['causal_cutoff_utc_ns']
    if isinstance(cutoff, bool) or not isinstance(cutoff, int) or cutoff <= 0:
        raise ValueError('Positive integer causal cutoff required')
    chosen = [r for r in snapshots
              if cutoff - 72 * 3600 * 10**9 <= r.collected_utc_ns <= cutoff]
    if not chosen:
        raise ValueError('No causal snapshots in frozen window')
    return cutoff, chosen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', action='append', choices=('DS26-0084', 'DS26-0170', 'DS26-0102'))
    args = parser.parse_args()
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        parser.error('QNAP is read-only')
    root.mkdir(exist_ok=False)
    inventory_path = Path('/srv/bulk/leo-dev/algo07v3-integrated-20261105/'
                          'ds26-input-inventory002.json')
    inventory = json.loads(inventory_path.read_bytes())
    template_path = Path('/srv/bulk/leo-dev/algo07v3-control-view-native-0066-20261106/'
                         'candidate-request.json')
    template = json.loads(template_path.read_bytes())
    config = Path(template['track_config']['path']).read_bytes()
    assert 'sha256:' + sha(config) == template['track_config']['sha256']
    assert template['runtime'] == runtime_versions()
    archive = TleArchiveReader(Path('/srv/bulk/leo/research/algo07-star-20261104/'
                                    'iteration000/tle-view'))
    snapshots = archive.list_snapshots('space-track')
    selection = dict(
        dataset_labels=args.case or ['DS26-0084', 'DS26-0170'],
        rationale='Two previously compared fast scans, including the documented eight-target '
                  'discovery case; broaden recovery-path coverage beyond 0002/0066. '
                  'DS26-0102 may be added because its saved audit explicitly exercised joint '
                  'recovery. No position error is used for selection; actual current branches '
                  'are measured.',
        inventory_sha256=sha(inventory_path.read_bytes()), source_receipts=[])
    (root / 'selection.json').write_text(json.dumps(selection, indent=2) + '\n')
    for label in selection['dataset_labels']:
        member = next(r for r in inventory['members'] if r['dataset_label'] == label)
        native_path = (Path('/srv/bulk/leo/research/algo07v3-20261104/tracks001/inputs')
                       / (label + '.json'))
        native = native_path.read_bytes()
        assert 'sha256:' + sha(native) == member['input_sha256']
        document = json.loads(native)
        assert document['source']['session_id'] == member['session_id']
        assert document['provenance']['run_id'] == member['run_id']
        prepared = prepare_tracks(document, TrackConfig(**json.loads(config)['config']))
        cutoff, eligible = causal_snapshots(snapshots, prepared['metadata'])
        bundle = root / label
        bundle.mkdir()
        (bundle / 'native.json').write_bytes(native)
        (bundle / 'config.json').write_bytes(config)
        target = bundle / 'tle/archive/space-track'
        target.mkdir(parents=True)
        for ref in eligible:
            data = archive.read(ref).encode()
            assert sha(data) == ref.sha256
            (target / ref.path.name).write_bytes(data)
        files = {str(p.relative_to(bundle)): sha(p.read_bytes())
                 for p in sorted(bundle.rglob('*')) if p.is_file()}
        manifest = dict(files=files, cutoff_utc_ns=cutoff, snapshot_count=len(eligible),
                        host_network_namespace=os.stat('/proc/self/ns/net').st_ino)
        (bundle / 'input-bindings.json').write_text(json.dumps(manifest, indent=2) + '\n')
        request = dict(template, identity={k: member[k] for k in
                       ('run_id', 'session_id', 'input_sha256')},
                       native_input=dict(path=str(bundle / 'native.json'),
                                         sha256=member['input_sha256']),
                       track_config=dict(path=str(bundle / 'config.json'),
                                         sha256='sha256:' + sha(config)),
                       tle_root=str(bundle / 'tle'),
                       output_root=str(root / (label + '-publication')),
                       scan_identities=[member['session_id']], title=member['recording_id'])
        validate_request(request)
        (root / (label + '-request.json')).write_text(json.dumps(request, indent=2) + '\n')
        (root / (label + '-run')).mkdir()
        receipt = dict(label=label, points=len(prepared['observations']),
                       tracks=len(prepared['tracks']), snapshots=len(eligible),
                       cutoff_utc_ns=cutoff,
                       native_sha256=sha(native), bundle_manifest_sha256=sha(
                           (bundle / 'input-bindings.json').read_bytes()))
        selection['source_receipts'].append(receipt)
        print(json.dumps(receipt), flush=True)
    (root / 'freeze-result.json').write_text(json.dumps(selection, indent=2) + '\n')


if __name__ == '__main__':
    main()
