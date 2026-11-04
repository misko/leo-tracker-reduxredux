"""Read-only DS26 progress from verifier receipts; never a parity acceptance gate.

This checks configuration and execution bindings, not the exported scientific
files. Unfinished receipt directories do not establish that a process is alive.
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

from verify_algo07_star import CONFIG, SIDES, digest, execution, read


def side_state(case, config, side):
    attempts = sorted(case.glob(f'verify-run-{side}-*'))
    if attempts:
        outcome = attempts[-1] / 'outcome.json'
        if not outcome.exists():
            return 'unfinished_attempt_receipt'
        if read(outcome)['exit_code'] != 0:
            return 'failed_attempt'
    receipt = execution(case, config, side)
    return read(receipt)['state'] if receipt else 'not_recorded'


def check_history(case, config):
    rows = []
    for attempt in sorted(case.glob('verify-check-*')):
        path = attempt / 'summary.json'
        if not path.exists():
            rows.append(dict(attempt=attempt.name, state='unfinished_check_receipt'))
            continue
        value = read(path)
        if value['state'] not in ('PASS', 'FAIL', 'INCOMPLETE'):
            raise ValueError('Unknown check state: ' + str(path))
        science = value.get('scientific_parity') is True
        full = value.get('case_full_parity') is True
        if value['state'] == 'PASS' and not science:
            raise ValueError('PASS without scientific parity: ' + str(path))
        if full and (not science or value.get('publication_parity') is not True
                     or value.get('requested_scope') != 'all' or value['state'] != 'PASS'):
            raise ValueError('Inconsistent full-case claim: ' + str(path))
        if science:
            if (value.get('configuration_sha256') != digest(case / CONFIG)
                    or value.get('scientific_difference_count') != 0
                    or value.get('link_error_count') != 0):
                raise ValueError('Unbound or contradictory scientific pass: ' + str(path))
            for side in SIDES:
                binding = value['executions'][side]
                receipt = Path(binding['path'])
                if (digest(receipt) != binding['sha256']
                        or read(receipt)['state'] != 'scientific_complete'
                        or receipt != execution(case, config, side)):
                    raise ValueError('Passed check does not bind current executions: ' + str(path))
        rows.append(dict(attempt=attempt.name, state=value['state'],
                         requested_scope=value.get('requested_scope'),
                         recorded_scientific_parity=science, recorded_full_parity=full,
                         summary_sha256=digest(path), error=value.get('error')))
    return rows


def report(plan_path, iteration):
    plan = read(plan_path)
    if plan.get('kind') != 'algo07-star-cohort-execution-plan':
        raise ValueError('Frozen cohort execution plan required')
    members = plan['members']
    labels = [m['dataset_label'] for m in members]
    available = [m['dataset_label'] for m in members if m['availability'] == 'available']
    if (len(set(labels)) != len(labels) or len(members) != plan['fast_members']
            or len(available) != plan['available_members']
            or len(members) - len(available) != plan['unavailable_members']
            or set(available) != set(plan['execution_order'])
            or len(available) != len(plan['execution_order'])
            or any(not re.fullmatch(r'DS26-[0-9]{4}', label) for label in labels)):
        raise ValueError('Complete unique DS26 denominator and ordering required')
    configured = {p.parent.name for p in iteration.glob('DS26-*/' + CONFIG)}
    if configured - set(available):
        raise ValueError('Configured cases outside available frozen membership')
    rows, common = [], None
    for member in members:
        label = member['dataset_label']
        row = dict(dataset_label=label, availability=member['availability'],
                   initialized=label in configured)
        if row['initialized']:
            case = iteration / label
            config = read(case / CONFIG)
            if (config.get('kind') != 'algo07-star-verification-case'
                    or config.get('schema_version') != 1
                    or config['run_id'] != member['run_id']):
                raise ValueError('Case configuration does not bind cohort native run: ' + label)
            pins = {k: config.get(k) for k in
                    ('pins', 'candidate_terminal_read_reuse', 'candidate_source_pins')}
            if common is None:
                common = pins
            elif common != pins:
                raise ValueError('Mixed fixture or implementation pins in iteration')
            row.update(configuration_sha256=digest(case / CONFIG),
                       sides={s: side_state(case, config, s) for s in SIDES},
                       checks=check_history(case, config))
        rows.append(row)
    counts = Counter(available=len(available), unavailable=len(members)-len(available),
                     initialized=len(configured), not_initialized=len(available)-len(configured),
                     recorded_science_pass=0, recorded_full_pass=0,
                     cases_with_recorded_failed_checks=0, unfinished_check_receipts=0)
    for row in rows:
        history = row.get('checks', [])
        finished = [h for h in history if h['state'] != 'unfinished_check_receipt']
        if finished:
            counts['recorded_science_pass'] += finished[-1]['recorded_scientific_parity']
            counts['recorded_full_pass'] += finished[-1]['recorded_full_parity']
        counts['cases_with_recorded_failed_checks'] += any(h['state'] == 'FAIL' for h in history)
        counts['unfinished_check_receipts'] += sum(
            h['state'] == 'unfinished_check_receipt' for h in history)
    return dict(kind='algo07-star-cohort-recorded-progress', cohort_members=len(members),
                plan_sha256=digest(plan_path), iteration=str(iteration.resolve()),
                counts=dict(counts), members=rows, live_processes_checked=False,
                scientific_exports_rehashed=False, ds26_equivalence_verified=False,
                speedup_established=False,
                scope=('Verifier CLI receipts only; '
                       'separate renderer diagnostics are not aggregated'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--iteration', type=Path, required=True)
    parser.add_argument('--json', action='store_true',
                        help='Include every member and check history')
    args = parser.parse_args()
    result = report(args.plan, args.iteration)
    print(json.dumps(result if args.json else
                     {k: v for k, v in result.items() if k != 'members'}, indent=2))
