"""Verify exact workspace experiments and retain all timing pairs and regressions."""

import argparse
import hashlib
import json
import shutil
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def read(path):
    return json.loads(path.read_bytes())


def main(kernel, training, layout_kernel, layout_training, tests):
    out = Path(__file__).resolve().parent
    data = {}
    for name, root, expected_count in (('kernel', kernel, 18), ('training', training, 8),
            ('layout-kernel', layout_kernel, 9), ('layout-training', layout_training, 8)):
        result = read(root / 'result.json')
        assert result['exact']
        assert len(result['rows']) == expected_count
        assert all(r['exact'] for r in result['rows'])
        for path, sha in result['bindings'].items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha, path
        dest = out / name
        dest.mkdir(exist_ok=True)
        for path in root.iterdir():
            if path.suffix in ('.json', '.py'):
                shutil.copyfile(path, dest / path.name)
        data[name] = result
    suites = ET.parse(tests).getroot().findall('testsuite')
    count = sum(int(s.attrib['tests']) for s in suites)
    assert count == 101
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('errors', 'failures', 'skipped'))
    shutil.copyfile(tests, out / 'tests.xml')
    summary = dict(tests=count, kernel_means={}, training_means=data['training']['means'],
                   layout_kernel_means=data['layout-kernel']['means'],
                   layout_training_means=data['layout-training']['means'],
                   exact_kernel_and_training=True, full_pipeline_speedup=None)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), layout='constrained')
    for ax, variant in zip(axes, ('lu', 'inverse', 'both'), strict=True):
        summary['kernel_means'][variant] = {}
        for side, color in (('baseline', '#427ba0'), ('candidate', '#41956a')):
            rows = [r for r in data['kernel']['rows']
                    if r['variant'] == variant and r['side'] == side]
            summary['kernel_means'][variant][side] = statistics.mean(r['seconds'] for r in rows)
            ax.plot([r['pair']+1 for r in rows], [r['seconds'] for r in rows],
                    'o-', color=color, label=side)
        ax.set(title=f'{variant} workspace reuse', xlabel='Alternating pair',
               ylabel='Seconds per complete likelihood')
        ax.set_xticks([1, 2, 3])
        ax.legend()
    fig.suptitle('Hard captured likelihood: 256 precision iterations, identical results')
    fig.savefig(out / 'kernel.png', dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout='constrained')
    table = ['| Arm / pair | Baseline seconds | Workspace seconds | Baseline CPU | Workspace CPU |',
             '| --- | ---: | ---: | ---: | ---: |']
    for ax, arm in zip(axes, ('c0', 'fitted_c'), strict=True):
        for side, color in (('baseline', '#427ba0'), ('candidate', '#41956a')):
            rows = [r for r in data['training']['rows'] if r['arm'] == arm and r['side'] == side]
            ax.plot([r['pair']+1 for r in rows], [r['seconds'] for r in rows],
                    'o-', color=color, label=side)
        ax.set(title=f'DS26-0066 target 1 / fold 1: {arm}', xlabel='Alternating pair',
               ylabel='Complete training seconds')
        ax.set_xticks([1, 2])
        ax.legend()
        for pair in range(2):
            a, b = [next(r for r in data['training']['rows']
                         if r['arm'] == arm and r['pair'] == pair and r['side'] == side)
                    for side in ('baseline', 'candidate')]
            table.append(f'| {arm} / {pair+1} | {a["seconds"]:.3f} | {b["seconds"]:.3f} | '
                         f'{a["cpu_seconds"]:.3f} | {b["cpu_seconds"]:.3f} |')
    fig.suptitle('Inverse-solve workspace: all five phase rounds and original fit budgets')
    fig.savefig(out / 'training.png', dpi=160)
    plt.close(fig)
    (out / 'training-table.md').write_text('\n'.join(table)+'\n')
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), layout='constrained')
    for variant, color in (('baseline', '#427ba0'), ('fortran', '#41956a'),
                           ('workspace', '#a46cba')):
        rows = [r for r in data['layout-kernel']['rows'] if r['variant'] == variant]
        axes[0].plot([r['pair']+1 for r in rows], [r['seconds'] for r in rows],
                     'o-', color=color, label=variant)
    axes[0].set(title='Captured likelihood: separate layout and buffer',
                xlabel='Rotating comparison', ylabel='Seconds per call')
    axes[0].set_xticks([1, 2, 3])
    axes[0].legend()
    table = ['| Arm / pair | Baseline seconds | Layout seconds | Baseline CPU | Layout CPU |',
             '| --- | ---: | ---: | ---: | ---: |']
    for ax, arm in zip(axes[1:], ('c0', 'fitted_c'), strict=True):
        for side, color in (('baseline', '#427ba0'), ('candidate', '#41956a')):
            rows = [r for r in data['layout-training']['rows']
                    if r['arm'] == arm and r['side'] == side]
            ax.plot([r['pair']+1 for r in rows], [r['seconds'] for r in rows],
                    'o-', color=color, label=side)
        ax.set(title=f'Complete DS26-0066 training: {arm}',
               xlabel='Alternating pair', ylabel='Seconds')
        ax.set_xticks([1, 2])
        ax.legend()
        for pair in range(2):
            a, b = [next(r for r in data['layout-training']['rows']
                         if r['arm'] == arm and r['pair'] == pair and r['side'] == side)
                    for side in ('baseline', 'candidate')]
            table.append(f'| {arm} / {pair+1} | {a["seconds"]:.3f} | {b["seconds"]:.3f} | '
                         f'{a["cpu_seconds"]:.3f} | {b["cpu_seconds"]:.3f} |')
    fig.suptitle('One-line Fortran identity layout: no mutable solve workspace')
    fig.savefig(out / 'layout-ablation.png', dpi=160)
    plt.close(fig)
    (out / 'layout-training-table.md').write_text('\n'.join(table)+'\n')
    (out / 'component-summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('kernel', 'training', 'layout-kernel', 'layout-training', 'tests'):
        parser.add_argument('--'+name, type=Path, required=True)
    main(**vars(parser.parse_args()))
