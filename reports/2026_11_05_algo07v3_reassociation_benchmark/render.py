"""Summarize alternating complete screens and the next measured hotspot."""

import argparse
import hashlib
import json
import pstats
import statistics
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def main(root):
    out = Path(__file__).resolve().parent
    result = read(root / 'benchmark.json')
    assert result['process']['returncode'] == 0 and not result['changed_sources']
    assert result['worker']['status'] == 'complete' and not result['worker']['resumed']
    assert read(root / 'parity.json')['profile_science_and_eight_pngs_exact']
    for name, sha in read(root / 'plan.json')['bindings'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha, name
    screens = read(root / 'screens.json')
    assert screens and all(r['exact'] and len(r['rows']) == 6 for r in screens)
    # Per-pair totals sum non-overlapping target screens, not nested profile calls.
    totals = {side: {field: [sum(next(r[field] for r in target['rows']
                                     if r['side'] == side and r['pair'] == pair)
                               for target in screens) for pair in range(3)]
                     for field in ('seconds', 'cpu_seconds')}
              for side in ('baseline', 'candidate')}
    means = {side: {field: statistics.mean(values) for field, values in fields.items()}
             for side, fields in totals.items()}
    profile = pstats.Stats(str(root / 'conservative.pstats'))
    functions = [dict(file=filename, line=line, function=fn, calls=data[1],
                      self_seconds=data[2], cumulative_seconds=data[3])
                 for (filename, line, fn), data in profile.stats.items()]
    functions.sort(key=lambda r: r['cumulative_seconds'], reverse=True)
    summary = dict(
        scan='DS26-0066', exact=True, means=means, totals=totals,
        wall_reduction_percent=100 * (1 - means['candidate']['seconds'] /
                                     means['baseline']['seconds']),
        cpu_reduction_percent=100 * (1 - means['candidate']['cpu_seconds'] /
                                    means['baseline']['cpu_seconds']),
        targets=[r['norad'] for r in screens],
        conservative_profile=read(root / 'conservative.json'),
        profile_functions=functions[:25],
        instrumented_total_seconds=result['overall_instrumented_seconds'],
        full_pipeline_speedup=None, production_modified=False,
    )
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    for name in ('benchmark.json', 'parity.json', 'plan.json', 'screens.json',
                 'conservative.json', 'resources-start.json', 'resources-end.json'):
        (out / name).write_bytes((root / name).read_bytes())
    (out / 'tests.xml').write_bytes(
        Path('/srv/bulk/leo-dev/algo07v3-reassociation-benchmark-tests.xml').read_bytes())
    (out / 'conservative.pstats').write_bytes((root / 'conservative.pstats').read_bytes())

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    colors = ['#777777', '#3465a4']
    x = np.arange(3)
    for i, side in enumerate(('baseline', 'candidate')):
        bars = axes[0].bar(x + (i - .5) * .36, totals[side]['seconds'],
                           width=.36, color=colors[i], label=side)
        axes[0].bar_label(bars, fmt='%.2f', padding=3)
    axes[0].set(xticks=x, xticklabels=['Baseline first', 'Candidate first', 'Baseline first'],
                ylabel='Sum of complete screen seconds', title='Alternating reassociation screens',
                ylim=(0, max(totals['baseline']['seconds']) * 1.32))
    axes[0].legend()
    selected = ['fit_and_gate', 'salvage', '_context']
    values = [sum(r['cumulative_seconds'] for r in functions if r['function'] == name)
              for name in selected]
    bars = axes[1].barh(['Paired fits + gates', 'Salvage', 'Context preparation'], values,
                        color='#3465a4')
    axes[1].bar_label(bars, fmt='%.2f s', padding=3)
    axes[1].set(xlabel='Profiled cumulative seconds', title='Conservative recovery: next target',
                xlim=(0, max(values) * 1.25))
    fig.text(.5, .015, 'DS26-0066 · exact screens and final science/eight PNGs · '
             'screen repeats and cProfile are not a complete-path speed benchmark',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, 1))
    fig.savefig(out / 'measurements.png', dpi=160)
    plt.close(fig)
    print(json.dumps({k: v for k, v in summary.items() if k != 'profile_functions'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    main(parser.parse_args().root)
