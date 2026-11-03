"""Read-only provenance audit of competing canonical peaks; never merge rows."""
import json
from collections import Counter
import numpy as np
from benchmark import ROOT, SESSIONS, ALIAS_HZ, digest


def distance(a, b, period):
    return abs((float(a) - float(b) + period / 2) % period - period / 2)


def pair_metadata(left, right, frame_period):
    if left['probe_key'] != right['probe_key']:
        raise ValueError('Pair must belong to the same persisted probe')
    return {
        'frequency_distance_hz': distance(left['tracking_cfo_hz'], right['tracking_cfo_hz'], ALIAS_HZ),
        'frame_epoch_distance_samples': distance(left['fractional_epoch_samples'], right['fractional_epoch_samples'], frame_period),
        'same_integer_epoch': left['integer_epoch_sample'] == right['integer_epoch_sample'],
        'same_candidate_rank': left['candidate_rank'] == right['candidate_rank'],
        'residual_classes': [left['residual_class'], right['residual_class']],
        'candidate_ids': [left['candidate_id'], right['candidate_id']],
        'fractional_margins': [left['fractional_margin'], right['fractional_margin']],
    }


def audit(scan):
    directory = ROOT.parent / '2026_10_02_ds13_timing_em/scans' / SESSIONS[scan]
    bundle_path = directory / 'bundle.json'
    bundle = json.loads(bundle_path.read_text())
    rows = bundle['alias_grouping']['representative_rows']
    policy = bundle['alias_grouping']['policy']
    families = {f['representative_candidate_id']: f for f in bundle['alias_grouping']['families']}
    ambiguous = {r['candidate_id']: r['reason'] for r in bundle['alias_grouping']['ambiguous_edges']}
    observations = ROOT / 'frozen' / f'{scan}-observations.npz'
    with np.load(observations) as data:
        measured, groups = data['measured_hz'], data['group']
    with np.load(directory / 'bundle.npz') as raw:
        indices = bundle['family_representatives']
        if not np.array_equal(raw['measured'][indices], measured):
            raise ValueError('Frozen frequency lineage mismatch')
        if not np.array_equal(raw['group'][indices], groups):
            raise ValueError('Frozen probe lineage mismatch')
    if not np.array_equal([r['tracking_cfo_hz'] for r in rows], measured):
        raise ValueError('Representative metadata order mismatch')
    source = ROOT / 'development-tracklets' / f'{scan}-feasible.json'
    assignments = json.loads(source.read_text())['assignments']
    accounting_path = ROOT / 'development-tracklets/accounting.json'
    accounting = json.loads(accounting_path.read_text())[scan]
    by_group = {}
    for assignment in assignments:
        by_group.setdefault(int(groups[assignment['row_index']]), []).append(assignment)
    pairs = []
    for row in accounting['rows']['competing_peak_for_already_assigned_satellite']:
        choices = by_group[int(groups[row])]
        # Nearest assigned peak is a descriptive comparator, not an identity assertion.
        owner = min(choices, key=lambda a: distance(measured[row], measured[a['row_index']], ALIAS_HZ))
        other = owner['row_index']
        pairs.append(dict(row_index=row, nearest_assigned_row=other,
                          nearest_assigned_catalog=owner['catalog_number'],
                          family_kinds=[families[rows[i]['candidate_id']]['kind'] for i in (row, other)],
                          upstream_ambiguity=[ambiguous.get(rows[i]['candidate_id']) for i in (row, other)],
                          **pair_metadata(rows[row], rows[other], policy['frame_period_samples'])))
    counts = {'competing_rows': len(pairs), 'same_integer_epoch': sum(p['same_integer_epoch'] for p in pairs),
              'same_candidate_rank': sum(p['same_candidate_rank'] for p in pairs),
              'either_upstream_ambiguous_edge': sum(any(p['upstream_ambiguity']) for p in pairs),
              'family_kind_pairs': dict(Counter('/'.join(p['family_kinds']) for p in pairs)),
              'class_pairs': dict(Counter('/'.join(p['residual_classes']) for p in pairs))}
    for hz in (50, 200, 600):
        near = [p for p in pairs if p['frequency_distance_hz'] <= hz]
        counts[f'within_{hz}_hz'] = {
            'count': len(near),
            'within_half_sample_epoch': sum(p['frame_epoch_distance_samples'] <= .5 for p in near),
            'within_one_sample_epoch': sum(p['frame_epoch_distance_samples'] <= 1 for p in near),
            'median_epoch_distance_samples': float(np.median([p['frame_epoch_distance_samples'] for p in near])) if near else None,
        }
    return dict(scan=scan, counts=counts, pairs=pairs, upstream_alias_policy=policy,
                source_sha256={str(p): digest(p) for p in (bundle_path, directory/'bundle.npz', observations, source, accounting_path)},
                interpretation='Frequency/epoch similarity is not proof of one physical signal. Distinct persisted candidate IDs remain distinct frozen observations. No assignments or denominator changed. Nearest comparator need not be the satellite that supplied the competing edge.')


def main():
    output = ROOT / 'peak-provenance'
    output.mkdir(exist_ok=True)
    for scan in 'AB':
        result = audit(scan)
        path = output / f'{scan}-families.json'
        with path.open('x') as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
        print(scan, json.dumps(result['counts']))


if __name__ == '__main__':
    main()
