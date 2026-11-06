"""Fresh scalar-phase comparison with exact owned publication."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--candidate-first', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    baseline = read(root / 'baseline-sources.json')
    candidate = read(root / 'candidate-sources.json')
    assert set(candidate) == set(baseline)
    bindings = {}
    helper = Path('src/leo/analysis/localization_v3/screen_geometry.py').resolve()
    bindings[str(helper)] = digest(helper)
    for name, sha in baseline.items():
        source = root / 'baseline-src' / name
        assert digest(source) == sha, name
        bindings[str(source)] = sha
        bindings[str(Path('src', name).resolve())] = digest(Path('src', name))
        target = root / 'candidate-src' / name
        assert digest(target) == candidate[name], name
        bindings[str(target)] = candidate[name]
    request = read(args.request)
    bundle = Path(request['native_input']['path']).parent
    comparator = Path('tools/compare_algo07v3_runs.py').resolve()
    runner = Path(__file__).with_name('run_baseline.sh').resolve()
    qualifier = Path('tools/qualify_algo07v3_cli.sh').resolve()
    for path in (Path(__file__).resolve(), runner, qualifier, comparator,
                 bundle / 'input-bindings.json'):
        bindings[str(path)] = digest(path)
    commands = {}
    for side in ('baseline', 'candidate'):
        target = root / f'{side}-request.json'
        write(target, dict(request, output_root=str(root / f'{side}-publication')))
        bindings[str(target)] = digest(target)
        (root / side).mkdir(exist_ok=False)
        command = ['/usr/bin/time', '-v', '-o', str(root / f'{side}-process-time.txt')]
        command += ['sh', str(runner), str(root / f'{side}-src'), str(bundle),
                    str(root / side), sys.executable, str(target), '1200', '0,1,2']
        commands[side] = command
    sequence = ['candidate', 'baseline'] if args.candidate_first else ['baseline', 'candidate']
    write(root / 'plan.json', dict(commands=commands, sequence=sequence, bindings=bindings,
                                  cpus=[0, 1, 2], blas_threads=1, timeout_seconds=1200,
                                  cpu_accounting='GNU time -v', production_modified=False))
    for side in sequence:
        command = commands[side]
        write(root / f'{side}-resources-start.json', dict(
            load=os.getloadavg(), cpu_pressure=Path('/proc/pressure/cpu').read_text()))
        print(f'Starting {side}', flush=True)
        with (root / f'{side}.log').open('xb') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        write(root / f'{side}-resources-end.json', dict(
            load=os.getloadavg(), cpu_pressure=Path('/proc/pressure/cpu').read_text()))
        print(f'Completed {side}', flush=True)
    for name, sha in bindings.items():
        assert digest(name) == sha, name
    command = [sys.executable, '-B', str(comparator)]
    for side in commands:
        command += [f'--{side}-request', str(root / f'{side}-request.json'),
                    f'--{side}-timing', str(root / side / 'attempt/supervisor.json')]
    for name in baseline:
        command += ['--changed-module', name.removesuffix('.py').replace('/', '.')]
    command += ['--output', str(root / 'comparison.json')]
    with (root / 'comparison.log').open('xb') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    print('Complete exact comparison saved', flush=True)


if __name__ == '__main__':
    main()
