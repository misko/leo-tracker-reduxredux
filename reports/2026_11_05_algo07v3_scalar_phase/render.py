"""Verify exact scalar-phase evidence and render component/native timings."""

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


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(pair, tests, proof):
    out = Path(__file__).resolve().parent
    module = 'leo/analysis/research/orbit_phase_geometry.py'
    original = str(Path('src', module).resolve())

    def check(bindings, legacy=False):
        for path, digest in bindings.items():
            target = pair / 'baseline-src' / module if legacy and path == original else Path(path)
            assert sha(target) == digest, path

    comparison = read(pair / 'comparison.json')
    assert comparison['exact_owned_science_and_artifacts'] and comparison['both_c_arms']
    assert comparison['source_changes'] == ['leo.analysis.research.orbit_phase_geometry']
    assert not comparison['added_modules']
    assert sha(Path('src', module)) == read(pair / 'candidate-sources.json')[module]
    check(read(pair / 'plan.json')['bindings'])
    suites = ET.parse(tests).getroot().findall('testsuite')
    count = sum(int(s.attrib['tests']) for s in suites)
    assert count == 975
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('errors', 'failures', 'skipped'))
    profile = Path('/srv/bulk/leo-dev/algo07v3-screen-postbank-0002-20261106/result.json')
    profiled = read(profile)
    check(profiled['bindings'], legacy=True)
    assert profiled['exact'] and profiled['accounting_valid'] and profiled['unchanged_inputs']
    shutil.copyfile(profile, out / 'profile.json')
    results = []
    for scan in ('0002', '0066'):
        root = Path(f'/srv/bulk/leo-dev/algo07v3-scalar-phase-{scan}-20261106')
        result = read(root / 'result.json')
        check(result['bindings'], legacy=True)
        assert result['exact'] and len(result['rows']) == 6
        assert all(r['exact'] and r['unchanged_inputs'] for r in result['rows'])
        dest = out / f'component-{scan}'
        dest.mkdir(exist_ok=True)
        for path in root.iterdir():
            if path.suffix in ('.json', '.py'):
                shutil.copyfile(path, dest / path.name)
        results.append(result)
    tree = ast.parse(Path('src', module).read_bytes())
    function = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == 'phase_shifted_states')
    expected = ast.parse((out / 'component-0066/candidate.py').read_bytes()).body[0]
    assert ast.dump(function) == ast.dump(expected)
    verified = read(proof / 'result.json')
    check(verified['bindings'])
    assert verified['complete'] and verified['full_screen_exact'] and verified['unchanged_inputs']
    assert len(verified['checks']) == 99 and all(r['exact'] for r in verified['checks'])
    shutil.copyfile(proof / 'result.json', out / 'states-proof.json')
    dest = out / 'native'
    dest.mkdir(exist_ok=True)
    for path in pair.iterdir():
        if path.is_file() and path.suffix in ('.json', '.txt'):
            shutil.copyfile(path, dest / path.name)
    stages = {}
    for side in ('baseline', 'candidate'):
        for name in ('supervisor.json', 'worker.log'):
            shutil.copyfile(pair / side / 'attempt' / name, dest / f'{side}-{name}')
        shutil.copyfile(pair / side / 'isolation.json', dest / f'{side}-isolation.json')
        shutil.copyfile(pair / f'{side}-src' / module, dest / f'{side}-phase.py')
        stages[side] = {r['stage']: r['seconds'] for line in
                       (pair / side / 'attempt/worker.log').read_text().splitlines()
                       if (r := json.loads(line)).get('event') == 'stage'}
    shutil.copyfile(tests, dest / 'tests.xml')
    summary = dict(tests=count, native_seconds=comparison['observed_process_seconds'],
                   stages=stages, component_means=[r['means'] for r in results],
                   profile_parts=profiled['parts'], exact_real_states=99,
                   exact_science_and_eight_pngs=True, production_changed=False,
                   runtime_integrated=True, full_ds26_qualified=False,
                   original_algo07_speedup=None)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8), layout='constrained')
    for axis, result, scan in zip(axes[:2], results, ('0002', '0066'), strict=True):
        for side, color in (('baseline', '#427ba0'), ('candidate', '#41956a')):
            rows = [r for r in result['rows'] if r['side'] == side]
            axis.plot([r['pair'] + 1 for r in rows], [r['seconds'] for r in rows],
                      'o-', color=color, label=side)
        axis.set(title=f'DS26-{scan}: complete screen', xlabel='Alternating pair', ylabel='Seconds')
        axis.set_xticks([1, 2, 3])
        axis.legend()
    full = comparison['observed_process_seconds']
    values = [full['baseline'], full['optimized']]
    axes[2].bar(['Baseline', 'Candidate'], values, color=['#427ba0', '#41956a'])
    for x, value in enumerate(values):
        axes[2].text(x, value, f'{value:.3f} s', ha='center', va='bottom')
    axes[2].set(title='DS26-0002: full native run\nOne shared-host pair', ylabel='Seconds',
                ylim=(0, max(values)*1.15))
    fig.suptitle('Share scalar-phase indices; retain per-satellite arithmetic and all hypotheses')
    fig.savefig(out / 'runtime.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair', 'tests', 'proof'):
        parser.add_argument('--' + name, type=Path, required=True)
    main(**vars(parser.parse_args()))
