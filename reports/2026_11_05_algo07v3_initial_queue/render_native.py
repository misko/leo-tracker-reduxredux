"""Verify the qualified native pair and export non-overlapping stage timings."""

import argparse
import ast
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(pair, tests):
    out = Path(__file__).resolve().parent
    baseline, candidate = [read(pair / f'{s}-sources.json') for s in ('baseline', 'candidate')]
    modules = sorted(name.removesuffix('.py').replace('/', '.') for name in baseline)
    comparison = read(pair / 'comparison.json')
    assert comparison['exact_owned_science_and_artifacts'] and comparison['both_c_arms']
    assert sorted(comparison['source_changes']) == modules and len(modules) == 5
    assert not comparison['added_modules']
    for name, sha in candidate.items():
        assert digest(Path('src', name)) == sha
    for path, sha in read(pair / 'plan.json')['bindings'].items():
        assert digest(Path(path)) == sha, path
    # Preserve the measured external prototypes' original source bindings.
    old = {str(Path('src', name).resolve()): pair / 'baseline-src' / name for name in baseline}
    for group in ('component', 'priority'):
        for scan in ('0002', '0066'):
            result = read(out / f'{group}-{scan}/result.json')
            assert result['exact']
            for path, sha in result['bindings'].items():
                assert digest(old.get(path, Path(path))) == sha, path
    suites = ET.parse(tests).getroot().findall('testsuite')
    count = sum(int(s.attrib['tests']) for s in suites)
    assert count >= 1200
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('errors', 'failures', 'skipped'))
    name = 'leo/analysis/localization_v3/initial_search.py'
    funcs = []
    for path in (pair / 'baseline-src' / name, Path('src', name)):
        funcs.append(next(n for n in ast.parse(path.read_bytes()).body
                          if isinstance(n, ast.FunctionDef) and n.name == 'fit_initial_arm'))
    assert ast.dump(funcs[0]) == ast.dump(funcs[1])
    profile = read(out / 'posterior/result.json')
    assert profile['exact'] and all(r['exact'] for r in profile['trials'])
    for path, sha in profile['bindings'].items():
        assert digest(Path(path)) == sha, path
    profiled_seconds = sum(r['seconds'] for r in profile['trials'])
    parts = {name: r['seconds'] for name, r in profile['parts'].items()}
    assert sum(parts.values()) <= profiled_seconds
    parts['remaining likelihood work'] = profiled_seconds - sum(parts.values())
    labels = sorted(parts, key=parts.get, reverse=True)
    fig, ax = plt.subplots(figsize=(10, 5), layout='constrained')
    values = [100 * parts[name] / profiled_seconds for name in labels]
    bars = ax.barh([n.replace('_', ' ') for n in labels], values, color='#427ba0')
    ax.bar_label(bars, fmt='%.1f%%', padding=4)
    ax.invert_yaxis()
    ax.set(xlabel='Percent of three captured likelihood evaluations', xlim=(0, 43),
           title='Current posterior cost: 1,560 observations, 175 nuisance columns\n'
                 '256 precision iterations; exact outputs and unchanged inputs')
    fig.savefig(out / 'posterior.png', dpi=160)
    plt.close(fig)
    dest = out / 'native'
    dest.mkdir(exist_ok=True)
    for path in pair.iterdir():
        if path.is_file() and path.suffix in ('.json', '.txt'):
            shutil.copyfile(path, dest / path.name)
    stages = {}
    for side in ('baseline', 'candidate'):
        for filename in ('supervisor.json', 'worker.log'):
            shutil.copyfile(pair / side / 'attempt' / filename, dest / f'{side}-{filename}')
        shutil.copyfile(pair / side / 'isolation.json', dest / f'{side}-isolation.json')
        for name in baseline:
            target = dest / f'{side}-src' / name
            target.parent.mkdir(exist_ok=True, parents=True)
            shutil.copyfile(pair / f'{side}-src' / name, target)
        stages[side] = {r['stage']: r['seconds'] for line in
                       (pair / side / 'attempt/worker.log').read_text().splitlines()
                       if (r := json.loads(line)).get('event') == 'stage'}
        receipt = read(pair / side / 'attempt/supervisor.json')
        stages[side]['evidence_save'] = receipt['worker']['evidence_save_seconds']
        stages[side]['publication'] = receipt['worker']['publication_seconds']
        stages[side]['other_process_time'] = receipt['process_seconds'] - sum(stages[side].values())
        assert stages[side]['other_process_time'] >= 0
    shutil.copyfile(tests, dest / 'tests.xml')
    total = comparison['observed_process_seconds']
    summary = dict(tests=count, native_seconds=total, stages=stages,
        exact_science_and_eight_pngs=True, production_changed=False,
        runtime_integrated=True, full_ds26_qualified=False, original_algo07_speedup=None)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    names = sorted(stages['candidate'], key=stages['candidate'].get, reverse=True)
    fig, ax = plt.subplots(figsize=(11, 9), layout='constrained')
    for offset, side, color in ((-.18, 'baseline', '#427ba0'), (.18, 'candidate', '#41956a')):
        ax.barh([i+offset for i in range(len(names))], [stages[side][n] for n in names],
                height=.35, color=color, label=side)
    ax.set_yticks(range(len(names)), labels=[n.replace('_', ' ') for n in names])
    ax.invert_yaxis()
    ax.set(xlabel='Elapsed seconds (non-overlapping stages)',
           title='ALGO07v3 / DS26-0002: queue independent initial branch/arm fits\n'
                 'Native GLRT through publication; capture, detector and queue excluded')
    ax.legend()
    fig.savefig(out / 'stages.png', dpi=160)
    plt.close(fig)
    table = ['| Stage | Baseline s | Candidate s | Candidate share |',
             '| --- | ---: | ---: | ---: |']
    for name in names:
        before, after = stages['baseline'][name], stages['candidate'][name]
        table.append(f'| {name} | {before:.3f} | {after:.3f} | '
                     f'{100*after/total["optimized"]:.2f}% |')
    (out / 'stage-table.md').write_text('\n'.join(table)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', type=Path, required=True)
    parser.add_argument('--tests', type=Path, required=True)
    main(**vars(parser.parse_args()))
