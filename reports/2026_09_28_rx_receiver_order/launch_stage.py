"""Freeze local evidence and execute one bounded, serialized research stage."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
REPORT = Path(__file__).resolve().parent
FORECAST = ROOT / 'reports/2026_09_28_rx_training_forecast'


def sha(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


stage = sys.argv[1]
attempt = sys.argv[2] if len(sys.argv) > 2 else stage
protocol = REPORT / 'PROTOCOL.md'
bank = FORECAST / 'candidate-bank.json'
partitions = FORECAST / 'partitions.json'
mapping = REPORT / 'alias-mapping.json'
inventory = ROOT / 'reports/2026_09_27_roof_direction_subset/evaluation_inventory.json'
opportunities = ROOT / 'reports/2026_09_28_rx_tracking_evidence/opportunities/opportunities.jsonl'
if stage == 'mapping':
    script = ROOT / 'tools/rx_training_alias_mapping.py'
    test = ROOT / 'tests/research/test_rx_training_alias_mapping.py'
    inputs = [inventory, bank, partitions]
    args = ['--inventory', str(inventory), '--partitions', str(partitions),
            '--candidate-bank', str(bank), '--protocol', str(protocol),
            '--protocol-sha256', sha(protocol), '--output', str(mapping)]
elif stage == 'sequences':
    script = ROOT / 'tools/rx_receiver_order_sequences.py'
    test = ROOT / 'tests/research/test_rx_receiver_order_sequences.py'
    inputs = [bank, partitions, mapping, opportunities]
    args = ['--candidate-bank', str(bank), '--rx-alias-mapping', str(mapping),
            '--partitions', str(partitions), '--opportunities', str(opportunities),
            '--output-summary', str(REPORT / 'sequences.json'),
            '--output-opportunities', str(REPORT / 'matched-opportunities.jsonl')]
else:
    raise ValueError(stage)
runtime = json.loads((FORECAST / 'runtime-binding.json').read_text())
runtime_receipts = {}
for name, row in runtime.items():
    if name == 'versions':
        continue
    path = Path(row['path'])
    value = subprocess.check_output(['sudo', '-n', 'sha256sum', str(path)], text=True).split()[0]
    if value != row['sha256']:
        raise ValueError(f'Runtime changed: {name}')
    runtime_receipts[name] = row
command = ['sudo', '-n', '/usr/bin/time', '-v', '-o', str(REPORT / f'{attempt}-resources.txt'),
           '/usr/bin/timeout', '--signal=TERM', '--kill-after=5s', '300s',
           '/usr/bin/prlimit', '--as=4294967296', '/usr/bin/nice', '-n', '19',
           '/usr/bin/env', 'OPENBLAS_NUM_THREADS=1', 'OMP_NUM_THREADS=1',
           'MKL_NUM_THREADS=1', 'NUMEXPR_NUM_THREADS=1', 'PYTHONHASHSEED=0',
           '/opt/leo-tracker/current-api/.venv/bin/python', '-m',
           'tools.' + script.stem, *args]
files = [protocol, script, test, Path(__file__), ROOT / 'tools/rx_training_candidate_bank.py', *inputs]
files += [REPORT / 'MAPPING-LAUNCH-AMENDMENT.md', REPORT / 'validation.json']
with (REPORT / f'{attempt}-launch.json').open('x') as handle:
    json.dump({'command': command, 'cwd': str(ROOT),
               'sha256': {str(path): sha(path) for path in files},
               'runtime': runtime_receipts}, handle, indent=2)
with (REPORT / f'{attempt}-terminal.log').open('x') as handle:
    result = subprocess.run(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
(REPORT / f'{attempt}-exit-code.txt').write_text(str(result.returncode) + '\n')
print(stage, result.returncode)
sys.exit(result.returncode)
