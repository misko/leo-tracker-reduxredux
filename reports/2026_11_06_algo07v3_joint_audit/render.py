"""Summarize completed, exactly compared joint-audit runs; never partial clocks."""

import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def summarize(root):
    comparison = read(root / 'comparison.json')
    assert comparison['exact_owned_science_and_artifacts'] and comparison['both_c_arms']
    modules = read(root / 'baseline-sources.json')
    expected = sorted(name.removesuffix('.py').replace('/', '.') for name in modules)
    assert comparison['source_changes'] == expected
    assert comparison['added_modules'] == []
    for record in (read(root / 'plan.json'), comparison):
        for name, sha in record.get('bindings', record.get('input_bindings', {})).items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha, name
    sides = {}
    for side in ('baseline', 'candidate'):
        receipt = read(root / side / 'attempt/supervisor.json')
        assert receipt['status'] == 'exited' and receipt['returncode'] == 0
        worker = receipt['worker']
        assert worker['status'] == 'complete' and not worker['resumed']
        assert all(read(root / side / 'isolation.json')['checks'].values())
        rows = [json.loads(line) for line in (root / side / 'attempt/worker.log')
                .read_text().splitlines()]
        stages = {r['stage']: r['seconds'] for r in rows if r.get('event') == 'stage'}
        stages['evidence_save'] = worker['evidence_save_seconds']
        stages['publication'] = worker['publication_seconds']
        stages['other'] = receipt['process_seconds'] - sum(stages.values())
        assert stages['other'] >= 0, 'Top-level stage clocks overlap or exceed the process clock'
        process = dict(line.strip().rsplit(': ', 1) for line in
                       (root / f'{side}-process-time.txt').read_text().splitlines() if ': ' in line)
        assert process['Exit status'] == '0'
        sides[side] = dict(seconds=receipt['process_seconds'], stages=stages,
                           cpu_seconds=sum(float(process[k]) for k in
                                           ('User time (seconds)', 'System time (seconds)')),
                           max_rss_kib=int(process['Maximum resident set size (kbytes)']))
    assert list(sides['baseline']['stages']) == list(sides['candidate']['stages'])
    return dict(root=str(root), exact=True, sides=sides, production_modified=False,
                wall_reduction_percent=100 * (1 - sides['candidate']['seconds'] /
                                              sides['baseline']['seconds']),
                cpu_reduction_percent=100 * (1 - sides['candidate']['cpu_seconds'] /
                                             sides['baseline']['cpu_seconds']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--label', default='ALGO07v3')
    args = parser.parse_args()
    result = summarize(args.root.resolve())
    args.output.mkdir(exist_ok=False)
    (args.output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    sides = result['sides']
    table = ['| Scope | Serial v3 | Batched v3 |', '| --- | ---: | ---: |']
    for field, label in (('seconds', 'Complete wall seconds'),
                         ('cpu_seconds', 'Outer command CPU seconds'),
                         ('max_rss_kib', 'Maximum process RSS KiB')):
        table.append(f"| {label} | {sides['baseline'][field]:.3f} | "
                     f"{sides['candidate'][field]:.3f} |")
    for stage in sides['baseline']['stages']:
        table.append(f"| {stage} | {sides['baseline']['stages'][stage]:.3f} | "
                     f"{sides['candidate']['stages'][stage]:.3f} |")
    (args.output / 'timings.md').write_text('\n'.join(table) + '\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    figure, axes = plt.subplots(1, 3, figsize=(15, 5.5))
    labels, colors = ['Serial v3', 'Batched v3'], ['#777777', '#3465a4']
    for axis, field, title in zip(
            axes[:2], ('seconds', 'cpu_seconds'),
            ('Complete elapsed time', 'CPU including descendants'), strict=True):
        values = [sides[s][field] for s in sides]
        bars = axis.bar(labels, values, color=colors)
        axis.bar_label(bars, fmt='%.1f s', padding=3)
        axis.set(title=title, ylabel='Seconds', ylim=(0, max(values) * 1.15))
    stages = sorted(sides['baseline']['stages'],
                    key=sides['baseline']['stages'].get, reverse=True)[:7][::-1]
    y = np.arange(len(stages))
    for i, side in enumerate(sides):
        axes[2].barh(y + (i - .5) * .36, [sides[side]['stages'][k] for k in stages],
                     height=.36, color=colors[i], label=labels[i])
    axes[2].set(yticks=y, yticklabels=stages, xlabel='Wall seconds', title='Largest stages')
    axes[2].legend()
    figure.suptitle(f'{args.label} · serial vs batched joint audits · exact outputs')
    figure.text(.5, .015, 'Native GLRT ready through publication; capture/GLRT/queue excluded. '
                'One sequential pair on a shared host.', ha='center', fontsize=9)
    figure.tight_layout(rect=(0, .045, 1, .94))
    figure.savefig(args.output / 'runtime.png', dpi=160)
    plt.close(figure)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
