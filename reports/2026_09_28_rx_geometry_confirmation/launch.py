"""Run a receipt-bound confirmation stage over existing derived artifacts."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
stage = sys.argv[1]
pilot = HERE.parent / '2026_09_28_rx_geometry_association'
inventory = HERE / 'selected-inventory.json'
opportunities = HERE / 'opportunities/opportunities.jsonl'
partitions = HERE / 'partitions.json'
bank = HERE / 'candidate-bank.json'
mapping = HERE / 'alias-mapping.json'
dataset = HERE / 'dataset.json'
protocol = HERE / 'PROTOCOL.md'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

if stage == 'opportunities':
    module = 'rx_paired_opportunities'
    args = ['--inventory', str(inventory), '--output-dir', str(opportunities.parent)]
    inputs = [inventory]
elif stage == 'partitions':
    module = 'rx_grouped_partitions'
    args = ['--opportunities', str(opportunities), '--output', str(partitions), '--evaluation-only']
    inputs = [opportunities]
elif stage == 'bank':
    module = 'rx_training_candidate_bank'
    args = ['--inventory', str(inventory), '--manifest', str(HERE / 'manifest.json'),
            '--partitions', str(partitions), '--snapshot-authority', str(HERE / 'snapshot-authority.json'),
            '--output', str(bank)]
    inputs = [inventory, HERE / 'manifest.json', partitions, HERE / 'snapshot-authority.json']
elif stage == 'mapping':
    module = 'rx_training_alias_mapping'
    args = ['--inventory', str(inventory), '--partitions', str(partitions), '--candidate-bank', str(bank),
            '--protocol', str(protocol), '--protocol-sha256', 'sha256:' + digest(protocol),
            '--output', str(mapping)]
    inputs = [inventory, partitions, bank]
elif stage == 'dataset':
    module = 'rx_geometry_dataset'
    args = ['--bank', str(bank), '--mapping', str(mapping), '--partitions', str(partitions),
            '--opportunities', str(opportunities), '--output', str(dataset)]
    inputs = [bank, mapping, partitions, opportunities]
elif stage == 'score':
    module = 'rx_geometry_frozen_score'
    args = ['--model', str(pilot / 'results.json'), '--training-dataset', str(pilot / 'dataset.json'),
            '--dataset', str(dataset), '--output', str(HERE / 'results.json')]
    inputs = [pilot / 'results.json', pilot / 'dataset.json', dataset]
else:
    raise ValueError(stage)
code = [ROOT / f'tools/{module}.py']
if stage in ('bank', 'mapping'):
    code += [ROOT / 'tools/rx_training_candidate_bank.py']
if stage == 'score':
    code += [ROOT / 'tools/rx_geometry_fit.py', ROOT / 'tools/rx_geometry_likelihood.py']
command = ['sudo', '-n', '/usr/bin/time', '-v', '-o', str(HERE / f'{stage}-resources.txt'),
           '/usr/bin/timeout', '--signal=TERM', '--kill-after=5s', '300s',
           '/usr/bin/prlimit', '--as=4294967296', '/usr/bin/nice', '-n', '19',
           '/usr/bin/env', 'OPENBLAS_NUM_THREADS=1', 'OMP_NUM_THREADS=1',
           'MKL_NUM_THREADS=1', 'NUMEXPR_NUM_THREADS=1', 'PYTHONHASHSEED=0',
           '/opt/leo-tracker/current-api/.venv/bin/python', '-m', 'tools.' + module, *args]
with (HERE / f'{stage}-launch.json').open('x') as handle:
    json.dump({'command': command, 'cwd': str(ROOT),
               'sha256': {str(p): digest(p) for p in [protocol, Path(__file__), *code, *inputs]}}, handle, indent=2)
with (HERE / f'{stage}-terminal.log').open('x') as handle:
    result = subprocess.run(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
(HERE / f'{stage}-exit-code.txt').write_text(str(result.returncode) + '\n')
if result.returncode == 0 and stage in ('bank', 'mapping'):
    target = bank if stage == 'bank' else mapping
    subprocess.run(['sudo', '-n', 'chown', '--reference=' + str(protocol), str(target)], check=True)
print(stage, result.returncode)
sys.exit(result.returncode)
