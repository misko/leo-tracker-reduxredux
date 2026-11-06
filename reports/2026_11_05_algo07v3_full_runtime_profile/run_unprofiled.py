"""Fresh isolated, unprofiled control for the current full-runtime profile."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def resources():
    return dict(load=os.getloadavg(), cpu_pressure=Path('/proc/pressure/cpu').read_text(),
                memory_pressure=Path('/proc/pressure/memory').read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    root.mkdir(exist_ok=False)
    request = json.loads(args.request.read_bytes())
    bundle = Path(request['native_input']['path']).parent
    write(root / 'request.json', dict(request, output_root=str(root / 'publication')))
    (root / 'cli').mkdir()
    paths = [*Path('src').rglob('*.py'), args.request, root / 'request.json', Path(__file__),
             Path('tools/qualify_algo07v3_cli.sh'), bundle / 'input-bindings.json']
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    command = ['/usr/bin/time', '-v', '-o', str(root / 'process-time.txt'), 'sh',
               'tools/qualify_algo07v3_cli.sh', str(bundle), str(root / 'cli'),
               sys.executable, str(root / 'request.json'), 'run', '1200']
    write(root / 'plan.json', dict(bindings=bindings, command=command,
                                  affinity=sorted(os.sched_getaffinity(0)), blas_threads=1,
                                  production_modified=False, profiled=False))
    write(root / 'resources-start.json', resources())
    with (root / 'run.log').open('xb') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    write(root / 'resources-end.json', resources())
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    result = json.loads((root / 'cli/attempt/supervisor.json').read_bytes())
    assert result['returncode'] == 0 and result['worker']['status'] == 'complete'
    assert not result['worker']['resumed']
    print(json.dumps(dict(seconds=result['process_seconds'], complete=True)), flush=True)


if __name__ == '__main__':
    main()
