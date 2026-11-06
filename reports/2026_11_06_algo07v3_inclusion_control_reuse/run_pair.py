"""Fresh complete native comparison of scoped inclusion-control reuse."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--request', type=Path, required=True)
    p.add_argument('--candidate-first', action='store_true')
    args = p.parse_args()
    root = args.root.resolve()
    root.mkdir(exist_ok=False)
    report = Path(__file__).resolve().parent
    baseline = json.loads((report / 'baseline-sources.json').read_bytes())
    bindings = {}
    for side in ('baseline', 'candidate'):
        hashes = {}
        for name in baseline:
            source = report / 'baseline-src' / name if side == 'baseline' else Path('src') / name
            if side == 'baseline' and digest(source) != baseline[name]:
                raise ValueError('Baseline source changed')
            target = root / f'{side}-src' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            hashes[name] = digest(target)
            bindings[str(target)] = hashes[name]
            bindings[str(source.resolve())] = digest(source)
        if side == 'candidate':
            name = 'leo/analysis/localization_v3/inclusion_controls.py'
            source = Path('src') / name
            target = root / 'candidate-src' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            hashes[name] = digest(target)
            bindings[str(source.resolve())] = digest(source)
            bindings[str(target)] = digest(target)
        write(root / f'{side}-sources.json', hashes)
    request = json.loads(args.request.read_bytes())
    bundle = Path(request['native_input']['path']).parent
    runner = report / 'run_baseline.sh'
    qualifier = Path('tools/qualify_algo07v3_cli.sh').resolve()
    comparator = Path('tools/compare_algo07v3_runs.py').resolve()
    for path in (Path(__file__).resolve(), runner, qualifier, comparator,
                 bundle / 'input-bindings.json'):
        bindings[str(path)] = digest(path)
    commands = {}
    for side in ('baseline', 'candidate'):
        target = root / f'{side}-request.json'
        write(target, dict(request, output_root=str(root / f'{side}-publication')))
        bindings[str(target)] = digest(target)
        (root / side).mkdir()
        commands[side] = ['/usr/bin/time', '-v', '-o', str(root / f'{side}-process-time.txt'),
                          'sh', str(runner), str(root / f'{side}-src'), str(bundle),
                          str(root / side), sys.executable, str(target), '1200', '0,1,2']
    sequence = ['candidate', 'baseline'] if args.candidate_first else ['baseline', 'candidate']
    write(root / 'plan.json', dict(commands=commands, sequence=sequence, bindings=bindings,
                                  cpus=[0, 1, 2], blas_threads=1, timeout_seconds=1200,
                                  production_modified=False))
    for side in sequence:
        write(root / f'{side}-resources-start.json', dict(
            load=os.getloadavg(), cpu_pressure=Path('/proc/pressure/cpu').read_text()))
        print(f'Starting {side}', flush=True)
        with (root / f'{side}.log').open('xb') as log:
            subprocess.run(commands[side], stdout=log, stderr=subprocess.STDOUT, check=True)
        write(root / f'{side}-resources-end.json', dict(
            load=os.getloadavg(), cpu_pressure=Path('/proc/pressure/cpu').read_text()))
        print(f'Completed {side}', flush=True)
    if not all(digest(path) == sha for path, sha in bindings.items()):
        raise ValueError('Bound source/input changed during pair')
    command = [sys.executable, '-B', str(comparator)]
    for side in commands:
        command += [f'--{side}-request', str(root / f'{side}-request.json'),
                    f'--{side}-timing', str(root / side / 'attempt/supervisor.json')]
    for name in baseline:
        command += ['--changed-module', name.removesuffix('.py').replace('/', '.')]
    command += ['--added-module', 'leo.analysis.localization_v3.inclusion_controls',
                '--output', str(root / 'comparison.json')]
    with (root / 'comparison.log').open('xb') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    print('Exact complete native comparison saved', flush=True)


if __name__ == '__main__':
    main()
