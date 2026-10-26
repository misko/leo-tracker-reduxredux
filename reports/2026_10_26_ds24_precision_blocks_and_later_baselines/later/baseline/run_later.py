"""Run the exact retained producer on four prepared inputs, under one case cap."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
PREPARED = HERE.parent / 'prepared'
WORK = HERE / 'work'
STUDY = Path('/srv/bulk/leo/research/ds24-precision-block-transfer-r01')
OLD = Path('/srv/bulk/leo/research/ds25-20261024')
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
PYTHON = REPO / '.venv/bin/python'
CASES = tuple(f'LATER4-{i:04}' for i in range(1, 5))


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p, data):
    with Path(p).open('x') as f:
        json.dump(data, f, indent=2, allow_nan=False)
        f.write('\n')


def stages(case):
    return [
        ('algo02', [str(PYTHON), str(REPO/'tools/algo02_scan.py'), '--run-dir', str(WORK), '--case', case, '--stage', 'all']),
        ('cavity', [str(PYTHON), str(OLD/'engine/ds24_engine.py'), '--root', str(WORK), '--case', case]),
    ]


def remaining_cap(began, cap=180.):
    remaining = cap - (time.monotonic() - began)
    if remaining <= 0:
        raise TimeoutError('aggregate case cap exhausted')
    return remaining


def freeze():
    began = time.monotonic()
    execution = read(PREPARED/'preparation_execution.json')
    if not execution['terminal'] or not execution['budget_pass']:
        raise ValueError('terminal budget-qualified preparation required')
    seal = read(PREPARED/'preparation_RF_seal.json')
    for p, h in seal['files'].items():
        if sha(p) != h:
            raise ValueError('preparation output changed: '+p)
    tests = read(HERE/'later_runner_tests.json')
    if tests['returncode']:
        raise ValueError('runner tests failed')
    inputs = {str(PREPARED/'preparation_RF_seal.json'): sha(PREPARED/'preparation_RF_seal.json')}
    if WORK.exists():
        raise ValueError('new work directory required')
    shutil.copytree(PREPARED, WORK)
    for p in sorted(WORK.rglob('*')):
        if p.is_file():
            original = PREPARED / p.relative_to(WORK)
            if sha(p) != sha(original):
                raise ValueError('input copy mismatch')
            inputs[str(p)] = sha(p)
    if tuple(m['dataset_label'] for m in read(WORK/'sample.json')['selected']) != CASES:
        raise ValueError('fixed member order changed')
    sources = read(OLD/'source_receipt.json')['files']
    sources.update({p: h.removeprefix('sha256:') for p, h in read(OLD/'protocol.json')['inference_sources_sha256'].items()})
    for p, h in sources.items():
        if sha(p) != h:
            raise ValueError('retained producer source changed: '+p)
    for p in [Path(__file__), HERE/'test_run_later.py', HERE/'selector_v2.py', HERE/'test_selector_v2.py',
              HERE/'selector_v2_tests.json', HERE/'later_runner_tests.json', HERE/'replay.json', HERE/'replay_seal.json',
              STUDY/'COORDINATOR_PLAN.md', OLD/'source_receipt.json', OLD/'protocol.json',
              Path('/srv/bulk/leo/research/ds24-detector-response-r01/influence/panel.py')]:
        sources[str(p)] = sha(p)
    pre_seconds = tests['seconds'] + read(HERE/'selector_v2_tests.json')['seconds'] + time.monotonic()-began + .020
    prior = read(HERE/'replay.json')['cumulative_numerical_seconds']
    if pre_seconds > 60 or prior+pre_seconds+4*180 > 840:
        raise ValueError('preparation/reservation cap exceeded')
    ready = {r['case']: r['status'] == 'prepared' for r in execution['rows']}
    if set(ready) != set(CASES):
        raise ValueError('preparation lost a fixed member')
    protocol = dict(cases=list(CASES), input_bindings=inputs, source_bindings=sources,
                    prepared_ready=ready, prior_replay_seconds=prior, preparation_seconds=pre_seconds,
                    per_case_cap=180., cumulative_cap=840., workers=2, BLAS_threads=1,
                    stages={c: stages(c) for c in CASES}, no_retry=True,
                    full_retained_producer=True, no_GPS_or_original_family_seeding=True,
                    preflight=str(STUDY/'audit/baseline_preflight.json'), go=str(STUDY/'baseline_go.json'))
    write(HERE/'later_protocol.json', protocol)
    print(json.dumps(dict(protocol=str(HERE/'later_protocol.json'), sha256=sha(HERE/'later_protocol.json'),
                          preparation_seconds=pre_seconds, prepared_ready=ready)), flush=True)


def one(case, protocol):
    started = time.monotonic()
    record = dict(case=case, status='not_ready', stages=[], arms=['c0','fitted_c'])
    if not protocol['prepared_ready'][case]:
        record.update(reason='upstream preparation not qualified', seconds=time.monotonic()-started)
        write(HERE/(case+'_baseline_execution.json'), record)
        return record
    # Reuse the original producer's existing external process-group supervisor.
    sys.path.insert(0, str(OLD/'engine')) if str(OLD/'engine') not in sys.path else None
    import run_baseline
    try:
        for name, command in protocol['stages'][case]:
            cap = remaining_cap(started, protocol['per_case_cap'])
            mark = time.monotonic()
            stage = dict(stage=name, command=command)
            record['stages'].append(stage)
            with (HERE/f'{case}_{name}.log').open('x') as log:
                try:
                    stage['returncode'] = run_baseline.run_command(command, log, cap)
                finally:
                    stage['seconds'] = time.monotonic()-mark
            if stage['returncode']:
                raise RuntimeError(name+' returned '+str(stage['returncode']))
            if name == 'algo02':
                result = read(WORK/case/'algo02_result.json')
                if result['status'] != 'accepted':
                    record.update(status='reference_unqualified', reason=result.get('reason'))
                    break
            if name == 'cavity':
                path = WORK/'family_cavity/position'/(case+'.json')
                result = read(path)
                if result['status'] != 'complete' or not result.get('reconstructed_fresh_reference'):
                    record.update(status='reference_unqualified', reason='full retained comparison incomplete')
                    break
                if set(result['policy_arms']) != {'c0','fitted_c'}:
                    raise ValueError('missing calibration arm')
                record.update(status='complete', result_path=str(path), result_sha256=sha(path))
    except (TimeoutError, subprocess.TimeoutExpired) as error:
        record.update(status='timeout', error=repr(error))
    except Exception as error:
        record.update(status='failed', error=repr(error))
    record['seconds'] = time.monotonic()-started
    write(HERE/(case+'_baseline_execution.json'), record)
    return record


def run():
    protocol = read(HERE/'later_protocol.json')
    digest = sha(HERE/'later_protocol.json')
    for key in ('input_bindings', 'source_bindings'):
        for p, h in protocol[key].items():
            if sha(p) != h:
                raise ValueError('bound source/input changed: '+p)
    for path, flag in [(protocol['preflight'], 'all_passed'), (protocol['go'], 'authorized')]:
        gate = read(path)
        if not gate[flag] or gate['protocol_sha256'] != digest:
            raise ValueError('matching preflight and root GO required')
    if any(os.environ.get(k) != '1' for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']):
        raise ValueError('BLAS1 required')
    if (HERE/'later_execution.json').exists() or any(HERE.glob('LATER4-*_baseline_execution.json')):
        raise ValueError('no retry or partial rerun')
    # Import once before threads; each numerical child has its own process.
    sys.path.insert(0, str(OLD/'engine'))
    import run_baseline
    rows = []
    began = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {pool.submit(one, c, protocol): c for c in CASES}
        for future in as_completed(jobs):
            try:
                row = future.result()
            except Exception as error:
                row = dict(case=jobs[future], status='supervisor_failed', error=repr(error), seconds=180.)
            rows.append(row)
            print(json.dumps(row), flush=True)
    total = protocol['prior_replay_seconds']+protocol['preparation_seconds']+sum(r['seconds'] for r in rows)
    result = dict(rows=sorted(rows,key=lambda r:r['case']), terminal=True, all_four_slots_preserved=len(rows)==4,
                  cumulative_worker_seconds=total, wall_seconds=time.monotonic()-began,
                  budget_pass=total<=protocol['cumulative_cap'], protocol_sha256=digest,
                  no_GPS_evaluation=True, no_new_CFO_refinement=True)
    write(HERE/'later_execution.json', result)
    outputs = [p for p in WORK.rglob('*') if p.is_file()]
    outputs += [HERE/'later_execution.json', HERE/'later_protocol.json']
    outputs += list(HERE.glob('LATER4-*_baseline_execution.json')) + list(HERE.glob('LATER4-*.log'))
    write(HERE/'later_RF_seal.json', dict(protocol_sha256=digest, files={str(p):sha(p) for p in sorted(outputs)}))
    print(json.dumps(dict(terminal=True, cumulative_worker_seconds=total, budget_pass=result['budget_pass'])), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['freeze','run'])
    {'freeze':freeze,'run':run}[p.parse_args().action]()
