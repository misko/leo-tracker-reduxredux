"""Freeze and run one bounded geometry-association stage."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
stage = sys.argv[1]
forecast = HERE.parent / '2026_09_28_rx_training_forecast'
receiver = HERE.parent / '2026_09_28_rx_receiver_order'
dataset = HERE / 'dataset.json'
if stage == 'dataset':
    module = 'tools.rx_geometry_dataset'
    inputs = {'bank': forecast / 'candidate-bank.json',
              'mapping': receiver / 'alias-mapping.json',
              'partitions': forecast / 'partitions.json',
              'opportunities': HERE.parent / '2026_09_28_rx_tracking_evidence/opportunities/opportunities.jsonl'}
    args = [value for key, path in inputs.items() for value in ('--' + key, str(path))]
    args += ['--output', str(dataset)]
elif stage == 'fit':
    module = 'tools.rx_geometry_fit'
    inputs = {'dataset': dataset}
    args = ['--dataset', str(dataset), '--output', str(HERE / 'results.json')]
else:
    raise ValueError(stage)
command = ['sudo', '-n', '/usr/bin/time', '-v', '-o', str(HERE / f'{stage}-resources.txt'),
           '/usr/bin/timeout', '--signal=TERM', '--kill-after=5s', '300s',
           '/usr/bin/prlimit', '--as=4294967296', '/usr/bin/nice', '-n', '19',
           '/usr/bin/env', 'OPENBLAS_NUM_THREADS=1', 'OMP_NUM_THREADS=1',
           'MKL_NUM_THREADS=1', 'NUMEXPR_NUM_THREADS=1', 'PYTHONHASHSEED=0',
           '/opt/leo-tracker/current-api/.venv/bin/python', '-m', module, *args]
files = [*inputs.values(), HERE / 'PROTOCOL.md', Path(__file__)]
for name in ('dataset', 'likelihood', 'fit'):
    files += [ROOT / f'tools/rx_geometry_{name}.py', ROOT / f'tests/research/test_rx_geometry_{name}.py']
runtime = subprocess.check_output(['sudo', '-n', '/opt/leo-tracker/current-api/.venv/bin/python',
    '-c', 'import sys,numpy,scipy,json; print(json.dumps(dict(python=sys.version,numpy=numpy.__version__,scipy=scipy.__version__)))'], text=True)
with (HERE / f'{stage}-launch.json').open('x') as handle:
    json.dump({'command': command, 'cwd': str(ROOT), 'runtime': json.loads(runtime),
               'sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}, handle, indent=2)
with (HERE / f'{stage}-terminal.log').open('x') as handle:
    result = subprocess.run(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
(HERE / f'{stage}-exit-code.txt').write_text(str(result.returncode) + '\n')
print(stage, result.returncode)
sys.exit(result.returncode)
