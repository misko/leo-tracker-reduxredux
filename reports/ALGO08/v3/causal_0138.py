"""Recover the exact signed DS30-0138 catalogue from two existing tmpfs archives."""

import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
from time import perf_counter_ns, process_time_ns

from leo.contracts.digests import canonical_digest
from leo.operations.tle_archive import TleArchiveReader

from duration_heldout import NATIVE, PAIR_PIN, PANEL, SPEC


SHM = Path('/dev/shm')
CASE = 'DS30-0138'
SESSION = 'fast-9828145f4a17561ff79503a2e8583c58'
INVENTORY = '9828145f4a17561ff79503a2e8583c580502cdf0463153ec8b1a64516645c3f9'
NATIVE_PIN = '5ddc90892db1dda58b43b120d23eedff9a16d97d93ad1756b7aa3a0e7a3a3ebe'
AUTHORITY = 'sha256:eda37d611e45a2812979dd3a28cc9ca1ec197565fb5f6a5f7faaf805fad76529'
ARCHIVE = 'sha256:286929b04dbf158604af60796bb5e976bbe1dc2f3cd72e91c9b55f1d91fd3e16'
OFFER = '2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236'
CUTOFF = 1794749065665518045
ISSUED, ADMITTED = 6773, 6717
HISTORY_NS = 72 * 3600 * 10**9
DONORS = {
    SHM/'leo-held-anchor-selected-dense-01/tle': ('sha256:0c9bdf4a80768161252ce2c28b4e96991276b6dc64ed3d6ff44d613a78b00ea2', 47, 84_051_499),
    SHM/'leo-v3-saved-0155-pair-01/tle': ('sha256:8ea284d7b0d6aab59dec80477ada3e1cbddb59c44714ebb103c047fa12de839e', 52, 92_934_518),
}


def checked(path, pin):
    contents = path.read_bytes()
    if sha256(contents).hexdigest() != pin.removeprefix('sha256:'):
        raise ValueError(f'Saved input digest changed at {path}')
    return contents


def snapshot_digest(refs):
    return canonical_digest({ref.path.name: ref.sha256 for ref in refs})


def length_digest(ref):
    return ref.sha256, ref.byte_size


def inspect_donors():
    readers = {}
    for root, (expected, count, nbytes) in DONORS.items():
        if root.resolve(strict=True) != root or root.stat().st_dev != SHM.stat().st_dev:
            raise ValueError('A donor is outside the named tmpfs catalogue')
        reader = TleArchiveReader(root)
        refs = reader.list_snapshots('space-track')
        if (len(refs) != count or sum(ref.byte_size for ref in refs) != nbytes or snapshot_digest(refs) != expected
                or any(ref.path.stat().st_dev != SHM.stat().st_dev for ref in refs)):
            raise ValueError(f'Donor catalogue was modified or is not tmpfs: {root}')
        readers[reader] = refs
    return readers


def exact_plan(readers, cutoff, pin):
    names, bodies = {}, {}
    for reader, refs in readers.items():
        for ref in refs:
            bodies.setdefault(length_digest(ref), (reader, ref))
            if cutoff-HISTORY_NS <= ref.collected_utc_ns < cutoff:
                present = names.setdefault(ref.path.name, ref)
                if length_digest(present) != length_digest(ref):
                    raise ValueError('Matching snapshot names have conflicting saved extents')
    ordered = sorted(names.values())
    if not ordered or snapshot_digest(ordered) != pin:
        raise ValueError('The local names do not reproduce the original sealed roster')
    return [(ref, *bodies[length_digest(ref)]) for ref in ordered]


def verify_archive(root, plan):
    reader = TleArchiveReader(root)
    actual = reader.list_snapshots()
    expected = [(row.path.name, length_digest(row)) for row, *_ in plan]
    if [(row.path.name, length_digest(row)) for row in actual] != expected:
        raise ValueError('Private catalogue names, ordering or byte counts changed')
    for ref in actual:
        if len(reader.read(ref)) != ref.byte_size:
            raise ValueError(f'Private snapshot length changed: {ref.path.name}')
    return snapshot_digest(actual)


def emit(path, data):
    with path.open('x') as handle:
        json.dump(data, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')


def write_projection(destination, plan):
    """Write every unique body once. The immutable copies share only private inodes."""
    folder = destination/'archive/space-track'
    folder.mkdir(parents=True)
    copied = {}
    output = []
    donor_counts = Counter()
    for ref, reader, donor in plan:
        target = folder/ref.path.name
        key = length_digest(ref)
        if key in copied:
            os.link(copied[key], target)
        else:
            data = reader.read(donor).encode('ascii')
            if len(data) != ref.byte_size:
                raise ValueError('The verified donor has a different original extent')
            with target.open('xb') as handle:
                handle.write(data)
            target.chmod(0o444)
            copied[key] = target
            donor_counts[str(reader.root)] += 1
        output.append(dict(name=ref.path.name, utc_ns=ref.collected_utc_ns, bytes=ref.byte_size,
                           sha256=ref.sha256, donor=str(donor.path)))
    digest = verify_archive(destination, plan)
    return dict(root=str(destination), snapshots_sha256=digest, snapshots=len(plan), bytes=sum(r['bytes'] for r in output),
                distinct_bodies=len(copied), distinct_body_bytes=sum(size for _, size in copied),
                unique_by_donor=dict(donor_counts), missing_bodies=0, missing_bytes=0, entries=output)


def stage(stage_root):
    if stage_root.parent.resolve(strict=True) != SHM or stage_root.exists():
        raise ValueError('Expected fresh private tmpfs stage')
    started = perf_counter_ns(), process_time_ns()
    pair = json.loads(checked(PANEL/'pair.json', PAIR_PIN))
    named = pair['runs']['candidate']
    receipt = named['receipt']
    work = PANEL/'candidate/fast-scan-automatic-work'
    terminal = json.loads(checked(work/receipt['run_id']/'terminal.json', receipt['terminal_sha256']))
    packet = checked(work/NATIVE, NATIVE_PIN)
    doc = json.loads(packet)
    inventory_bytes = checked(PANEL/'candidate/fast-scan-inputs'/f'{SESSION}.json', INVENTORY)
    inventory = json.loads(inventory_bytes)
    manifests = [[str(Path(ref['path'])/'manifest.json'), ref['manifest_digest']] for ref in inventory['segments']]
    prescribed = [[row['path'], row['sha256']] for row in pair['cache_observation']['manifests']]
    detector = pair['candidate_specification']['detector_sha256']
    cutoff = doc['clock_anchor']['before']['realtime_ns']
    if (pair['candidate_specification_digest'] != SPEC or 'sha256:'+detector != doc['provenance']['detector_sha256']
            or pair['archive']['snapshots_sha256'] != ARCHIVE or cutoff != CUTOFF
            or terminal['native_sha256'] != 'sha256:'+NATIVE_PIN or named['raw_authority'] != AUTHORITY
            or receipt['session_id'] != SESSION or doc['source']['session_id'] != SESSION
            or doc['source']['raw_recording_authority_digest'] != AUTHORITY
            or inventory['window_count'] != ISSUED or doc['provenance']['processed_windows'] != ADMITTED
            or doc['source']['input_manifest_sha256'] != 'sha256:'+INVENTORY or manifests != prescribed):
        raise ValueError('Saved packet differs from original signed receipt, exact cutoff or inventory')
    offer = checked(Path(pair['region']), OFFER)
    plan = exact_plan(inspect_donors(), cutoff, ARCHIVE)
    stage_root.mkdir(mode=0o700)
    projection = write_projection(stage_root/'tle', plan)
    native_file, inventory_file, offer_file = (stage_root/name for name in ('named-detections.json', 'inventory.json', 'operator-offer.json'))
    for path, payload in ((native_file, packet), (inventory_file, inventory_bytes), (offer_file, offer)):
        with path.open('xb') as handle:
            handle.write(payload)
        path.chmod(0o444)
    local_archive = {k: projection[k] for k in ('root', 'snapshots_sha256', 'snapshots', 'bytes')}
    emit(stage_root/'request.json', dict(case=CASE, recording=pair['recording'], original_archive=pair['archive'],
         local_archive=local_archive, native_file=str(native_file), native_sha256=NATIVE_PIN, inventory='sha256:'+INVENTORY,
         offer_file=str(offer_file), offer_sha256=OFFER, local_libraries={}, session=SESSION, raw_authority=AUTHORITY,
         manifests=manifests, detector_sha256=detector, causal_cutoff_utc_ns=cutoff, original_pair_sha256=PAIR_PIN))
    emit(stage_root/'projection.json', dict(case=CASE, archive=projection, cutoff_utc_ns=cutoff, hours=72,
         authority=AUTHORITY, native_sha256=NATIVE_PIN, inventory_sha256=INVENTORY, offer_sha256=OFFER,
         request_sha256=sha256((stage_root/'request.json').read_bytes()).hexdigest(), original_pair_sha256=PAIR_PIN,
         output=local_archive, donor_catalogues={str(k): v for k, v in DONORS.items()},
         waveform_reads=0, backing_catalogue_reads=0, prior_source_chronology='original collection stamps retained',
         preparation=dict(elapsed_ns=perf_counter_ns()-started[0], cpu_ns=process_time_ns()-started[1])))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    stage(p.parse_args().root)
