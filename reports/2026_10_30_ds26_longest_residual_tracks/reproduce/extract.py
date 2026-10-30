"""Read frozen receipts; summarize the five longest published-residual tracks."""
import hashlib
import json
import math
from pathlib import Path

STUDY = Path('/srv/bulk/leo/research/ds26-longest-residual-20261030')
FROZEN = Path('/srv/bulk/leo/research/algo03-full-evaluation-20261030')
OUT = STUDY / 'rejection-audit'
ARMS = ('c0', 'fitted_c')
sources = {}


def read(path):
    data = path.read_bytes()
    sources[str(path)] = hashlib.sha256(data).hexdigest()
    return json.loads(data)


def slim_gate(g):
    return {k: v for k, v in g.items() if k != 'observation_ids'}


def extract(row):
    case, tid = row['case'], row['track_id']
    root = FROZEN / 'cases' / case / 'candidate-v2/recovery'
    decision = read(root / 'decision.json')
    attempt = next(a for a in decision['attempts'] if a['track_id'] == tid)
    annotation = read(root / tid / 'annotation/result.json')
    protocol = read(root / tid / 'annotation/protocol.json')
    out = {k: row[k] for k in ('case', 'track_id', 'component', 'residual_points', 'span_s', 'wholly_unassociated')}
    selected = decision.get('selected')
    out.update(scan_decision=decision['decision'], target_attempt=attempt,
               selected_target_norads=[t['norad'] for t in selected['targets']] if selected else [],
               selected_target_components=[t['component'] for t in selected['targets']] if selected else [],
               assessed_rank=decision['selected_track_ids'].index(tid) + 1,
               no_budget_omission=True,
               annotation_protocol={k: protocol[k] for k in ('seed_list', 'block_s', 'guard_s', 'target_used_for_calibration', 'GPS_used', 'future_TLE')},
               partition_plan=protocol.get('partition_plan'),
               annotation_folds=[])
    for fold in annotation['folds']:
        for arm in ARMS:
            proposals = sorted(fold['proposals'], key=lambda p: p['arms'][arm]['scores']['conditional_target']['negative_twice_log_density'])
            condensed = []
            for proposal in proposals:
                v = proposal['arms'][arm]
                score = v['scores']['conditional_target']
                condensed.append(dict(norad=proposal['norad'], alias=proposal['alias'],
                    score={k: score[k] for k in ('negative_twice_log_density', 'points', 'rms_hz', 'normalized_quadratic') if k in score},
                    graph_final_phase_change_s=v['final_phase_change_s'],
                    minimum_target_elevation_deg=v['minimum_target_elevation_deg'],
                    target_phase_training_mean_s=v.get('target_phase_training_mean_s'),
                    target_phase_training_sigma_s=v.get('target_phase_training_sigma_s'),
                    target_phase_boundary_mass=v.get('target_phase_boundary_mass'),
                    prior={k: v.get('prior', {}).get(k) for k in ('kind', 'active_curved_family', 'phase_prior_mean_s', 'phase_prior_sigma_s', 'prior_mass_in_phase_box')}))
            best = condensed[0]
            failed = []
            if best['score']['rms_hz'] > 450: failed.append('target_held_RMS_above_450_Hz')
            if best['graph_final_phase_change_s'] > .01: failed.append('training_graph_phase_refresh_above_0.01_s')
            if best['minimum_target_elevation_deg'] < 0: failed.append('target_below_horizon')
            margin = condensed[1]['score']['negative_twice_log_density'] - best['score']['negative_twice_log_density']
            if margin < 10: failed.append('predictive_margin_below_10')
            out['annotation_folds'].append(dict(seed=fold['seed'], arm=arm,
                winner=best['norad'], runner_up=condensed[1]['norad'], margin=margin,
                failed_adequacy_or_margin_checks=failed, candidates=condensed))
    trial = root / tid / 'trial'
    if not trial.exists():
        out['trial'] = None
        return out
    out['trial'] = dict(path=str(trial), roles={}, exact_replay=[])
    for role in ('control', 'target_0'):
        doc = read(trial / f'{role}.json')
        summary = dict(paired_valid=doc['paired_valid'], arms={})
        for arm, v in doc['arms'].items():
            fit = v['history'][-1]['fit']
            completed = fit.get('success') is True if 'success' in fit else fit.get('stopped') == 'small_step_and_improvement'
            summary['arms'][arm] = dict(endpoint_east_north_km=v['endpoint_east_north_km'],
                negative_twice_elbo=v['negative_twice_elbo'], incumbent_RMS_hz=v['RMS_hz'],
                final_phase_change_s=v['final_phase_change_s'], lost_points=v['lost_points'],
                optimizer_completed_for_shadow_policy=completed,
                optimizer={k: fit[k] for k in ('success', 'stopped', 'evaluations', 'negative_twice_elbo') if k in fit},
                failed_curved_gates=[slim_gate(g) for g in v['gates']['tracks'] if not g['compatible']],
                failed_linear_gates=[slim_gate(g) for g in v['linear_gates'] if not g['compatible']],
                target_diagnostics=[{k: d[k] for k in ('component', 'norad', 'RMS_hz', 'bias_hz')} for d in v.get('target_diagnostics', [])])
        out['trial']['roles'][role] = summary
    replay = read(trial / 'exact_owner_replay.json')
    out['trial']['all_verified'] = replay['all_verified']
    for r in replay['rows']:
        ranges = {}
        for family in r['exact_family_replays']:
            for key, value in family['all_gate_slacks'].items():
                if value < 0:
                    old = ranges.get(key, [value, value])
                    ranges[key] = [min(old[0], value), max(old[1], value)]
        target_ranges = {}
        for family in r['exact_family_replays']:
            for key, value in family['all_gate_slacks'].items():
                if key.startswith(row['component'] + '/linear/'):
                    old = target_ranges.get(key, [value, value])
                    target_ranges[key] = [min(old[0], value), max(old[1], value)]
        abs_acf_range = None
        for key, bounds in target_ranges.items():
            if key.endswith('/lag1'):
                threshold = 4 / math.sqrt(row['residual_points'])
                abs_acf_range = [(1 - bounds[1]) * threshold, (1 - bounds[0]) * threshold]
        out['trial']['exact_replay'].append(dict(role=r['role'], arm=r['arm'], verified=r['verified'],
            incumbent_ownership_change_count=len(r['incumbent_ownership_changes']),
            control_ownership_change_count=len(r['control_ownership_changes']),
            phase_reference_check=r['phase_reference_check'],
            receiver_coefficient_change=r['receiver_coefficient_change'],
            failed_gate_slack_ranges_across_family_replays=ranges,
            target_gate_slack_ranges=target_ranges,
            target_lag1_absolute_acf_range_implied_by_slack=abs_acf_range,
            target_lag1_threshold=4 / math.sqrt(row['residual_points'])))
    return out


if __name__ == '__main__':
    rows = read(STUDY / 'top10.json')[:5]
    results = [extract(row) for row in rows]
    document = dict(scope='frozen receipt audit; no inference, RF collection, or policy changes',
        source_root=str(FROZEN), tracks=results, source_sha256=sources,
        identity_interpretation='Conditional ranking given frozen graph and bounded candidate search; no NORAD ground truth or posterior identity probability.',
        c_comparison='Every recorded candidate comparison uses matched random grouped partitions and both c arms. No geographic accuracy comparison or position improvement is inferred from frequency fit.')
    (OUT / 'audit.json').write_text(json.dumps(document, indent=2, allow_nan=False) + '\n')
    print(json.dumps([dict(case=r['case'], status=r['target_attempt']['status'], trial=r['trial'] is not None) for r in results], indent=2))
