"""Check complete matched matrix and frozen-population arithmetic."""
import hashlib
import json
from pathlib import Path

import numpy as np

from common import HERE, DATASET, save_json


def main():
    records = [json.loads(p.read_text()) for p in (HERE/'results').glob('*.json')]
    sources = {s['source_id']:s for s in json.loads((DATASET/'sources.json').read_text())}
    expected = {f'{s}-full-fitted-c-original' for s in sources}
    expected |= {f'{s}-{mode}-{arm}-{method}' for s in sources
                 for mode in ['full','early_to_late','late_to_early']
                 for arm in ['fitted-c','zero-c'] for method in ['continuation','A','B','C']}
    assert len(records)==len(expected)==125
    assert {r['task'] for r in records}==expected
    failures = []
    results = {}
    missing_code_bindings = []
    for r in records:
        results[r['task']] = r
        if r.get('status')=='failed':
            failures.append(dict(task=r['task'],error=r['error']))
            continue
        source = sources[r['source_id']]
        if 'code_sha256' not in r:
            missing_code_bindings.append(r['task'])
        for name,value in r.get('code_sha256',{}).items():
            assert 'sha256:'+hashlib.sha256((HERE/name).read_bytes()).hexdigest()==value
        m = r['full_scan']
        assert m['observations']==source['observation_count']
        assert r['source_receipt']['tracking_input_sha256']==source['tracking_input_sha256']
        assert r['source_receipt']['terminal_sha256']==source['terminal_sha256']
        assert r['source_receipt']['tle_sha256']==source['tle_sha256']
        assert r['endpoint_audit']['feasible']
        assert r['challenge']['observations']+r['outside_challenge']['observations']==m['observations']
        assert r['challenge']['associated']+r['outside_challenge']['associated']==m['associated']
        assert max(abs(t) for t in m['total_timing_s'].values()) <= 20.+1e-6
        if r['method']=='original':
            assert m['associated']==source['original_associated_count']
            assert abs(m['objective']-source['baseline_audit']['objective'])<1e-7
        else:
            assert 1 <= r['inference_diagnostics']['evaluations'] <= 180
        if r['arm']=='zero-c':
            assert r['vector'][6]==m['c']==0.
        a = np.load(HERE/'results'/(r['task']+'.npz'))
        assert len(a['associated'])==m['observations']
        assert a['associated'].sum()==m['associated']
        assert np.isfinite(a['residual_hz']).all()
        if r['mode']=='full' and r['arm']=='fitted-c':
            assert m['associated']-m['new_associations']+m['lost_associations']==source['original_associated_count']
        if r['mode']!='full':
            assert (~a['train_mask']).sum()==r['held']['observations']
            assert a['associated'][~a['train_mask']].sum()==r['held']['associated']
    for source in sources:
        for method in ['continuation','A','B','C']:
            for arm in ['fitted-c','zero-c']:
                early_path = HERE/'results'/f'{source}-early_to_late-{arm}-{method}.npz'
                late_path = HERE/'results'/f'{source}-late_to_early-{arm}-{method}.npz'
                if not early_path.exists() or not late_path.exists():
                    continue  # Failed receipt remains explicit in failures.
                early = np.load(early_path)['train_mask']
                late = np.load(late_path)['train_mask']
                assert np.array_equal(early,~late)
    # Verify that the frozen challenge capsule has not changed.
    capsule = json.loads((DATASET/'manifest.json').read_text())
    if isinstance(capsule.get('files'),list):
        for entry in capsule['files']:
            key = entry.get('path',entry.get('file'))
            expected_hash = entry['sha256'].removeprefix('sha256:')
            assert hashlib.sha256((DATASET/key).read_bytes()).hexdigest()==expected_hash
    elif isinstance(capsule.get('files'),dict):
        for key,value in capsule['files'].items():
            expected_hash = value['sha256'] if isinstance(value,dict) else value
            assert hashlib.sha256((DATASET/key).read_bytes()).hexdigest()==expected_hash.removeprefix('sha256:')
    save_json(HERE/'validation.json',dict(expected_receipts=125,received=len(records),failures=failures,
        original_replay_verified=True,fixed_denominators_verified=True,budgets_verified=True,
        fixed_c_verified=True,temporal_masks_complementary=True,physical_bounds_verified=True,
        frozen_dataset_manifest_verified=True,
        receipt_code_hashes_verified=True,early_receipts_bound_by_final_manifest=missing_code_bindings,
        qualification='No independent identity truth; original saved production audit uses its original local search constraints. Common research audit uses full regional disk.'))
    print(json.dumps(dict(receipts=len(records),failures=len(failures),validated=True)),flush=True)


if __name__=='__main__':
    main()
