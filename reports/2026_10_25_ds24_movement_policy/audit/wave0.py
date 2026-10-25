"""Independent coordinator inventory/protocol audit, without inference or GPS."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    protocol = read(ROOT/'protocol.json')
    ledger = read(ROOT/'cohort_ledger.json')
    preflight = read(ROOT/'preflight.json')
    membership = read(HERE/'baseline_membership.json')
    hashes = []
    for item in [protocol[k] for k in ('plan', 'cohort', 'preflight')] + ledger['authorities']:
        assert sha(item['path']) == item['sha256'], item['path']
        assert Path(item['path']).stat().st_size == item['bytes']
        hashes.append(item)
    sample = read('/srv/bulk/leo/research/ds25-20261024/sample.json')['selected']
    sample = {row['dataset_label']: row for row in sample if row['mode'] == 'fast'}
    execution = read('/srv/bulk/leo/research/ds25-20261024/execution.json')['receipts']
    execution = {row['case']: row for row in execution}
    assert len(sample) == len(ledger['rows']) == ledger['population'] == 34
    assert {r['case'] for r in ledger['rows']} == set(sample)
    eligible = sorted((r for r in ledger['rows'] if r['eligible']),
                      key=lambda r: (r['captured_utc_ns'], r['case']))
    cases = [r['case'] for r in eligible]
    assert len(cases) == ledger['eligible_count'] == 24
    assert cases == ledger['eligible_cases'] == protocol['cases']
    assert set(cases) == set(membership['cases'])
    assert {r['case'] for r in ledger['rows'] if not r['eligible']} == {
        *(f'DS24-{i:04d}' for i in range(1, 10)), 'DS24-0103'}
    assert protocol['seeds'] == [2026102504, 2026102505]
    expected = [dict(case=c, seed=s, fold=f) for c in cases for s in protocol['seeds'] for f in range(3)]
    assert protocol['job_dispatch'] == expected
    assert protocol['smoke_jobs'] == expected[:2]
    assert protocol['expected_counts'] == dict(fold_jobs=144, train_position_fits=576,
        crossover_vectors=1152, noise_scores=3456)
    assert protocol['scientific_inference_uses_GPS'] is False and protocol['no_new_RF'] is True
    assert protocol['region_center_latlon'] == [37.906, -122.545]
    assert protocol['region_width_km'] == 25
    resources = protocol['resources']
    assert resources['start_workers'] == 2 and resources['max_movement_workers'] == 6
    assert resources['recovery_workers'] == resources['audit_workers'] == resources['blas_threads'] == 1
    assert resources['global_cpu_heavy_processes'] == 8
    assert resources['per_fold_seconds'] == 240 and resources['batch_wall_seconds'] == 2700
    assert resources['recovery_pilot_seconds'] == 1800
    assert preflight['allocated_cpu_capacity'] >= 8
    assert preflight['affinity_cpu_count'] >= 8
    for row in ledger['rows']:
        original = sample[row['case']]
        for key in ('recording_id', 'session_id', 'session_ids', 'captured_utc_ns', 'raw_authority_digest'):
            assert row[key] == original[key]
        assert row['frozen_execution_status'] == execution[row['case']]['status']
        if not row['eligible']:
            assert row['frozen_reason'] == 'input_unavailable'
            assert row['inherited_tracking_authorities'] == []
            continue
        original = membership['cases'][row['case']]
        assert row['baseline']['sha256'] == original['baseline_sha256']
        for binding in [row['baseline'], row['existing_rx1'], *row['frozen_scan_files']]:
            assert sha(binding['path']) == binding['sha256'], binding['path']
            assert Path(binding['path']).stat().st_size == binding['bytes']
            hashes.append(binding)
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip() == preflight['working_git_head']
    dirty = subprocess.check_output(['git', 'diff', '--binary', 'HEAD'], cwd=REPO)
    assert hashlib.sha256(dirty).hexdigest() == preflight['tracked_diff_sha256']
    output = dict(status='passed', GPS_used=False, no_position_fits=True, source_sha256=sha(Path(__file__)),
        root_protocol_sha256=sha(ROOT/'protocol.json'), membership_sha256=sha(HERE/'baseline_membership.json'),
        population=34, eligible=24, unavailable=10, jobs=len(expected), verified_file_bindings=len(hashes),
        native_curved_points=sum(r['curved_points'] for r in membership['cases'].values()),
        native_predictive_points=sum(r['predictive_points'] for r in membership['cases'].values()),
        working_tree_preserved=True, source_runner_audits_still_required=True)
    destination = HERE/'wave0.json'
    assert not destination.exists()
    destination.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
