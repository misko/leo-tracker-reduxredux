"""Verify a full timer profile against a fresh native run and render all stages."""

import argparse
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import compare_algo07v3_runs as comparison
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def read(path):
    return json.loads(path.read_bytes())


def profile_module_changes(a, b, expected_changed, expected_added):
    """The profiler imports the byte-identical CLI instead of executing it as -m."""
    assert expected_changed == expected_added == []
    assert set(a) - set(b) == {'__main__', '__mp_main__'}
    assert set(b) - set(a) == {'leo.cli.algo07v3'}
    assert all(a[k] == b[k] for k in a.keys() & b.keys())
    assert a['__main__']['sha256'] == a['__mp_main__']['sha256'] == (
        b['leo.cli.algo07v3']['sha256'])
    return set(), set()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile', type=Path, required=True)
    p.add_argument('--native', type=Path, required=True)
    args = p.parse_args()
    out = Path(__file__).resolve().parent
    full = read(args.profile / 'profile.json')
    assert not full['changed_sources']
    assert read(args.profile / 'plan.json')['timers_only']
    assert not list(args.profile.glob('*.pstats'))
    clock = dict(full['process'], worker=full['worker'],
                 request_sha256=full['worker']['request_sha256'])
    derived = out / 'profile-supervisor.json'
    derived.write_text(json.dumps(clock, indent=2) + '\n')
    original = comparison.module_changes
    comparison.module_changes = profile_module_changes
    try:
        equality = comparison.compare(SimpleNamespace(
            baseline_request=args.native / 'candidate-request.json',
            candidate_request=args.profile / 'request.json',
            baseline_timing=args.native / 'candidate/attempt/supervisor.json',
            candidate_timing=derived, changed_module=[], added_module=[]))
    finally:
        comparison.module_changes = original
    equality['entry_point_bytes_identical'] = True
    equality['entry_point_module_aliases'] = ['__main__', '__mp_main__', 'leo.cli.algo07v3']
    assert equality['exact_owned_science_and_artifacts']
    (out / 'comparison.json').write_text(json.dumps(equality, indent=2) + '\n')
    control = read(args.native / 'candidate/attempt/supervisor.json')
    raw = [json.loads(line) for line in
           (args.native / 'candidate/attempt/worker.log').read_text().splitlines()
           if line.startswith('{')]
    unprofiled = {r['stage']: r['seconds'] for r in raw if r.get('event') == 'stage'}
    unprofiled['evidence_save'] = control['worker']['evidence_save_seconds']
    unprofiled['publication'] = control['worker']['publication_seconds']
    unprofiled['other_process'] = control['process_seconds'] - sum(unprofiled.values())
    stages = read(args.profile / 'stage-resources.json')
    substages = read(args.profile / 'recovery-substages.json')
    workers = [read(q) for q in sorted(args.profile.glob('profile-*.json'))]
    assert all(r['completed'] and r['seconds'] >= 0 for r in stages + substages)
    assert all(r['timers_only'] and r['end'] >= r['start']
               and min(r['self_cpu_seconds'], r['children_cpu_seconds']) >= 0 for r in workers)
    named = {r['name']: r for r in stages}
    assert set(named) == set(unprofiled) - {'evidence_save', 'publication', 'other_process'}
    worker_cpu = read(args.profile / 'worker-resources.json')[0]
    totals = dict(unprofiled_seconds=control['process_seconds'],
                  profiled_seconds=clock['process_seconds'],
                  profiled_worker_seconds=worker_cpu['seconds'],
                  profiled_cpu_seconds=worker_cpu['self_cpu_seconds']
                  + worker_cpu['children_cpu_seconds'],
                  task_count=len(workers), exact=True, production_modified=False)
    summary = dict(totals=totals, unprofiled_stages=unprofiled,
                   profiled_stages=stages, recovery_substages=substages, tasks=workers)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    ordered = sorted(unprofiled, key=unprofiled.get, reverse=True)
    table = '| Stage | Unprofiled wall s | Share | Profiled wall s | Profiled CPU s |\n'
    table += '| --- | ---: | ---: | ---: | ---: |\n'
    for name in ordered:
        r = named.get(name)
        cells = ('—', '—') if r is None else (
            f"{r['seconds']:.3f}", f"{r['self_cpu_seconds'] + r['children_cpu_seconds']:.3f}")
        table += (f"| {name} | {unprofiled[name]:.3f} | "
                  f"{100*unprofiled[name]/control['process_seconds']:.1f}% | "
                  f"{cells[0]} | {cells[1]} |\n")
    (out / 'stages.md').write_text(table)
    fig, axes = plt.subplots(1, 2, figsize=(15, 7), layout='constrained')
    show = ordered[:15][::-1]
    bars = axes[0].barh(show, [unprofiled[n] for n in show])
    axes[0].bar_label(bars, labels=[f'{unprofiled[n]:.1f}' for n in show], padding=3)
    axes[0].set(xlabel='Unprofiled wall seconds',
                title=f"Full ALGO07v3 · DS26-0066 · {control['process_seconds']:.1f} s\n"
                      'Native GLRT ready through publication')
    show_cpu = sorted(named, key=lambda n: named[n]['seconds'], reverse=True)[:8]
    x = np.arange(len(show_cpu))
    axes[1].bar(x-.2, [named[n]['seconds'] for n in show_cpu], width=.4, label='Wall')
    axes[1].bar(x+.2, [named[n]['self_cpu_seconds'] + named[n]['children_cpu_seconds']
                       for n in show_cpu], width=.4, label='Parent + reaped-child CPU')
    axes[1].set(xticks=x, xticklabels=show_cpu, ylabel='Profiled seconds',
                title='Independent CPU and wall clocks\nParallel CPU work may exceed wall time')
    axes[1].tick_params(axis='x', labelrotation=40)
    axes[1].legend()
    fig.savefig(out / 'full-stages.png', dpi=150)
    plt.close(fig)
    longest = sorted(workers, key=lambda r: r['seconds'], reverse=True)[:20][::-1]
    labels = [f"{r['stage'] or r['top_stage']} · {r['item']}" for r in longest]
    fig, ax = plt.subplots(figsize=(12, 8), layout='constrained')
    ax.barh(range(len(longest)), [r['seconds'] for r in longest], label='Task wall window')
    ax.scatter([r['self_cpu_seconds'] for r in longest], range(len(longest)),
               color='tab:orange', label='Task self CPU')
    ax.set(yticks=range(len(longest)), yticklabels=labels, xlabel='Seconds',
           title='Longest individual fits/scoring tasks · overlapping windows are not additive')
    ax.legend()
    fig.savefig(out / 'longest-tasks.png', dpi=150)
    plt.close(fig)
    dest = out / 'profile'
    dest.mkdir(exist_ok=True)
    for name in ('profile.json', 'plan.json', 'stage-resources.json', 'worker-resources.json',
                 'recovery-substages.json', 'resources-start.json', 'resources-end.json'):
        shutil.copyfile(args.profile / name, dest / name)
    print(json.dumps(totals, indent=2))


if __name__ == '__main__':
    main()
