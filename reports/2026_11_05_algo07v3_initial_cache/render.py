"""Verify and render repeated-calculation profiling and alternating initial searches."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--benchmark', type=Path, required=True)
    parser.add_argument('--tests', type=Path, required=True)
    args = parser.parse_args()
    profile = json.loads((args.profile / 'profile.json').read_bytes())
    result = json.loads((args.benchmark / 'result.json').read_bytes())
    assert profile['complete'] and profile['exact'] and result['exact']
    assert len(result['rows']) == 6 and all(r['exact'] for r in result['rows'])
    assert [r['side'] for r in result['rows']] == [
        'baseline', 'candidate', 'candidate', 'baseline', 'baseline', 'candidate']
    oracles = {str(Path('src/leo/analysis/localization_v3', name).resolve()): Path('tools', oracle)
               for name, oracle in (
                   ('position.py', 'algo07v3_preinitial_cache_position_oracle.py'),
                   ('initial_search.py', 'algo07v3_preinitial_cache_search_oracle.py'))}
    for record in (profile, result):
        for path, sha in record['bindings'].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha:
                # The previous implementation remains frozen after integration.
                assert path in oracles, path
                assert hashlib.sha256(oracles[path].read_bytes()).hexdigest() == sha, path
    suites = list(ET.parse(args.tests).getroot().iter('testsuite'))
    assert sum(int(s.attrib['tests']) for s in suites) == 8
    assert not any(int(s.attrib[k]) for s in suites for k in ('errors', 'failures', 'skipped'))
    out = Path(__file__).resolve().parent
    for root, names, folder in (
            (args.profile, ('profile.json', 'plan.json'), 'profile'),
            (args.benchmark, ('result.json', 'plan.json', 'sources.json'), 'benchmark')):
        dest = out / folder
        dest.mkdir(exist_ok=True)
        for name in names:
            (dest / name).write_bytes((root / name).read_bytes())
    (out / 'prototype-tests.xml').write_bytes(args.tests.read_bytes())
    means = result['means']
    summary = dict(exact=True, means=means, profile_totals=profile['totals'],
                   profiled_problems=len(profile['rows']), full_pipeline_speedup=None,
                   elapsed_reduction_percent=100 * (
                       1 - means['candidate']['seconds'] / means['baseline']['seconds']),
                   cpu_reduction_percent=100 * (
                       1 - means['candidate']['cpu_seconds'] / means['baseline']['cpu_seconds']))
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout='constrained')
    for ax, key, title in zip(axes, ('seconds', 'cpu_seconds'),
                              ('Complete initial-search elapsed seconds',
                               'Parent + reaped-child CPU seconds'), strict=True):
        maximum = 0
        for side, offset, color in [('baseline', -.18, '#68778b'), ('candidate', .18, '#168579')]:
            subset = [r for r in result['rows'] if r['side'] == side]
            values = [sum(r[key]) if isinstance(r[key], list) else r[key] for r in subset]
            maximum = max(maximum, max(values))
            bars = ax.bar([r['pair'] + offset for r in subset], values, width=.35,
                          label=side, color=color)
            ax.bar_label(bars, labels=[f'{v:.2f}' for v in values], padding=3, fontsize=9)
        ax.set(xticks=[0, 1, 2], xticklabels=['B → C', 'C → B', 'B → C'],
               ylim=(0, maximum * 1.18), ylabel=title)
        ax.grid(axis='y', alpha=.2)
    axes[1].legend(loc='upper center', bbox_to_anchor=(.5, 1.15), ncol=2)
    fig.suptitle('DS26-0002 · bounded-scope one-entry calculation reuse\n'
                 'All six full initial searches exact; prepared-stage benchmark')
    fig.savefig(out / 'initial-search.png', dpi=160)
    plt.close(fig)
    totals = profile['totals']
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout='constrained')
    labels = ['All calls', 'Repeated position', 'One-entry eligible']
    for ax, values, title in (
            (axes[0], [totals['calls'], totals['repeated'], totals['hits']['1']], 'Executed calls'),
            (axes[1], [totals['seconds'], totals['repeat_seconds'], totals['hit_seconds']['1']],
             'Seconds inside original calculation')):
        bars = ax.bar(labels, values, color=['#68778b', '#c28a27', '#168579'])
        ax.bar_label(bars, labels=[f'{v:.2f}' if ax is axes[1] else str(v) for v in values],
                     padding=3)
        ax.set(ylabel=title, ylim=(0, max(values) * 1.18))
        ax.grid(axis='y', alpha=.2)
    fig.suptitle('DS26-0002 · observation-only serial initial-search profile\n'
                 'Repeated-call bars are subsets, not additive; cache overhead excluded')
    fig.savefig(out / 'repeated-calculations.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
