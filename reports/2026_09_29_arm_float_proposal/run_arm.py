"""Time proposals only on CPU0 and audit every selected peak against Python."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / '2026_09_29_arm_lag_discovery'
sys.path.insert(0, str(HERE.parent / '2026_09_28_arm_full_optimization'))
import arm_cohort as a


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    binary = args.binary.resolve()
    out = HERE / args.output
    out.mkdir(exist_ok=False)
    manifest = json.loads((HERE.parent/'2026_09_28_arm_boundary_fallback/arm-cohort-v1/manifest.json').read_text())
    old = manifest['remote_directory']
    remote = '/mnt/glrtbench/float-proposal-' + str(int(time.time()))
    a.remote('mkdir ' + shlex.quote(remote)); a.upload(binary, remote+'/proposal')
    assert a.remote('sha256sum '+remote+'/proposal').split()[0] == a.sha(binary)
    features = {}
    for row in map(json.loads, (PRIOR/'ds7-704-v1/rows.jsonl').read_text().splitlines()):
        c = row['context']
        features[(c['session_id'], c['visit_index'], row['window'], row['rx'])] = row
    results = []
    for index, ctx in enumerate(manifest['selected']):
        source = a.INPUTS/ctx['file']; assert a.sha(source) == ctx['sha256']
        raw = np.load(source, allow_pickle=False)
        assert a.remote(f'sha256sum {old}/case-{index}.ci16').split()[0] == hashlib.sha256(raw.tobytes()).hexdigest()
        edge = ctx['target']['edge']; template = a.template_map()[edge]['exact']
        assert a.remote(f'sha256sum {old}/{edge}-exact.c128').split()[0] == template['sha256']
        for repeat in range(3):
            cmd = [remote+'/proposal', '2500000', old+'/'+edge+'-exact.c128', old+f'/case-{index}.ci16', '--combined-only']
            output = a.remote(shlex.join(cmd), timeout=60)
            (out/f'case-{index}-r{repeat}.jsonl').write_text(output)
            rows = list(map(json.loads, output.splitlines()))
            assert {(r['probe_index'], r['receiver_id']) for r in rows} == {(w, rx) for w in range(11) for rx in range(2)}
            assert len(rows) == 22
            mismatches = []
            for row in rows:
                expected = features[(ctx['session_id'], ctx['visit_index'], row['probe_index'], row['receiver_id'])]['ranked_epochs']['combined'][:4]
                actual = row['top4']['combined']
                if actual != expected:
                    mismatches.append({'window': row['probe_index'], 'rx': row['receiver_id'], 'actual': actual, 'expected': expected})
            costs = {key: sum(r['timings_ms'][key] for r in rows) for key in rows[0]['timings_ms']}
            results.append({'context': ctx, 'repeat': repeat, 'timings_ms': costs, 'mismatches': mismatches})
            print(index, repeat, costs, 'mismatches', len(mismatches), flush=True)
    summary = {'complete': True, 'binary_sha256': a.sha(binary), 'remote_directory': remote,
        'scope': 'proposal-only CPU0; no final GLRT or capture; three repeats of four unique dwells',
        'windows_including_repeats': 264, 'unique_windows': 88,
        'rank_mismatches': sum(len(r['mismatches']) for r in results), 'rows': results,
        'mean_timings_ms': {k: sum(r['timings_ms'][k] for r in results)/len(results) for k in results[0]['timings_ms']}}
    (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(summary['mean_timings_ms'], flush=True)


if __name__ == '__main__':
    main()
