"""Plan or explicitly run frozen DS26 jobs; compare saved evaluation reports.

No arguments select planning, never inference. Full means all frozen members,
including unavailable inputs. GPS is used only after loading committed evidence.
"""

import argparse
import copy
import hashlib
import importlib
import json
import math
import os
import signal
import subprocess
import sys
import time
import uuid
from collections import Counter
from contextlib import suppress
from pathlib import Path

SNAPSHOT = Path('/srv/bulk/leo-dev/algo07v3-shortcuts-20261107')
QUICK = ('DS26-0002', 'DS26-0066', 'DS26-0102')
VERSIONS = {
    'algo07v3': ('leo.cli.algo07v3', 'leo.storage.localization_v3', 'LocalizationV3Store'),
    'algo07v4': ('leo.cli.algo07v4', 'leo.storage.localization_v4', 'LocalizationV4Store'),
    'algo07v5': ('leo.cli.algo07v5', 'leo.storage.localization_v5', 'LocalizationV5Store'),
}
ARMS = ('c0', 'fitted_c')
METRICS = ('gps_error_km', 'residual_rms_hz', 'frequency_score', 'associated_points')


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(value):
    return 'sha256:' + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    ).hexdigest()


def file_digest(path):
    with Path(path).open('rb') as stream:
        return 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    path = Path(path)
    temporary = path.with_suffix('.partial')
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def local_output(path):
    path = Path(path).resolve()
    if path.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only; evaluation output must be local')
    return path


def source_binding(path):
    path = Path(path).resolve()
    if not (path / 'leo').is_dir() and (path / 'src/leo').is_dir():
        path = path / 'src'
    files = {
        str(p.relative_to(path)): file_digest(p)
        for p in sorted((path / 'leo').rglob('*'))
        if p.is_file() and p.suffix in ('.py', '.so', '.h', '.c', '.inc')
    }
    if not files:
        raise ValueError('Source root must contain leo sources')
    return dict(root=str(path), sha256=digest(files), files=files)


def owned_import(name, source):
    root = source['root']
    if root not in sys.path:
        sys.path.insert(0, root)
    module = importlib.import_module(name)
    if not Path(module.__file__).resolve().is_relative_to(root):
        raise ValueError('Imported implementation differs from --source-root: ' + name)
    return module


def make_plan(args):
    training_policy = getattr(args, 'annotation_training_policy', None)
    control_policy = getattr(args, 'inclusion_control_policy', None)
    schedule_policy = getattr(args, 'joint_schedule_policy', None)
    if training_policy is not None and args.version != 'algo07v5':
        raise ValueError('--annotation-training-policy requires --version algo07v5')
    if control_policy is not None and args.version != 'algo07v5':
        raise ValueError('--inclusion-control-policy requires --version algo07v5')
    if schedule_policy is not None and args.version != 'algo07v5':
        raise ValueError('--joint-schedule-policy requires --version algo07v5')
    snapshot, output = args.snapshot.resolve(), local_output(args.output)
    inventory = read(snapshot / 'inventory.json')
    template = read(snapshot / 'template-request.json')
    members = inventory['members']
    by_case = {m['dataset_label']: m for m in members}
    if len(by_case) != len(members):
        raise ValueError('Duplicate frozen member')
    selected = args.cases.split(',') if args.cases else (
        list(by_case) if args.profile == 'full' else list(QUICK)
    )
    if len(set(selected)) != len(selected) or set(selected) - set(by_case):
        raise ValueError('Cases must be unique members of the frozen inventory')
    if args.profile == 'full' and set(selected) != set(by_case):
        raise ValueError('Full profile requires every frozen member')
    if not 1 <= args.repeats <= 100:
        raise ValueError('Repetitions must be in 1..100')
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 7200:
        raise ValueError('Per-worker timeout must be in (0, 7200] seconds')
    source = source_binding(args.source_root)
    training = {}
    if training_policy is not None:
        contract = owned_import('leo.contracts.localization_v5', source)
        training['annotation_training_policy'] = contract.annotation_training_policy(
            training_policy)
    if control_policy is not None:
        contract = owned_import('leo.contracts.localization_v5', source)
        training['inclusion_control_policy'] = contract.inclusion_control_policy(control_policy)
    if schedule_policy is not None:
        contract = owned_import('leo.contracts.localization_v5', source)
        training['joint_schedule_policy'] = contract.joint_schedule_policy(schedule_policy)
    manifest = read(args.native_manifest) if args.native_manifest else None
    references = read(args.references) if args.references else {}
    config = snapshot / 'inputs/config.json'
    config_sha = file_digest(config)
    if config_sha != 'sha256:' + inventory['config_sha256'].removeprefix('sha256:'):
        raise ValueError('Frozen configuration digest differs')
    batch = uuid.uuid4().hex[:16]
    rows = []
    for repetition in range(args.repeats):
        for case in selected:
            member = by_case[case]
            row = dict(case=case, repetition=repetition, availability=member['availability'],
                       input_sha256=member.get('input_sha256'),
                       tle_sha256=digest(member.get('causal_snapshots', {})))
            row['reference'] = references.get(case, template.get('evaluation_reference'))
            if member['availability'] != 'available':
                rows.append(dict(row, status='missing', request=None))
                continue
            request = copy.deepcopy(template)
            request.update(
                native_input=dict(path=str(snapshot / 'inputs' / case / 'native.json'),
                                  sha256=member['input_sha256']),
                track_config=dict(path=str(config), sha256=config_sha),
                tle_root=str(snapshot / 'inputs' / case / 'tle'),
                output_root=str(output / f'{case}-r{repetition}' / args.version / 'publication'),
                scan_identities=[member['session_id']], title=member['recording_id'],
                evaluation_reference=None,
            )
            request['identity'] = dict(
                run_id=f'{args.version}-{batch}-{case}-r{repetition}',
                session_id=member['session_id'], input_sha256=member['input_sha256'])
            row['workload_sha256'] = digest({
                k: v for k, v in request.items() if k not in ('identity', 'output_root', 'title')})
            if args.version in ('algo07v4', 'algo07v5') and manifest is not None:
                version = args.version.removeprefix('algo07')
                module = owned_import(f'leo.operations.localization_{version}_job', source)
                if training:
                    request = module.make_request(
                        request, manifest, annotation_training_policy=training_policy,
                        **({'inclusion_control_policy': control_policy}
                           if control_policy is not None else {}),
                        **({'joint_schedule_policy': schedule_policy}
                           if schedule_policy is not None else {}))
                else:
                    request = module.make_request(request, manifest)
            rows.append(dict(row, status='planned', request=request))
    compact = [{k: v for k, v in m.items() if k != 'causal_snapshots'} for m in members]
    return dict(schema_version=1, version=args.version,
                module=args.module or VERSIONS[args.version][0],
                profile=args.profile, snapshot=str(snapshot), output=str(output),
                inventory_sha256=file_digest(snapshot / 'inventory.json'),
                source=source, backend_manifest=manifest, timeout_seconds=args.timeout,
                evaluator=dict(path=str(Path(__file__).resolve()), sha256=file_digest(__file__)),
                backend_bound=args.version == 'algo07v3' or manifest is not None,
                selected=selected, members=compact, jobs=rows,
                missing=[m['dataset_label'] for m in members if m['availability'] != 'available'],
                config_sha256=config_sha, inference_requested=args.action == 'run', **training)


def descendants(pid):
    """Discover descendants even when the version CLI gives its worker a new session."""
    parents = {}
    for entry in Path('/proc').iterdir():
        if entry.name.isdecimal():
            with suppress(FileNotFoundError, ProcessLookupError, PermissionError):
                fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
                parents[int(entry.name)] = int(fields[1])
    found = {pid}
    while True:
        expanded = found | {p for p, parent in parents.items() if parent in found}
        if expanded == found:
            return found
        found = expanded


def supervise(command, log_path, timeout, environment):
    """Delegate the scientific deadline to the existing CLI, with a bounded outer watchdog.

    wait4 includes descendants reaped by the launcher. Forced outer cleanup cannot
    guarantee that accounting, so its CPU is explicitly incomplete and never compared.
    """
    began = time.monotonic()
    forced = terminating = False
    with Path(log_path).open('xb') as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                 env=environment, start_new_session=True)
        deadline = began + timeout + 5
        try:
            while True:
                pid, status, usage = os.wait4(child.pid, os.WNOHANG)
                if pid:
                    child.returncode = os.waitstatus_to_exitcode(status)
                    break
                if time.monotonic() >= deadline:
                    forced = True
                    for p in descendants(child.pid) - {child.pid}:
                        with suppress(ProcessLookupError):
                            os.kill(p, signal.SIGKILL)
                    with suppress(ProcessLookupError):
                        os.kill(child.pid, signal.SIGKILL if terminating else signal.SIGTERM)
                    terminating, deadline = True, time.monotonic() + 2
                time.sleep(0.02)
        finally:
            if child.returncode is None:
                for p in descendants(child.pid):
                    with suppress(ProcessLookupError):
                        os.kill(p, signal.SIGKILL)
                child.wait()
    return dict(returncode=child.returncode, wall_seconds=time.monotonic() - began,
                cpu_seconds=usage.ru_utime + usage.ru_stime, cpu_complete=not forced,
                status='timed_out' if forced else 'exited')


def project(evidence, reference):
    result = {}
    for arm in ARMS:
        summary = evidence['presentation']['arms'][arm]
        score = evidence['selected']['arms'][arm]
        error = None
        if reference is not None:
            lat, lon = map(math.radians, summary['endpoint_latlon'])
            rlat, rlon = map(math.radians, (reference['latitude_deg'], reference['longitude_deg']))
            a = (math.sin((lat - rlat) / 2) ** 2
                 + math.cos(lat) * math.cos(rlat) * math.sin((lon - rlon) / 2) ** 2)
            error = 12742.0176 * math.asin(math.sqrt(min(1, a)))
        result[arm] = dict(summary, gps_error_km=error,
                           frequency_score=score.get('negative_twice_elbo', score.get('objective')),
                           owners=evidence['selected']['owners'][arm])
    return result


def run_plan(plan, python):
    if plan['version'] in ('algo07v4', 'algo07v5') and plan['backend_manifest'] is None:
        version = plan['version'].removeprefix('algo07')
        raise ValueError(
            f'Running {version} requires --native-manifest; planning remains inference-free')
    output = Path(plan['output'])
    environment = dict(os.environ, PYTHONPATH=plan['source']['root'], PYTHONDONTWRITEBYTECODE='1',
                       OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    report = dict(schema_version=1, plan=plan, plan_sha256=digest(plan), results=[])
    for job in plan['jobs']:
        row = {k: v for k, v in job.items() if k != 'request'}
        if job['status'] != 'missing':
            folder = output / f"{job['case']}-r{job['repetition']}" / plan['version']
            folder.mkdir(parents=True, exist_ok=False)
            write(folder / 'request.json', job['request'])
            row['request_path'] = str(folder / 'request.json')
            try:
                request = job['request'].get('job', job['request'])
                if source_binding(plan['source']['root']) != plan['source']:
                    raise ValueError('Bound source changed since planning')
                if file_digest(plan['evaluator']['path']) != plan['evaluator']['sha256']:
                    raise ValueError('Evaluation implementation changed since planning')
                inventory_path = Path(plan['snapshot']) / 'inventory.json'
                if file_digest(inventory_path) != plan['inventory_sha256']:
                    raise ValueError('Frozen inventory changed since planning')
                for key in ('native_input', 'track_config'):
                    if file_digest(request[key]['path']) != request[key]['sha256']:
                        raise ValueError('Bound input changed: ' + key)
                member = next(m for m in read(inventory_path)['members']
                              if m['dataset_label'] == job['case'])
                snapshots = list(Path(request['tle_root']).rglob('*.tle'))
                by_name = {p.name: p for p in snapshots}
                if (len(by_name) != len(snapshots)
                        or set(by_name) != set(member['causal_snapshots'])):
                    raise ValueError('Frozen causal TLE membership changed')
                for name, sha in member['causal_snapshots'].items():
                    if file_digest(by_name[name]) != 'sha256:' + sha.removeprefix('sha256:'):
                        raise ValueError('Frozen causal TLE changed: ' + name)
                command = [python, '-B', '-m', plan['module'], 'run', '--request',
                           str(folder / 'request.json'), '--work-dir', str(folder / 'work'),
                           '--timeout', str(plan['timeout_seconds'])]
                if plan['version'] in ('algo07v4', 'algo07v5'):
                    write(folder / 'backend-manifest.json', plan['backend_manifest'])
                    command += ['--native-manifest', str(folder / 'backend-manifest.json')]
                row['command'] = command
                row['process'] = supervise(command, folder / 'stdout.log',
                                           plan['timeout_seconds'], environment)
                lines = (folder / 'stdout.log').read_text(errors='replace').splitlines()
                events = []
                for line in lines:
                    with suppress(json.JSONDecodeError):
                        events.append(json.loads(line))
                row['stdout_json'] = events
                row['supervisor'] = events[-1] if events else None
                stage_log = folder / 'work/worker.log'
                row['stage_log'] = str(stage_log) if stage_log.exists() else None
                row['stage_events'] = []
                if stage_log.exists():
                    for line in stage_log.read_text(errors='replace').splitlines():
                        with suppress(json.JSONDecodeError):
                            row['stage_events'].append(json.loads(line))
                supervisor = row['supervisor'] or {}
                worker = supervisor.get('worker') or {}
                if (row['process']['status'] == 'timed_out'
                        or supervisor.get('status') == 'timed_out'):
                    row['status'] = 'timed_out'
                elif row['process']['returncode'] or worker.get('status') != 'complete':
                    row['status'] = 'failed'
                else:
                    _, module, cls = VERSIONS[plan['version']]
                    store_class = getattr(owned_import(module, plan['source']), cls)
                    store = store_class(request['output_root'])
                    saved = store.load(request['identity']['run_id'])
                    if saved['evidence']['identity'] != request['identity']:
                        raise ValueError('Saved evidence identity differs from bound request')
                    row.update(status='complete', arms=project(saved['evidence'], job['reference']),
                               result_sha256=saved['receipt']['result_sha256'])
            except Exception as error:
                row.update(status='failed', error=f'{type(error).__name__}: {error}')
        report['results'].append(row)
        report['statuses'] = dict(Counter(r['status'] for r in report['results']))
        write(output / 'report.json', report)
    return report


def distribution(values):
    values = sorted(v for v in values if v is not None and math.isfinite(v))
    def percentile(q):
        if not values:
            return None
        x = (len(values) - 1) * q
        lo, hi = math.floor(x), math.ceil(x)
        return values[lo] + (values[hi] - values[lo]) * (x - lo)
    return dict(count=len(values), median=percentile(.5), p90=percentile(.9),
                p95=percentile(.95), max=values[-1] if values else None)


def compare(baseline, candidate):
    for key in ('inventory_sha256', 'selected', 'config_sha256', 'timeout_seconds'):
        if baseline['plan'][key] != candidate['plan'][key]:
            raise ValueError('Comparison requires matched frozen inputs: ' + key)
    def index(report):
        rows = {(r['case'], r['repetition']): r for r in report['results']}
        if len(rows) != len(report['results']):
            raise ValueError('Duplicate case/repetition')
        return rows
    left, right = index(baseline), index(candidate)
    pairs = []
    expected = {(j['case'], j['repetition'])
                for report in (baseline, candidate) for j in report['plan']['jobs']}
    for key in sorted(expected | left.keys() | right.keys()):
        a, b = left.get(key), right.get(key)
        pair = dict(case=key[0], repetition=key[1],
                    baseline_status=a['status'] if a else 'absent',
                    candidate_status=b['status'] if b else 'absent')
        if a and b and a['status'] == b['status'] == 'complete':
            if any(a[k] != b[k] for k in (
                    'input_sha256', 'tle_sha256', 'reference', 'workload_sha256')):
                raise ValueError('Paired input/reference binding differs')
            pair['arms'] = {}
            for arm in ARMS:
                x, y = a['arms'][arm], b['arms'][arm]
                changed = sum(x['owners'].get(k) != y['owners'].get(k)
                              for k in x['owners'].keys() | y['owners'].keys())
                metrics = {}
                for metric in METRICS:
                    av, bv = x.get(metric), y.get(metric)
                    delta = bv - av if av is not None and bv is not None else None
                    metrics[metric] = dict(baseline=av, candidate=bv, delta=delta)
                pair['arms'][arm] = dict(metrics, ownership_changes=changed)
            if a['process']['cpu_complete'] and b['process']['cpu_complete']:
                pair['timing'] = {m: dict(baseline=a['process'][m], candidate=b['process'][m],
                                          delta=b['process'][m] - a['process'][m])
                                  for m in ('wall_seconds', 'cpu_seconds')}
                for timing in pair['timing'].values():
                    av, bv = timing['baseline'], timing['candidate']
                    timing['speedup'] = av / bv if bv > 0 else None
                    timing['reduction_percent'] = 100 * (av - bv) / av if av > 0 else None
        pairs.append(pair)
    summaries = {}
    for arm in ARMS:
        summaries[arm] = {
            metric: {side: distribution(p['arms'][arm][metric][side]
                                        for p in pairs if 'arms' in p)
                     for side in ('baseline', 'candidate', 'delta')}
            for metric in METRICS}
    timings = {}
    for metric in ('wall_seconds', 'cpu_seconds'):
        usable = [p['timing'][metric] for p in pairs if 'timing' in p]
        av, bv = (sum(t[side] for t in usable) for side in ('baseline', 'candidate'))
        timings[metric] = {
            side: distribution(t[side] for t in usable)
            for side in ('baseline', 'candidate', 'delta', 'speedup', 'reduction_percent')}
        timings[metric]['aggregate'] = dict(
            baseline_sum=av, candidate_sum=bv, speedup=av / bv if bv > 0 else None,
            reduction_percent=100 * (av - bv) / av if av > 0 else None)
    return dict(schema_version=1, baseline_source=baseline['plan']['source'],
                candidate_source=candidate['plan']['source'], pairs=pairs, arms=summaries,
                statuses={s: dict(Counter(p[s + '_status'] for p in pairs))
                          for s in ('baseline', 'candidate')},
                timing=timings,
                note=('Only paired complete jobs enter metrics; failures/missing/timeout never '
                      'imply speedup. Frequency fit is separate from GPS accuracy.'))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith('--') and argv[0] not in ('--help', '-h'):
        argv.insert(0, 'plan')
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    for action in ('plan', 'run'):
        command = commands.add_parser(action)
        command.add_argument('--profile', choices=('quick', 'full'), default='quick')
        command.add_argument('--version', choices=VERSIONS, default='algo07v4')
        command.add_argument('--module', help='CLI module belonging to the selected version')
        command.add_argument('--snapshot', type=Path, default=SNAPSHOT)
        command.add_argument('--output', type=Path, required=True,
                             help='Fresh local directory; /srv/bulk is recommended')
        command.add_argument('--source-root', type=Path,
                             default=Path(__file__).resolve().parents[1] / 'src')
        command.add_argument('--native-manifest', type=Path)
        command.add_argument('--annotation-training-policy',
                             choices=('lbfgsb-full5-625-v1', 'lbfgsb-gn-fallback-full5-v1'),
                             help='Opt-in annotation training policy for algo07v5')
        command.add_argument('--inclusion-control-policy', choices=('native-complete-controls-v1',),
                             help='Opt-in exact native control reuse for algo07v5')
        command.add_argument('--joint-schedule-policy',
                             choices=('defer-factorized-unless-retry-v1',),
                             help='Opt-in conditional factorized diagnostics for algo07v5')
        command.add_argument('--references', type=Path, help='Per-case evaluation-only GPS map')
        command.add_argument('--cases', help='Comma-separated labels; quick defaults to 3 controls')
        command.add_argument('--repeats', type=int, default=1)
        command.add_argument('--timeout', type=float, default=1200)
        command.add_argument('--python', default=sys.executable)
    command = commands.add_parser('compare')
    command.add_argument('--baseline', type=Path, required=True)
    command.add_argument('--candidate', type=Path, required=True)
    command.add_argument('--output', type=Path, required=True, help='Fresh local directory')
    args = parser.parse_args(argv)
    try:
        if args.action == 'compare':
            result = compare(read(args.baseline), read(args.candidate))
            output = local_output(args.output)
            output.mkdir(parents=True, exist_ok=False)
            write(output / 'comparison.json', result)
        else:
            if args.module and args.module != VERSIONS[args.version][0]:
                raise ValueError('Module/version mismatch; register future versions explicitly')
            plan = make_plan(args)
            output = Path(plan['output'])
            output.mkdir(parents=True, exist_ok=False)
            write(output / 'plan.json', dict(plan, plan_sha256=digest(plan)))
            if args.action == 'run':
                result = run_plan(plan, args.python)
                print(json.dumps(dict(output=str(output), statuses=result['statuses'])))
                return int(any(r['status'] != 'complete' for r in result['results']))
        print(json.dumps(dict(output=str(output), action=args.action)))
        return 0
    except (ValueError, OSError, KeyError, ImportError) as error:
        print(f'{type(error).__name__}: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
