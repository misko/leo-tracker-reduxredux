"""Limited outcome diagnostic for the declared real numerical cancellation pair.

This preserves the complete raw decision diff and separately compares named
scientific projections. It never qualifies ordinary deadline or full-stage parity.
"""
import argparse
import json
from pathlib import Path

from diff_algo07_star_evidence import differences, normalized
from run_algo03_shadow import check_read_audit

from leo.cli.algo07_profile import digest, verify, write_new
from leo.contracts.fast_graph_position import validate_terminal


def read(path):
    return json.loads(path.read_text())


def run(study, output):
    plan_path = study / 'plan.json'
    plan = read(plan_path)
    if digest(Path(plan['manifest'])) != plan['manifest_sha256']:
        raise ValueError('Frozen runtime manifest changed')
    runtime_check = verify(Path(plan['manifest']))
    if not runtime_check['verified']:
        raise ValueError('Frozen runtime verification failed')
    for name, expected in plan['source_pins'].items():
        if digest(Path(name)) != expected:
            raise ValueError('Pinned trial source changed')
    outcomes, decisions, receipts = {}, {}, {}
    for side in plan['order']:
        root = study / side
        launch = read(study / f'{side}-launch.json')
        execution = read(study / f'{side}-execution.json')
        if launch['plan_sha256'] != digest(plan_path) or execution['returncode'] != 0:
            raise ValueError('Trial did not complete under this plan')
        audit = execution['read_audit']
        audited = check_read_audit(root, audit['root_process_id'],
                                  supervisor_pid=audit['supervisor_process_id'])
        if audited != audit or not audited['verified']:
            raise ValueError('Process read audit changed or failed')
        descriptor = read(root / 'snapshot/descriptor.json')
        input_binding = plan['inputs'][side]
        original_descriptor_path = Path(input_binding['descriptor'])
        if digest(original_descriptor_path) != input_binding['descriptor_sha256']:
            raise ValueError('Planned input descriptor changed')
        original_descriptor = read(original_descriptor_path)
        expected_descriptor = dict(original_descriptor,
                                   root=str(root / 'snapshot/inference'))
        if descriptor != expected_descriptor:
            raise ValueError('Copied input descriptor differs from planned export')
        validate_terminal(descriptor['terminal'], input_sha256=descriptor['input_sha256'])
        if descriptor['input_sha256'] != plan['inputs'][side]['input_sha256']:
            raise ValueError('Native input binding changed')
        source = Path(descriptor['root']).resolve(strict=True)
        if not source.is_relative_to(root.resolve()):
            raise ValueError('Copied input leaves trial root')
        for relative, expected in descriptor['files'].items():
            member = source / relative
            if (member.is_symlink() or not member.resolve(strict=True).is_relative_to(source)
                    or 'sha256:' + digest(member) != expected):
                raise ValueError('Copied input changed')
        decision = read(root / 'decision.json')
        clock = read(root / 'clock-receipt.json')
        if (clock['schedule'] != plan['schedule'] or clock['stop_after'] != plan['stop_after']
                or len(clock['children']) != len(plan['schedule'])
                or any(c['returncode'] != 0 for c in clock['children'])):
            raise ValueError('Declared numerical children did not complete')
        omitted = [a['track_id'] for a in decision['attempts']
                   if a['status'] == 'discovery_budget_exhausted']
        if omitted != plan['expected_omitted_track_ids']:
            raise ValueError('Cancellation admitted different work')
        selected = decision['selected']
        if selected is None or set(selected['arms']) != {'c0', 'fitted_c'}:
            raise ValueError('Expected retained recovery with both arms')
        for mapping in (selected['source_receipts'], decision['source_support_receipt']):
            for name, expected in mapping.items():
                member = Path(name).resolve(strict=True)
                if not member.is_relative_to(root.resolve()) or digest(member) != expected:
                    raise ValueError('Selected scientific evidence changed')
        decisions[side] = normalized(decision, str(root))
        outcomes[side] = {key: decision[key] for key in (
            'policy', 'decision', 'maximum_seconds', 'no_GPS_selection', 'causal_only',
            'matched_c_arms', 'ranking', 'eligible_tracks', 'selected_track_ids', 'rf_checks')}
        outcomes[side].update(
            selected={key: selected[key]
                      for key in ('kind', 'arms', 'targets', 'inactive_fragment')},
            attempts=[{key: a[key] for key in ('track_id', 'points', 'status')}
                      for a in decision['attempts']],
            stages=[{key: s[key] for key in ('name', 'status', 'returncode', 'seconds')}
                    for s in decision['stages']])
        receipts[side] = dict(
            decision_sha256=digest(root / 'decision.json'),
            execution_sha256=digest(study / f'{side}-execution.json'),
            clock_receipt_sha256=digest(root / 'clock-receipt.json'),
            input_sha256=descriptor['input_sha256'], read_audit=audited,
            real_wall_seconds=execution['real_wall_seconds'])
    if receipts['reference']['input_sha256'] != receipts['candidate']['input_sha256']:
        raise ValueError('Trials use different native inputs')
    delta = list(differences(outcomes['reference'], outcomes['candidate']))
    raw_delta = list(differences(decisions['reference'], decisions['candidate']))
    result = dict(
        kind='controlled-algo03-cancellation-limited-outcome-diagnostic',
        compared_fields=list(outcomes['reference']), outcomes_equal=not delta,
        outcome_differences=delta, complete_decision_differences=raw_delta,
        receipts=receipts, plan_sha256=digest(plan_path), script_sha256=digest(Path(__file__)),
        numerical_children_stubbed=False, stage_durations_are_synthetic=True,
        scientific_parity_qualified=False, production_deadline_behavior_qualified=False,
        original_failed_comparison_unchanged=True, performance_comparison=False)
    write_new(output, result)
    print(json.dumps(dict(outcomes_equal=not delta, outcome_difference_count=len(delta),
                          complete_decision_difference_count=len(raw_delta),
                          scientific_parity_qualified=False, output=str(output))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    run(args.study.resolve(strict=True), args.output)
