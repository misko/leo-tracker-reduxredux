"""Render nested joint-kernel attribution without calling it a speed benchmark."""

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads((args.root / 'result.json').read_bytes())
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in data['bindings'].items())
    assert len(data['rows']) == 6 and all(r['exact'] for r in data['rows'])
    args.output.mkdir(exist_ok=False)
    table = ['| Phase pairs | Contractions | Whole wall | Whole CPU | Assigned CPU | '
             'Unassigned CPU |', '| ---: | --- | ---: | ---: | ---: | ---: |']
    for row in data['rows']:
        assigned = sum(v['cpu_seconds'] for v in row['statements'].values())
        assert 0 <= assigned <= row['cpu_seconds']
        mode = 'Optimized' if row['optimized'] else 'Direct'
        table.append(f"| {row['phase_pairs']:,} | {mode} | {row['seconds']:.6f} s | "
                     f"{row['cpu_seconds']:.6f} s | {assigned:.6f} s | "
                     f"{row['cpu_seconds'] - assigned:.6f} s |")
    largest = max(row['phase_pairs'] for row in data['rows'])
    selected = [row for row in data['rows'] if row['phase_pairs'] == largest]
    for row in selected:
        mode = 'Optimized' if row['optimized'] else 'Direct'
        table += [f'\n### {mode}, {largest:,} pairs\n',
                  '| Statement | Calls | CPU seconds | % of whole-call CPU |',
                  '| --- | ---: | ---: | ---: |']
        for key, value in sorted(row['statements'].items(),
                                 key=lambda item: item[1]['cpu_seconds'], reverse=True)[:10]:
            table.append(f"| `{key}` | {value['calls']} | {value['cpu_seconds']:.6f} | "
                         f"{100 * value['cpu_seconds'] / row['cpu_seconds']:.2f}% |")
    (args.output / 'timings.md').write_text('\n'.join(table) + '\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    names = {'(coefficient, sign, logdet)': 'Solve + determinant',
             'rhs': 'Right-hand side', 'off': 'Cross-family contraction',
             'log_density': 'Log density',
             'gram[:, :, :d1, :d1]': 'Gram: first diagonal block',
             'gram[:, :, d1:, d1:]': 'Gram: second diagonal block',
             'gram[:, :, :d1, d1:]': 'Gram: upper cross block',
             'gram[:, :, d1:, :d1]': 'Gram: lower cross block'}
    for axis, row in zip(axes, selected, strict=True):
        ranked = sorted(row['statements'].items(),
                        key=lambda item: item[1]['cpu_seconds'], reverse=True)[:7][::-1]
        labels = [names.get(key.split(': ', 1)[1], key.split(': ', 1)[1]) for key, _ in ranked]
        values = [100 * v['cpu_seconds'] / row['cpu_seconds'] for _, v in ranked]
        bars = axis.barh(labels, values, color='#3465a4')
        axis.bar_label(bars, fmt='%.1f%%', padding=3)
        axis.set(xlabel='% of instrumented whole-call CPU',
                 title='Predictive / optimized' if row['optimized'] else 'Numerical / direct',
                 xlim=(0, max(values) * 1.2))
    figure.suptitle(f'Actual DS26-0102 phase integral · {largest:,} phase pairs')
    figure.text(.5, .02, 'Nested component attribution, not a pipeline speed measurement. '
                'All results and inputs remain exact; one CPU / one BLAS thread.',
                ha='center', fontsize=9)
    figure.tight_layout(rect=(0, .055, 1, .94))
    figure.savefig(args.output / 'statements.png', dpi=160)
    plt.close(figure)
    print('\n'.join(table))


if __name__ == '__main__':
    main()
