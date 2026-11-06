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


def verify_bindings(bindings, root):
    for original, sha in bindings.items():
        path = Path(original)
        choices = [path]
        if '/src/' in original:
            relative = original.split('/src/', 1)[1]
            choices += [root/side/relative for side in ('baseline-src','candidate-src')]
        if path.name == 'probe_algo07v3_fixed_priors.py':
            choices += [root/'measured-kernel-probe.py',root/'measured-training-probe.py']
        if path.name == 'profile_empty_updates.py':
            choices += [root/'measured-empty-profile.py']
        assert any(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==sha
                   for p in choices), original


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
        bindings = read(source/'complete-source-bindings.json')
        bindings.update(plan['bindings'])
        assert read(source/'complete-source-check.json')['unchanged']
        verify_bindings(bindings,root)
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
                     'candidate-sources.json', 'complete-source-bindings.json',
                     'complete-source-check.json', 'baseline-request.json',
                     'candidate-request.json', 'baseline-resources-start.json',
                     'baseline-resources-end.json', 'candidate-resources-start.json',
                     'candidate-resources-end.json'):
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
        ax.set_title('DS26-'+case['name'].split('-')[-2])
        ax.set_xlabel('Stage wall seconds')
        ax.legend()
        ax.grid(axis='x', alpha=.2)
    fig.suptitle('Fixed-prior shortcut: exact results, not adopted\n'
                 'Shared-host native timings regress on both cases')
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
whole-process difference to this fixed-prior shortcut. CPU/RSS and complete stages
are retained in native-summary.json; RSS is a per-process maximum, not aggregate.

![Complete native stages](native-stages.png)
''')
    captured = {}
    for label in ('initial', 'recovery'):
        result = read(root/label/'result.json')
        assert result['exact'] and all(r['exact'] for r in result['rows'])
        verify_bindings(result['bindings'],root)
        captured[label] = {side:sum(r['seconds'] for r in result['rows'] if r['side']==side)/6
                           for side in ('baseline','candidate')}
    training = read(root/'training/result.json')
    assert training['exact'] and all(r['exact'] for r in training['rows'])
    verify_bindings(training['bindings'],root)
    attribution = read(root/'empty-update-profile.json')
    assert all(case['exact'] for case in attribution['cases'])
    verify_bindings(attribution['bindings'],root)
    fitted = {arm:{r['side']:r['seconds'] for r in training['rows'] if r['arm']==arm}
              for arm in ('c0','fitted_c')}
    fig, axes = plt.subplots(1,2,figsize=(10,4),layout='constrained')
    for ax, table, ylabel in ((axes[0],captured,'Captured likelihood seconds'),
                              (axes[1],fitted,'Complete training-fit seconds')):
        for j,side in enumerate(('baseline','candidate')):
            bars=ax.bar([i+(j-.5)*.35 for i in range(len(table))],
                        [row[side] for row in table.values()],width=.35,label=side)
            ax.bar_label(bars,fmt='%.3f',padding=3)
        ax.set_xticks(range(len(table)),list(table))
        ax.set(ylabel=ylabel,ylim=(0,ax.get_ylim()[1]*1.15))
        ax.grid(axis='y',alpha=.2)
        ax.legend(loc='upper center',ncol=2)
    fig.suptitle('Fixed coefficient-prior shortcut: complete outputs unchanged\n'
                 'Six alternating captured-call pairs; one full-fit pair per arm')
    fig.savefig(root/'component.png',dpi=150)
    plt.close(fig)


if __name__ == '__main__':
    main()
