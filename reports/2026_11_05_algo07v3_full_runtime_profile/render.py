"""Publish independently timed stages; reject the inconsistent parent flat profile."""

import argparse
import hashlib
import json
import pstats
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def read(path):
    return json.loads(path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--parts', type=Path, required=True)
    parser.add_argument('--tests', type=Path, required=True)
    args = parser.parse_args()
    out = Path(__file__).resolve().parent
    profile = read(args.profile / 'profile.json')
    control = read(args.control / 'cli/attempt/supervisor.json')
    parts = read(args.parts / 'result.json')
    parity = read(args.profile / 'fresh-parity.json')
    assert parity['profile_science_and_eight_pngs_exact'] and parts['exact']
    assert not profile['changed_sources']
    for clock in (profile['process'], control):
        assert clock['status'] == 'exited' and clock['returncode'] == 0
    assert profile['worker']['status'] == control['worker']['status'] == 'complete'
    assert not profile['worker']['resumed'] and not control['worker']['resumed']
    for bindings in (read(args.profile / 'plan.json')['bindings'],
                     read(args.control / 'plan.json')['bindings'],
                     parity['bindings'], parts['bindings']):
        for name, sha in bindings.items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha, name
    suites = list(ET.parse(args.tests).getroot().iter('testsuite'))
    assert sum(int(s.attrib['tests']) for s in suites) == 11
    assert not any(int(s.attrib[k]) for s in suites for k in ('errors', 'failures', 'skipped'))
    raw = [json.loads(line) for line in
           (args.control / 'cli/attempt/worker.log').read_text().splitlines()]
    stages = [r for r in raw if r.get('event') == 'stage']
    resource_rows = read(args.profile / 'stage-resources.json')
    assert [r['stage'] for r in stages] == [r['name'] for r in resource_rows]
    assert all(r['completed'] and min(r['self_cpu_seconds'], r['children_cpu_seconds']) >= 0
               for r in resource_rows)
    parent_path = args.profile / f"profile-{profile['process']['pid']}.pstats"
    parent = pstats.Stats(str(parent_path))
    anomalies = [dict(file=k[0], line=k[1], function=k[2], self_seconds=v[2],
                      cumulative_seconds=v[3]) for k, v in parent.stats.items()
                 if v[2] > v[3] + 1e-6]
    parent_check = dict(exclusive_sum=parent.total_tt,
                        worker_wall=read(args.profile / 'worker-resources.json')[0]['seconds'],
                        self_exceeds_cumulative=anomalies,
                        usable_for_function_ranking=False,
                        sha256=hashlib.sha256(parent_path.read_bytes()).hexdigest())
    assert anomalies and parent.total_tt > parent_check['worker_wall']
    children = []
    for path in sorted(args.profile.glob('profile-*.json')):
        stat_path = path.with_suffix('.pstats')
        stats = pstats.Stats(str(stat_path))
        bad = [k for k, v in stats.stats.items() if v[2] > v[3] + 1e-6 or min(v[2:4]) < 0]
        children.append(dict(metadata=read(path), exclusive_sum=stats.total_tt,
                             accounting_consistent=not bad, inconsistent_functions=bad,
                             sha256=hashlib.sha256(stat_path.read_bytes()).hexdigest()))
    rows = sorted(stages, key=lambda r: r['seconds'], reverse=True)
    elapsed = control['process_seconds']
    table = '| Stage | Unprofiled seconds | Share of total | Profiled seconds |\n'
    table += '| --- | ---: | ---: | ---: |\n'
    profiled_stages = {r['stage']: r['seconds'] for r in profile['stages']}
    for row in rows:
        table += (f"| {row['stage']} | {row['seconds']:.3f} | "
                  f"{100 * row['seconds'] / elapsed:.1f}% | "
                  f"{profiled_stages[row['stage']]:.3f} |\n")
    (out / 'stage-table.md').write_text(table)
    for root, folder, names in (
            (args.profile, 'profile', ['profile.json', 'plan.json', 'fresh-parity.json',
                                      'stage-resources.json', 'worker-resources.json',
                                      'recovery-substages.json', 'resources-start.json',
                                      'resources-end.json']),
            (args.control, 'control', ['plan.json', 'process-time.txt',
                                      'resources-start.json', 'resources-end.json']),
            (args.parts, 'posterior', ['result.json', 'original.py', 'instrumented.py'])):
        dest = out / folder
        dest.mkdir(exist_ok=True)
        for name in names:
            (dest / name).write_bytes((root / name).read_bytes())
    (out / 'control/supervisor.json').write_text(json.dumps(control, indent=2) + '\n')
    (out / 'control/stages.json').write_text(json.dumps(stages, indent=2) + '\n')
    (out / 'profile/parent-accounting-rejected.json').write_text(
        json.dumps(parent_check, indent=2) + '\n')
    (out / 'profile/children.json').write_text(json.dumps(children, indent=2) + '\n')
    (out / 'tests.xml').write_bytes(args.tests.read_bytes())
    summary = dict(scan='DS26-0002', unprofiled_seconds=elapsed,
                   profiled_seconds=profile['process']['process_seconds'],
                   complete_science_and_pngs_exact=True, parent_function_profile_usable=False,
                   child_profiles=len(children), posterior_trials_exact=3,
                   stage_wall_cpu_accounting_independent=True, tests=11,
                   full_dataset_qualification=False, production_modified=False)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')

    fig, ax = plt.subplots(figsize=(11, 7), layout='constrained')
    show = rows[:12][::-1]
    bars = ax.barh([r['stage'] for r in show], [r['seconds'] for r in show], color='#326ba8')
    ax.bar_label(bars, labels=[f"{r['seconds']:.1f} s" for r in show], padding=4)
    ax.set(xlabel='Unprofiled wall seconds', xlim=(0, 44),
           title=f'DS26-0002 · current ALGO07v3 · {elapsed:.1f} s total\n'
                 'Native GLRT ready through publication · largest stages')
    ax.grid(axis='x', alpha=.2)
    fig.savefig(out / 'stages.png', dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout='constrained')
    named = {r['name']: r for r in resource_rows}
    names = ['predictive', 'initial', 'conservative', 'family', 'plot_evidence']
    x = np.arange(len(names))
    axes[0].bar(x - .2, [named[n]['seconds'] for n in names], width=.4, label='Wall')
    axes[0].bar(x + .2, [named[n]['self_cpu_seconds'] + named[n]['children_cpu_seconds']
                         for n in names], width=.4, label='Parent + child CPU')
    axes[0].set(xticks=x, xticklabels=names, ylabel='Profiled seconds',
                title='Independent clocks · parallel CPU work can exceed wall time')
    axes[0].tick_params(axis='x', labelrotation=25)
    axes[0].legend()
    seconds = sum(r['seconds'] for r in parts['trials'])
    segments = dict(parts['parts'])
    values = {name: row['seconds'] / seconds * 100 for name, row in segments.items()}
    values['other bound work'] = 100 - sum(values.values())
    ordered = sorted(values, key=values.get)
    axes[1].barh(ordered, [values[n] for n in ordered], color='#49a078')
    axes[1].set(xlabel='Share of instrumented call time (%)',
                title='DS26-0066 captured 256-iteration likelihood\n'
                      'Three complete results exact; not pipeline speed')
    fig.savefig(out / 'cpu-and-posterior.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
