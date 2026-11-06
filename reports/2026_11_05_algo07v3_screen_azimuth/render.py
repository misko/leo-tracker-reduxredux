"""Verify exact screen-projection evidence and render component/native timings."""

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
    module = 'leo/analysis/localization_v3/screen_geometry.py'
    original = str(Path('src', module).resolve())

    def check(bindings, legacy=False):
        for path, digest in bindings.items():
            target = pair / 'baseline-src' / module if legacy and path == original else Path(path)
            assert sha(target) == digest, path

    comparison = read(pair / 'comparison.json')
    assert comparison['exact_owned_science_and_artifacts'] and comparison['both_c_arms']
    assert comparison['source_changes'] == ['leo.analysis.localization_v3.screen_geometry']
    assert not comparison['added_modules']
    assert sha(Path('src', module)) == read(pair / 'candidate-sources.json')[module]
    check(read(pair / 'plan.json')['bindings'])
    suites = ET.parse(tests).getroot().findall('testsuite')
    count = sum(int(s.attrib['tests']) for s in suites)
    assert count == 1162
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('errors', 'failures', 'skipped'))
    profile = Path('/srv/bulk/leo-dev/algo07v3-screen-postendpoint-0002-20261106/result.json')
    profiled = read(profile)
    check(profiled['bindings'], legacy=True)
    assert profiled['exact'] and profiled['accounting_valid'] and profiled['unchanged_inputs']
    shutil.copyfile(profile, out / 'profile.json')
    after_path = Path('/srv/bulk/leo-dev/algo07v3-screen-postazimuth-0066-20261106/result.json')
    after_profile = read(after_path)
    check(after_profile['bindings'])
    assert (after_profile['exact'] and after_profile['accounting_valid']
            and after_profile['unchanged_inputs'])
    shutil.copyfile(after_path, out / 'profile-after.json')
    results = []
    for scan in ('0002', '0066'):
        root = Path(f'/srv/bulk/leo-dev/algo07v3-azimuth-{scan}-20261106')
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
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    expected = ast.parse((out / 'component-0066/candidate.py').read_bytes()).body
    assert [ast.dump(n) for n in functions] == [ast.dump(n) for n in expected]
    history = read(pair / 'history-parity.json')
    assert history['exact_owned_science_and_artifacts'] and history['both_c_arms']
    assert not history['timing_comparison'] and len(history['source_changes']) == 10
    verified = read(proof / 'result.json')
    check(verified['bindings'])
    assert verified['complete'] and verified['full_screen_exact'] and verified['unchanged_inputs']
    assert len(verified['checks']) == 99 and all(r['exact'] for r in verified['checks'])
    shutil.copyfile(proof / 'result.json', out / 'projections-proof.json')
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
        shutil.copyfile(pair / f'{side}-src' / module, dest / f'{side}-screen.py')
        stages[side] = {r['stage']: r['seconds'] for line in
                       (pair / side / 'attempt/worker.log').read_text().splitlines()
                       if (r := json.loads(line)).get('event') == 'stage'}
        receipt = read(pair / side / 'attempt/supervisor.json')
        stages[side]['evidence_save'] = receipt['worker']['evidence_save_seconds']
        stages[side]['publication'] = receipt['worker']['publication_seconds']
        stages[side]['other_process_time'] = receipt['process_seconds'] - sum(stages[side].values())
        assert stages[side]['other_process_time'] >= 0
    shutil.copyfile(tests, dest / 'tests.xml')
    failed_tests = {}
    for name in ('prototype-tests', 'prototype-tests-fixed'):
        path = Path(f'/srv/bulk/leo-dev/algo07v3-azimuth-{name}-20261106.xml')
        failed_tests[name] = dict(sha256=sha(path), xml=path.read_text())
    (dest / 'initial-test-errors.json').write_text(json.dumps(failed_tests, indent=2)+'\n')
    summary = dict(tests=count, native_seconds=comparison['observed_process_seconds'],
                   stages=stages, component_means=[r['means'] for r in results],
                   profile_parts=profiled['parts'], profile_after_parts=after_profile['parts'],
                   exact_real_projections=99,
                   exact_science_and_eight_pngs=True, production_changed=False,
                   runtime_integrated=True, full_ds26_qualified=False,
                   original_algo07_speedup=None, earlier_ds26_0066_exact=True)
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
    axes[2].set(title='DS26-0066: full native run\nOne shared-host pair', ylabel='Seconds',
                ylim=(0, max(values)*1.15))
    fig.suptitle('Omit discarded azimuth; retain elevation, Doppler and all hypotheses')
    fig.savefig(out / 'runtime.png', dpi=160)
    plt.close(fig)
    names = sorted(stages['candidate'], key=stages['candidate'].get, reverse=True)
    fig, ax = plt.subplots(figsize=(11, 9), layout='constrained')
    for offset, side, color in ((-.18, 'baseline', '#427ba0'), (.18, 'candidate', '#41956a')):
        values = [stages[side][name] for name in names]
        ax.barh([i + offset for i in range(len(names))], values, height=.35,
                color=color, label=side)
    ax.set_yticks(range(len(names)), labels=[n.replace('_', ' ') for n in names])
    ax.invert_yaxis()
    ax.set(xlabel='Elapsed seconds (non-overlapping stages)',
           title='ALGO07v3 / DS26-0066: native GLRT through publication\n'
                 'One sequential shared-host pair; capture, detector and queue excluded')
    ax.legend()
    fig.savefig(out / 'stages.png', dpi=160)
    plt.close(fig)
    table = ['| Stage | Baseline s | Candidate s | Candidate share |',
             '| --- | ---: | ---: | ---: |']
    for name in names:
        before, after = stages['baseline'][name], stages['candidate'][name]
        table.append(f'| {name} | {before:.3f} | {after:.3f} | '
                     f'{100 * after / full["optimized"]:.2f}% |')
    (out / 'stage-table.md').write_text('\n'.join(table) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair', 'tests', 'proof'):
        parser.add_argument('--' + name, type=Path, required=True)
    main(**vars(parser.parse_args()))
