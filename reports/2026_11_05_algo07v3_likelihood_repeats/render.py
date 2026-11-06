"""Validate and summarize exact-input profiling and Cholesky experiments."""

import argparse
import hashlib
import json
import shutil
import statistics
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def read(path):
    return json.loads(path.read_bytes())


def bindings_match(bindings, native=None):
    measured = Path(__file__).resolve().parent / 'measured'
    historical = {str(Path('tools', name).resolve()): measured / name for name in
                  ('probe_algo07v3_cholesky.py', 'benchmark_algo07v3_cholesky_training.py')}
    if native is not None:
        name = 'leo/analysis/localization_v3/hierarchical.py'
        historical[str(Path('src', name).resolve())] = native / 'baseline-src' / name
    # Original measured bytes remain bound after adapting probes or integrating
    # the independently qualified one-module candidate.
    for name, digest in bindings.items():
        source = historical.get(name, Path(name))
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest, name


def main(profile, kernel, training, tests, native=None, broad_tests=None):
    target = Path(__file__).resolve().parent
    bindings_match(read(profile / 'plan.json')['bindings'], native)
    run, parity = read(profile / 'profile.json'), read(profile / 'parity.json')
    assert run['process']['returncode'] == 0 and not run['changed_sources']
    assert parity['profile_science_and_eight_pngs_exact'] and parity['shared_implementation_exact']
    suites = ET.parse(tests).getroot().findall('testsuite')
    assert sum(int(s.attrib['tests']) for s in suites) == 31
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('errors', 'failures', 'skipped'))
    rows = defaultdict(lambda: defaultdict(float))
    process_files = list(profile.glob('calls-*.json'))
    for path in process_files:
        for name, row in read(path)['rows'].items():
            stage = name.split(':', 1)[0]
            for k in ('calls', 'seconds', 'repeat_calls', 'repeat_seconds', 'cross_label_calls',
                      'key_seconds', 'output_check_seconds'):
                rows[stage][k] += row[k]
            for capacity, seconds in row['hit_seconds'].items():
                rows[stage][f'cache_{capacity}_eligible_seconds'] += seconds
    kresult = read(kernel / 'result.json')
    bindings_match(kresult['bindings'], native)
    assert kresult['exact'] and len(kresult['rows']) == 10
    tresult = read(training / 'result.json')
    bindings_match(tresult['bindings'], native)
    assert tresult['exact'] and len(tresult['rows']) == 8
    assert all(r['exact'] for r in tresult['rows'])
    means = {side: statistics.mean(r['seconds'] for r in kresult['rows'] if r['side'] == side)
             for side in ('baseline', 'candidate')}
    totals = {k: sum(r[k] for r in rows.values()) for k in next(iter(rows.values()))}
    summary = dict(profile_seconds=run['process']['process_seconds'], stages=rows,
                   totals=totals, process_files=len(process_files), kernel_means=means,
                   training_means=tresult['means'], exact_publication=True, tests=31,
                   runtime_integrated=False, full_pipeline_speedup=None)
    if native is not None:
        comparison = read(native / 'comparison.json')
        assert comparison['exact_owned_science_and_artifacts'] and comparison['both_c_arms']
        assert comparison['source_changes'] == ['leo.analysis.localization_v3.hierarchical']
        assert not comparison['added_modules']
        bindings_match(read(native / 'plan.json')['bindings'], native)
        name = 'leo/analysis/localization_v3/hierarchical.py'
        integrated = (Path('src', name).read_bytes() ==
                      (native / 'candidate-src' / name).read_bytes())
        assert integrated and broad_tests is not None
        broad = ET.parse(broad_tests).getroot().findall('testsuite')
        assert all(int(s.attrib[k]) == 0 for s in broad for k in ('errors', 'failures', 'skipped'))
        summary.update(runtime_integrated=True,
                       broad_tests=sum(int(s.attrib['tests']) for s in broad),
                       native_seconds=comparison['observed_process_seconds'],
                       native_exact_science_and_pngs=True)
        dest = target / 'native'
        dest.mkdir(exist_ok=True)
        for filename in ('plan.json', 'comparison.json', 'baseline-sources.json',
                         'candidate-sources.json', 'baseline-process-time.txt',
                         'candidate-process-time.txt', 'baseline-resources-start.json',
                         'baseline-resources-end.json', 'candidate-resources-start.json',
                         'candidate-resources-end.json'):
            shutil.copyfile(native / filename, dest / filename)
        for side in ('baseline', 'candidate'):
            for filename in ('supervisor.json', 'worker.log'):
                shutil.copyfile(native / side / 'attempt' / filename, dest / f'{side}-{filename}')
            shutil.copyfile(native / side / 'isolation.json', dest / f'{side}-isolation.json')
            shutil.copyfile(native / f'{side}-src' / name, dest / f'{side}-hierarchical.py')
        shutil.copyfile(broad_tests, dest / 'tests-broad.xml')
    (target / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    for source, name, files in (
        (profile, 'profile', ['plan.json', 'profile.json', 'parity.json', 'worker.log',
                              'resources-start.json', 'resources-end.json']
                             + [p.name for p in process_files]),
        (kernel, 'kernel', ['result.json', 'original.py', 'candidate.py']),
        (training, 'training', ['plan.json', 'result.json', 'original.py', 'candidate.py']),
    ):
        destination = target / name
        destination.mkdir(exist_ok=True)
        for filename in files:
            shutil.copyfile(source / filename, destination / filename)
    shutil.copyfile(tests, target / 'tests.xml')
    largest = sorted(rows, key=lambda name: rows[name]['seconds'], reverse=True)[:7]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), layout='constrained')
    axes[0].barh(largest, [rows[n]['seconds'] for n in largest], label='All calls', color='#477ea8')
    axes[0].barh(largest, [rows[n]['repeat_seconds'] for n in largest],
                 label='Exact repeated inputs', color='#d8873b')
    axes[0].invert_yaxis()
    axes[0].legend(fontsize=8)
    axes[0].set(title='Likelihood calls across processes',
                xlabel='Accumulated call seconds, not wall time')
    for axis, arm in zip(axes[1:], ('c0', 'fitted_c'), strict=True):
        for side, color in (('baseline', '#477ea8'), ('candidate', '#41956a')):
            selected = [r for r in tresult['rows'] if r['arm'] == arm and r['side'] == side]
            axis.plot([r['pair'] + 1 for r in selected], [r['seconds'] for r in selected],
                      'o-', label=side, color=color)
        axis.set(title=f'DS26-0066 full training: {arm}',
                 xlabel='Alternating pair', ylabel='Elapsed seconds')
        axis.set_xticks([1, 2])
        axis.legend()
    fig.suptitle('Measure repeated work; qualify complete fits before changing factorization')
    fig.savefig(target / 'likelihood.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('profile', 'kernel', 'training', 'tests'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--native', type=Path)
    parser.add_argument('--broad-tests', type=Path)
    main(**vars(parser.parse_args()))
