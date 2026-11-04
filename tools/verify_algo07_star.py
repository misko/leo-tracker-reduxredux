"""One entry point for bounded, exact ALGO07 versus ALGO07* research checks.

No inference settings or comparison tolerances are supplied by this wrapper.
The existing independent watcher, coordinator and strict comparators own them.
"""
import argparse
import contextlib
import fcntl
import importlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))

from leo.application.algo07_star import ALGORITHMS  # noqa: E402
from leo.cli.algo07_profile import destination, digest, write_new  # noqa: E402

SIDES = ('reference', 'candidate')
CONFIG = 'verify-algo07-star.json'


def read(path):
    return json.loads(Path(path).read_text())


def inputs(config):
    """Revalidate native bytes, and reject overlapping or production stores."""
    roots = [Path(config[s]).resolve(strict=True) for s in SIDES]
    if any(a.is_relative_to(b) for a, b in (roots, roots[::-1])):
        raise ValueError('Reference and candidate stores must be independent')
    receipts = []
    for root in roots:
        receipt = read(root / 'algo07-star-input.json')
        if (receipt['kind'] != 'algo07-star-native-evidence'
                or root == Path(receipt['source_root']).resolve()
                or root.is_relative_to('/mnt/qnap01')):
            raise ValueError('Private native evidence exports required')
        if receipt['run_id'] != config['run_id']:
            raise ValueError('Wrong native run')
        for row in receipt['files']:
            p = (root / row['path']).resolve(strict=True)
            if not p.is_relative_to(root) or digest(p) != row['sha256']:
                raise ValueError('Native evidence changed')
        receipts.append(receipt)
    if any(receipts[0][k] != receipts[1][k]
           for k in ('run_id', 'session_id', 'input_sha256')):
        raise ValueError('Different native observations')
    return receipts[0]


def initialize(args):
    from leo.storage.fast_scan import FastScanStore

    case = destination(args.case)
    if (case / CONFIG).exists():
        raise ValueError('Configuration already exists; use status, run or check')
    fixture = args.fixture.resolve(strict=True)
    config = dict(schema_version=1, kind='algo07-star-verification-case',
                  run_id=args.run_id, python=sys.executable,
                  reference=str((args.reference or case / 'reference').resolve()),
                  candidate=str((args.candidate or case / 'candidate').resolve()),
                  runtimes=str(fixture / 'runtimes-r2.json'),
                  manifest=str(fixture / 'frozen-r2.json'),
                  archive_manifest=str(fixture / 'frozen.json'),
                  archive_view=str(fixture / 'tle-view'))
    for key in ('runtimes', 'manifest', 'archive_manifest', 'archive_view'):
        if getattr(args, key, None):
            config[key] = str(getattr(args, key).resolve(strict=True))
    for side in SIDES:
        for suffix in ('execution', 'publication', 'evidence'):
            key = side + '_' + suffix
            if getattr(args, key, None):
                config[key] = str(getattr(args, key).resolve(strict=True))
    config['pins'] = {key: digest(Path(config[key]))
                      for key in ('runtimes', 'manifest', 'archive_manifest')}
    # An init is cheap: only public native documents, never a raw-IQ replay.
    for side in SIDES:
        root = Path(config[side])
        if not root.exists():
            FastScanStore(args.source).export_replay_inputs(args.run_id, root)
    inputs(config)
    write_new(case / CONFIG, config)
    return dict(state='initialized', case=str(case), next='status, then run each side')


def load(case):
    config = read(case / CONFIG)
    if config.get('kind') != 'algo07-star-verification-case' or config['schema_version'] != 1:
        raise ValueError('Unknown verification configuration')
    for key, sha in config['pins'].items():
        if digest(Path(config[key])) != sha:
            raise ValueError(f'Changed configuration input: {key}')
    specifications = read(config['runtimes'])
    if (tuple(specifications) != ALGORITHMS
            or any(specifications[a]['maximum_seconds'] != 1200 for a in ALGORITHMS)):
        raise ValueError('Original six-stage 1200-second budgets required')
    inputs(config)
    return config


def stage_status(root):
    rows, previous = [], None
    for number, algorithm in enumerate(ALGORITHMS, 1):
        module = importlib.import_module('leo.storage.fast_graph_position' +
                                        ('' if number == 1 else f'_v{number}'))
        store = getattr(module, 'FastGraphPositionStore' +
                        ('' if number == 1 else f'V{number}'))(root)
        if previous is None:
            jobs = list(store.inputs())
            if len(jobs) != 1:
                raise ValueError('Exactly one private native input required')
            job = jobs[0]
        else:
            job = store.job(previous)
        previous = store.status(job['job_id'])
        state = previous['state'] if previous else 'not_started'
        rows.append(dict(algorithm=algorithm, state=state))
        if state != 'complete':
            break
        store.terminal(job)
    return rows


def execution(case, config, side):
    # New wrapper receipts take precedence over an explicitly adopted old run.
    attempts = sorted(case.glob(f'verify-run-{side}-*/execution.json'))
    if attempts:
        return attempts[-1]
    if config.get(side + '_execution'):
        return Path(config[side + '_execution'])
    # Support the pre-wrapper cohort batch without renaming its evidence.
    attempts = sorted(case.glob(f'{side}-chain-*.json'))
    return attempts[-1] if attempts else None


def status(case, config):
    sides = {}
    for side in SIDES:
        receipt = execution(case, config, side)
        sides[side] = dict(stages=stage_status(Path(config[side])),
                           execution=str(receipt) if receipt else None,
                           execution_state=read(receipt)['state'] if receipt else 'unrecorded')
    return dict(state='status', sides=sides, parity_verified=False)


def reserve(case, stem):
    for n in range(1, 10000):
        path = destination(case / f'{stem}-{n:04d}')
        try:
            path.mkdir()
            return path
        except FileExistsError:
            continue
    raise ValueError('Too many attempts')


def replay_command(config, side, output):
    script = 'run_algo07_star_reference.py' if side == 'reference' else 'run_algo07_star.py'
    return ['timeout', '--kill-after=15', '1785', config['python'], '-B',
            str(REPO / 'tools/algo07_star_archive.py'), 'exec',
            '--view', config['archive_view'], '--manifest', config['archive_manifest'], '--',
            config['python'], '-B', str(REPO / 'tools' / script),
            '--root', config[side], '--runtimes', config['runtimes'],
            '--manifest', config['manifest'], '--maximum-seconds', '1500',
            '--output', str(output)]


def replay(case, config, side):
    # CLI lock supplements (does not replace) the components' actual job locks.
    with (case / f'verify-{side}.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prior = sorted(case.glob(f'verify-run-{side}-*'))
        if prior:
            last = prior[-1]
            if (not (last / 'outcome.json').exists()
                    or read(last / 'outcome.json')['exit_code'] != 0):
                raise ValueError('Previous attempt unfinished or failed; inspect before retrying')
        receipt = execution(case, config, side)
        if receipt and read(receipt)['state'] == 'stage_failed':
            raise ValueError('Scientific stage failed; retain and investigate this case')
        rows = stage_status(Path(config[side]))
        if any(r['state'] not in ('complete', 'not_started') for r in rows):
            raise ValueError('A stage is active or failed; inspect status instead of restarting')
        if len(rows) == 6 and rows[-1]['state'] == 'complete' and receipt:
            return dict(state=read(receipt)['state'], execution=str(receipt))
        if os.geteuid() != 0:
            raise ValueError('run needs sudo for its private read-only TLE mount namespace')
        attempt = reserve(case, 'verify-run-' + side)
        output = attempt / 'execution.json'
        command = replay_command(config, side, output)
        write_new(attempt / 'command.json',
                  dict(command=command, source_sha256=digest(Path(__file__))))
        env = dict(os.environ, PYTHONPATH=f'{REPO}/src:{REPO}/tools',
                   OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        with (attempt / 'process.log').open('xb') as log:
            process = subprocess.Popen(command, cwd=REPO, env=env, stdout=log, stderr=log)
            while True:
                try:
                    code = process.wait(timeout=30)
                    break
                except subprocess.TimeoutExpired:
                    print(f'{side}: still running; log {attempt / "process.log"}', flush=True)
        write_new(attempt / 'outcome.json', dict(exit_code=code))
        if code or not output.exists():
            raise ValueError(f'Execution failed ({code}); retained evidence: {attempt}')
        result = read(output)
        if result['state'] not in ('scientific_complete', 'checkpointed'):
            raise ValueError(f'Execution {result["state"]}; inspect {output}')
        return dict(state=result['state'], next_stage=result.get('next_stage'),
                    execution=str(output), next='Repeat run to resume, or check when both complete')


def verdict(science, publication, scope):
    science_ok = science.get('scientific_json_and_array_parity') is True
    figures_ok = publication is not None and publication.get('publication_exact') is True
    code = (1 if not science_ok else
            0 if scope == 'science' or figures_ok else
            2 if publication is None else 1)
    return dict(state=('PASS' if code == 0 else 'INCOMPLETE' if code == 2 else 'FAIL'),
                requested_scope=scope, scientific_parity=science_ok,
                publication_parity=figures_ok if publication is not None else 'not_checked',
                case_full_parity=science_ok and figures_ok, exit_code=code,
                ds26_equivalence_verified=False, speedup_established=False,
                production_modified=False)


def check(case, config, scope):
    from compare_algo07_star_links import compare
    from compare_algo07_star_publication import run as compare_publication
    from export_algo07_star_stages import run as export

    receipts = [execution(case, config, s) for s in SIDES]
    if any(p is None or read(p)['state'] != 'scientific_complete' for p in receipts):
        return dict(state='INCOMPLETE', exit_code=2,
                    reason='Both execution receipts must be complete')
    attempt = reserve(case, 'verify-check')
    exports = []
    try:
        for side in SIDES:
            existing = config.get(side + '_evidence')
            output = Path(existing) if existing else attempt / (side + '-evidence')
            if not existing:
                print(f'Exporting {side} through the public worker-evidence port', flush=True)
                with contextlib.redirect_stdout(io.StringIO()):
                    export(SimpleNamespace(root=Path(config[side]), output=output,
                                           through='ALGO07'))
            for algorithm in ALGORITHMS:
                descriptor = read(output / algorithm / 'descriptor.json')
                if Path(descriptor['source_store_root']).resolve() != Path(config[side]).resolve():
                    raise ValueError('Export belongs to a different private store')
            exports.append(output)
        print('Rehashing evidence and comparing all six scientific stages', flush=True)
        paths = (Path(config['runtimes']), Path(config['manifest']), *receipts)
        science = compare(*exports, classify_accounting=True, execution_paths=paths)
        write_new(attempt / 'science.json', science)
        publication = None
        if scope == 'all' and all(config.get(s + '_publication') for s in SIDES):
            with contextlib.redirect_stdout(io.StringIO()):
                publication = compare_publication(SimpleNamespace(
                    reference=Path(config['reference']), candidate=Path(config['candidate']),
                    reference_publication=Path(config['reference_publication']),
                    candidate_publication=Path(config['candidate_publication']),
                    run_id=config['run_id'], output=attempt / 'publication.json'))
        result = verdict(science, publication, scope)
        result.update(evidence=str(attempt),
                      configuration_sha256=digest(case / CONFIG),
                      executions={s: dict(path=str(p), sha256=digest(p))
                                  for s, p in zip(SIDES, receipts, strict=True)},
                      scientific_difference_count=len(science['scientific_differences']),
                      link_error_count=len(science['link_errors']))
    except (ValueError, OSError, KeyError) as error:
        result = dict(state='FAIL', exit_code=1, error=str(error), evidence=str(attempt))
    write_new(attempt / 'summary.json', result)
    return result


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest='operation', required=True)
    init = commands.add_parser('init', help='Save fixture paths; clone/adopt private native inputs')
    init.add_argument('--fixture', type=Path, required=True)
    init.add_argument('--run-id', required=True)
    init.add_argument('--source', type=Path, default=Path('/srv/bulk/leo'))
    for name in ('reference', 'candidate', 'runtimes', 'manifest',
                 'archive-manifest', 'archive-view'):
        init.add_argument('--' + name, type=Path)
    for side in SIDES:
        for suffix in ('execution', 'publication', 'evidence'):
            init.add_argument(f'--{side}-{suffix}', type=Path)
    state = commands.add_parser('status', help='Read stage progress; does not imply parity')
    run = commands.add_parser('run', help='Advance one side for at most 30 min; repeat to resume')
    run.add_argument('--side', choices=SIDES, required=True)
    verify = commands.add_parser('check', help='Rehash/compare completed runs; write a summary')
    verify.add_argument('--scope', choices=('all', 'science'), default='all')
    for side in SIDES:
        for suffix in ('execution', 'publication', 'evidence'):
            verify.add_argument(f'--{side}-{suffix}', type=Path)
    for sub in (init, state, run, verify):
        sub.add_argument('--case', type=Path, required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        case = destination(args.case)
        if args.operation == 'init':
            result = initialize(args)
        else:
            config = load(case)
            if args.operation == 'status':
                result = status(case, config)
            elif args.operation == 'run':
                result = replay(case, config, args.side)
            else:
                for side in SIDES:
                    for suffix in ('execution', 'publication', 'evidence'):
                        key = side + '_' + suffix
                        if getattr(args, key, None):
                            config[key] = str(getattr(args, key).resolve(strict=True))
                result = check(case, config, args.scope)
        print(json.dumps(result, indent=2))
        return result.get('exit_code', 0)
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps(dict(state='ERROR', error=str(error))), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
