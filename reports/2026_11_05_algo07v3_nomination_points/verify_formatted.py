"""Replay the final formatted source and compare complete publication exactly."""

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def main(root, pair):
    root.mkdir(exist_ok=False)
    source = Path('src/leo/analysis/localization_v3/residual_screen.py')
    measured = pair / 'candidate-src/leo/analysis/localization_v3/residual_screen.py'
    assert ast.dump(ast.parse(source.read_bytes())) == ast.dump(ast.parse(measured.read_bytes()))
    request = json.loads((pair / 'candidate-request.json').read_bytes())
    request['output_root'] = str(root / 'publication')
    (root / 'request.json').write_text(json.dumps(request, indent=2) + '\n')
    (root / 'run').mkdir()
    paths = [*Path('src').rglob('*.py'), Path(__file__), root / 'request.json', measured,
             Path('tools/qualify_algo07v3_cli.sh'), Path('tools/compare_algo07v3_runs.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    plan = dict(bindings=bindings, syntax_tree_identical=True, blas_threads=1, cpus=[0, 1, 2],
                original_pair=str(pair), load=os.getloadavg(),
                cpu_pressure=Path('/proc/pressure/cpu').read_text())
    (root / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    bundle = Path(request['native_input']['path']).parent
    command = ['/usr/bin/time', '-v', '-o', str(root / 'process-time.txt'),
               'taskset', '-c', '0,1,2', 'sh', 'tools/qualify_algo07v3_cli.sh', str(bundle),
               str(root / 'run'), sys.executable, str(root / 'request.json'), 'run', '1200']
    with (root / 'run.log').open('xb') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    command = [sys.executable, '-B', 'tools/compare_algo07v3_runs.py',
               '--baseline-request', str(pair / 'candidate-request.json'),
               '--baseline-timing', str(pair / 'candidate/attempt/supervisor.json'),
               '--candidate-request', str(root / 'request.json'),
               '--candidate-timing', str(root / 'run/attempt/supervisor.json'),
               '--changed-module', 'leo.analysis.localization_v3.residual_screen',
               '--output', str(root / 'comparison.json')]
    with (root / 'comparison.log').open('xb') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    print('Final formatted source: complete science and PNGs exact', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--pair', type=Path, required=True)
    main(**vars(parser.parse_args()))
