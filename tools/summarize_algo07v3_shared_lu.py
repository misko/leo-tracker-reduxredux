"""Summarize a completed, source-bound full-worker shared-LU experiment."""

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from types import SimpleNamespace

from compare_algo07v3_runs import compare
from observe_algo07v3_pair_cpu import fields


def read(path):
    return json.loads(path.read_bytes())


def kernel_totals(rows, field='seconds'):
    if not rows or any(r[field] < 0 for r in rows):
        raise ValueError('Completed nonnegative kernel measurements required')
    return {mode: dict(
        calls=sum(r['optimized'] == optimized for r in rows),
        seconds=sum(r[field] for r in rows if r['optimized'] == optimized),
        phase_pairs=sum(r['phase_pairs'] for r in rows if r['optimized'] == optimized),
    ) for mode, optimized in [('optimized', True), ('direct', False)]}


def stage_totals(path):
    result = {}
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get('event') == 'stage':
            name = row['stage']
            if name in result:
                raise ValueError(f'Duplicate top-level stage: {name}')
            result[name] = row['seconds']
    if not result:
        raise ValueError('No completed top-level stage measurements')
    return result


def summarize(root):
    for p, digest in read(root / 'plan.json')['bindings'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Changed binding: {p}')
    # Require the normal full comparison, including successful fresh clocks.
    verification = compare(SimpleNamespace(
        baseline_request=root / 'baseline/request.json',
        candidate_request=root / 'candidate/request.json',
        baseline_timing=root / 'baseline/supervisor.json',
        candidate_timing=root / 'candidate/supervisor.json',
        changed_module=[], added_module=[]))
    calls = [read(root / side / 'kernel-calls.json') for side in ('baseline', 'candidate')]
    def signature(rows):
        return [(r['optimized'], r['phase_pairs']) for r in rows]

    if signature(calls[0]) != signature(calls[1]):
        raise ValueError('Kernel execution sequence changed')
    sides = {}
    direct_only = False
    libraries = None
    for side, rows in zip(('baseline', 'candidate'), calls, strict=True):
        folder = root / side
        backend = read(folder / 'backend.json')
        if backend.get('direct_only'):
            direct_only = True
            if any(r['threads'] != 1 for r in backend['libraries']):
                raise ValueError('Direct chunks changed BLAS threads')
            if libraries is not None and libraries != backend['libraries']:
                raise ValueError('Different BLAS providers between sides')
            libraries = backend['libraries']
            bindings = {r['path']: r['sha256'] for r in libraries}
        else:
            bindings = backend['bindings']
        for p, digest in bindings.items():
            if hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest:
                raise ValueError(f'Changed backend binding: {p}')
        sides[side] = dict(
            process_seconds=read(folder / 'supervisor.json')['process_seconds'],
            stages=stage_totals(folder / 'worker.log'), kernel=kernel_totals(rows),
            kernel_cpu=kernel_totals(rows, 'cpu_seconds')
            if all('cpu_seconds' in r for r in rows) else None,
            kernel_grids=[dict(optimized=mode, phase_pairs=pairs,
                               calls=sum(r['optimized'] == mode and r['phase_pairs'] == pairs
                                         for r in rows),
                               seconds=sum(r['seconds'] for r in rows
                                           if r['optimized'] == mode and r['phase_pairs'] == pairs))
                          for mode, pairs in sorted({(r['optimized'], r['phase_pairs'])
                                                     for r in rows})])
    if sides['baseline']['stages'].keys() != sides['candidate']['stages'].keys():
        raise ValueError('Stage inventory differs')
    cpu = None
    if direct_only:
        if (any(r['parallel'] for r in calls[0])
                or not any(r['parallel'] for r in calls[1])
                or any(r['parallel'] and r['optimized'] for r in calls[1])):
            raise ValueError('Direct-only dispatch invariant failed')
        captures = [read(root / side / 'captures.json') for side in ('baseline', 'candidate')]
        if ({k: (v['input'], v['result']) for k, v in captures[0].items()}
                != {k: (v['input'], v['result']) for k, v in captures[1].items()}):
            raise ValueError('Captured native inputs/results differ')
        totals = {}
        for side in sides:
            usage = read(root / side / 'supervisor.json')['reaped_child_cpu']
            if (set(usage) != {'user_seconds', 'system_seconds'}
                    or any(v < 0 for v in usage.values())):
                raise ValueError('Invalid full-worker CPU counters')
            totals[side + '_seconds'] = sum(usage.values())
        cpu = dict(totals, scope='RUSAGE_CHILDREN deltas across completed supervisor waits',
                   resolution_seconds=None)
    cpu_path = root / 'reaped-child-cpu.json'
    if cpu_path.exists() and not direct_only:
        receipt = read(cpu_path)
        if receipt['complete']:
            for side in sides:
                if receipt[f'{side}_completed_pid'] != read(root / side / 'supervisor.json')['pid']:
                    raise ValueError('CPU observer refers to different worker')
            if receipt['initial_children'].split() != [str(receipt['candidate_completed_pid'])]:
                raise ValueError('CPU observer did not isolate candidate child')
            a, b = (fields(receipt[k]) for k in ('baseline_raw_stat', 'terminal_raw_stat'))
            if a['start_ticks'] != b['start_ticks']:
                raise ValueError('CPU observer supervisor identity changed')
            baseline = a['child_user_ticks'] + a['child_system_ticks']
            total = b['child_user_ticks'] + b['child_system_ticks']
            tick = receipt['clock_ticks_per_second']
            if tick <= 0 or total < baseline:
                raise ValueError('Invalid CPU observer counters')
            cpu = dict(baseline_seconds=baseline / tick,
                       candidate_seconds=(total - baseline) / tick,
                       scope=receipt['scope'], resolution_seconds=1 / tick)
    return dict(verification=verification, sides=sides, external_prototype=True,
                variant='direct-only ordered chunks' if direct_only else 'shared-factorization',
                production_modified=False, cpu_accounting_available=cpu is not None,
                reaped_child_cpu=cpu,
                scope='imports through public artifact publication; excludes capture/GLRT/queue')


def render(summary, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    sides = summary['sides']
    b, c = (sides[s] for s in ('baseline', 'candidate'))
    names = list(b['stages'])
    rows = [('Complete process', b['process_seconds'], c['process_seconds'])]
    rows += [(n, b['stages'][n], c['stages'][n]) for n in names]
    rows += [(f'Kernel {mode} (nested)', b['kernel'][mode]['seconds'],
              c['kernel'][mode]['seconds']) for mode in ('optimized', 'direct')]
    table = '| Scope | Baseline s | Candidate s | Wall reduction |\n| --- | ---: | ---: | ---: |\n'
    for name, baseline, candidate in rows:
        pct = f'{100 * (1 - candidate / baseline):.2f}%' if baseline else 'n/a'
        table += f'| {name} | {baseline:.3f} | {candidate:.3f} | {pct} |\n'
    table += ('\nKernel calls by phase-grid size (nested):\n\n'
              '| Mode | Phase pairs/call | Calls per side | Baseline s | Candidate s |\n'
              '| --- | ---: | ---: | ---: | ---: |\n')
    for first, second in zip(b['kernel_grids'], c['kernel_grids'], strict=True):
        mode = 'optimized' if first['optimized'] else 'direct'
        table += (f"| {mode} | {first['phase_pairs']} | {first['calls']} | "
                  f"{first['seconds']:.3f} | {second['seconds']:.3f} |\n")
    if summary['reaped_child_cpu']:
        cpu = summary['reaped_child_cpu']
        table += (f"\nReaped child CPU: {cpu['baseline_seconds']:.2f} → "
                  f"{cpu['candidate_seconds']:.2f} CPU seconds. {cpu['scope']}.\n")
    if b['kernel_cpu'] and c['kernel_cpu']:
        table += ('\nNested kernel CPU totals:\n\n'
                  '| Mode | Baseline CPU s | Candidate CPU s |\n| --- | ---: | ---: |\n')
        for mode in ('optimized', 'direct'):
            table += (f"| {mode} | {b['kernel_cpu'][mode]['seconds']:.3f} | "
                      f"{c['kernel_cpu'][mode]['seconds']:.3f} |\n")
    (out / 'native-timings.md').write_text(table)
    fig, axes = plt.subplots(1, 2, figsize=(13, 7), layout='constrained')
    order = sorted(names, key=lambda n: b['stages'][n])
    for ax, labels, values in [
        (axes[0], order, lambda s: [s['stages'][n] for n in order]),
        (axes[1], ['Direct contractions', 'Optimized contractions'],
         lambda s: [s['kernel'][m]['seconds'] for m in ('direct', 'optimized')]),
    ]:
        y = np.arange(len(labels))
        for offset, side in [(-.2, 'baseline'), (.2, 'candidate')]:
            ax.barh(y + offset, values(sides[side]), height=.4, label=side)
        ax.set(yticks=y, yticklabels=labels, xlabel='Elapsed seconds')
        ax.legend()
    axes[0].set_title('Complete stages (one sequential pair)')
    axes[1].set_title('Joint kernel totals\nNested within stages; do not add both')
    fig.suptitle(f"DS26-0102: external {summary['variant']} prototype\n"
                 f"Full process: {b['process_seconds']:.1f} → {c['process_seconds']:.1f} s")
    fig.savefig(out / 'native-timings.png', dpi=150)
    plt.close(fig)


def render_chunks(root, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    completion = read(root / 'complete.json')
    if not completion['completed']:
        raise ValueError('Completed chunk benchmark required')
    for p, digest in completion['bindings'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Changed chunk binding: {p}')
    summaries = []
    for workers in (2, 3):
        result = read(root / f'workers{workers}/result.json')
        if not result['exact'] or len(result['rows']) != 24:
            raise ValueError('Complete exact alternating chunk pairs required')
        for mode in (True, False):
            means = {}
            for side in ('baseline', 'candidate'):
                rows = [r for r in result['rows'] if r['side'] == side and r['optimized'] == mode]
                if len(rows) != 6 or not all(r['exact'] for r in rows):
                    raise ValueError('Six exact measurements per side/mode required')
                means[side] = {metric: statistics.mean(r[metric] for r in rows)
                               for metric in ('seconds', 'cpu_seconds')}
            summaries.append(dict(workers=workers, optimized=mode, means=means))
    (out / 'chunk-summary.json').write_text(json.dumps(summaries, indent=2) + '\n')
    table = ('| Workers | Mode | Baseline wall s | Candidate wall s | '
             'Baseline CPU s | Candidate CPU s |\n| ---: | --- | ---: | ---: | ---: | ---: |\n')
    for row in summaries:
        b, c = (row['means'][k] for k in ('baseline', 'candidate'))
        mode = 'optimized' if row['optimized'] else 'direct'
        table += (f"| {row['workers']} | {mode} | {b['seconds']:.6f} | {c['seconds']:.6f} | "
                  f"{b['cpu_seconds']:.6f} | {c['cpu_seconds']:.6f} |\n")
    (out / 'chunk-timings.md').write_text(table)
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), layout='constrained')
    x = np.arange(2)
    for ax, metric, title in zip(axes, ('seconds', 'cpu_seconds'), ('Wall time', 'CPU work'),
                                strict=True):
        for offset, workers in ((-.2, 2), (.2, 3)):
            selected = [r for r in summaries if r['workers'] == workers]
            ratios = [r['means']['candidate'][metric] / r['means']['baseline'][metric]
                      for r in selected]
            bars = ax.bar(x + offset, ratios, width=.4, label=f'{workers} workers')
            ax.bar_label(bars, fmt='%.2f×', padding=3)
        ax.axhline(1., color='black', linestyle='--', label='serial baseline')
        ax.set(xticks=x, xticklabels=['Optimized\npredictive mode', 'Direct\nnumerical mode'],
               ylabel='Candidate / matched baseline mean', title=title, ylim=(0, 2.5))
        ax.legend()
    fig.suptitle('Captured joint integration: chunk concurrency tradeoff\n'
                 'Six alternating pairs per mode/configuration; all outputs exact')
    fig.savefig(out / 'chunk-timings.png', dpi=150)
    plt.close(fig)
    return summaries


def render_direct_grids(root, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    result = read(root / 'result.json')
    if not result['exact_native_results']:
        raise ValueError('Exact original native results required')
    for p, digest in result['bindings'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Changed actual-grid binding: {p}')
    summaries = []
    for pairs in sorted({r['phase_pairs'] for r in result['rows']}):
        means = {}
        for side in ('baseline', 'candidate'):
            rows = [r for r in result['rows'] if r['phase_pairs'] == pairs and r['side'] == side]
            if len(rows) != 6 or not all(r['exact_native_result'] for r in rows):
                raise ValueError('Six exact alternating observations per side/grid required')
            means[side] = {k: statistics.mean(r[k] for r in rows)
                           for k in ('seconds', 'cpu_seconds')}
        summaries.append(dict(phase_pairs=pairs, means=means))
    (out / 'actual-grid-summary.json').write_text(json.dumps(summaries, indent=2) + '\n')
    table = ('| Phase pairs | Baseline wall s | Candidate wall s | Baseline CPU s | '
             'Candidate CPU s |\n| ---: | ---: | ---: | ---: | ---: |\n')
    for row in summaries:
        b, c = (row['means'][k] for k in ('baseline', 'candidate'))
        table += (f"| {row['phase_pairs']} | {b['seconds']:.6f} | {c['seconds']:.6f} | "
                  f"{b['cpu_seconds']:.6f} | {c['cpu_seconds']:.6f} |\n")
    (out / 'actual-grid-timings.md').write_text(table)
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), layout='constrained')
    x = np.arange(len(summaries))
    for ax, metric, title in zip(axes, ('seconds', 'cpu_seconds'), ('Wall time', 'CPU work'),
                                strict=True):
        ratios = [r['means']['candidate'][metric] / r['means']['baseline'][metric]
                  for r in summaries]
        bars = ax.bar(x, ratios, color='#ee854a')
        ax.bar_label(bars, fmt='%.2f×', padding=3)
        ax.axhline(1., color='black', linestyle='--', label='serial baseline')
        ax.set(xticks=x, xticklabels=[f"{r['phase_pairs']:,}" for r in summaries],
               xlabel='Phase pairs per call', ylabel='Candidate / matched baseline mean',
               title=title, ylim=(0, 1.5))
        ax.legend()
    variant = result.get('variant', 'direct-chunks')
    description = ('owned factor reuse' if variant == 'owned-lu'
                   else 'three ordered chunk workers')
    fig.suptitle(f'DS26-0102 actual direct grids: {description}\n'
                 'Six alternating pairs per grid; all outputs match the native capture')
    fig.savefig(out / 'actual-grid-timings.png', dpi=150)
    plt.close(fig)
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--chunks', type=Path)
    parser.add_argument('--direct-grids', type=Path)
    args = parser.parse_args()
    result = summarize(args.root)
    args.output.mkdir(exist_ok=False)
    (args.output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    render(result, args.output)
    if args.chunks:
        render_chunks(args.chunks, args.output)
    if args.direct_grids:
        render_direct_grids(args.direct_grids, args.output)
    print(json.dumps(result['sides']))


if __name__ == '__main__':
    main()
