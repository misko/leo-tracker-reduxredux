"""Render observed key cost separately from complete prepared recovery clocks."""

import argparse
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared', type=Path, action='append', required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parent
    dependency = json.loads((root / 'dependencies.json').read_bytes())
    assert dependency['saved_native_audit_exact']
    controls = dependency['controls']
    names = [f['field'] for f in controls[0]['fields']]
    mean = {s: {name: np.mean([next(f[s] for f in c['fields'] if f['field'] == name)
                               for c in controls]) for name in names}
            for s in ('copy_seconds', 'buffer_seconds')}
    cases = []
    for path in args.prepared:
        result = json.loads((path / 'result.json').read_bytes())
        assert result['exact'] and result['saved_native_audit_exact']
        assert result['baseline_has_no_fingerprint_overhead']
        name = path.name.replace('algo07v3-control-view-', '')
        shutil.copyfile(path / 'result.json', root / f'{name}.json')
        rows = {r['side']: r for r in result['rows']}
        cases.append(dict(name=name, baseline_s=rows['baseline']['seconds'],
                          candidate_s=rows['candidate']['seconds'],
                          key_s=sum(c['key_seconds'] for c in rows['candidate']['controls']),
                          reused=sum(c['reused'] for c in rows['candidate']['controls']),
                          controls=len(rows['candidate']['controls'])))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout='constrained')
    labels = ['Copy then hash', 'Hash buffer',
              'Without discovery geometry\ncopy/hash retained fields']
    values = [sum(mean['copy_seconds'].values()), sum(mean['buffer_seconds'].values()),
              sum(v for k, v in mean['copy_seconds'].items() if k != 'geometry')]
    axes[0].bar(labels, values, color=['tab:blue', 'tab:orange', 'tab:green'])
    axes[0].set_ylabel('Mean per-control field fingerprint seconds')
    axes[0].set_title('DS26-0066 observed key cost\nJSON encoding and copying results excluded')
    for i, case in enumerate(cases):
        for j, side in enumerate(('baseline', 'candidate')):
            axes[1].bar(i+(j-.5)*.32, case[f'{side}_s'], width=.32,
                        color=['tab:blue', 'tab:orange'][j], label=side if i == 0 else None)
    axes[1].set_xticks(range(len(cases)), [c['name'] for c in cases])
    axes[1].set_ylabel('Complete prepared recovery wall seconds')
    axes[1].set_title('Exact complete recovery\nOriginal baseline has no key checks')
    axes[1].legend()
    fig.savefig(root / 'profile.png', dpi=150)
    plt.close(fig)
    summary = dict(field_means=mean, cases=cases)
    (root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(cases, indent=2))


if __name__ == '__main__':
    main()
