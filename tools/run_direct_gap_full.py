"""Run the frozen DS26 and DS29 direct-gap cohorts, then await historical controls."""

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HISTORICAL_UNIT = 'leo-ds26-ds29-evaluation-20261113.service'
COHORTS = ('DS26', 'DS29')
STATES = ('running_candidate', 'refreshing_controls', 'reporting',
          'waiting_historical', 'complete', 'incomplete', 'failed')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def local(path):
    path = Path(path).resolve()
    if path.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only: ' + str(path))
    return path


def save(path, value):
    temporary = path.with_name(path.name + '.partial')
    with temporary.open('w') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def manifest_scope(path):
    manifest = read(path)
    if manifest['profile'] != 'full' or manifest['repeats'] != 1:
        raise ValueError('Full single-repeat manifest required: ' + str(path))
    if manifest['fast_flags'].get('--recovery-target-limit') != '0':
        raise ValueError('Zero legacy recovery required: ' + str(path))
    roles = manifest['roles']
    if (roles['baseline'].get('initial') is not None
            or roles['candidate'].get('initial') is not None
            or roles['baseline'].get('direct_gap') is not None
            or roles['candidate'].get('direct_gap', {}).get('id') != 'direct-timing-gap-v1'):
        raise ValueError('Direct-gap candidate and legacy initial policies required: ' + str(path))
    historical = manifest.get('historical_baseline_root')
    if not historical:
        raise ValueError('Historical controls required: ' + str(path))
    members = [row['dataset_label'] for row in manifest['members']]
    scheduled = [row['case'] for row in manifest['schedule']]
    selected = manifest['selection']['cases']
    if (not members or len(members) != len(set(members))
            or sorted(scheduled) != sorted(members)
            or sorted(selected) != sorted(members)
            or any(row['repetition'] != 0 for row in manifest['schedule'])):
        raise ValueError('Manifest does not cover its frozen inventory exactly: ' + str(path))
    cohort = members[0].split('-', 1)[0]
    if cohort not in COHORTS or any(not case.startswith(cohort + '-') for case in members):
        raise ValueError('One DS26 or DS29 cohort required: ' + str(path))
    protocol = read(Path(historical) / 'protocol.json')
    if sorted(protocol['cases']) != sorted(members):
        raise ValueError('Historical protocol does not cover the exact cohort: ' + str(path))
    output = local(manifest['output'])
    if manifest.get('archive_root'):
        local(manifest['archive_root'])
    return cohort, output


def bindings(args):
    if len(args.manifest) != 2 or len({str(path.resolve()) for path in args.manifest}) != 2:
        raise ValueError('Exactly two distinct manifests required')
    paths = [args.runner, args.collector, *args.manifest]
    frozen = {str(path.resolve()): sha(path) for path in paths}
    scopes = {}
    for path in args.manifest:
        cohort, staging = manifest_scope(path)
        if cohort in scopes:
            raise ValueError('Duplicate cohort: ' + cohort)
        scopes[cohort] = dict(manifest=str(path.resolve()), staging=str(staging),
                              report=str(args.output / 'reports' / cohort.lower()))
    if set(scopes) != set(COHORTS):
        raise ValueError('Both DS26 and DS29 manifests required')
    owned = [args.output, *[Path(scope['staging']) for scope in scopes.values()],
             *[Path(scope['report']) for scope in scopes.values()]]
    if len({str(path.resolve()) for path in owned}) != len(owned):
        raise ValueError('Coordinator, staging, and report paths must be distinct')
    for report in (Path(scope['report']) for scope in scopes.values()):
        local(report)
    return frozen, scopes


def append_event(path, event):
    with path.open('a') as stream:
        stream.write(json.dumps(event, sort_keys=True) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def command(args, state, status_path, events_path, cohort, phase, argv):
    for path, expected in state['bindings'].items():
        if sha(path) != expected:
            raise ValueError('Frozen input changed: ' + path)
    state['status'] = phase
    state['sequence'] += 1
    number = state['sequence']
    logfile = args.output / 'logs' / f'{number:04d}-{cohort}-{phase}.log'
    logfile.parent.mkdir(parents=True, exist_ok=True)
    event = dict(sequence=number, cohort=cohort, phase=phase, argv=argv,
                 log=str(logfile), started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    state['active_command'] = event
    save(status_path, state)
    append_event(events_path, event)
    with logfile.open('x') as stream:
        result = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, check=False)
    event['returncode'] = result.returncode
    event['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    append_event(events_path, event)
    state['last_command'] = event
    state['active_command'] = None
    save(status_path, state)
    if result.returncode:
        raise RuntimeError(f'{phase} for {cohort} returned {result.returncode}; see {logfile}')


def service_state(unit):
    argv = ['systemctl', '--user', 'show', unit,
            '--property=LoadState,ActiveState,SubState,Result']
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=15,
                                check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return dict(state='unknown', error=str(error))
    observed = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    active = observed.get('ActiveState')
    state = ('unknown' if result.returncode != 0 else
             'stopped' if observed.get('LoadState') == 'not-found'
             or active in ('inactive', 'failed') else
             'active' if active in ('active', 'activating', 'deactivating', 'reloading')
             else 'unknown')
    return dict(state=state, observed=observed, argv=argv, returncode=result.returncode,
                stderr=result.stderr.strip())


def refresh_collect(args, state, status_path, events_path, cohort):
    scope = state['scopes'][cohort]
    command(args, state, status_path, events_path, cohort, 'refreshing_controls',
            [sys.executable, '-B', str(args.runner), 'refresh', '--manifest',
             scope['manifest']])
    command(args, state, status_path, events_path, cohort, 'reporting',
            [sys.executable, '-B', str(args.collector), '--manifest',
             scope['manifest'], '--runner', str(args.runner), '--output',
             scope['report']])
    report = read(Path(scope['report']) / 'summary.json')
    if report.get('candidate_coverage_complete') is not True:
        raise ValueError('Collector lost candidate coverage: ' + cohort)
    state['coverage'][cohort] = dict(
        candidate_coverage_complete=report['candidate_coverage_complete'],
        paired_coverage_complete=report['paired_coverage_complete'],
        expected_count=report['expected_count'], statuses=report['statuses'],
        scientific_failures=report['scientific_failures'], report=scope['report'])
    save(status_path, state)


def run(args):
    args.output = local(args.output)
    args.runner = args.runner.resolve()
    args.collector = args.collector.resolve()
    args.manifest = [path.resolve() for path in args.manifest]
    if args.cpus != '21' or args.interval < 300:
        raise ValueError('This study requires CPU 21 and a control interval '
                         'of at least 300 seconds')
    args.output.mkdir(parents=True, exist_ok=True)
    lock_path = local(args.lock_file) if args.lock_file else args.output / 'coordinator.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        status_path = args.output / 'status.json'
        events_path = args.output / 'commands.jsonl'
        try:
            frozen, scopes = bindings(args)
        except Exception as error:
            if status_path.exists():
                prior = read(status_path)
                prior['status'] = 'failed'
                prior['error'] = str(error)
                save(status_path, prior)
            raise
        if status_path.exists():
            state = read(status_path)
            if (state['bindings'] != frozen or state['scopes'] != scopes
                    or state['historical_unit'] != args.historical_unit):
                state['status'] = 'failed'
                state['error'] = 'Existing coordinator is bound to different frozen inputs'
                save(status_path, state)
                raise ValueError('Existing coordinator is bound to different frozen inputs')
            if state.get('active_command'):
                state['status'] = 'failed'
                state['error'] = ('Interrupted command retained for investigation; '
                                  'no automatic retry')
                save(status_path, state)
                raise RuntimeError(state['error'])
            if state['status'] in ('complete', 'incomplete', 'failed'):
                return 0 if state['status'] == 'complete' else 1
        else:
            state = dict(status='running_candidate', bindings=frozen, scopes=scopes,
                         historical_unit=args.historical_unit, sequence=0,
                         candidate_done=[], active_command=None, coverage={})
            save(status_path, state)
        try:
            for cohort in COHORTS:
                if cohort in state['candidate_done']:
                    continue
                scope = scopes[cohort]
                command(args, state, status_path, events_path, cohort, 'running_candidate',
                        [sys.executable, '-B', str(args.runner), 'run', '--manifest',
                         scope['manifest'], '--cpus', args.cpus])
                terminal = read(Path(scope['staging']) / 'terminal.json')
                if terminal.get('candidate_coverage_complete') is not True:
                    raise ValueError('Runner returned success without candidate coverage: '
                                     + cohort)
                state['candidate_done'].append(cohort)
                state['coverage'][cohort] = terminal
                save(status_path, state)
                refresh_collect(args, state, status_path, events_path, cohort)
            while True:
                for cohort in COHORTS:
                    coverage = state['coverage'].get(cohort, {})
                    if coverage.get('paired_coverage_complete') is not True:
                        refresh_collect(args, state, status_path, events_path, cohort)
                if all(state['coverage'][cohort]['paired_coverage_complete'] for cohort in COHORTS):
                    state['status'] = 'complete'
                    state['completion_basis'] = ('paired_coverage; scientific failures '
                                                 'retained separately')
                    save(status_path, state)
                    return 0
                historical = service_state(args.historical_unit)
                state['historical_service'] = historical
                state['status'] = ('incomplete' if historical['state'] == 'stopped'
                                   else 'waiting_historical')
                save(status_path, state)
                if historical['state'] == 'stopped':
                    return 1
                time.sleep(args.interval)
        except Exception as error:
            state['status'] = 'failed'
            state['error'] = str(error)
            save(status_path, state)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--collector', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, action='append', required=True)
    parser.add_argument('--cpus', default='21')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--historical-unit', default=HISTORICAL_UNIT)
    parser.add_argument('--interval', type=int, default=300)
    parser.add_argument('--lock-file', type=Path)
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    raise SystemExit(main())
