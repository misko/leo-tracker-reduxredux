"""Summarize current native stage clocks and exact non-forking screen profiles."""

import hashlib
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def read(path):
    return json.loads(path.read_bytes())


def main():
    out = Path(__file__).resolve().parent
    previous = out.parent / '2026_11_05_algo07v3_nomination_points'
    contexts = [('Measured candidate', previous / 'native', 'candidate-'),
                ('Same-numerics confirmation', previous / 'formatted', '')]
    runs = []
    for label, root, prefix in contexts:
        comparison = read(root / 'comparison.json')
        assert comparison['exact_owned_science_and_artifacts'] and comparison['both_c_arms']
        receipt = read(root / f'{prefix}supervisor.json')
        assert receipt['returncode'] == 0 and not receipt['worker']['resumed']
        total = receipt['process_seconds']
        stages = {r['stage']: r['seconds'] for line in
                  (root / f'{prefix}worker.log').read_text().splitlines()
                  if (r := json.loads(line)).get('event') == 'stage'}
        stages['evidence_save'] = receipt['worker']['evidence_save_seconds']
        stages['publication'] = receipt['worker']['publication_seconds']
        stages['other_supervision_and_unscoped'] = total - sum(stages.values())
        assert min(stages.values()) >= 0
        runs.append(dict(label=label, total=total, stages=stages))
    order = sorted(runs[0]['stages'], key=runs[0]['stages'].get, reverse=True)
    table = ['| Stage | Measured candidate | Share | Confirmation | Share |',
             '| --- | ---: | ---: | ---: | ---: |']
    for name in order:
        a, b = [r['stages'][name] for r in runs]
        table.append(f'| {name} | {a:.3f} s | {a/runs[0]["total"]:.1%} | '
                     f'{b:.3f} s | {b/runs[1]["total"]:.1%} |')
    table.append(f'| **Total** | **{runs[0]["total"]:.3f} s** | 100% | '
                 f'**{runs[1]["total"]:.3f} s** | 100% |')
    (out / 'stage-table.md').write_text('\n'.join(table) + '\n')
    profiles = []
    for scan in ('0002', '0066'):
        root = Path(f'/srv/bulk/leo-dev/algo07v3-screen-reprofile-{scan}-20261106')
        result = read(root / 'result.json')
        assert result['exact'] and result['accounting_valid'] and result['unchanged_inputs']
        for path, digest in result['bindings'].items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, path
        shutil.copyfile(root / 'result.json', out / f'screen-{scan}.json')
        profiles.append(dict(scan=scan, seconds=result['seconds'], parts=result['parts'],
                             top_functions=result['functions'][:15]))
    summary = dict(runs=runs, profiles=profiles,
                   source_commit='8e3fb0224265e7fb28323098f206fddb068cb283',
                   production_changed=False, whole_dataset_qualification=False,
                   original_algo07_speedup=None)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    names = [n for n in order if runs[0]['stages'][n] >= 1]
    fig, axes = plt.subplots(1, 2, figsize=(14, 8), layout='constrained')
    y = np.arange(len(names))
    for index, run in enumerate(runs):
        values = [run['stages'][n] for n in names]
        color = ('#427ba0', '#bb7755')[index]
        axes[0].barh(y + (index - .5)*.35, values, height=.35, color=color,
                     label=f'{run["label"]}: {run["total"]:.1f} s')
        axes[1].barh(y + (index - .5)*.35, np.array(values)/run['total']*100,
                     height=.35, color=color)
    for ax in axes:
        ax.set_yticks(y, [n.replace('_', ' ') for n in names])
        ax.invert_yaxis()
        ax.grid(axis='x', alpha=.2)
    axes[0].set(xlabel='Elapsed seconds', title='Absolute clocks vary across identical runs')
    axes[1].set(xlabel='Share of complete process (%)',
                title='Repeated position fits remain dominant')
    axes[0].legend(fontsize=8, loc='lower right')
    fig.suptitle('ALGO07v3 / DS26-0002: native GLRT input through publication\n'
                 'Exact science, both calibration arms and eight PNGs; stages below 1 s omitted')
    fig.savefig(out / 'stages.png', dpi=160)
    plt.close(fig)
    print(json.dumps(dict(native=[r['total'] for r in runs],
                          profiles=[(r['scan'], r['seconds']) for r in profiles])))


if __name__ == '__main__':
    main()
