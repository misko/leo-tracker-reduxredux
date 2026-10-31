"""Frozen DS27 fast evaluation: public ALGO02/03 reuse, then exact installed ALGO04.

No geographic truth, RF collection, production writes, or scientific gate changes.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

STUDY = Path(__file__).resolve().parent
RELEASE = Path('/opt/leo-fast-graph/f9e262f96b6e2e75b397f69d50a0ea9104e293ef')
REPOSITORY = Path('/srv/bulk/leo-dev/fast-algo02-production-v1')
BASELINE = Path('/srv/bulk/leo/research/algo03-full-evaluation-20261030/runtime-baseline-production')
CANDIDATE = Path('/srv/bulk/leo/research/algo03-full-evaluation-20261030/runtime-candidate')
for directory in (RELEASE / 'src', RELEASE / 'tools', STUDY):
    sys.path.insert(0, str(directory))

from offline_algo04 import digest, inventory, read, write


def runner_module():
    path = REPOSITORY / 'tools/run_algo03_dataset_evaluation.py'
    spec = importlib.util.spec_from_file_location('ds27_frozen_dataset_runner', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fast_cases(document):
    return [c for c in document['cases'] if c['recording_format'] == 'short_window_iq_recording']


def paired_source(case, baseline, job, terminal):
    return (baseline['state'] == 'complete' and terminal.get('state') == 'complete'
            and case['input'] is not None
            and job.get('input_sha256') == case['input']['sha256']
            and terminal.get('input_sha256') == case['input']['sha256']
            and terminal.get('session_id') == case['input']['session_id']
            and terminal.get('baseline') == baseline['terminal']
            and (terminal.get('read_audit') or {}).get('verified') is True)


def verify_protocol(study):
    protocol = read(study / 'evaluation-protocol.json')
    for name, expected in protocol['source_hashes'].items():
        if digest(name) != expected:
            raise ValueError('Frozen coordinator dependency changed: ' + name)
    return protocol


def prepare(study):
    from algo04_production_worker import verify_release
    from leo.storage.fast_graph_position_v2 import FastGraphPositionStoreV2

    runner = runner_module()
    seal = read(study / 'input-availability-seal.json')
    for name, expected in seal['files'].items():
        if digest(name) != expected:
            raise ValueError('Frozen public input map changed: ' + name)
    if digest(study / 'dataset/manifest.json') != seal['dataset_manifest_sha256']:
        raise ValueError('DS27 membership changed')
    freezes = {str(root): runner.verify_runtime(root) for root in (BASELINE, CANDIDATE)}
    verify_release()
    runner.freeze_dataset(SimpleNamespace(
        manifest=study / 'dataset/manifest.json', historical_root=None,
        public_map=study / 'completed-algo02-job-map.json', input_map=study / 'public-input-map.json',
        dataset='DS27', study=study))
    dataset = read(study / 'datasets/DS27.json')
    fast = fast_cases(dataset)
    if len(dataset['cases']) != 28 or len(fast) != 15:
        raise ValueError('Frozen DS27 denominator differs from 28 total / 15 fast')
    input_hashes = {c['input']['sha256'] for c in fast if c['input']}
    completed = []
    store = FastGraphPositionStoreV2('/srv/bulk/leo')
    for job in store.completed_inputs(minimum_completed_utc_ns=1):
        if job.get('input_sha256') not in input_hashes:
            continue
        terminal, receipt = store.terminal(job)
        completed.append(dict(job=job, terminal_receipt=receipt,
                              historical_read_audit_verified=(terminal.get('read_audit') or {}).get('verified') is True))
    write(study / 'completed-algo03-job-map.json', completed)
    write(study / 'runtime-hashes.json', dict(
        runtimes={root: dict(freeze_sha256=digest(Path(root) / 'runtime-freeze.json'),
                             python=value['python'], files=value['files']) for root, value in freezes.items()},
        installed_ALGO04_release=str(RELEASE),
        installed_release_manifest_sha256=digest(RELEASE / 'release-manifest.json')))
    paths = [Path(__file__), study / 'offline_algo04.py', study / 'test_offline_algo04.py',
             study / 'test_coordinate_evaluation.py',
             REPOSITORY / 'tools/run_algo03_dataset_evaluation.py',
             study / 'dataset/manifest.json', study / 'input-availability-seal.json',
             study / 'public-input-map.json', study / 'completed-algo02-job-map.json',
             study / 'completed-algo03-job-map.json', study / 'datasets/DS27.json',
             study / 'runtime-hashes.json', BASELINE / 'runtime-freeze.json',
             CANDIDATE / 'runtime-freeze.json', RELEASE / 'release-manifest.json']
    write(study / 'evaluation-protocol.json', dict(
        schema='ds27-algo02-algo03-algo04-offline/v1', dataset_members=28,
        fast_cases=[c['case'] for c in fast], adaptive_cases_excluded_from_evaluation=13,
        all_inventory_members_retained=True, maximum_workers=12, maximum_seconds_per_stage=1200,
        threads_per_process=1, source_hashes={str(p): digest(p) for p in paths},
        baseline_runtime=str(BASELINE), candidate_runtime=str(CANDIDATE), algo04_release=str(RELEASE),
        public_ALGO03_reuse_requires_exact_ALGO02_and_qualified_immutable_terminal=True,
        same_observations_candidates_priors_budgets=True, arms=['c0', 'fitted_c'],
        no_GPS=True, no_new_RF=True, production_changed=False))
    print(json.dumps(dict(prepared=True, all_members=28, fast_cases=15,
                          fast_with_input=sum(c['input'] is not None for c in fast),
                          fast_with_completed_ALGO02=sum(c.get('production_job') is not None for c in fast),
                          reusable_ALGO03_candidates=len(completed))), flush=True)


def reuse_candidate(case, study, baseline, *, store=None):
    """Reuse only the public completed/export ports, with an exact paired baseline."""
    from algo04_cache import relocate
    from leo.storage.fast_graph_position_v2 import FastGraphPositionStoreV2

    folder = study / 'cases' / case['case']
    rejections = []
    store = store if store is not None else FastGraphPositionStoreV2('/srv/bulk/leo')
    for record in read(study / 'completed-algo03-job-map.json'):
        job = record['job']
        if not case['input'] or job.get('input_sha256') != case['input']['sha256']:
            continue
        # Pairing mismatches do not consume a numerical attempt.
        terminal, before = store.terminal(job)
        if before != record['terminal_receipt'] or not paired_source(case, baseline, job, terminal):
            rejections.append(dict(job_id=job['job_id'], reason='not_immutable_exact_paired_qualified_v2'))
            continue
        began = time.monotonic()
        destination = folder / 'public-algo03-export'
        descriptor = store.export_recovery(job, destination)
        output = folder / 'candidate-v2'
        output.mkdir(exist_ok=False)
        files = {name.removeprefix('recovery/'): expected for name, expected in descriptor['files'].items()
                 if name.startswith('recovery/')}
        relocation = relocate(destination / 'recovery', output / 'recovery',
                              descriptor['source_recovery_root'], files)
        shutil.copyfile(destination / 'incumbent-terminal.json', output / 'terminal.json')
        if digest(output / 'terminal.json') != before['sha256']:
            raise ValueError('Exported ALGO03 terminal differs from frozen public receipt')
        current, after = store.terminal(job)
        if before != after or current != terminal:
            raise ValueError('Public ALGO03 source changed during reuse')
        write(output / 'cache-relocation.json', relocation)
        receipt = dict(case=case['case'], dataset='DS27', phase='candidate', state='complete',
                       decision=terminal['decision'], reused_production=True,
                       exact_paired_ALGO02=True, source_unchanged=True,
                       source_job=job, source_terminal_receipt=before,
                       private_export_descriptor_sha256=digest(destination / 'descriptor.json'),
                       terminal_path=str(output / 'terminal.json'),
                       failure=terminal.get('failure'), read_audit=terminal.get('read_audit'),
                       seconds=terminal['recovery_seconds'], maximum_seconds=1200,
                       orchestration_wall_seconds=time.monotonic() - began)
        write(folder / 'candidate-receipt.json', receipt)
        return receipt
    write(folder / 'ALGO03-reuse-check.json', dict(rejections=rejections, reused=False))
    return None


def one(case_name, study):
    protocol = verify_protocol(study)
    runner = runner_module()
    dataset = read(study / 'datasets/DS27.json')
    case = next(c for c in fast_cases(dataset) if c['case'] == case_name)
    folder = study / 'cases' / case_name
    folder.mkdir(parents=True, exist_ok=True)
    receipt_path = folder / 'pipeline-receipt.json'
    if receipt_path.exists():
        return read(receipt_path)
    began = time.monotonic()
    summary = dict(case=case_name, dataset='DS27', state='failed',
                   arms=['c0', 'fitted_c'], no_GPS=True, production_changed=False)
    try:
        freezes = {str(root): runner.verify_runtime(root) for root in (BASELINE, CANDIDATE)}
        baseline = runner.baseline_one(case, study, BASELINE, Path(freezes[str(BASELINE)]['python']), 1200)
        summary['baseline'] = baseline['state']
        if (folder / 'candidate-receipt.json').exists():
            candidate = read(folder / 'candidate-receipt.json')
        else:
            candidate = reuse_candidate(case, study, baseline) if baseline['state'] == 'complete' else None
            if candidate is None:
                candidate = runner.candidate_one(case, study, CANDIDATE,
                                                  Path(freezes[str(CANDIDATE)]['python']), 1200)
        summary['candidate'] = candidate['state']
        output = folder / 'candidate-v3'
        command = [str(RELEASE / 'venv/bin/python'), '-B', str(study / 'offline_algo04.py'),
                   '--source-terminal', str(folder / 'candidate-v2/terminal.json'),
                   '--source-recovery', str(folder / 'candidate-v2/recovery'),
                   '--output', str(output), '--maximum-seconds', '1200']
        code, pid = runner.bounded(command, folder / 'algo04-worker.log', 1230,
                                   cwd=study, environment=runner.environment(RELEASE))
        numerical = read(output / 'receipt.json')
        summary.update(state=numerical['state'], numerical=numerical['state'],
                       numerical_returncode=code, numerical_process_id=pid,
                       decision=numerical.get('decision'), failure=numerical.get('failure', numerical.get('reason')),
                       ALGO03_reused=candidate.get('reused_production', False),
                       terminal_path=numerical.get('terminal_path'),
                       protocol_sha256=digest(study / 'evaluation-protocol.json'))
    except Exception as error:
        summary.update(state='failed', failure=f'{type(error).__name__}: {error}')
    summary['seconds'] = time.monotonic() - began
    write(receipt_path, summary)
    return summary


def batch(study, workers):
    if not 1 <= workers <= 12:
        raise ValueError('DS27 requires 1..12 concurrent case workers')
    protocol = verify_protocol(study)
    with (study / 'evaluation-coordinator.lock').open('a') as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        cases = protocol['fast_cases']
        receipts = []
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1',
                           OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
                           PYTHONPATH=os.pathsep.join(map(str, (RELEASE / 'src', RELEASE / 'tools', study))))
        runner = runner_module()

        def work(case):
            folder = study / 'cases' / case
            folder.mkdir(parents=True, exist_ok=True)
            receipt = folder / 'pipeline-receipt.json'
            if receipt.exists():
                return read(receipt)
            command = [sys.executable, '-B', str(Path(__file__)), 'one', '--study', str(study), '--case', case]
            try:
                code, pid = runner.bounded(command, folder / 'coordinator.log', 3750,
                                           cwd=study, environment=environment)
                if receipt.exists():
                    return read(receipt)
                reason = f'Case supervisor exited {code} without pipeline receipt'
            except Exception as error:
                reason = f'{type(error).__name__}: {error}'
            value = dict(case=case, dataset='DS27', state='failed', failure=reason,
                         all_failures_retained=True, no_GPS=True, production_changed=False)
            write(receipt, value)
            return value

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for future in as_completed([pool.submit(work, c) for c in cases]):
                receipt = future.result()
                receipts.append(receipt)
                print(json.dumps(receipt), flush=True)
                path = study / 'evaluation-progress.json'
                temporary = path.with_suffix('.partial')
                temporary.write_text(json.dumps(dict(total=len(cases), terminal=len(receipts),
                    all_terminal=len(receipts) == len(cases), receipts=receipts), indent=2) + '\n')
                temporary.replace(path)
        write(study / 'evaluation-seal.json', dict(
            cases=cases, all_terminal=True, protocol_sha256=digest(study / 'evaluation-protocol.json'),
            pipeline_receipts={c: digest(study / 'cases' / c / 'pipeline-receipt.json') for c in cases},
            no_GPS=True, production_changed=False))


def main():
    os.umask(0o022)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'one'))
    parser.add_argument('--study', type=Path, default=STUDY)
    parser.add_argument('--workers', type=int, default=12)
    parser.add_argument('--case')
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.study.resolve())
    elif args.command == 'run':
        batch(args.study.resolve(), args.workers)
    else:
        print(json.dumps(one(args.case, args.study.resolve())), flush=True)


if __name__ == '__main__':
    main()
