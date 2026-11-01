"""Execute the frozen guarded candidate on saved DS24 ALGO06 research states.

Only the baseline I/O adapter changes: these are saved evaluated outcomes, not
live V5 terminals. Numerical search, guards, priors and budgets remain frozen.
"""
import argparse
import copy
import csv
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parent))
import run_candidate as runner

SOURCE = Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_01_ds25_fast_causal_variants')
INPUT = OUT/'inputs'
OUTPUT = OUT/'candidate'
BASE_SOURCE_INVENTORY = runner.source_inventory
BASE_CONFIGURE = runner.configure


def source_inventory():
    return dict(BASE_SOURCE_INVENTORY(), **{str(Path(__file__)): runner.sha(__file__)})


def configure(input_root, output_root):
    BASE_CONFIGURE(input_root, output_root)
    runner.e.ROOTS = dict(runner.e.ROOTS, DS24=input_root)


def authority(case):
    """Independently compose the saved ALGO06 endpoint and native owners."""
    z = runner.read(SOURCE/'inputs'/(case+'.json'))
    result = runner.read(SOURCE/'position'/case/'result.json')
    decision = result['decisions']['72h_30s']
    trial = result['trials'][decision['trial']] if decision['status']=='qualified' else None
    owners = copy.deepcopy(z['baseline_owners'])
    arms = {}
    for arm in runner.e.ARMS:
        row = trial['arms'][arm] if trial else z['baseline_arms'][arm]
        if trial:
            for oid in trial['entry']['observation_ids']:
                if oid in owners[arm]:
                    raise ValueError('Duplicate ALGO06 baseline owner')
                owners[arm][oid] = trial['entry']['norad']
        arms[arm] = dict(x=row['endpoint_east_north_km'], objective=row['negative_twice_elbo'])
    return dict(schema='ds24-saved-algo06-authority/v1', case=case, arms=arms,
                owners=owners, source='saved 72h_30s research baseline; not a live public V5 terminal',
                source_sha256={str(p): runner.sha(p) for p in
                    (SOURCE/'inputs'/(case+'.json'), SOURCE/'position'/case/'result.json')})


def saved_preflight(d, z, baseline, receipt):
    if receipt['schema'] != 'ds24-saved-algo06-authority/v1':
        raise ValueError('Expected saved DS24 authority')
    for path, digest in receipt['source_sha256'].items():
        if runner.sha(path) != digest:
            raise ValueError('Saved baseline changed')
    differences = {}
    for arm in runner.e.ARMS:
        point = np.asarray(d['problems'][arm][1])
        expected = receipt['arms'][arm]
        if not np.array_equal(point, np.asarray(expected['x'])):
            raise ValueError('Saved baseline endpoint mismatch')
        if z['baseline_owners'][arm] != receipt['owners'][arm]:
            raise ValueError('Saved baseline owner mismatch')
        delta = runner.e.objective(d['problems'][arm][0], d, point)-expected['objective']
        if abs(delta)>1e-4 or baseline[arm]['associated']!=len(receipt['owners'][arm]):
            raise ValueError('Saved baseline score/count mismatch')
        differences[arm] = float(delta)
    return dict(authority=receipt['source'], objective_difference=differences,
                endpoints_exact=True, owner_maps_exact=True,
                public_terminal_verified=False)


runner.source_inventory = source_inventory
runner.configure = configure
runner.preflight_public = saved_preflight


def prepare():
    if (INPUT/'roster.json').exists():
        raise FileExistsError('DS24 inputs already prepared')
    roster = runner.read(SOURCE/'roster.json')['cases']
    cases = sorted(p.stem for p in (SOURCE/'inputs').glob('DS24-*.json'))
    assert len(roster)==34 and len(cases)==25
    source_paths = {SOURCE/'roster.json', SOURCE/'protocol.json', SOURCE/'position-errors.csv',
                    SOURCE/'dataset/manifest.json'}
    dependency_roots = set()
    rows = []
    for case in cases:
        for rel in (f'inputs/{case}.json', f'catalogues/{case}.json',
                    f'position/{case}/result.json', f'screen/{case}/result.json'):
            src = SOURCE/rel
            if src.exists():
                dst = INPUT/rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                source_paths.add(src)
        z = runner.read(INPUT/'inputs'/(case+'.json'))
        # Pin complete exported recovery trees, including snapshots, binary
        # orbit caches, model receipts and selected addition protocols.
        dependency_roots.add(Path(z['recovery_path']))
        dependency_roots.add(Path(z['native_path']))
        source_paths.add(Path(z['inventory_path']))
        inv = runner.read(z['inventory_path'])
        dependency_roots.add(Path(inv['job']['root']))
        for selection in (z.get('selected'), z.get('gap_selected')):
            if selection:
                for field in ('path', 'trial'):
                    if selection.get(field):dependency_roots.add(Path(selection[field]))
        receipt = authority(case)
        # Filename is the frozen runner's I/O convention only; schema and
        # checker explicitly identify saved research, never a public terminal.
        runner.write(INPUT/'exports'/case/'published-algo06.json', receipt)
        member = next(r for r in roster if r['case']==case)
        rows.append(dict(case=case, recording_id=member['recording_id']))
    roots = [p for p in dependency_roots if not any(p!=q and p.is_relative_to(q) for q in dependency_roots)]
    for root in roots:
        if str(root).startswith('/mnt/qnap01'):
            raise ValueError('Only prepared exports may be hashed here')
        source_paths.update(p for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    print('Hashing', len(source_paths), 'baseline dependency files', flush=True)
    hashes = {str(p):runner.sha(p) for p in sorted(source_paths)}
    runner.write(INPUT/'external-input-hashes.json', hashes)
    unavailable = [dict(case=r['case'], recording_id=r['recording_id'], reason=r.get('reason'))
                   for r in roster if r['case'] not in cases]
    runner.write(INPUT/'roster.json', dict(rows=rows, unavailable=unavailable, full_members=34,
        selection='All 25 available frozen DS24 fast ALGO06 baselines; nine missing GLRT inputs retained',
        evaluation_site=[37.849061591561885,-122.48574968092912], truth_used_for_inference=False))


def preflight():
    proof = runner.preflight(INPUT, OUTPUT)
    hashes = runner.read(INPUT/'external-input-hashes.json')
    for path, digest in hashes.items():
        if runner.sha(path)!=digest:raise ValueError('External baseline changed: '+path)
    proof['external_input_sha256'].update(hashes)
    proof['baseline_authority'] = 'Saved DS24 ALGO06 research outcomes, not live public V5 terminals'
    runner.write(OUTPUT/'preflight.json', proof)


def supervise(case):
    protocol = runner.verify_frozen(INPUT, OUTPUT, case)
    folder = OUTPUT/case
    folder.mkdir(exist_ok=True, parents=True)
    with (folder/'supervisor.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (folder/'result.json').exists():return runner.read(folder/'result.json')
        if (folder/'attempt.json').exists():
            result = runner.fallback(protocol['baselines'][case], 'prior_incomplete_attempt', case=case)
        else:
            runner.write(folder/'attempt.json', dict(case=case, started_utc_ns=time.time_ns(),
                protocol_sha256=runner.sha(OUTPUT/'protocol.json'), limit_s=runner.SETTINGS['process_limit_s']))
            began = time.monotonic()
            with (folder/'worker.log').open('w') as log:
                process = subprocess.Popen([sys.executable, str(Path(__file__)), 'worker', '--case', case],
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1'))
                try:
                    code = process.wait(timeout=runner.SETTINGS['process_limit_s'])
                    if code==0 and (folder/'worker_result.json').exists():
                        result = runner.read(folder/'worker_result.json')
                    else:result = runner.fallback(protocol['baselines'][case], 'worker_failure', case=case, returncode=code)
                except subprocess.TimeoutExpired:
                    runner.terminate_group(process)
                    result = runner.fallback(protocol['baselines'][case], 'compute_fallback', case=case,
                        limit_s=runner.SETTINGS['process_limit_s'])
            result['supervisor_seconds'] = time.monotonic()-began
        runner.write(folder/'result.json', result)
    return result


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare','preflight','freeze','run','worker'])
    parser.add_argument('--case')
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    if args.action=='prepare':prepare()
    elif args.action=='preflight':preflight()
    elif args.action=='freeze':runner.freeze(INPUT, OUTPUT)
    elif args.action=='worker':runner.run_worker(args.case, INPUT, OUTPUT)
    else:
        cases = [args.case] if args.case else runner.read(OUTPUT/'protocol.json')['cases']
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            pending = {pool.submit(supervise, case):case for case in cases}
            for future in as_completed(pending):
                result = future.result()
                print(pending[future], result['execution_status'], result['selected'], flush=True)
