"""Validate measured sources, full screens, geometry and native publication."""

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


def main(pair, benchmarks, profiles, geometry, tests, formatted):
    out = Path(__file__).resolve().parent
    name = 'leo/analysis/localization_v3/residual_screen.py'
    old = {str(Path('src', name).resolve()): pair / 'baseline-src' / name,
           str(Path('tools/probe_algo07v3_nomination_points.py').resolve()):
           out / 'measured/probe_algo07v3_nomination_points.py'}

    def check(bindings):
        for path, sha in bindings.items():
            assert digest(old.get(path, Path(path))) == sha, path

    comparison = read(pair / 'comparison.json')
    assert comparison['exact_owned_science_and_artifacts'] and comparison['both_c_arms']
    assert comparison['source_changes'] == ['leo.analysis.localization_v3.residual_screen']
    assert not comparison['added_modules']
    check(read(pair / 'plan.json')['bindings'])
    assert ast.dump(ast.parse(Path('src', name).read_bytes())) == ast.dump(
        ast.parse((pair / 'candidate-src' / name).read_bytes()))
    final = read(formatted / 'comparison.json')
    assert final['exact_owned_science_and_artifacts'] and final['both_c_arms']
    assert final['source_changes'] == ['leo.analysis.localization_v3.residual_screen']
    assert not final['added_modules']
    final_plan = read(formatted / 'plan.json')
    assert final_plan['syntax_tree_identical']
    for path, sha in final_plan['bindings'].items():
        assert digest(Path(path)) == sha, path
    suites = ET.parse(tests).getroot().findall('testsuite')
    count = sum(int(s.attrib['tests']) for s in suites)
    assert count > 770
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('errors', 'failures', 'skipped'))
    benchmark_rows, profile_rows = [], []
    for roots, label, results in ((benchmarks, 'benchmark', benchmark_rows),
                                (profiles, 'profile', profile_rows)):
        assert len(roots) == 2
        for index, root in enumerate(roots):
            r = read(root / 'result.json')
            check(r['bindings'])
            assert r['exact']
            if label == 'benchmark':
                assert len(r['rows']) == 6 and all(x['exact'] for x in r['rows'])
            else:
                assert r['accounting_valid'] and r['unchanged_inputs']
            results.append(r)
            dest = out / f'{label}-{index}'
            dest.mkdir(exist_ok=True)
            for filename in ('result.json', 'plan.json', 'original.py', 'candidate.py'):
                if (root / filename).exists():
                    shutil.copyfile(root / filename, dest / filename)
    proof = read(geometry / 'result.json')
    check(proof['bindings'])
    assert proof['complete'] and proof['full_screen_exact']
    assert len(proof['checks']) == 99 and all(r['exact'] for r in proof['checks'])
    shutil.copyfile(geometry / 'result.json', out / 'geometry.json')
    dest = out / 'native'
    dest.mkdir(exist_ok=True)
    for filename in ('plan.json', 'comparison.json', 'baseline-sources.json',
                     'candidate-sources.json', 'baseline-process-time.txt',
                     'candidate-process-time.txt', 'baseline-resources-start.json',
                     'baseline-resources-end.json', 'candidate-resources-start.json',
                     'candidate-resources-end.json'):
        shutil.copyfile(pair / filename, dest / filename)
    for side in ('baseline', 'candidate'):
        for filename in ('supervisor.json', 'worker.log'):
            shutil.copyfile(pair / side / 'attempt' / filename, dest / f'{side}-{filename}')
        shutil.copyfile(pair / side / 'isolation.json', dest / f'{side}-isolation.json')
        shutil.copyfile(pair / f'{side}-src' / name, dest / f'{side}-screen.py')
    shutil.copyfile(tests, dest / 'tests.xml')
    dest = out / 'formatted'
    dest.mkdir(exist_ok=True)
    for filename in ('plan.json', 'comparison.json', 'process-time.txt'):
        shutil.copyfile(formatted / filename, dest / filename)
    for filename in ('supervisor.json', 'worker.log'):
        shutil.copyfile(formatted / 'run/attempt' / filename, dest / filename)
    shutil.copyfile(formatted / 'run/isolation.json', dest / 'isolation.json')
    shutil.copyfile(Path('src', name), dest / 'residual_screen.py')
    stages = {}
    for side in ('baseline', 'candidate'):
        stages[side] = {r['stage']: r['seconds'] for line in
                        (pair / side / 'attempt/worker.log').read_text().splitlines()
                        if (r := json.loads(line)).get('event') == 'stage'}
    summary = dict(tests=count, native_seconds=comparison['observed_process_seconds'],
                   screen_seconds={k: v['residual_screen'] for k, v in stages.items()},
                   native_stages=stages, complete_science_eight_pngs_exact=True,
                   benchmarks=[dict(means=r['means'], targets=r['targets'])
                               for r in benchmark_rows],
                   profile_parts=[r['parts'] for r in profile_rows],
                   geometry_checks=99, runtime_integrated=True,
                   production_modified=False, full_ds26_qualified=False,
                   formatted_confirmation_seconds=final['observed_process_seconds']['optimized'])
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8), layout='constrained')
    for axis, r, scan in zip(axes[:2], benchmark_rows, ('DS26-0002', 'DS26-0066'), strict=True):
        for side, color in (('baseline', '#477ea8'), ('candidate', '#41956a')):
            rows = [x for x in r['rows'] if x['side'] == side]
            axis.plot([x['pair'] + 1 for x in rows], [x['seconds'] for x in rows],
                      'o-', color=color, label=side)
        axis.set(title=f'{scan}: complete screen', xlabel='Alternating pair', ylabel='Seconds')
        axis.set_xticks([1, 2, 3])
        axis.legend()
    native = comparison['observed_process_seconds']
    values = [native['baseline'], native['optimized']]
    axes[2].bar(['Baseline', 'Candidate'], values, color=['#477ea8', '#41956a'])
    for index, value in enumerate(values):
        axes[2].text(index, value, f'{value:.2f} s', ha='center', va='bottom')
    axes[2].set(title='DS26-0002: full native run\nOne shared-host pair', ylabel='Seconds')
    axes[2].set_ylim(0, max(values) * 1.15)
    fig.suptitle('Project the original nomination points; preserve all finalist evidence')
    fig.savefig(out / 'runtime.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair', 'geometry', 'tests', 'formatted'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('benchmarks', 'profiles'):
        parser.add_argument('--' + name, type=Path, nargs=2, required=True)
    main(**vars(parser.parse_args()))
