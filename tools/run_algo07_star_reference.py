"""Run unchanged production watcher entrypoints once per private reference stage.

This independent path deliberately does not invoke the candidate coordinator.
It keeps the original worker budgets and checkpoints before a stage if the
remaining bounded invocation cannot accommodate that budget.
"""
import argparse
import importlib
import json
import os
import resource
import time
from pathlib import Path

from run_algo07_star import verify_coverage, worker_environment

from leo.application.algo07_star import ALGORITHMS
from leo.application.automatic_fast_graph import execute
from leo.cli.algo07_profile import digest, verify, write_new


def watcher_command(algorithm, spec, root):
    number = int(algorithm[4:])-1
    module = 'leo.cli.fast_graph_position'+('' if number == 1 else f'_v{number}')
    pythonpath = spec.get('watcher_pythonpath', f'{spec["runtime"]}/src:{spec["runtime"]}/tools')
    command = ['/usr/bin/env', *worker_environment(spec, algorithm), f'PYTHONPATH={pythonpath}',
               spec['python'], '-B', '-m', module, '--bulk-root', str(root),
               '--maximum-seconds', str(spec['maximum_seconds']), '--once']
    if number > 1:
        # Admission cutoffs concern production rollout, not scientific inputs.
        # The private root contains exactly one fresh eligible scan.
        command += ['--minimum-completed-utc-ns', '1']
    if number > 2:
        command += ['--worker-root', spec['runtime']]
    return command


def run(args):
    if not 0 < args.maximum_seconds <= 1800:
        raise ValueError('Bounded reference invocation required')
    root = args.root.resolve(strict=True)
    receipt = json.loads((root/'algo07-star-input.json').read_text())
    if (receipt['kind'] != 'algo07-star-native-evidence' or
            root == Path(receipt['source_root']) or root.is_relative_to('/mnt/qnap01')):
        raise ValueError('Isolated native-input reference root required')
    specifications = json.loads(args.runtimes.read_text())
    frozen = json.loads(args.manifest.read_text())
    manifest_hash = digest(args.manifest)
    pins = {Path(row['path']).resolve() for row in frozen['files']}
    if args.runtimes.resolve() not in pins or set(specifications) != set(ALGORITHMS):
        raise ValueError('Complete frozen runtime specification required')
    if any(type(s['maximum_seconds']) is not int or not 1 <= s['maximum_seconds'] <= 1200
           for s in specifications.values()):
        raise ValueError('Original bounded worker budgets required')
    verify_coverage(specifications, frozen)
    if not verify(args.manifest)['verified']:
        raise ValueError('Frozen reference changed')
    started = time.monotonic()
    previous = None
    rows = []
    result = dict(state='checkpointed', stages=rows, production_modified=False,
                  scientific_parity_checked=False, script_sha256=digest(Path(__file__)),
                  runtime_manifest_sha256=manifest_hash, load_average=list(os.getloadavg()))
    for number, algorithm in enumerate(ALGORITHMS, 1):
        suffix = '' if number == 1 else f'_v{number}'
        module = importlib.import_module('leo.storage.fast_graph_position'+suffix)
        cls = getattr(module, 'FastGraphPositionStore'+('' if number == 1 else f'V{number}'))
        store = cls(root)
        if previous is None:
            jobs = list(store.inputs())
            if len(jobs) != 1 or jobs[0]['input_sha256'] != receipt['input_sha256']:
                raise ValueError('One matching native reference input required')
            job = jobs[0]
        else:
            job = store.job(previous)
        status = store.status(job['job_id'])
        executed = not status or status['state'] != 'complete'
        spec = specifications[algorithm]
        if (executed and
                args.maximum_seconds-(time.monotonic()-started) < spec['maximum_seconds']+60):
            result['next_stage'] = algorithm
            break
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        mark = time.monotonic()
        command = watcher_command(algorithm, spec, root)
        code = None
        if executed:
            log_path = args.output.with_name(args.output.stem+'-'+algorithm+'.log')
            with log_path.open('xb') as log:
                code = execute(command, log=log, timeout=spec['maximum_seconds']+45)
        previous = store.status(job['job_id'])
        elapsed = time.monotonic()-mark
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        row = dict(algorithm=algorithm, executed=executed, wall_seconds=elapsed,
                   exit_code=code, command=command, user_cpu_seconds=after.ru_utime-before.ru_utime,
                   system_cpu_seconds=after.ru_stime-before.ru_stime)
        rows.append(row)
        if code not in (None, 0) or not previous or previous['state'] != 'complete':
            result.update(state='stage_failed', failed_stage=algorithm)
            break
        store.terminal(job)
        if algorithm == args.through:
            result.update(state='scientific_complete' if algorithm == 'ALGO07' else 'checkpointed',
                          next_stage=None if algorithm == 'ALGO07' else ALGORITHMS[number])
            break
    verify_coverage(specifications, frozen)
    result['runtime_verification'] = verify(args.manifest)
    if digest(args.manifest) != manifest_hash or not result['runtime_verification']['verified']:
        raise ValueError('Frozen reference changed during execution')
    write_new(args.output, result)
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'runtimes', 'manifest', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--through', choices=ALGORITHMS, default='ALGO07')
    parser.add_argument('--maximum-seconds', type=int, default=1800)
    run(parser.parse_args())
