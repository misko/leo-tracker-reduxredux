"""Read-only DS24 metadata extension; stable labels and separately sealed revisions."""
import argparse
import copy
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'support'))
from raw_inventory import digest, inventory
from mint import counts, legacy_census, legacy_member
from freeze_ds23_dataset import compact_member


def write(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def adaptive_rates(document):
    d = document.get('manifest', document)
    values = [d.get('receipt', {}).get('plan', {}).get('geometry', {}).get('sample_rate_hz'),
              d.get('timing', {}).get('sample_rate_hz')]
    return sorted(set(v for v in values if v is not None))


def merge_members(parent, current):
    """Keep prior identities/labels; append new identities in acquisition order."""
    old = {m['raw_recording']['identity_sha256']: m for m in parent}
    fresh = {m['raw_recording']['identity_sha256']: m for m in current}
    if len(fresh) != len(current):
        raise ValueError('duplicate content identity')
    if set(old) - set(fresh):
        raise ValueError('previous members missing from current census')
    result = []
    for key, previous in old.items():
        m = copy.deepcopy(fresh.pop(key))
        if m['captured_utc_ns'] != previous['captured_utc_ns']:
            raise ValueError('previous acquisition time changed')
        m['dataset_label'] = previous['dataset_label']
        result.append(m)
    next_id = max(int(m['dataset_label'].split('-')[-1]) for m in parent) + 1
    for m in sorted(fresh.values(), key=lambda m: (m['captured_utc_ns'], m['recording_id'])):
        m = copy.deepcopy(m)
        m['dataset_label'] = f'DS24-{next_id:04d}'
        next_id += 1
        result.append(m)
    return result


def main(cutoff):
    if (HERE / 'manifest.json').exists():
        raise ValueError('refusing to overwrite a frozen revision')
    parent_raw = (HERE / 'parent-manifest.json').read_bytes()
    parent = json.loads(parent_raw)
    start = parent['start_utc_ns']
    assert cutoff > parent['cutoff_utc_ns']
    roots = set(parent['discovery_roots'])
    for base in (Path('/srv/bulk/leo'), Path('/srv/postgres-nvme')):
        roots.update(str(p) for p in base.iterdir()
                     if p.is_dir() and p.name.startswith(('fast8-', 'fast-scan-recordings')))
    groups = defaultdict(list)
    errors, excluded = [], []
    checked = 0
    for root in sorted(roots):
        base = Path(root)
        if not base.exists():
            continue
        next(base.iterdir(), None)  # fail explicitly on access errors
        for path in sorted(base.rglob('manifest.json')):
            if any(p.startswith('.') for p in path.relative_to(base).parts):
                continue
            checked += 1
            try:
                raw = path.read_bytes()
                d = json.loads(raw)
                if d.get('kind') == 'short_window_iq_recording':
                    groups[path.parent.parent].append((path, d, digest(raw)))
            except (OSError, ValueError) as e:
                errors.append(dict(path=str(path), error=str(e)))
    selected = []
    for root, segments in groups.items():
        stamp = min(d['created_utc_ns'] for _, d, _ in segments)
        rates = sorted({d.get('sample_rate_hz', d.get('configuration', {}).get('sample_rate_hz'))
                        for _, d, _ in segments}, key=str)
        reason = ('outside_acquisition_start_window' if not start <= stamp < cutoff else
                  'sample_rate_not_uniform_10MSps' if rates != [10000000] else None)
        evidence = dict(root=str(root), captured_utc_ns=stamp, sample_rates_hz=rates,
                        segment_manifests=[dict(path=str(p), sha256=s) for p, _, s in segments])
        if reason:
            excluded.append(dict(evidence, reason=reason))
        else:
            selected.append(root)
    print('fast eligible roots:', len(selected), flush=True)
    raw_inventory = inventory(selected, Path('/srv/bulk/leo'), 2**63 - 1,
                              start_ns=start, dataset_id='DS24', required_channels=None)
    errors.extend(raw_inventory['discovery_errors'])
    members = []
    for raw in raw_inventory['members']:
        m = compact_member(raw)
        m['sample_rate_hz'] = 10000000
        m['recording_metadata'] = []
        run = Path(m['raw_recording']['root']) / 'run.json'
        if run.exists():
            b = run.read_bytes()
            d = json.loads(b)
            m['recording_metadata'].append(dict(path=str(run), sha256=digest(b),
                                                state=d.get('state'), fault=d.get('fault')))
            if d.get('state') not in ('stopped', 'complete') or d.get('fault'):
                m['recording_state'] = 'incomplete'
        m['raw_manifest_digest'] = digest(json.dumps(
            [(Path(s['path']).parent.name, s['sha256']) for s in m['raw_recording']['segments']],
            separators=(',', ':')).encode())
        m['raw_authority_digest'] = m.get('raw_authority_digest') or m['raw_manifest_digest']
        m['analysis_availability'] = ('existing_tracking_contract' if m['tracking_inputs'] else
                                      'existing_tracking_contract_unavailable')
        members.append(m)
    census = legacy_census(start, cutoff - 1)
    errors.extend(census['errors'])
    adaptive_audit = []
    by_identity = {m['raw_recording']['identity_sha256']: m for m in members}
    for row in census['members']:
        d = row['document'].get('manifest', row['document'])
        rates = adaptive_rates(d)
        accepted = d.get('kind') == 'starlink_adaptive_hop_iq' and rates == [10000000]
        adaptive_audit.append(dict(path=row['path'], sha256=row['sha256'], kind=d.get('kind'),
                                   sample_rates_hz=rates, included=accepted))
        if not accepted:
            continue
        m = compact_member(legacy_member(row))
        m['sample_rate_hz'] = 10000000
        key = m['raw_recording']['identity_sha256']
        if key in by_identity:
            by_identity[key]['raw_recording']['duplicate_roots'].append(m['raw_recording']['root'])
        else:
            by_identity[key] = m
    if errors:
        write('discovery-errors.json', errors)
        raise ValueError('discovery errors require reconciliation')
    members = merge_members(parent['members'], list(by_identity.values()))
    # Recheck every selected source manifest after enumeration. Never claim an atomic snapshot.
    for m in members:
        assert start <= m['captured_utc_ns'] < cutoff
        for item in m['raw_recording']['segments'] + m['source_inputs'] + m['tracking_inputs']:
            if digest(Path(item['path']).read_bytes()) != item['sha256']:
                raise ValueError('source changed during inventory: ' + item['path'])
    result = dict(schema=parent['schema'], dataset_id='DS24', revision=2,
                  created_utc=datetime.now(UTC).isoformat(), start_utc_ns=start, cutoff_utc_ns=cutoff,
                  parent_manifest_sha256=digest(parent_raw), parent_revision_member_count=len(parent['members']),
                  selection='All discovered fast and adaptive acquisitions with uniform actual 10 MS/s metadata, '
                            'starting in [original DS24 start, current cutoff); stable old labels; new labels appended.',
                  analysis_readiness_required=False, complete_recording_required=False,
                  scientific_outcomes_used_for_membership=False, discovery_roots=sorted(roots),
                  additional_discovery_roots=census['roots'], metadata_snapshot_is_atomic=False,
                  payloads_copied_or_rehashed=False, counts=counts(members), members=members,
                  discovery_errors=errors)
    write('discovery.json', dict(checked_fast_manifests=checked, excluded_fast=excluded,
                                 adaptive_checked=census['checked'], adaptive_candidates=adaptive_audit))
    write('manifest.json', result)
    sha = digest((HERE / 'manifest.json').read_bytes())
    (HERE / 'manifest.sha256').write_text(sha + '  manifest.json\n')
    write('evaluation-units.json', dict(dataset_id='DS24', revision=2, manifest_sha256=sha,
          case_ids=[m['case_id'] for m in members], dataset_labels=[m['dataset_label'] for m in members]))
    write('verification.json', dict(verified=True, parent_labels_preserved=True,
          parent_members_retained=len(parent['members']), added=len(members)-len(parent['members']),
          unique_content_identities=len({m['raw_recording']['identity_sha256'] for m in members}),
          source_hashes_rechecked=True, **result['counts']))
    write('seal.json', dict(files={str(p.relative_to(HERE)): digest(p.read_bytes())
          for p in sorted(HERE.rglob('*')) if p.is_file() and p.name != 'seal.json'
          and '__pycache__' not in p.parts}))
    print(json.dumps(result['counts']), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cutoff-ns', type=int, required=True)
    main(parser.parse_args().cutoff_ns)
