"""One explicit bounded arm-batch; never automatically expands to all methods."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(path):
    return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seal(path, document):
    with Path(path).open('x') as stream:
        json.dump(document, stream, indent=2, allow_nan=False)
    with Path(path).with_suffix('.seal.json').open('x') as stream:
        json.dump({'prediction_sha256':digest(path)}, stream)


def launch(unit, args):
    folder = Path(args.folder)
    output = folder / f'{unit}.json'
    launched = output.with_suffix('.launch.json')
    if output.exists() or launched.exists():
        raise FileExistsError(output)
    folder.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(HERE/'replay_approach.py'), unit, '--arm', args.arm,
               '--output', str(output), '--seed-source', args.seed_source, '--predictor', args.predictor]
    if args.parent_folder:
        command += ['--parent', str(Path(args.parent_folder)/f'{unit}.json')]
    parent_seconds = 0.
    if args.parent_folder:
        parent_launch = Path(args.parent_folder)/f'{unit}.launch.json'
        if digest(parent_launch) != json.loads(parent_launch.with_suffix('.seal.json').read_text())['prediction_sha256']:
            raise ValueError('parent launch seal mismatch')
        parent_seconds = json.loads(parent_launch.read_text())['wall_seconds']
        if parent_seconds > 90:
            raise ValueError('parent exceeded primary budget')
    env = dict(os.environ)
    env.update({k:'1' for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']})
    env['PYTHONPATH'] = str(ROOT/'src')
    start = time.monotonic()
    receipt = dict(unit_id=unit, arm=args.arm, command=command, timeout_seconds=90,
                   workers=args.workers, numerical_threads=1, status='running',
                   supervisor_sha256=digest(__file__), parent_seconds=parent_seconds,
                   numerical_environment={k:env[k] for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']})
    try:
        run = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=90.)
        receipt.update(status='complete' if run.returncode == 0 else 'error',
                       returncode=run.returncode, stdout=run.stdout, stderr=run.stderr)
    except subprocess.TimeoutExpired as error:
        receipt.update(status='timeout', stdout=str(error.stdout or ''), stderr=str(error.stderr or ''))
    incomplete = None
    if output.exists():
        try:
            valid = json.loads(output.with_suffix('.seal.json').read_text())['prediction_sha256'] == digest(output)
        except (OSError, ValueError, KeyError):
            valid = False
        if not valid:
            forensic = output.with_suffix('.incomplete.json')
            if forensic.exists():
                raise FileExistsError(forensic)
            output.rename(forensic)
            incomplete = dict(path=str(forensic), sha256=digest(forensic))
            old_seal = output.with_suffix('.seal.json')
            if old_seal.exists():
                old_seal.rename(output.with_suffix('.invalid-seal.json'))
            receipt['status'] = 'error' if receipt['status'] != 'timeout' else 'timeout'
    if not output.exists():
        seal(output, dict(schema='localization-approach-attempt/v1', unit_id=unit,
             config=dict(arm=args.arm, predictor=args.predictor, seed_source=args.seed_source),
             status='timeout' if receipt['status']=='timeout' else 'error', fits=[], best=None,
             supervisor_generated=True, exception=dict(type='WorkerDidNotSeal',message=receipt['status']),
             supervisor_sha256=digest(__file__), incomplete_artifact=incomplete))
    try:
        prediction_digest = digest(output)
        if json.loads(output.with_suffix('.seal.json').read_text())['prediction_sha256'] != prediction_digest:
            raise ValueError('prediction seal mismatch')
        native = json.loads(output.read_text())
        receipt.update(prediction_sha256=prediction_digest, native_status=native['status'])
        if native['status'] == 'error':
            receipt['status'] = 'error'
    except (OSError, ValueError, KeyError) as error:
        receipt.update(status='error', seal_error=str(error))
    receipt['wall_seconds'] = time.monotonic() - start
    receipt['cumulative_seconds'] = parent_seconds + receipt['wall_seconds']
    receipt['within_budget'] = receipt['wall_seconds'] <= 90 and receipt['cumulative_seconds'] <= 180
    seal(launched, receipt)
    print(json.dumps({k:receipt[k] for k in ['unit_id','arm','status','wall_seconds']}), flush=True)
    return receipt


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--arm', required=True, choices=['A1','B1','C1','oracle'])
    p.add_argument('--units', nargs='+', required=True)
    p.add_argument('--folder', required=True)
    p.add_argument('--workers', type=int, choices=[1,2], default=1)
    p.add_argument('--seed-source', choices=['cached','fresh'], default='cached')
    p.add_argument('--predictor', choices=['oracle','selected'], default='selected')
    p.add_argument('--parent-folder')
    args=p.parse_args()
    if not 1 <= len(args.units) <= 8 or len(set(args.units)) != len(args.units):
        p.error('one explicit batch of 1..8 unique units required')
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(lambda unit: launch(unit,args), args.units))
