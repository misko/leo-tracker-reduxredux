"""Render the bounded reuse/covariance investigation from retained receipts."""

import argparse
import hashlib
import json
import shutil
import statistics
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def mean(rows, side):
    return statistics.mean(r['seconds'] for r in rows if r['side'] == side)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reuse', type=Path, required=True)
    p.add_argument('--kernel', type=Path, required=True)
    p.add_argument('--training', type=Path, required=True)
    p.add_argument('--tests', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parent
    data = {}
    for name in ('reuse', 'kernel', 'training'):
        path = getattr(args, name) / 'result.json'
        data[name] = json.loads(path.read_bytes())
        bindings = data[name].get('bindings', data[name].get('plan', {}).get('bindings', {}))
        for original, sha in bindings.items():
            choices = [Path(original), root / 'measured' / Path(original).name]
            if not any(q.is_file() and hashlib.sha256(q.read_bytes()).hexdigest() == sha
                       for q in choices):
                raise ValueError(f'Measured source/input changed: {original}')
        shutil.copyfile(path, root / f'{name}.json')
    shutil.copyfile(args.tests, root / 'tests.xml')
    kernel = data['kernel']['cases'][0]
    training = data['training']['rows']
    assert kernel['kind'] == 'workspace' and kernel['exact']
    assert all(r['exact'] for r in training)
    assert data['kernel']['cases'][1]['kind'] == 'symmetric'
    assert not data['kernel']['cases'][1]['exact']
    stages_path = root.parent / '2026_11_06_algo07v3_training_queue/stages.json'
    stages = json.loads(stages_path.read_bytes())
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), layout='constrained')
    names = ['predictive', 'initial', 'conservative', 'family', 'native_preparation',
             'residual_screen', 'admission', 'numerical', 'cavity', 'plot_evidence',
             'png_rendering', 'evidence_save']
    for j, (run, label) in enumerate(zip(stages, ['Run A: 193.9 s', 'Run B: 152.5 s'],
                                        strict=True)):
        axes[0].barh([i + (j - .5) * .35 for i in range(len(names))],
                     [run['stages'][n] for n in names], height=.35, label=label)
    axes[0].set_yticks(range(len(names)), [n.replace('_', ' ') for n in names])
    axes[0].invert_yaxis()
    axes[0].set_xlabel('Stage wall seconds; unchanged-code executions')
    axes[0].set_title('DS26-0002: largest pipeline stages\nNative GLRT ready → artifacts published')
    axes[0].legend()
    for arm, color in [('c0', '#1976d2'), ('fitted_c', '#d76a2b')]:
        for pair in range(2):
            pair_rows = [r for r in training if r['arm'] == arm and r['pair'] == pair]
            values = [next(r['seconds'] for r in pair_rows if r['side'] == side)
                      for side in ('baseline', 'candidate')]
            axes[1].plot([0, 1], values, 'o-', color=color, alpha=.8,
                         label=f'{arm}, pair {pair + 1}')
    axes[1].set_xticks([0, 1], ['Current v3', 'Covariance buffer reuse'])
    axes[1].set_xlim(-.25, 1.25)
    axes[1].set_ylabel('Complete prepared training fit, seconds')
    axes[1].set_title('DS26-0066: difficult fold\nExact full optimizer/phase/state signatures')
    axes[1].legend()
    for ax in axes:
        ax.grid(alpha=.2, axis='x' if ax is axes[0] else 'y')
    fig.savefig(root / 'profile.png', dpi=150)
    plt.close(fig)
    table = []
    for arm in ('c0', 'fitted_c'):
        rows = [r for r in training if r['arm'] == arm]
        a, b = mean(rows, 'baseline'), mean(rows, 'candidate')
        table.append(f'| {arm} | {a:.3f} | {b:.3f} | {100 * (a-b)/a:+.2f}% |')
    a, b = mean(kernel['rows'], 'baseline'), mean(kernel['rows'], 'candidate')
    detail = '\n'.join(f"| {r['arm']} | {r['pair'] + 1} | {r['side']} | "
                       f"{r['seconds']:.3f} | {r['cpu_seconds']:.3f} |"
                       for r in training)
    census = '\n'.join(f"| {scan} | {case['targets']} | {case['eligible_fold_problems']} | "
                       f"{case['unique_masks']} | {case['potentially_reusable_fits_per_arm']} |"
                       for scan, case in zip(['DS26-0002', 'DS26-0066'],
                                             data['reuse']['cases'], strict=True))
    (root / 'measurements.md').write_text(f'''# Measurements

![Pipeline profile and complete covariance trials](profile.png)

| Calibration arm | Baseline mean s | Buffer-reuse mean s | Time reduction |
| --- | ---: | ---: | ---: |
{chr(10).join(table)}

Captured 256-iteration likelihood: {a:.6f} → {b:.6f} s,
{100 * (a-b)/a:.2f}% reduction. Six alternating pairs, three calls per side.
All 36 timed calls are exact. The separate symmetric-product candidate fails
complete likelihood equality; no speed comparison is claimed for it.

| Arm | Pair | Side | Elapsed s | CPU s |
| --- | ---: | --- | ---: | ---: |
{detail}

| Scan | Targets | Fold problems | Distinct masks | Potential duplicate fits per arm |
| --- | ---: | ---: | ---: | ---: |
{census}

Mask equality is a necessary condition only. The single duplicate is target 2,
fold 0 versus target 3, fold 0. The slow target 1, fold 1 is unique. This does
not justify a general training cache, nor prove those two complete models equal.
''')
    bindings = {str(stages_path): hashlib.sha256(stages_path.read_bytes()).hexdigest()}
    (root / 'render-inputs.json').write_text(json.dumps(bindings, indent=2) + '\n')


if __name__ == '__main__':
    main()
