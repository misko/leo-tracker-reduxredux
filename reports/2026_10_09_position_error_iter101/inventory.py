"""Metadata-only inventory; production access is development-allowlisted."""
import collections
import datetime
import hashlib
import json
from pathlib import Path

from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.regional_position_v3 import B7Store

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(document):
    diagnostics = document.get('diagnostics', {})
    retained = diagnostics.get('retained_basins', [])
    spacing = {f"point:{r['east_km']:g}:{r['north_km']:g}": r.get('spacing_km') for r in retained}
    failure_sets = diagnostics.get('b7', {}).get('regional_failures')
    if failure_sets is None:
        failure_sets = {'baseline': diagnostics.get('regional_failures', [])}
    failures = []
    for region, rows in failure_sets.items():
        for row in rows:
            if row.get('stage') == 'calibration':
                failures.append(dict(region=region, basin=row.get('basin'), reason=row.get('reason'),
                                     retained_baseline=row.get('basin') in spacing,
                                     baseline_spacing_km=spacing.get(row.get('basin'))))
    return dict(schema_version=document.get('schema_version'), analysis_id=document.get('analysis_id'),
                configuration_sha256=document.get('configuration_sha256'),
                checkpoint_binding=diagnostics.get('checkpoint_binding'),
                b7_policy_present='b7' in diagnostics, retained_count=len(retained),
                retained_spacing_counts=dict(collections.Counter(str(r.get('spacing_km')) for r in retained)),
                calibration_failures=failures,
                evidence_scope='Retained membership/spacing refer to baseline pass only; other passes require checkpoints')


def main():
    historical = ROOT / 'reports/2026_10_09_position_error_iter85/protocol.json'
    newer = ROOT / 'reports/2026_10_09_position_error_iter89/membership.json'
    protocol = json.loads(historical.read_text())
    membership = json.loads(newer.read_text())
    allow = {s for g in membership['grouping']['groups'] if g['assignment'] == 'development' for s in g['session_ids']}
    assert len(allow) == 45
    rows = []
    for binding in protocol['members']:
        member = binding['member']
        row = dict(dataset=member['dataset'], label=member.get('inventory_label'), session_id=member['session_id'],
                   scope='historical-consumed', sources=[], metadata_failures=[])
        sources = dict(binding['regions'])
        sources['baseline'] = binding.get('loader_binding', {}).get('baseline_path')
        for name, value in sources.items():
            if not value:
                row['metadata_failures'].append(dict(source=name, reason='No archived region binding'))
                continue
            path = ROOT / value
            try:
                row['sources'].append(dict(name=name, path=value, sha256=digest(path), **summarize(json.loads(path.read_text()))))
            except Exception as error:
                row['metadata_failures'].append(dict(source=name, reason=f'{type(error).__name__}: {error}'))
        rows.append(row)
    stores = [('B7', B7Store(Path('/srv/bulk/leo'))), ('hard60', Hard60Store(Path('/srv/bulk/leo')))]
    for member in membership['members']:
        if member['session_id'] not in allow:
            continue
        row = dict(dataset='POST18-development', label=member['dataset_label'], session_id=member['session_id'],
                   scope='newly-opened-analysis-metadata-development-only', sources=[], metadata_failures=[])
        for name, store in stores:
            try:
                status = store.status(member['session_id'])
                if status.manifest is None:
                    row['metadata_failures'].append(dict(source=name, reason=f'Publication unavailable: {status.state}'))
                else:
                    row['sources'].append(dict(name=name, document_sha256=status.manifest.document_sha256,
                                               **summarize(status.manifest.document.model_dump(mode='json'))))
            except Exception as error:
                row['metadata_failures'].append(dict(source=name, reason=f'{type(error).__name__}: {error}'))
        rows.append(row)
    assert len(rows) == 193
    result = dict(created_utc=datetime.datetime.now(datetime.UTC).isoformat(),
                  authorities={str(historical.relative_to(ROOT)): digest(historical), str(newer.relative_to(ROOT)): digest(newer)},
                  script_sha256=digest(Path(__file__)), members=rows,
                  restrictions='No fit, reference/error extraction, reserve access, quality exclusion, or authority mutation; no unseen validation claim',
                  exposure='Supplemental analysis-metadata access of all45 development IDs; original89 exposure authority unchanged; ac11 and7eb previously consumed')
    (HERE / 'inventory.json').write_text(json.dumps(result, indent=2)+'\n')
    for dataset in collections.Counter(r['dataset'] for r in rows):
        subset=[r for r in rows if r['dataset']==dataset]
        print(dataset, len(subset), 'with metadata', sum(bool(r['sources']) for r in subset), 'calibration failure members', sum(any(s['calibration_failures'] for s in r['sources']) for r in subset))


if __name__ == '__main__':
    main()
