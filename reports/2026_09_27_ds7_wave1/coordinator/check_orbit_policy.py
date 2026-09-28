"""Read-only reproduction of DS6's per-object selection for the DS7 smoke input."""
import hashlib
import json
from pathlib import Path

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records, parse_element_sets

root = Path(__file__).resolve().parents[3]
source = root / 'reports/2026_09_27_ds7_wave1/baseline/exports/scan-fw-5f7bf896e4552887-tracks.json'
data = json.loads(source.read_text())
archive = TleArchiveReader(Path('/var/lib/leo/tle'))
cutoff = data['start_utc_ns'] - 505_000_000_000
base = archive.select_latest_before(cutoff)
assert base.digest == data['snapshot_sha256']
snapshots = archive.list_snapshots()
latest = [max((s for s in snapshots if s.provider == provider and s.collected_utc_ns < cutoff),
              key=lambda s: (s.collected_utc_ns, s.sha256))
          for provider in sorted({s.provider for s in snapshots if s.collected_utc_ns < cutoff})]


def read(snapshot):
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    return list(parse_element_set_records(payload)), catalogue.element_epoch_utc_ns()


before, _ = read(base)
choices = {}
for snapshot in latest:
    records, epochs = read(snapshot)
    for record, epoch in zip(records, epochs, strict=True):
        key = (epoch, snapshot.collected_utc_ns, snapshot.digest)
        old = choices.get(record.satellite_number)
        if old is None or key > old[0]:
            choices[record.satellite_number] = (key, record)
changed = [r.satellite_number for r in before if choices[r.satellite_number][1].text != r.text]
result = {
    'schema': 'ds7-original-orbit-policy-audit/v1',
    'source_commit': '75b76f66974c78588c6599822e8007aaa767466b',
    'source_policy': 'reports/2026_09_27_ds6_element_freshness/catalogue.py',
    'session_id': data['session_id'], 'input_manifest_sha256': data['manifest_sha256'],
    'cutoff_utc_ns': cutoff, 'baseline_snapshot_sha256': base.digest,
    'policy': 'newest per object among latest provider snapshots before start minus505seconds; retain original catalogue identity/order',
    'baseline_object_count': len(before), 'changed_object_count': len(changed),
    'changed_catalog_numbers': changed,
    'provider_snapshots': [{'provider': s.provider, 'sha256': s.digest,
                            'collected_utc_ns': s.collected_utc_ns} for s in latest],
    'code_sha256': 'sha256:' + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'track_export_sha256': 'sha256:' + hashlib.sha256(source.read_bytes()).hexdigest(),
    'raw_iq_read_bytes': 0,
}
out = Path(__file__).with_name('original-orbit-policy.json')
with out.open('x') as stream:
    json.dump(result, stream, indent=2)
print(json.dumps({'objects': len(before), 'changed_objects': len(changed), 'receipt': str(out)}))
