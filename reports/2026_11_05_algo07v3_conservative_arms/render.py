"""Verify and publish conservative-stage pairs plus complete-path ABBA timing."""

import argparse
import hashlib
import json
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path

from check_algo07v3_publication import evidence_snapshot
from compare_algo07v3_runs import matched_requests, scientific_values

from leo.storage.localization_v3 import LocalizationV3Store


def read(path):
    return json.loads(path.read_bytes())


def verify(bindings):
    for name, sha in bindings.items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha, name


def main(root):
    out = Path(__file__).resolve().parent
    suites = list(ET.parse(root / 'tests.xml').getroot().iter('testsuite'))
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('failures', 'errors', 'skipped'))
    count = sum(int(s.attrib['tests']) for s in suites)
    component = read(root / 'component-pairs.json')
    assert component['exact'] and len(component['rows']) == 6
    verify(component['bindings'])
    for name in ('tests.xml', 'test-command.json', 'focused-tests.xml', 'component-pairs.json'):
        (out / name).write_bytes((root / name).read_bytes())
    samples, reference, reference_request = [], None, None
    for pair, directory in enumerate((root, root / 'reverse')):
        prefix = '' if pair == 0 else 'reverse-'
        plan, comparison = read(directory / 'plan.json'), read(directory / 'comparison.json')
        assert comparison['exact_owned_science_and_artifacts']
        verify(plan['bindings'])
        verify(comparison['input_bindings'])
        for name in ('plan.json', 'comparison.json', 'baseline-sources.json'):
            (out / (prefix + name)).write_bytes((directory / name).read_bytes())
        for side in plan['sequence']:
            clock = read(directory / side / 'attempt/supervisor.json')
            assert clock['status'] == 'exited' and clock['returncode'] == 0
            assert clock['worker']['status'] == 'complete' and not clock['worker']['resumed']
            assert all(read(directory / side / 'isolation.json')['checks'].values())
            request = read(directory / f'{side}-request.json')
            saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
            if reference is not None:
                matched_requests(reference_request, request)
                scientific_values(reference['evidence'], saved['evidence'])
                assert evidence_snapshot(reference['evidence'], reference['pngs']) == (
                    evidence_snapshot(saved['evidence'], saved['pngs']))
                assert reference['pngs'] == saved['pngs']
            else:
                reference, reference_request = saved, request
            log = [json.loads(line) for line in (directory / side / 'attempt/worker.log')
                   .read_text().splitlines()]
            stages = {r['stage']: r['seconds'] for r in log if r.get('event') == 'stage'}
            text = (directory / f'{side}-process-time.txt').read_text()
            values = dict(line.strip().rsplit(': ', 1)
                          for line in text.splitlines() if ': ' in line)
            assert values['Exit status'] == '0'
            samples.append(dict(pair=pair, side=side, seconds=clock['process_seconds'],
                                stages=stages, user_seconds=float(values['User time (seconds)']),
                                system_seconds=float(values['System time (seconds)']),
                                maximum_rss_kbytes=int(values[
                                    'Maximum resident set size (kbytes)'])))
            for name in (f'{side}-process-time.txt', f'{side}-resources-start.json',
                         f'{side}-resources-end.json'):
                (out / (prefix + name)).write_bytes((directory / name).read_bytes())
            for name, path in {'supervisor.json': 'attempt/supervisor.json',
                               'isolation.json': 'isolation.json'}.items():
                (out / f'{prefix}{side}-{name}').write_bytes((directory / side / path).read_bytes())
    means = {side: {field: statistics.mean(r[field] for r in samples if r['side'] == side)
                    for field in ('seconds', 'user_seconds', 'system_seconds')}
             for side in ('baseline', 'candidate')}
    stage_means = {side: {name: statistics.mean(r['stages'][name] for r in samples
                                               if r['side'] == side)
                          for name in samples[0]['stages']}
                   for side in means}
    component_means = {side: {field: statistics.mean(r[field] for r in component['rows']
                                                    if r['side'] == side)
                              for field in ('seconds', 'self_cpu_seconds', 'children_cpu_seconds')}
                       for side in means}
    summary = dict(exact=True, cross_pair_science_and_pngs_exact=True, samples=samples,
                   means=means, stage_means=stage_means, component_means=component_means,
                   component_tests=count, full_scan='DS26-0002', component_scan='DS26-0066',
                   observed_full_reduction_percent=100 * (1 - means['candidate']['seconds'] /
                                                         means['baseline']['seconds']),
                   component_reduction_percent=100 * (1 - component_means['candidate']['seconds'] /
                                                     component_means['baseline']['seconds']),
                   selected_model=reference['evidence']['presentation']['selected_model'],
                   arms=reference['evidence']['presentation']['arms'],
                   production_modified=False, dataset_wide_qualification=False,
                   matched_full_scans=1, completed_full_runs=len(samples),
                   full_historical_equivalence=False, qualified_speedup=None)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    colors = dict(baseline='#777777', candidate='#3465a4')
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    bars = axes[0].bar(['Baseline 1', 'Candidate 1', 'Candidate 2', 'Baseline 2'],
                       [r['seconds'] for r in samples], color=[colors[r['side']] for r in samples])
    axes[0].bar_label(bars, fmt='%.1f s', padding=3)
    axes[0].set(ylabel='Native GLRT ready → supervisor exit (seconds)',
                title='DS26-0002 · four fresh complete runs',
                ylim=(0, max(r['seconds'] for r in samples) * 1.16))
    names = sorted(stage_means['baseline'], key=stage_means['baseline'].get, reverse=True)[:7][::-1]
    y = np.arange(len(names))
    for i, side in enumerate(means):
        axes[1].barh(y + (i - .5) * .36, [stage_means[side][name] for name in names],
                     height=.36, color=colors[side], label=side)
    axes[1].set(yticks=y, yticklabels=names, xlabel='Mean wall seconds',
                title='Largest stages · both c arms exact')
    axes[1].legend()
    fig.text(.5, .015, 'All science, ownership, eight PNGs and publication exact · '
             'shared-host subset, not population qualification · capture/GLRT/queue excluded',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, 1))
    fig.savefig(out / 'runtime.png', dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(3)
    for i, side in enumerate(means):
        values = [r['seconds'] for r in component['rows'] if r['side'] == side]
        bars = ax.bar(x + (i - .5) * .36, values, width=.36, color=colors[side], label=side)
        ax.bar_label(bars, fmt='%.2f', padding=3)
    ax.set(xticks=x, xticklabels=['Baseline first', 'Candidate first', 'Baseline first'],
           ylabel='Complete conservative-stage seconds',
           title='DS26-0066 · alternating prepared-stage pairs',
           ylim=(0, max(r['seconds'] for r in component['rows']) * 1.3))
    ax.legend()
    fig.text(.5, .015, 'Every complete stage matches the saved serial result · '
             'fresh scan contexts · three CPUs / one BLAS thread', ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, 1))
    fig.savefig(out / 'component.png', dpi=160)
    plt.close(fig)
    print(json.dumps({k: v for k, v in summary.items() if k != 'samples'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    main(parser.parse_args().root)
