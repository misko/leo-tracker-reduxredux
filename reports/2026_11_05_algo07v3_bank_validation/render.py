"""Verify component trials, final sources, tests and two-module native parity."""

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


def main(pair, tests, reverse):
    out = Path(__file__).resolve().parent
    modules = read(pair / 'baseline-sources.json')
    old = {str(Path('src', name).resolve()): pair / 'baseline-src' / name for name in modules}
    probe = str(Path('tools/probe_algo07v3_bank_validation.py').resolve())
    comparison = read(pair / 'comparison.json')
    assert comparison['exact_owned_science_and_artifacts'] and comparison['both_c_arms']
    assert set(comparison['source_changes']) == {
        n.removesuffix('.py').replace('/', '.') for n in modules}
    assert not comparison['added_modules']
    for name, digest in read(pair / 'candidate-sources.json').items():
        assert sha(Path('src', name)) == digest
    for path, digest in read(pair / 'plan.json')['bindings'].items():
        assert sha(Path(path)) == digest, path
    repeated = read(reverse / 'comparison.json')
    assert repeated['exact_owned_science_and_artifacts'] and repeated['both_c_arms']
    assert repeated['source_changes'] == comparison['source_changes']
    assert not repeated['added_modules']
    for path, digest in read(reverse / 'plan.json')['bindings'].items():
        assert sha(Path(path)) == digest, path
    cross = read(reverse / 'cross-pair.json')
    assert cross['verifier_sha256'] == sha(out / 'verify_repeats.py')
    for side in ('baseline', 'candidate'):
        assert cross[side]['exact_owned_science_and_artifacts'] and cross[side]['both_c_arms']
        assert not cross[side]['source_changes'] and not cross[side]['added_modules']
    suites = ET.parse(tests).getroot().findall('testsuite')
    count = sum(int(s.attrib['tests']) for s in suites)
    assert count >= 840
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('errors', 'failures', 'skipped'))
    results = {}
    for version in ('array', 'immutable'):
        marker = '' if version == 'array' else '-immutable'
        archived = out / 'measured' / f'{version}_snapshot_probe.py'
        for scan in ('0002', '0066'):
            root = Path(f'/srv/bulk/leo-dev/algo07v3-bank-validation{marker}-{scan}-20261106')
            result = read(root / 'result.json')
            for path, digest in result['bindings'].items():
                actual = archived if path == probe else old.get(path, Path(path))
                assert sha(actual) == digest, path
            assert result['exact'] and len(result['rows']) == 6
            assert all(r['exact'] and r['unchanged_inputs'] for r in result['rows'])
            dest = out / f'{version}-{scan}'
            dest.mkdir(exist_ok=True)
            for path in root.iterdir():
                if path.suffix in ('.json', '.py'):
                    shutil.copyfile(path, dest / path.name)
            results[version, scan] = result
    for module, function, measured in (
        ('leo/analysis/localization_v3/residual_screen.py', 'screen_candidates', 'screen'),
        ('leo/analysis/research/orbit_phase_geometry.py', 'phase_shifted_states', 'phase_states'),
    ):
        tree = ast.parse(Path('src', module).read_bytes())
        actual = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
        expected = ast.parse((out / 'immutable-0066' / f'candidate-{measured}.py').read_bytes())
        assert ast.dump(actual) == ast.dump(expected.body[0])
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
        for module in modules:
            shutil.copyfile(pair / f'{side}-src' / module,
                            dest / f'{side}-{Path(module).name}')
        stages[side] = {r['stage']: r['seconds'] for line in
                       (pair / side / 'attempt/worker.log').read_text().splitlines()
                       if (r := json.loads(line)).get('event') == 'stage'}
    shutil.copyfile(tests, dest / 'tests.xml')
    dest = out / 'native-reverse'
    dest.mkdir(exist_ok=True)
    for path in reverse.iterdir():
        if path.is_file() and path.suffix in ('.json', '.txt'):
            shutil.copyfile(path, dest / path.name)
    reverse_stages = {}
    for side in ('baseline', 'candidate'):
        for name in ('supervisor.json', 'worker.log'):
            shutil.copyfile(reverse / side / 'attempt' / name, dest / f'{side}-{name}')
        shutil.copyfile(reverse / side / 'isolation.json', dest / f'{side}-isolation.json')
        for module in modules:
            assert sha(reverse / f'{side}-src' / module) == sha(pair / f'{side}-src' / module)
        reverse_stages[side] = {r['stage']: r['seconds'] for line in
                               (reverse / side / 'attempt/worker.log').read_text().splitlines()
                               if (r := json.loads(line)).get('event') == 'stage'}
    for filename in ('algo07v3-bank-validation-tests-20261106.xml',
                     'algo07v3-bank-validation-metadata-test-20261106.xml',
                     'algo07v3-bank-validation-immutable-tests-20261106.xml'):
        raw = Path('/srv/bulk/leo-dev') / filename
        # Preserve pytest's literal trailing spaces inside JSON string data.
        (out / (filename + '.json')).write_text(json.dumps(dict(
            original_path=str(raw), sha256=sha(raw), text=raw.read_text()), indent=2)+'\n')
    summary = dict(tests=count, native_seconds=comparison['observed_process_seconds'],
                   native_stages=stages, exact_science_and_eight_pngs=True,
                   reverse_native_seconds=repeated['observed_process_seconds'],
                   reverse_native_stages=reverse_stages, cross_pair_exact=True,
                   final_benchmarks={s: results['immutable', s]['means'] for s in ('0002', '0066')},
                   runtime_integrated=True, production_changed=False,
                   full_ds26_qualified=False, original_algo07_speedup=None)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), layout='constrained')
    for axis, scan in zip(axes[0], ('0002', '0066'), strict=True):
        r = results['immutable', scan]
        for side, color in (('baseline', '#427ba0'), ('candidate', '#41956a')):
            rows = [v for v in r['rows'] if v['side'] == side]
            axis.plot([v['pair'] + 1 for v in rows], [v['seconds'] for v in rows],
                      'o-', color=color, label=side)
        axis.set(title=f'DS26-{scan}: complete screen', xlabel='Alternating pair', ylabel='Seconds')
        axis.set_xticks([1, 2, 3])
        axis.legend()
    for side, color in (('baseline', '#427ba0'), ('candidate', '#41956a')):
        values = [r[side]['residual_screen'] for r in (stages, reverse_stages)]
        key = 'baseline' if side == 'baseline' else 'optimized'
        full = [r['observed_process_seconds'][key] for r in (comparison, repeated)]
        for axis, numbers in zip(axes[1], (values, full), strict=True):
            axis.plot([1, 2], numbers, 'o-', color=color, label=side)
    for axis, title in zip(axes[1], ('Native residual-screen stage', 'Complete native process'),
                           strict=True):
        axis.set(title=f'DS26-0002: {title}', ylabel='Seconds')
        axis.set_xticks([1, 2], ['Candidate first', 'Baseline first'])
        axis.legend()
    fig.suptitle('Validate an immutable orbit bank once; retain all scientific calculations')
    fig.savefig(out / 'runtime.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', type=Path, required=True)
    parser.add_argument('--tests', type=Path, required=True)
    parser.add_argument('--reverse', type=Path, required=True)
    main(**vars(parser.parse_args()))
