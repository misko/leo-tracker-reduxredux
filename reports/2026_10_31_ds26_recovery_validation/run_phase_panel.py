"""Bounded matched phase-reference validation on a preselected RF-only panel."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import time

ROOT = Path(__file__).parent
REPO = Path('/srv/bulk/leo-dev/fast-algo02-production-v1')

def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')

def main():
    out = ROOT / 'phase-panel'
    out.mkdir(exist_ok=False)
    runner = out / 'run_phase_reference.py'
    shutil.copyfile(ROOT / 'phase0265/run_phase0265.py', runner)
    panel = json.loads((ROOT / 'phase-validation-panel.json').read_text())
    protocol = dict(panel=panel, workers=3, numerical_threads=1, per_case_timeout_s=600,
                    annotation_only=True, GPS_used=False, production_change=False,
                    runner_sha256=hashlib.sha256(runner.read_bytes()).hexdigest(),
                    panel_sha256=hashlib.sha256((ROOT/'phase-validation-panel.json').read_bytes()).hexdigest())
    write(out / 'protocol.json', protocol)
    env = dict(os.environ, PYTHONPATH='src:tools', OPENBLAS_NUM_THREADS='1',
               OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    def run(row):
        source = Path(row['source'])
        inventories = list(source.parents[2].glob('all-large-track-recovery/*/inventory.json'))
        assert len(inventories) == 1, inventories
        destination = out / row['case']
        cmd = [str(REPO/'.venv/bin/python'), str(runner), '--annotation-only',
               '--inventory', str(inventories[0]), '--source', str(source.parent), '--output', str(destination)]
        started = time.monotonic()
        with (out / (row['case']+'.log')).open('w') as log:
            try:
                result = subprocess.run(cmd, cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
                rc, error = result.returncode, None
            except subprocess.TimeoutExpired:
                rc, error = -1, '600s case timeout'
        receipt = dict(case=row['case'], role=row['panel_role'], command=cmd,
                       exit_code=rc, error=error, seconds=time.monotonic()-started)
        write(out / (row['case']+'-receipt.json'), receipt)
        print(json.dumps(receipt), flush=True)
        return receipt
    with ThreadPoolExecutor(max_workers=3) as executor:
        receipts = list(executor.map(run, panel['rows']))
    write(out / 'terminal.json', dict(receipts=receipts, all_completed=all(r['exit_code']==0 for r in receipts)))

if __name__ == '__main__':
    main()
