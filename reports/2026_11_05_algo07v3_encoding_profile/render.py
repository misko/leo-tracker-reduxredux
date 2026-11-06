"""Validate live-encoding receipts and render the current runtime breakdown."""

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


def main(root, tests):
    target = Path(__file__).resolve().parent
    plan = json.loads((root / 'plan.json').read_bytes())
    for name, digest in plan['bindings'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    benchmark = json.loads((root / 'benchmark.json').read_bytes())
    assert benchmark['process']['returncode'] == 0 and not benchmark['changed_sources']
    assert benchmark['full_pipeline_speed_benchmark'] is False
    parity = json.loads((root / 'parity.json').read_bytes())
    assert parity['profile_science_and_eight_pngs_exact']
    assert parity['shared_implementation_exact']
    suites = ET.parse(tests).getroot().findall('testsuite')
    assert sum(int(s.attrib['tests']) for s in suites) == 14
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('errors', 'failures', 'skipped'))
    calls = json.loads((root / 'encoding.json').read_bytes())
    assert len(calls) == 1
    rows = calls[0]['rows']
    assert len(rows) == 7 and all(r['completed'] for r in rows)
    assert all(r['exact'] for r in rows if r['name'] != 'original_first')
    means = {side: statistics.mean(r['seconds'] for r in rows if r['name'] == side)
             for side in ('baseline', 'candidate')}
    stages = [json.loads(line) for line in (root / 'worker.log').read_text().splitlines()]
    stages = [r for r in stages if r['event'] == 'stage']
    assert len({r['stage'] for r in stages}) == len(stages)
    summary = dict(encoding_means_seconds=means,
                   encoding_percent_change=100 * (means['candidate'] / means['baseline'] - 1),
                   stages=stages,
                   native_to_render_seconds=benchmark['worker']['native_to_render_seconds'],
                   instrumented_process_seconds=benchmark['process']['process_seconds'],
                   exact_publication=True, runtime_changed=False, tests=14)
    (target / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    for name in ('plan.json', 'benchmark.json', 'encoding.json', 'parity.json', 'worker.log',
                 'resources-start.json', 'resources-end.json',
                 'original-pack.py', 'candidate-pack.py'):
        shutil.copyfile(root / name, target / name)
    shutil.copyfile(tests, target / 'tests.xml')
    large = sorted((r for r in stages if r['seconds'] >= 1),
                   key=lambda r: r['seconds'], reverse=True)
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.5), gridspec_kw={'width_ratios': [1.6, 1]})
    axes[0].barh([r['stage'].replace('_', ' ') for r in large],
                 [r['seconds'] for r in large], color='#397da8')
    axes[0].invert_yaxis()
    axes[0].set(xlabel='Elapsed seconds', title='Current v3 stages — DS26-0002')
    for i, row in enumerate(large):
        axes[0].text(row['seconds'] + .4, i, f"{row['seconds']:.2f}", va='center', fontsize=9)
    axes[0].set_xlim(0, 46)
    profile = calls[0]['profile']
    costs = dict(profile['clocks'], unclassified=profile['remaining_seconds'])
    axes[1].barh(list(costs), list(costs.values()), color='#b06a3b')
    axes[1].invert_yaxis()
    axes[1].set(xlabel='Scoped profiled seconds', title='Evidence encoding — 3.59 seconds')
    fig.suptitle('Repeated fitting dominates; NPY-header caching is rejected', fontsize=15)
    fig.text(.5, .02, 'Three CPUs, one BLAS thread. Encoding trials run after rendering. '
             'Not a capture-to-publication speed benchmark.', ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .05, 1, .95))
    fig.savefig(target / 'runtime.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--tests', type=Path, required=True)
    args = parser.parse_args()
    main(args.root, args.tests)
