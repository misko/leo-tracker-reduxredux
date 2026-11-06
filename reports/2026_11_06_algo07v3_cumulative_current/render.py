"""Retain a failed historical reference and an exact cache-eviction census."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from compare_algo07v3_runs import compare


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main(root, census_root):
    out = Path(__file__).resolve().parent
    census = read(census_root / 'result.json')
    for plan in (read(root / 'plan.json'), census['plan']):
        for name, digest in plan['bindings'].items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    clock = read(root / 'v3-run/attempt/supervisor.json')
    assert clock['status'] == 'exited' and clock['returncode'] == 0
    assert clock['worker']['status'] == 'complete' and not clock['worker']['resumed']
    assert all(read(root / 'v3-run/isolation.json')['checks'].values())
    reference = read(root / 'reference-timing/summary.json')
    assert reference['state'] == 'incomplete' and reference['completed_path_seconds'] is None
    drift = read(root / 'reference-drift.json')
    assert len(drift['failed']) == 9
    assert sum(r['path'].endswith('.pyc') for r in drift['failed']) == 7
    baseline = Path('/srv/bulk/leo-dev/algo07v3-lapack-native-0002-20261106')
    comparison = compare(SimpleNamespace(
        baseline_request=baseline / 'candidate-request.json',
        candidate_request=root / 'v3-request.json',
        baseline_timing=baseline / 'candidate/attempt/supervisor.json',
        candidate_timing=root / 'v3-run/attempt/supervisor.json',
        changed_module=[], added_module=[]))
    assert comparison['exact_owned_science_and_artifacts']
    write(out / 'v3-unchanged-comparison.json', comparison)
    rows = []
    for arm, result in census['results'].items():
        assert result['exact'] and len(result['problems']) == 5
        summary = result['summary']
        assert summary['8']['avoidable_calls'] == 0
        assert summary['16'] == summary['32'] == summary['64']
        rows.append(dict(arm=arm, profiled_fit_seconds=result['fit']['seconds'],
                         profiled_fit_cpu_seconds=result['fit']['cpu_seconds'],
                         calls=sum(r['calls'] for r in result['problems']),
                         misses=summary['8']['misses'],
                         avoidable_calls=summary['16']['avoidable_calls'],
                         avoidable_seconds=summary['16']['avoidable_calculation_seconds']))
    tests = Path('/srv/bulk/leo-dev/algo07v3-position-cache-tests-20261106.xml')
    suites = list(ET.parse(tests).getroot().iter('testsuite'))
    assert sum(int(s.attrib['tests']) for s in suites) == 10
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('failures', 'errors', 'skipped'))
    log = root / 'v3-run/attempt/worker.log'
    stages = [json.loads(line) for line in log.read_text().splitlines() if line.startswith('{')]
    stages = {r['stage']: r['seconds'] for r in stages if r.get('event') == 'stage'}
    assert sum(stages.values()) <= clock['process_seconds']
    summary = dict(native_seconds=clock['process_seconds'], native_stages=stages,
                   exact_unchanged_native_outputs=True, cache_census=rows, tests=10,
                   original_reference_state=reference['state'], reference_drift=drift,
                   original_algo07_speedup=None, cache_speedup=None,
                   runtime_changed=False, production_changed=False)
    write(out / 'summary.json', summary)
    copies = {name: root / name for name in (
        'plan.json', 'candidate-execution.json', 'reference-execution.json',
        'candidate-process-time.txt', 'reference-process-time.txt',
        'candidate-resources-start.json', 'candidate-resources-end.json',
        'reference-resources-start.json', 'reference-resources-end.json',
        'reference-drift.json', 'reference-copy-search.json')}
    copies.update({
        'native-supervisor.json': root / 'v3-run/attempt/supervisor.json',
        'native-isolation.json': root / 'v3-run/isolation.json',
        'native-worker.log': log,
        'failed-reference-summary.json': root / 'reference-timing/summary.json',
        'failed-reference.log': root / 'reference.log',
        'failed-reference-process.log': (
            root / 'reference-timing/inference-attempt-0001/process.log'),
        'failed-reference-command.json': (
            root / 'reference-timing/inference-attempt-0001/process.command.json'),
        'cache-census.json': census_root / 'result.json',
        'cache-plan.json': census_root / 'plan.json', 'cache-tests.xml': tests})
    for name, path in copies.items():
        (out / name).write_bytes(path.read_bytes())
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    names = sorted(stages, key=stages.get, reverse=True)[:12]
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(names, [stages[n] for n in names], color='#237e73')
    ax.bar_label(bars, fmt='%.1f s', padding=3)
    ax.invert_yaxis()
    ax.set(xlabel='Elapsed seconds', xlim=(0, max(stages.values()) * 1.18),
           title=f"Current ALGO07v3: {clock['process_seconds']:.1f} s · DS26-0002")
    fig.text(.5, .01, 'Exact unchanged outputs · original ALGO07 reference failed preflight · '
             'no new speedup ratio', ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, 1))
    fig.savefig(out / 'stages.png', dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    for ax, row in zip(axes, rows, strict=True):
        sizes = (8, 16, 32, 64)
        counts = [census['results'][row['arm']]['summary'][str(n)]['misses'] for n in sizes]
        bars = ax.bar([str(n) for n in sizes], counts, color='#4b78a1')
        ax.bar_label(bars, padding=3)
        ax.set(xlabel='Shadow cache capacity', ylabel='Calculated cache misses',
               title=f"{row['arm']}: at most {row['avoidable_seconds']:.3f} s reusable work",
               ylim=(0, max(counts) * 1.18))
    fig.suptitle('Hard DS26-0066 training: larger per-problem caches offer little benefit')
    fig.text(.5, .01, 'Observation only: every original call executes · both complete fits exact · '
             'five independent phase problems per arm', ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .05, 1, .94))
    fig.savefig(out / 'cache-census.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--census-root', type=Path, required=True)
    args = parser.parse_args()
    main(args.root.resolve(), args.census_root.resolve())
