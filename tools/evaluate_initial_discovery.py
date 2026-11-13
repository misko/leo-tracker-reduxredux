"""Freeze and run complete-worker initial-discovery pairs on whole recordings.

The direct baseline is the frozen fast v5 with zero recovery targets. Original
v3 evidence remains context in its independently frozen campaign. Planning never
runs inference. Every role uses its own actual evaluator and source bindings.
"""

import argparse
import copy
import fcntl
import hashlib
import importlib.util
import json
import math
import os
import random
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from initial_discovery_archive import archive_role, resources_ready

ORIGINAL = Path('/srv/bulk/leo-dev/ds26-ds29-evaluation-20261113')
PYTHON = '/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python'
FAST_FLAGS = {
    '--annotation-training-policy': 'lbfgsb-gn-fallback-full5-v1',
    '--inclusion-control-policy': 'native-complete-controls-v1',
    '--joint-schedule-policy': 'defer-factorized-unless-retry-v1',
    '--recovery-target-limit': '0',
}
SIDES = ('baseline', 'candidate')
ENVIRONMENT = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                   OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.partial')
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sha(path):
    with Path(path).open('rb') as stream:
        return 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()


def local(path):
    path = Path(path).resolve()
    if path.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    return path


def evaluator(path):
    spec = importlib.util.spec_from_file_location('discovery_evaluator', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def host():
    return dict(utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                loadavg=os.getloadavg(), affinity=sorted(os.sched_getaffinity(0)),
                pressure=Path('/proc/pressure/cpu').read_text())


def assignments(members, *, seed, profile, cases=None, development=(), quick_groups=4):
    """Randomize indivisible recording groups using availability only."""
    by_case = {member['dataset_label']: member for member in members}
    if len(by_case) != len(members) or not by_case:
        raise ValueError('Inventory membership must be nonempty and unique')
    groups = {}
    for member in members:
        key = member['recording_id']
        groups.setdefault(key, []).append(member['dataset_label'])
    if cases is not None:
        selected = cases.split(',')
        if len(selected) != len(set(selected)) or set(selected) - by_case.keys():
            raise ValueError('Cases must be unique frozen members')
        if any(set(group) & set(selected) and not set(group) <= set(selected)
               for group in groups.values()):
            raise ValueError('Explicit cases must include whole recording groups')
    elif profile == 'full':
        selected = sorted(by_case)
    else:
        eligible = sorted(key for key, group in groups.items()
                          if not set(group) & set(development)
                          and all(by_case[case]['availability'] == 'available' for case in group))
        if not 1 <= quick_groups <= len(eligible):
            raise ValueError('Quick group count exceeds untouched available groups')
        random.Random(seed).shuffle(eligible)
        selected = [case for key in eligible[:quick_groups] for case in sorted(groups[key])]
    selected_groups = sorted(key for key, group in groups.items() if set(group) <= set(selected))
    random.Random(seed + ':order').shuffle(selected_groups)
    ordered = [case for key in selected_groups for case in sorted(groups[key])]
    if profile == 'full' and set(ordered) != set(by_case):
        raise ValueError('Full profile must include every frozen member')
    if profile == 'quick' and set(ordered) & set(development):
        raise ValueError('Quick qualification cannot include development groups')
    return dict(group_key='whole recording_id', groups=groups, cases=ordered,
                development_cases=sorted(set(development) & by_case.keys()),
                missing_cases=sorted(case for case, member in by_case.items()
                                     if member['availability'] != 'available'),
                selection_uses='membership and availability only; no scientific outcomes or GPS')


def prepare(args):
    output = local(args.output)
    archive = local(args.archive_root) if args.archive_root else None
    if archive and (archive.is_relative_to(output) or output.is_relative_to(archive)):
        raise ValueError('Archive and staging roots must be disjoint')
    resources = dict(reserve_gib=args.reserve_gib, expected_gib=args.expected_gib,
                     stage_free_gib=args.stage_free_gib, archive_free_gib=args.archive_free_gib)
    if any(not math.isfinite(value) or value < 0 for value in resources.values()):
        raise ValueError('Finite nonnegative resource guards required')
    snapshot = args.snapshot.resolve()
    ev = evaluator(args.candidate_evaluator)
    inventory = read(snapshot / 'inventory.json')
    consumed = set()
    for path in args.development_split:
        document = read(path)
        consumed.update(document.get('development_cases', []))
        consumed.update(document.get('first_screen_cases', []))
    selected = assignments(inventory['members'], seed=args.seed, profile=args.profile,
                           cases=args.cases, development=consumed, quick_groups=args.quick_groups)
    if not 1 <= args.repeats <= 100 or not 1 <= args.timeout <= 2400:
        raise ValueError('Repetitions must be1..100 and timeout1..2400 seconds')
    if args.profile == 'development' and args.cases is None:
        raise ValueError('Development screen requires explicit cases')
    if any(m['dataset_label'].startswith('DS29-') for m in inventory['members']) and not args.references:
        raise ValueError('DS29 requires its explicit evaluation-only reference map')
    roles = dict(
        baseline=dict(source=ev.source_binding(args.baseline_source),
                      evaluator=str(args.baseline_evaluator.resolve()), initial=None,
                      native_manifest=str(args.baseline_native_manifest.resolve()),
                      backend_manifest=read(args.baseline_native_manifest)),
        candidate=dict(source=ev.source_binding(args.candidate_source),
                       evaluator=str(args.candidate_evaluator.resolve()),
                       native_manifest=str(args.candidate_native_manifest.resolve()),
                       backend_manifest=read(args.candidate_native_manifest),
                       initial=dict(id='initial-discovery-v1', seed_policy=args.initial_seed_policy,
                                    ranking_policy=args.initial_ranking_policy)))
    historical = args.historical_baseline_root.resolve() if args.historical_baseline_root else None
    if historical:
        protocol = read(historical / 'protocol.json')
        if (args.profile != 'full' or args.repeats != 1
                or protocol['snapshot'] != str(snapshot)
                or protocol['sources']['candidate'] != roles['baseline']['source']
                or protocol['candidate_limit'] != 0 or protocol['timeout'] != args.timeout
                or protocol['references'] != (str(args.references.resolve()) if args.references else None)):
            raise ValueError('Historical controls require the matched frozen full v5-zero cohort')
    paths = [Path(__file__), ROOT / 'initial_discovery_archive.py', snapshot / 'inventory.json', snapshot / 'template-request.json',
             snapshot / 'inputs/config.json', args.baseline_native_manifest.resolve(),
             args.candidate_native_manifest.resolve(),
             args.baseline_evaluator.resolve(), args.candidate_evaluator.resolve(),
             *[p.resolve() for p in args.development_split]]
    for role in roles.values():
        native = role['backend_manifest']
        paths += [Path(native[key]) for key in ('binary', 'source', 'wrapper')]
        paths += [Path(native['provider']['path'])]
    if args.references:
        paths.append(args.references.resolve())
    if historical:
        paths.append(historical / 'protocol.json')
    schedule = []
    for repetition in range(args.repeats):
        for index, case in enumerate(selected['cases']):
            schedule.append(dict(case=case, repetition=repetition,
                                 order=list(SIDES if (index + repetition) % 2 == 0 else reversed(SIDES))))
    return dict(schema_version=3 if historical else 2, snapshot=str(snapshot), output=str(output),
                historical_baseline_root=str(historical) if historical else None,
                archive_root=str(archive) if archive else None, resource_limits=resources,
                references=str(args.references.resolve()) if args.references else None,
                profile=args.profile, seed=args.seed, timeout=args.timeout, repeats=args.repeats,
                selection=selected, roles=roles, schedule=schedule,
                members=inventory['members'], bindings={str(p): sha(p) for p in paths},
                baseline='frozen fast v5, recovery_target_limit=0',
                original_v3_context=str(ORIGINAL), fast_flags=FAST_FLAGS,
                accuracy='Report c0 and fitted_c separately; DS29 references are operator locations.',
                performance='E2E CPU/work and contended wall only; serial repeated evidence required for a speed claim.')


def check_bindings(manifest):
    for name, expected in manifest['bindings'].items():
        if sha(name) != expected:
            raise ValueError('Frozen bound file changed: ' + name)
    ev = evaluator(manifest['roles']['candidate']['evaluator'])
    for side in SIDES:
        source = manifest['roles'][side]['source']
        if ev.source_binding(source['root']) != source:
            raise ValueError('Frozen source tree changed: ' + side)


def command(manifest, assignment, side, destination, cpus):
    role = manifest['roles'][side]
    args = ['taskset', '-c', cpus, PYTHON, '-B', role['evaluator'], 'run',
            '--profile', 'quick', '--snapshot', manifest['snapshot'],
            '--cases', assignment['case'], '--version', 'algo07v5',
            '--output', str(destination), '--timeout', str(manifest['timeout']),
            '--source-root', role['source']['root'], '--native-manifest', role['native_manifest']]
    for flag, value in manifest['fast_flags'].items():
        args += [flag, value]
    if manifest['references']:
        args += ['--references', manifest['references']]
    if role['initial'] is not None:
        args += ['--initial-seed-policy', role['initial']['seed_policy'],
                 '--initial-ranking-policy', role['initial']['ranking_policy']]
    return args


def validate_report(report, manifest, assignment, side, *, historical_output=None):
    plan = report['plan']
    role = manifest['roles'][side]
    ev = evaluator(role['evaluator'])
    if ev.digest(plan) != report['plan_sha256']:
        raise ValueError('Worker plan hash differs')
    expected = dict(source=role['source'], version='algo07v5', snapshot=manifest['snapshot'],
                    module='leo.cli.algo07v5',
                    output=historical_output or str(Path(manifest['output']) / (assignment['case'] + '-r' + str(assignment.get('repetition', 0))) / side),
                    selected=[assignment['case']], timeout_seconds=manifest['timeout'],
                    inventory_sha256=manifest['bindings'][str(Path(manifest['snapshot']) / 'inventory.json')],
                    config_sha256=manifest['bindings'][str(Path(manifest['snapshot']) / 'inputs/config.json')],
                    evaluator=dict(path=role['evaluator'], sha256=manifest['bindings'][role['evaluator']]),
                    backend_manifest=role['backend_manifest'])
    for key, value in expected.items():
        if plan[key] != value:
            raise ValueError('Worker binding differs: ' + key)
    if plan.get('initial_discovery_policy') != role['initial']:
        raise ValueError('Worker initial policy differs')
    policies = dict(annotation_training_policy='lbfgsb-gn-fallback-full5-v1',
                    inclusion_control_policy='native-complete-controls-v1',
                    joint_schedule_policy='defer-factorized-unless-retry-v1',
                    recovery_target_policy='rf-target-prefix-v1')
    for key, value in policies.items():
        if plan[key]['id'] != value:
            raise ValueError('Worker fast policy differs: ' + key)
    if plan['recovery_target_policy']['maximum_targets'] != 0:
        raise ValueError('Worker recovery target limit differs')
    job, = plan['jobs']
    row, = report['results']
    if row['case'] != assignment['case'] or job['case'] != assignment['case']:
        raise ValueError('Worker case differs')
    if row['repetition'] != 0 or job['repetition'] != 0:
        raise ValueError('One fresh worker repetition required')
    if row['status'] not in ('complete', 'missing', 'failed', 'timed_out'):
        raise ValueError('Unknown worker outcome')
    member, = [m for m in manifest['members'] if m['dataset_label'] == row['case']]
    if row['availability'] != member['availability'] or job['availability'] != member['availability']:
        raise ValueError('Worker availability differs')
    if (row['status'] == 'missing') != (member['availability'] != 'available'):
        raise ValueError('Worker missing status differs from frozen availability')
    if job.get('request'):
        request = job['request']
        if request['job']['evaluation_reference'] is not None:
            raise ValueError('GPS leaked into inference')
        if request.get('initial_discovery_policy') != role['initial']:
            raise ValueError('Request initial policy differs')
        template = read(Path(manifest['snapshot']) / 'template-request.json')
        expected_job = copy.deepcopy(template)
        expected_job.update(
            native_input=dict(path=str(Path(manifest['snapshot']) / 'inputs' / row['case'] / 'native.json'),
                              sha256=member['input_sha256']),
            track_config=dict(path=str(Path(manifest['snapshot']) / 'inputs/config.json'),
                              sha256=expected['config_sha256']),
            tle_root=str(Path(manifest['snapshot']) / 'inputs' / row['case'] / 'tle'),
            output_root=str(Path(plan['output']) / (row['case'] + '-r0') / 'algo07v5/publication'),
            scan_identities=[member['session_id']], title=member['recording_id'], evaluation_reference=None,
            identity=dict(run_id=request['job']['identity']['run_id'], session_id=member['session_id'],
                          input_sha256=member['input_sha256']))
        if request['job'] != expected_job or not expected_job['identity']['run_id'].startswith('v5-'):
            raise ValueError('Actual requested job differs from the frozen template/inventory')
        workload = digest({key: value for key, value in expected_job.items()
                           if key not in ('identity', 'output_root', 'title')})
        if row['workload_sha256'] != workload or job['workload_sha256'] != workload:
            raise ValueError('Actual requested workload digest differs')
        if request['backend_manifest'] != role['backend_manifest']:
            raise ValueError('Requested native manifest differs')
        for key in policies:
            if request.get(key) != plan[key]:
                raise ValueError('Requested fast policy differs: ' + key)
    elif member['availability'] == 'available':
        raise ValueError('Available worker requires its actual bound request')
    if (row['input_sha256'] != member.get('input_sha256')
            or row['tle_sha256'] != digest(member.get('causal_snapshots', {}))):
        raise ValueError('Worker scientific input differs')
    refs = read(manifest['references']) if manifest['references'] else {}
    template = read(Path(manifest['snapshot']) / 'template-request.json')
    if row['reference'] != job['reference'] or row['reference'] != refs.get(
            row['case'], template.get('evaluation_reference')):
        raise ValueError('Worker evaluation reference differs')
    return row


def inspect_publication(args):
    """Load through the role's public store in a fresh source-isolated process."""
    ev = evaluator(args.evaluator)
    source = ev.source_binding(args.source_root)
    store_module = ev.owned_import('leo.storage.localization_v5', source)
    canonical_digest = ev.owned_import('leo.contracts.digests', source).canonical_digest
    report = read(args.report)
    plan = report['plan']
    planned, = plan['jobs']
    row, = report['results']
    request = read(args.request)
    if (ev.digest(plan) != report['plan_sha256'] or source != plan['source']
            or plan['evaluator'] != dict(path=str(args.evaluator.resolve()), sha256=sha(args.evaluator))
            or planned['request'] != request or row['request_path'] != str(args.request)
            or row['result_sha256'] != args.result_sha256 or row['status'] != 'complete'
            or row['case'] != planned['case'] or row['repetition'] != planned['repetition']
            or row['process']['returncode'] != 0):
        raise ValueError('Report/request/source/evaluator binding differs')
    job = request['job']
    saved = store_module.LocalizationV5Store(job['output_root']).load(job['identity']['run_id'])
    evidence = saved['evidence']
    if evidence['identity'] != job['identity'] or saved['receipt']['result_sha256'] != args.result_sha256:
        raise ValueError('Public evidence identity/result binding differs')
    provenance = evidence['provenance']
    modules = provenance['modules']
    for name, module in modules.items():
        path = Path(module['path']).resolve()
        if (not path.is_relative_to(source['root'])
                or source['files'].get(str(path.relative_to(source['root'])))
                != 'sha256:' + module['sha256'].removeprefix('sha256:')):
            raise ValueError('Saved implementation module differs from bound source: ' + name)
    if canonical_digest({name: module['sha256'] for name, module in modules.items()}) != provenance['implementation_sha256']:
        raise ValueError('Saved implementation aggregate differs')
    request_sha256 = canonical_digest(request)
    if (row['reference'] != planned['reference']
            or provenance['request_sha256'] != request_sha256
            or provenance['native_backend']['manifest'] != request['backend_manifest']
            or request['backend_manifest'] != plan['backend_manifest']
            or ev.project(evidence, row['reference']) != row['arms']):
        raise ValueError('Public request/native/metric binding differs')
    for key in ('annotation_training_policy', 'inclusion_control_policy',
                'joint_schedule_policy', 'recovery_target_policy', 'initial_discovery_policy'):
        if request.get(key) != provenance.get(key):
            raise ValueError('Actual evidence policy differs: ' + key)
    receipts = provenance['native_backend']['receipts']
    counts = {key: sum(receipt['counts'].get(key, 0) for receipt in receipts)
              for key in sorted({key for receipt in receipts for key in receipt['counts']})}
    work = {key: provenance[key]['counts'] for key in (
        'annotation_training_work', 'inclusion_control_work', 'joint_schedule_work')
        if key in provenance}
    initial = evidence['audit']['initial']
    if request.get('initial_discovery_policy') != initial.get('initial_discovery_policy'):
        raise ValueError('Initial audit policy differs')
    inventory = evidence['audit']['recovery_inventory']
    recovery = dict(original_targets=inventory['original_selected_track_ids'],
                    omitted_targets=inventory['policy_omitted_track_ids'],
                    selected_targets=[row['track_id'] for row in inventory['selected_targets']],
                    consumed_targets=evidence['audit']['numerical_recovery']['completed_target_ids'])
    if recovery['selected_targets'] or recovery['consumed_targets']:
        raise ValueError('Zero recovery target policy executed a target')
    result = dict(public_store_validated=True, result_sha256=args.result_sha256,
                  request_sha256=request_sha256, report_sha256=sha(args.report),
                  source_sha256=source['sha256'], evaluator_sha256=sha(args.evaluator),
                  manifest_sha256=args.manifest_sha256,
                  backend_manifest_sha256=canonical_digest(request['backend_manifest']),
                  native_counts=counts, work=work,
                  initial_discovery_policy=initial.get('initial_discovery_policy'),
                  initial_keys=sorted(initial),
                  initial_counts={key: initial.get(key) for key in (
                      'unique_RF_hypotheses', 'fully_fitted_hypotheses',
                      'fresh_radio_seed_budget', 'selected_hypothesis')},
                  initial_ranking=initial.get('initial_discovery_ranking'),
                  recovery_inventory=recovery)
    if args.output.exists() and read(args.output) != result:
        raise ValueError('Saved work receipt differs from freshly validated public evidence')
    write(args.output, result)


def aggregate(manifest, records):
    ev = evaluator(manifest['roles']['candidate']['evaluator'])
    reports = {}
    for side in SIDES:
        source = manifest['roles'][side]['source']
        plan = dict(source=source, selected=manifest['selection']['cases'],
                    inventory_sha256=manifest['bindings'][str(Path(manifest['snapshot']) / 'inventory.json')],
                    config_sha256=manifest['bindings'][str(Path(manifest['snapshot']) / 'inputs/config.json')],
                    timeout_seconds=manifest['timeout'],
                    jobs=[dict(case=a['case'], repetition=a['repetition']) for a in manifest['schedule']])
        rows = []
        for assignment in manifest['schedule']:
            key = (assignment['case'], assignment['repetition'])
            report = records.get(key, {}).get(side)
            if report:
                row = copy.deepcopy(report['results'][0])
                row['repetition'] = assignment['repetition']
                if manifest.get('historical_baseline_root'):
                    # Comparison inputs are copies. Original process receipts
                    # stay unchanged in their original reports; historical
                    # wall/CPU values never enter paired timing arithmetic.
                    row['process'] = dict(cpu_complete=False)
                rows.append(row)
        reports[side] = dict(plan=plan, results=rows)
    result = ev.compare(reports['baseline'], reports['candidate'])
    for pair in result['pairs']:
        current = records.get((pair['case'], pair['repetition']), {})
        pair['actual_work'] = {side: current[side]['results'][0].get('actual_work')
                               for side in current}
        pair['stage_seconds'] = {
            side: {event['stage']: event['seconds'] for event in current[side]['results'][0]
                   .get('stage_events', []) if event.get('event') == 'stage'}
            for side in current}
    result.update(execution_mode='contended', headline_timing_eligible=False,
                  complete_coverage=len(records) == len(manifest['schedule']) and all(
                      set(value) == set(SIDES) for value in records.values()),
                  manifest_sha256=digest(manifest), expected_pairs=len(manifest['schedule']),
                  inventory_missing=manifest['selection']['missing_cases'])
    result['candidate_coverage_complete'] = all('candidate' in records.get(
        (a['case'], a['repetition']), {}) for a in manifest['schedule'])
    result['paired_coverage_complete'] = result['complete_coverage']
    if manifest.get('historical_baseline_root'):
        result.pop('timing', None)
        result.update(execution_mode='historical_controls_accuracy_only',
                      historical_baseline_pending=[a['case'] for a in manifest['schedule']
                          if 'baseline' not in records.get((a['case'], a['repetition']), {})],
                      note='Historical controls support matched accuracy/work only; no paired timing is computed.')
        for pair in result['pairs']:
            pair.pop('stage_seconds', None)
            pair['execution_modes'] = dict(baseline='historical_import' if pair['baseline_status'] != 'absent'
                                            else 'historical_pending', candidate='fresh_candidate'
                                            if pair['candidate_status'] != 'absent' else 'absent')
    return result


def validated_work(report, manifest, side, folder, report_path):
    row = report['results'][0]
    if row['status'] != 'complete':
        return report
    work_path = folder / (side + '-work.json')
    role = manifest['roles'][side]
    cmd = [PYTHON, '-B', str(Path(__file__).resolve()), 'inspect',
           '--source-root', role['source']['root'], '--evaluator', role['evaluator'],
           '--request', row['request_path'], '--result-sha256', row['result_sha256'],
           '--report', str(report_path), '--manifest-sha256', digest(manifest),
           '--output', str(work_path)]
    subprocess.run(cmd, env=dict(ENVIRONMENT, PYTHONPATH=role['source']['root']), check=True, cwd=ROOT)
    report = copy.deepcopy(report)
    report['results'][0]['actual_work'] = read(work_path)
    return report


def import_historical(manifest, assignment, folder):
    """Keep the original public report and request paths; import no fresh identity."""
    root = Path(manifest['historical_baseline_root'])
    origin = root / (assignment['case'] + '-r0')
    report_path, execution_path = origin / 'candidate/report.json', origin / 'candidate-execution.json'
    receipt_path = folder / 'baseline-historical-import.json'
    if not report_path.exists():
        if receipt_path.exists():
            raise ValueError('Previously imported historical report disappeared')
        return None
    execution = read(execution_path)
    command_args = execution['command']

    def flag(name):
        if command_args.count(name) != 1:
            raise ValueError('Historical command has an ambiguous binding: ' + name)
        return command_args[command_args.index(name) + 1]

    role = manifest['roles']['baseline']
    expected = dict(manifest['fast_flags'])
    expected.update({'--snapshot': manifest['snapshot'], '--cases': assignment['case'],
                     '--profile': 'quick',
                     '--version': 'algo07v5', '--source-root': role['source']['root'],
                     '--native-manifest': role['native_manifest']})
    if manifest['references']:
        expected['--references'] = manifest['references']
    elif '--references' in command_args:
        raise ValueError('Unexpected historical reference map')
    if (execution['execution_mode'] != 'bulk_contended' or role['evaluator'] not in command_args
            or any(flag(name) != value for name, value in expected.items())
            or float(flag('--timeout')) != manifest['timeout']):
        raise ValueError('Historical execution bindings differ')
    report = read(report_path)
    validate_report(report, manifest, assignment, 'baseline', historical_output=flag('--output'))
    report = validated_work(report, manifest, 'baseline', folder, report_path)
    receipt = dict(execution_mode='historical_import', source_report=str(report_path),
                   source_report_sha256=sha(report_path), source_execution=str(execution_path),
                   source_command_sha256=digest(command_args), manifest_sha256=digest(manifest),
                   public_work_sha256=sha(folder / 'baseline-work.json')
                   if report['results'][0]['status'] == 'complete' else None,
                   timing_eligible=False)
    if receipt_path.exists() and read(receipt_path) != receipt:
        raise ValueError('Historical import binding changed')
    write(receipt_path, receipt)
    return report


def run(manifest_path, cpus):
    manifest = read(manifest_path)
    output = local(manifest['output'])
    requested_cpus = {int(cpu) for cpu in cpus.split(',')}
    if not requested_cpus or not requested_cpus <= os.sched_getaffinity(0):
        raise ValueError('Requested CPUs are unavailable')
    output.mkdir(parents=True, exist_ok=True)
    archive_root = local(manifest['archive_root']) if manifest['archive_root'] else None
    if archive_root:
        archive_root.mkdir(parents=True, exist_ok=True)
    with (ROOT / 'discovery.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check_bindings(manifest)
        records, failures = {}, []
        for assignment in manifest['schedule']:
            case, repetition = assignment['case'], assignment['repetition']
            folder = output / (case + '-r' + str(repetition))
            folder.mkdir(exist_ok=True)
            records[(case, repetition)] = {}
            for side in assignment['order']:
                check_bindings(manifest)
                if side == 'baseline' and manifest.get('historical_baseline_root'):
                    imported = import_historical(manifest, assignment, folder)
                    if imported is not None:
                        records[(case, repetition)][side] = imported
                        if imported['results'][0]['status'] not in ('complete', 'missing'):
                            failures.append(dict(case=case, repetition=repetition, side=side,
                                                 status=imported['results'][0]['status']))
                    continue
                destination = folder / side
                report_path = destination / 'report.json'
                receipt_path = folder / (side + '-execution.json')
                expected_command = command(manifest, assignment, side, destination, cpus)
                if archive_root and receipt_path.exists():
                    prior = read(receipt_path)
                    if prior['command'] != expected_command:
                        raise ValueError('Saved execution command differs')
                    if prior.get('archive'):
                        archive_role(destination, archive_root / folder.name / side, receipt_path,
                                     staging_root=output, archive_root=archive_root)
                if not report_path.exists():
                    if destination.exists() or receipt_path.exists():
                        raise RuntimeError('Interrupted worker retained for investigation: ' + str(destination))
                    resources = resources_ready(output, archive_root, **manifest['resource_limits'])
                    if not resources['ready']:
                        write(output / 'resource-stop.json', dict(
                            status='admission_stopped', case=case, side=side, resources=resources, observed=host()))
                        raise RuntimeError('Resource guard stopped admission; completed evidence retained')
                    receipt = dict(command=expected_command, before=host(), execution_mode='contended',
                                   headline_timing_eligible=False)
                    write(receipt_path, receipt)
                    with (folder / (side + '.log')).open('x') as log:
                        process = subprocess.run(expected_command, env=ENVIRONMENT,
                                                 stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
                    receipt.update(returncode=process.returncode, after=host())
                    write(receipt_path, receipt)
                    if not report_path.exists():
                        failures.append(dict(case=case, repetition=repetition, side=side,
                                             status='evaluator_failed', receipt=str(receipt_path)))
                        continue
                receipt = read(receipt_path)
                if receipt['command'] != expected_command:
                    raise ValueError('Saved execution command differs')
                report = read(report_path)
                row = validate_report(report, manifest, assignment, side)
                report = validated_work(report, manifest, side, folder, report_path)
                if row['status'] not in ('complete', 'missing'):
                    failures.append(dict(case=case, repetition=repetition, side=side, status=row['status']))
                records[(case, repetition)][side] = report
                if archive_root:
                    archive_role(destination, archive_root / folder.name / side, receipt_path,
                                 staging_root=output, archive_root=archive_root)
                print(json.dumps(dict(case=case, repetition=repetition, side=side, status=row['status'])), flush=True)
            summary = aggregate(manifest, records)
            write(output / 'comparison.json', summary)
            write(output / 'progress.json', dict(completed_pairs=sum(set(r) == set(SIDES) for r in records.values()),
                                                expected=len(manifest['schedule']), statuses=summary['statuses'],
                                                failures=failures, updated=host()))
        done = summary['candidate_coverage_complete'] if manifest.get('historical_baseline_root') else summary['complete_coverage']
        write(output / 'terminal.json', dict(status='complete' if summary['complete_coverage'] else
                                            'candidate_complete' if done else 'incomplete',
                                            candidate_coverage_complete=summary['candidate_coverage_complete'],
                                            paired_coverage_complete=summary['complete_coverage'],
                                            failures=failures, after=host()))
    return 0 if done else 1


def refresh(manifest_path):
    """Read-only scientific refresh; import newly available controls, never infer."""
    manifest = read(manifest_path)
    if not manifest.get('historical_baseline_root'):
        raise ValueError('Refresh requires historical-control mode')
    output = local(manifest['output'])
    output.mkdir(parents=True, exist_ok=True)
    records = {}
    with (ROOT / 'discovery.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check_bindings(manifest)
        for assignment in manifest['schedule']:
            case, repetition = assignment['case'], assignment['repetition']
            folder = output / (case + '-r' + str(repetition))
            folder.mkdir(exist_ok=True)
            current = records[(case, repetition)] = {}
            imported = import_historical(manifest, assignment, folder)
            if imported is not None:
                current['baseline'] = imported
            stage = folder / 'candidate'
            receipt = folder / 'candidate-execution.json'
            if receipt.exists():
                execution = read(receipt)
                saved_command = execution['command']
                if (len(saved_command) < 3 or saved_command[:2] != ['taskset', '-c']
                        or saved_command != command(manifest, assignment, 'candidate', stage, saved_command[2])):
                    raise ValueError('Saved candidate execution command differs')
            if manifest['archive_root'] and receipt.exists() and read(receipt).get('archive'):
                archive_role(stage, Path(manifest['archive_root']) / folder.name / 'candidate', receipt,
                             staging_root=output, archive_root=Path(manifest['archive_root']))
            report_path = stage / 'report.json'
            if report_path.exists():
                if not receipt.exists():
                    raise ValueError('Candidate report has no execution provenance')
                report = read(report_path)
                validate_report(report, manifest, assignment, 'candidate')
                current['candidate'] = validated_work(report, manifest, 'candidate', folder, report_path)
        summary = aggregate(manifest, records)
        write(output / 'comparison.json', summary)
        write(output / 'refresh-status.json', dict(candidate_coverage_complete=summary['candidate_coverage_complete'],
                                                  paired_coverage_complete=summary['paired_coverage_complete'],
                                                  historical_baseline_pending=summary['historical_baseline_pending'],
                                                  statuses=summary['statuses'], after=host()))
        terminal_path = output / 'terminal.json'
        terminal = read(terminal_path) if terminal_path.exists() else {}
        failures = terminal.get('failures', []) + [dict(case=case, repetition=repetition, side=side,
            status=report['results'][0]['status']) for (case, repetition), current in records.items()
            for side, report in current.items() if report['results'][0]['status'] not in ('complete', 'missing')]
        failures = list({(f['case'], f['repetition'], f['side'], f['status']): f for f in failures}.values())
        terminal.update(status='complete' if summary['paired_coverage_complete'] else 'candidate_complete'
                        if summary['candidate_coverage_complete'] else 'incomplete',
                        candidate_coverage_complete=summary['candidate_coverage_complete'],
                        paired_coverage_complete=summary['paired_coverage_complete'], failures=failures,
                        refreshed=host())
        write(terminal_path, terminal)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    plan = commands.add_parser('plan')
    plan.add_argument('--snapshot', type=Path, required=True)
    plan.add_argument('--output', type=Path, required=True)
    plan.add_argument('--manifest', type=Path, required=True)
    plan.add_argument('--archive-root', type=Path,
                      help='Verified archive; original absolute staging paths remain symlinks')
    plan.add_argument('--reserve-gib', type=float, default=20)
    plan.add_argument('--expected-gib', type=float, default=10)
    plan.add_argument('--stage-free-gib', type=float, default=10)
    plan.add_argument('--archive-free-gib', type=float, default=10)
    plan.add_argument('--historical-baseline-root', type=Path,
                      help='Original full cohort root; reuse its unchanged candidate reports for accuracy/work only')
    plan.add_argument('--candidate-source', type=Path, required=True)
    plan.add_argument('--candidate-evaluator', type=Path, required=True)
    plan.add_argument('--baseline-source', type=Path, default=ORIGINAL / 'frozen-v5/src')
    plan.add_argument('--baseline-evaluator', type=Path, default=ORIGINAL / 'frozen-v5/tools/evaluate_algo07.py')
    plan.add_argument('--baseline-native-manifest', type=Path, default=ORIGINAL / 'native-001/manifest.json')
    plan.add_argument('--candidate-native-manifest', type=Path, required=True)
    plan.add_argument('--references', type=Path)
    plan.add_argument('--development-split', type=Path, action='append', default=[])
    plan.add_argument('--profile', choices=('development', 'quick', 'full'), default='quick')
    plan.add_argument('--cases')
    plan.add_argument('--quick-groups', type=int, default=4)
    plan.add_argument('--initial-seed-policy', choices=('legacy', 'anchor-round-robin-v1'), default='anchor-round-robin-v1')
    plan.add_argument('--initial-ranking-policy', choices=('legacy', 'warm-center-v1'), default='warm-center-v1')
    plan.add_argument('--seed', default='initial-discovery-ds26-ds29-20261113-v1')
    plan.add_argument('--repeats', type=int, default=1)
    plan.add_argument('--timeout', type=int, default=1200)
    execute = commands.add_parser('run')
    execute.add_argument('--manifest', type=Path, required=True)
    execute.add_argument('--cpus', required=True)
    update = commands.add_parser('refresh')
    update.add_argument('--manifest', type=Path, required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('--source-root', type=Path, required=True)
    inspect.add_argument('--evaluator', type=Path, required=True)
    inspect.add_argument('--request', type=Path, required=True)
    inspect.add_argument('--report', type=Path, required=True)
    inspect.add_argument('--manifest-sha256', required=True)
    inspect.add_argument('--result-sha256', required=True)
    inspect.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == 'plan':
        manifest = prepare(args)
        path = local(args.manifest)
        if path.exists() and read(path) != manifest:
            raise ValueError('Existing frozen manifest differs')
        write(path, manifest)
        print(path)
        return 0
    if args.action == 'inspect':
        inspect_publication(args)
        return 0
    if args.action == 'refresh':
        return refresh(args.manifest)
    return run(args.manifest, args.cpus)


if __name__ == '__main__':
    raise SystemExit(main())
