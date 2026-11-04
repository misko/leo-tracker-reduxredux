"""Time one fresh GLRT-ready-to-publication path using the existing pinned drivers.

Run reference and candidate sequentially in distinct invocations. This is not
raw-IQ-to-publication timing or an equivalence gate. Explicit checkpoint mode
advances only verified completed stages, never retries failed work, and keeps one
outer timer through publication. Incomplete paths never earn a speedup claim.
"""
import argparse
import fcntl
import json
import os
import subprocess
import time
from pathlib import Path

from verify_algo07_star import CONFIG, SIDES, digest, load, read, replay_command, stage_status

from leo.cli.algo07_profile import destination, verify, write_new

ALGORITHMS = tuple(f'ALGO{i:02d}' for i in range(2, 8))


def fresh_command(config, side, output):
    command = replay_command(config, side, output)
    index = command.index('--maximum-seconds') + 1
    if command[index] != '1500':
        raise ValueError('Unexpected coordinator budget')
    # Both paths get the same longer invocation admission window. All six
    # scientific worker limits remain pinned at 1200 seconds. The existing
    # outer timeout remains 1785 seconds; a timeout never earns a timing ratio.
    command[index] = '1800'
    return command


def require_fresh(config, side):
    if stage_status(Path(config[side])) != [dict(algorithm='ALGO02', state='not_started')]:
        raise ValueError('Timing requires a fresh path with no completed or active stages')


def publication_command(config, side, plan, output):
    import hashlib

    code = plan['driver_code']
    if hashlib.sha256(code.encode()).hexdigest() != plan['driver_sha256']:
        raise ValueError('Publication driver hash mismatch')
    return ['timeout', '--kill-after=15', '600', plan['python'], '-B', '-c', code,
            config[side], str(output), config['run_id']]


def execute(command, environment, output):
    write_new(output.with_suffix('.command.json'), dict(command=command, environment=environment))
    start = time.monotonic()
    with output.with_suffix('.log').open('xb') as log:
        result = subprocess.run(command, env={**os.environ, **environment},
                                stdout=log, stderr=subprocess.STDOUT, check=False)
    receipt = dict(returncode=result.returncode, wall_seconds=time.monotonic() - start)
    write_new(output.with_suffix('.execution.json'), receipt)
    return receipt


def bound_outer_timeout(command, remaining):
    if command[:2] != ['timeout', '--kill-after=15'] or remaining <= 0:
        raise ValueError('A positive bounded research command is required')
    bounded = list(command)
    bounded[2] = str(min(int(command[2]), remaining))
    return bounded


def checkpointed_inference(config, side, output, environment, deadline):
    """At most six advancing invocations, inside one 30-minute research limit."""
    attempts, completed = [], 0
    started = time.monotonic()
    for number in range(1, 7):
        remaining = int(deadline - time.monotonic())
        if remaining <= 0:
            raise ValueError('Research timing deadline exhausted; no complete-path timing')
        directory = output / f'inference-attempt-{number:04d}'
        directory.mkdir()
        receipt_path = directory / 'inference.json'
        command = bound_outer_timeout(fresh_command(config, side, receipt_path), remaining)
        receipt = execute(command, environment, directory / 'process')
        if receipt['returncode'] != 0:
            raise ValueError('Inference process failed; checkpoint mode never retries failed work')
        value = read(receipt_path)
        rows = stage_status(Path(config[side]))
        count = sum(row['state'] == 'complete' for row in rows)
        attempts.append(dict(receipt_path=str(receipt_path), receipt_sha256=digest(receipt_path),
                             state=value['state'], completed_stages=count, **receipt))
        write_new(directory / 'progress.json', attempts[-1])
        if count <= completed or [row['algorithm'] for row in rows] != list(ALGORITHMS[:len(rows)]):
            raise ValueError('Checkpoint made no verified forward progress')
        if value['state'] == 'scientific_complete':
            if count != 6 or len(rows) != 6:
                raise ValueError('Completed inference does not have six completed public stages')
            return dict(returncode=0, wall_seconds=time.monotonic() - started,
                        attempts=attempts), receipt_path
        if (value['state'] != 'checkpointed' or count >= 6
                or value.get('next_stage') != ALGORITHMS[count]
                or rows != [dict(algorithm=a, state='complete') for a in ALGORITHMS[:count]]
                + [dict(algorithm=ALGORITHMS[count], state='not_started')]):
            raise ValueError('Only a verified completed checkpoint may advance')
        completed = count
        print(f'{side}: verified {completed}/6 stages; advancing checkpoint', flush=True)
    raise ValueError('Six advancing invocations exhausted without completion')


def run(args):
    case = args.case.resolve(strict=True)
    with (case / f'verify-{args.side}.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return run_locked(args, case)


def run_locked(args, case):
    config = load(case)
    if not config.get('candidate_terminal_read_reuse'):
        raise ValueError('This protocol compares the pinned terminal-read candidate')
    require_fresh(config, args.side)
    plan = read(args.publication_plan)
    if (digest(args.presentation_manifest) != plan['manifest_sha256']
            or not verify(args.presentation_manifest)['verified']):
        raise ValueError('Frozen presentation runtime changed')
    output = destination(args.output)
    output.mkdir(exist_ok=False)
    inference_receipt = output / 'inference.json'
    inference_command = fresh_command(config, args.side, inference_receipt)
    publish_command = publication_command(config, args.side, plan, output / 'publication')
    repo = Path(__file__).resolve().parents[1]
    threads = dict(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    env = dict(threads, PYTHONPATH=f'{repo}/src:{repo}/tools')
    renderer = Path(plan['renderer'])
    render_env = dict(threads, PYTHONPATH=f'{renderer}/src:{renderer}/tools')
    summary = dict(kind='algo07-star-glrt-ready-timing', side=args.side,
                   state='incomplete', completed_path_seconds=None,
                   configuration_sha256=digest(case / CONFIG),
                   script_sha256=digest(Path(__file__)),
                   publication_plan_sha256=digest(args.publication_plan),
                   presentation_manifest_sha256=digest(args.presentation_manifest),
                   coordinator_admission_seconds=1800, scientific_stage_seconds=1200,
                   load_average_start=list(os.getloadavg()),
                   native_glrt_included=False, acquisition_included=False,
                   production_queue_included=False, scientific_parity_verified=False,
                   scope='Fresh private native evidence through eight published artifacts',
                   preflight_and_comparison_excluded=True, cache_condition='OS cache uncontrolled')
    resume = getattr(args, 'resume_completed_checkpoints', False)
    summary.update(resume_completed_checkpoints=resume,
                   total_research_limit_seconds=1800 if resume else None)
    write_new(output / 'plan.json', summary)
    start = time.monotonic()
    try:
        print(f'{args.side}: timing fresh six-stage inference', flush=True)
        if resume:
            summary['inference'], inference_receipt = checkpointed_inference(
                config, args.side, output, env, start + 1800)
        else:
            summary['inference'] = execute(inference_command, env, output / 'inference-process')
        summary['final_inference_receipt'] = str(inference_receipt)
        if summary['inference']['returncode'] != 0:
            raise ValueError('Inference process failed; no complete-path timing')
        if read(inference_receipt)['state'] != 'scientific_complete':
            raise ValueError('Inference checkpointed or failed; no complete-path timing')
        print(f'{args.side}: timing first publication', flush=True)
        if resume:
            remaining = int(start + 1800 - time.monotonic())
            if remaining <= 0:
                raise ValueError('Research timing deadline exhausted before publication')
            publish_command = bound_outer_timeout(publish_command, remaining)
        summary['publication'] = execute(
            publish_command, render_env, output / 'publication-process')
        elapsed = time.monotonic() - start
        if summary['publication']['returncode'] != 0:
            raise ValueError('Publication failed; no complete-path timing')
        last = (output / 'publication-process.log').read_text().splitlines()[-1]
        published = json.loads(last)
        summary['published'] = published
        if (published['artifacts'] != 8 or not published['grid_complete']
                or published['grid_evaluated'] != published['grid_planned']):
            raise ValueError('Incomplete artifacts or grid; no qualified complete-path timing')
        if (load(case) != config or not verify(args.presentation_manifest)['verified']
                or digest(Path(__file__)) != summary['script_sha256']):
            raise ValueError('Implementation or inputs changed during timing')
        summary.update(state='completed_unqualified', completed_path_seconds=elapsed)
    except (ValueError, OSError, KeyError) as error:
        summary['error'] = str(error)
    summary.update(observed_trial_seconds=time.monotonic() - start,
                   load_average_end=list(os.getloadavg()))
    write_new(output / 'summary.json', summary)
    print(json.dumps({k: v for k, v in summary.items() if k != 'published'}, indent=2))
    return 0 if summary['state'] == 'completed_unqualified' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--side', choices=SIDES, required=True)
    parser.add_argument('--publication-plan', type=Path, required=True)
    parser.add_argument('--presentation-manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume-completed-checkpoints', action='store_true',
                        help='Advance verified checkpoints within one 1800-second total bound')
    raise SystemExit(run(parser.parse_args()))
