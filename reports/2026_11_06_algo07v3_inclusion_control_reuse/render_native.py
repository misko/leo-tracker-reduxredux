"""Verify and retain complete native scan clocks, isolation and exactness receipts."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def read(path):
    return json.loads(path.read_bytes())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native', type=Path, action='append', required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parent
    cases = []
    for index, source in enumerate(args.native):
        out = root / f'native-{index}'
        out.mkdir(exist_ok=True)
        comparison, plan = read(source / 'comparison.json'), read(source / 'plan.json')
        assert comparison['exact_owned_science_and_artifacts']
        for original, sha in plan['bindings'].items():
            path = Path(original)
            choices = [path]
            if '/src/' in original:
                relative = original.split('/src/', 1)[1]
                choices += [root / side / relative for side in ('baseline-src', 'candidate-src')]
            assert any(q.exists() and hashlib.sha256(q.read_bytes()).hexdigest() == sha
                       for q in choices), path
        clocks = {}
        for side in ('baseline', 'candidate'):
            clock = read(source / side / 'attempt/supervisor.json')
            assert clock['returncode'] == 0 and not clock['worker']['resumed']
            assert all(read(source / side / 'isolation.json')['checks'].values())
            events = [json.loads(line) for line in
                      (source / side / 'attempt/worker.log').read_text().splitlines()
                      if line.startswith('{')]
            stages = {r['stage']: r['seconds'] for r in events if r.get('event') == 'stage'}
            stages['evidence_save'] = clock['worker']['evidence_save_seconds']
            stages['publication'] = clock['worker']['publication_seconds']
            stages['other'] = clock['process_seconds'] - sum(stages.values())
            assert stages['other'] >= 0
            resources = dict(line.strip().rsplit(': ', 1) for line in
                             (source / f'{side}-process-time.txt').read_text().splitlines()
                             if ': ' in line)
            assert resources['Exit status'] == '0'
            clocks[side] = dict(seconds=clock['process_seconds'], stages=stages,
                               cpu_seconds=float(resources['User time (seconds)']) +
                               float(resources['System time (seconds)']),
                               max_rss_kib=int(resources['Maximum resident set size (kbytes)']),
                               major_faults=int(resources['Major (requiring I/O) page faults']))
            for name, path in [('supervisor.json', source / side / 'attempt/supervisor.json'),
                               ('isolation.json', source / side / 'isolation.json'),
                               ('worker.log', source / side / 'attempt/worker.log'),
                               ('process-time.txt', source / f'{side}-process-time.txt')]:
                shutil.copyfile(path, out / f'{side}-{name}')
        for name in ('comparison.json', 'plan.json', 'baseline-sources.json',
                     'candidate-sources.json'):
            shutil.copyfile(source / name, out / name)
        cases.append(dict(name=source.name, clocks=clocks, exact=True))
        shutil.copytree(source / 'candidate-src', root / 'candidate-src', dirs_exist_ok=True)
    (root / 'native-summary.json').write_text(json.dumps(cases, indent=2) + '\n')
    fig, axes = plt.subplots(1, len(cases), figsize=(7 * len(cases), 6), squeeze=False,
                             layout='constrained')
    for ax, case in zip(axes[0], cases, strict=True):
        clocks = case['clocks']
        stages = sorted(clocks['baseline']['stages'],
                        key=clocks['baseline']['stages'].get, reverse=True)[:10]
        for j, side in enumerate(('baseline', 'candidate')):
            ax.barh([i + (j-.5)*.35 for i in range(len(stages))],
                    [clocks[side]['stages'][s] for s in stages], height=.35,
                    label=f"{side}: {clocks[side]['seconds']:.1f} s total")
        ax.set_yticks(range(len(stages)), [s.replace('_', ' ') for s in stages])
        ax.invert_yaxis()
        ax.set_title(case['name'].replace('algo07v3-inclusion-control-native-', ''))
        ax.set_xlabel('Stage wall seconds')
        ax.legend()
        ax.grid(axis='x', alpha=.2)
    fig.savefig(root / 'native-stages.png', dpi=150)
    plt.close(fig)
    rows = []
    for case in cases:
        a, b = (case['clocks'][s] for s in ('baseline', 'candidate'))
        rows.append(f"| {case['name']} | {a['seconds']:.3f} | {b['seconds']:.3f} | "
                    f"{100*(1-b['seconds']/a['seconds']):+.2f}% | "
                    f"{a['stages']['predictive']:.3f} | {b['stages']['predictive']:.3f} |")
    (root / 'native-measurements.md').write_text('''# Complete native comparisons

| Scan/pair | Baseline s | Candidate s | Reduction | Recovery baseline s | Recovery candidate s |
| --- | ---: | ---: | ---: | ---: | ---: |
''' + '\n'.join(rows) + '''

All scientific audits, both c arms, ownership, grid/path and eight PNGs are exact.
Fresh isolated runs use CPUs 0–2, one BLAS thread and unchanged 1,200-second
outer bounds. Capture, detector extraction and queue waiting are excluded.
Unchanged stages and shared-host timing variation prevent attributing every
whole-process difference to this control-reuse change. CPU/RSS and complete stages
are retained in native-summary.json; RSS is a per-process maximum, not aggregate.

![Complete native stages](native-stages.png)
''')


if __name__ == '__main__':
    main()
