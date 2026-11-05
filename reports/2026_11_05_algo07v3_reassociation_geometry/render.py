"""Publish the fresh DS26-0066 reassociation geometry qualification receipts."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def main(root):
    out = Path(__file__).resolve().parent
    comparison = read(root / 'comparison.json')
    assert comparison['exact_owned_science_and_artifacts']
    for bindings in (read(root / 'plan.json')['bindings'], comparison['input_bindings']):
        for name, digest in bindings.items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    suites = list(ET.parse(root / 'tests.xml').getroot().iter('testsuite'))
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('failures', 'errors', 'skipped'))
    count = sum(int(s.attrib['tests']) for s in suites)
    times, stages, resources = {}, {}, {}
    for name in ('plan.json', 'comparison.json', 'tests.xml', 'test-command.json',
                 'baseline-sources.json'):
        (out / name).write_bytes((root / name).read_bytes())
    for side in ('baseline', 'candidate'):
        clock = read(root / side / 'attempt/supervisor.json')
        assert clock['status'] == 'exited' and clock['returncode'] == 0
        assert clock['worker']['status'] == 'complete' and not clock['worker']['resumed']
        assert all(read(root / side / 'isolation.json')['checks'].values())
        times[side] = clock['process_seconds']
        rows = [json.loads(line) for line in (root / side / 'attempt/worker.log')
                .read_text().splitlines()]
        stages[side] = {r['stage']: r['seconds'] for r in rows if r.get('event') == 'stage'}
        text = (root / f'{side}-process-time.txt').read_text()
        values = dict(line.strip().rsplit(': ', 1) for line in text.splitlines() if ': ' in line)
        assert values['Exit status'] == '0'
        resources[side] = dict(user_seconds=float(values['User time (seconds)']),
                               system_seconds=float(values['System time (seconds)']),
                               maximum_rss_kbytes=int(values['Maximum resident set size (kbytes)']))
        for name in (f'{side}-process-time.txt', f'{side}-resources-start.json',
                     f'{side}-resources-end.json'):
            (out / name).write_bytes((root / name).read_bytes())
        for name, path in {'supervisor.json': 'attempt/supervisor.json',
                           'isolation.json': 'isolation.json'}.items():
            (out / f'{side}-{name}').write_bytes((root / side / path).read_bytes())
    from leo.storage.localization_v3 import LocalizationV3Store
    request = read(root / 'candidate-request.json')
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    packet = saved['evidence']['presentation']
    summary = dict(
        exact=True, scan='DS26-0066', seconds=times, stages=stages, resources=resources,
        observed_seconds_saved=times['baseline'] - times['candidate'],
        observed_latency_ratio=times['baseline'] / times['candidate'],
        qualified_speedup=None, component_tests=count,
        selected_model=packet['selected_model'], arms=packet['arms'],
        production_modified=False, dataset_wide_qualification=False,
    )
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    colors = ['#777777', '#3465a4']
    bars = axes[0].bar(['Baseline', 'Shared phase interpolation'], list(times.values()),
                       color=colors)
    axes[0].bar_label(bars, fmt='%.1f s', padding=3)
    axes[0].set(ylabel='Native GLRT ready → supervisor exit (seconds)',
                title='DS26-0066 · fresh complete pipeline pair',
                ylim=(0, max(times.values()) * 1.16))
    labels = sorted(stages['baseline'], key=stages['baseline'].get, reverse=True)[:7][::-1]
    if 'admission' not in labels:
        labels[0] = 'admission'
    y = np.arange(len(labels))
    for i, side in enumerate(times):
        axes[1].barh(y + (i - .5) * .36, [stages[side][k] for k in labels],
                     height=.36, color=colors[i], label=side)
    axes[1].set(yticks=y, yticklabels=labels, xlabel='Observed wall seconds',
                title='Stages · reassociation screen is inside admission')
    axes[1].legend()
    fig.text(.5, .02, 'Exact both-arm science, ownership, eight PNGs and publication · '
             'single shared-host pair, not a qualified speedup · capture/GLRT/queue excluded',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, 1))
    fig.savefig(out / 'runtime.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    main(parser.parse_args().root)
