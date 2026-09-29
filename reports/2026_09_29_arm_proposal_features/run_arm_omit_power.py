"""Saved-IQ CPU0 timing wrapper for the frozen ARM float-proposal runner."""
import hashlib
import json
from pathlib import Path
import shlex
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / '2026_09_29_arm_lag_discovery'
FROZEN = HERE.parent / '2026_09_29_arm_float_proposal/run_arm.py'
sys.path.insert(0, str(HERE.parent / '2026_09_28_arm_full_optimization'))
import arm_cohort as a


def main():
    binary = HERE / 'builds/arm/proposal_feature_ablation'
    receipt_path = binary.parent / 'build-receipt.json'
    receipt = json.loads(receipt_path.read_text())
    assert receipt['target'] == 'arm'
    assert a.sha(binary) == receipt['binaries'][binary.name]
    output = HERE / 'arm4-omit-power-v1'
    output.mkdir(exist_ok=False)
    manifest = json.loads((HERE.parent/'2026_09_28_arm_boundary_fallback/arm-cohort-v1/manifest.json').read_text())
    saved_remote = manifest['remote_directory']
    remote = '/mnt/glrtbench/feature-ablation-' + str(int(time.time()))
    a.remote('mkdir ' + shlex.quote(remote))
    a.upload(binary, remote + '/proposal')
    assert a.remote('sha256sum ' + remote + '/proposal').split()[0] == a.sha(binary)
    expected = {}
    for row in map(json.loads, (HERE/'host32-omit-power/rows.jsonl').read_text().splitlines()):
        c = row['context']
        expected[(c['session_id'], c['visit_index'], row['window'], row['rx'])] = row['ranked_epochs']['combined']
    results = []
    for index, context in enumerate(manifest['selected']):
        source = a.INPUTS / context['file']
        assert a.sha(source) == context['sha256']
        assert a.remote(f'sha256sum {saved_remote}/case-{index}.ci16').split()[0] == hashlib.sha256(np.load(source, allow_pickle=False).tobytes()).hexdigest()
        edge = context['target']['edge']
        template = a.template_map()[edge]['exact']
        assert a.remote(f'sha256sum {saved_remote}/{edge}-exact.c128').split()[0] == template['sha256']
        for repeat in range(3):
            command = [remote+'/proposal', '2500000', saved_remote+'/'+edge+'-exact.c128', saved_remote+f'/case-{index}.ci16', '--combined-only', '--omit=power']
            raw = a.remote(shlex.join(command), timeout=60)
            (output/f'case-{index}-r{repeat}.jsonl').write_text(raw)
            rows = list(map(json.loads, raw.splitlines()))
            assert len(rows) == 22
            assert {(r['probe_index'], r['receiver_id']) for r in rows} == {(window, rx) for window in range(11) for rx in range(2)}
            assert all(r['feature_mask'] == ['lag1', 'lag3', 'lag5'] for r in rows)
            mismatches = []
            for row in rows:
                key = (context['session_id'], context['visit_index'], row['probe_index'], row['receiver_id'])
                if row['top4']['combined'] != expected[key]:
                    mismatches.append({'window': row['probe_index'], 'rx': row['receiver_id'],
                                       'actual': row['top4']['combined'], 'expected': expected[key]})
            timings = {key: sum(row['timings_ms'][key] for row in rows) for key in rows[0]['timings_ms']}
            results.append({'context': context, 'repeat': repeat, 'timings_ms': timings, 'mismatches': mismatches})
            print(index, repeat, timings, 'mismatches', len(mismatches), flush=True)
    summary = {'complete': True, 'scope': 'saved-IQ proposal-only CPU0; no RF, capture, or GLRT',
               'wrapper_of_frozen_runner': str(FROZEN), 'frozen_runner_sha256': a.sha(FROZEN),
               'binary_sha256': a.sha(binary), 'build_receipt_sha256': a.sha(receipt_path),
               'remote_directory': remote, 'windows_including_repeats': 264, 'unique_windows': 88,
               'rank_mismatches_vs_host_omit_power': sum(len(r['mismatches']) for r in results), 'rows': results,
               'mean_timings_ms': {key: sum(r['timings_ms'][key] for r in results)/len(results) for key in results[0]['timings_ms']}}
    (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary['mean_timings_ms']), flush=True)


if __name__ == '__main__':
    main()
