"""Merge disjoint RF-qualified additions once, then audit the final control."""

import copy
from pathlib import Path
import numpy as np

import audit_ds23_family_cavity as auditor
from ds23_frequency_events import make_event_problem, attach_event_predictive
from probe_ds23_reentry_family_cavity import assert_curved_gate_replay
from probe_ds23_single_curved_reentry import OUT as OLD
from probe_ds23_support_aware_reentry import OUT, build, refit
from probe_ds23_worst_association_bottleneck import setup, inventory
from probe_ds23_frequency_events import summary
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read, write, sha


def main():
    assert read(OUT/'execution.json')['all_passed']
    cases = read(OUT/'protocol.json')['cases']
    protocol = dict(cases=cases, action='one cold fit of the union of disjoint already-paired-valid additions',
          no_new_identity_or_hyperparameter_search=True, no_GPS_or_future_TLE_used=True,
          selection='maximum added points among paired-valid repairs; no geographic selection',
          source_sha256=sha(Path(__file__)), before_any_support_control_geographic_evaluation=True)
    if (OUT/'finalization_protocol.json').exists():
        raise FileExistsError('preserve frozen finalization')
    write(OUT/'finalization_protocol.json', protocol)
    all_cases = []
    for case in cases:
        d = setup(case)
        old = read(OLD/(case+'_positions.json'))
        control = read(OUT/(case+'.json'))
        good = [r for r in control['trials'] if r['paired_valid']]
        candidates = list(good)
        merged = None
        if good and old['selected'] is not None:
            first = max(good, key=lambda r:r['added_curved_points'])
            second = old['selected']
            additions = {r['component']: r for r in first['additions']}
            conflicts = [r for r in second['additions'] if r['component'] in additions and
                         r['candidate_index'] != additions[r['component']]['candidate_index']]
            additions.update({r['component']: r for r in second['additions']})
            if not conflicts and len(additions) > max(len(first['additions']), len(second['additions'])):
                node, mask = copy.deepcopy(d['node']), d['keep'].copy()
                for row in additions.values():
                    k = next(k for k, r in enumerate(node['seed']['rows']) if r['component'] == row['component'])
                    node['seed']['rows'][k].update(candidate_index=row['candidate_index'], candidate_norad=row['norad'])
                    node['aliases'][k] = row['alias']
                    mask[d['base'].slices[k]] = True
                labels = sorted({r['candidate_index'] for r in node['seed']['rows']})
                means = d['all_means'][labels]
                pair = {arm: refit(d, node, mask, arm, means) for arm in ['c0', 'fitted_c']}
                merged = dict(node=node, mask=mask, entries=d['entries'], means=means, arms=pair,
                              additions=list(additions.values()), added_curved_points=int(mask.sum()-d['keep'].sum()),
                              paired_valid=bool(valid(pair) and all(r['final_phase_change_s'] <= .01 for r in pair.values())))
                if merged['paired_valid']:
                    candidates.append(merged)
                write(OUT/(case+'_merged.json'), merged)
                print(case, 'RF-qualified union', merged['added_curved_points'], merged['paired_valid'], flush=True)
        checks, nulls = [], []
        for arm, baseline in d['arms'].items():
            p = build(d, d['node'], d['keep'], arm, baseline['phase_reference'], d['means'])
            x = np.asarray(baseline['endpoint_east_north_km'])
            delta = p.calculate(x)['negative_twice_elbo']-baseline['negative_twice_elbo']
            if abs(delta) > 1e-5:
                raise ValueError('mode-support null does not preserve incumbent')
            nulls.append(dict(arm=arm, objective_difference=delta))
        for trial in control['trials']+([merged] if merged else []):
            for arm, saved in trial['arms'].items():
                p = build(d, trial['node'], np.asarray(trial['mask'], bool), arm, saved['phase_reference'], np.asarray(trial['means']))
                x = np.asarray(saved['endpoint_east_north_km'])
                delta = p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo']
                if abs(delta) > 1e-5:
                    raise ValueError('support control endpoint does not replay')
                replay = summary(p, x, d['entries'])
                assert_curved_gate_replay(saved['gates'], replay['gates'])
                assert_curved_gate_replay(saved['linear_gates'], replay['linear_gates'])
                direct = auditor.density(d, p, x, np.asarray(trial['means']), d['entries'])
                checks.append(dict(arm=arm, endpoint_difference=delta, **direct))
        selected = max(candidates, key=lambda r:r['added_curved_points']) if candidates else None
        coverage = None
        if selected:
            coverage = {}
            for arm, saved in selected['arms'].items():
                # The standard coverage adapter calls the default builder;
                # compute the same membership using this explicitly simpler model.
                p = build(d, selected['node'], np.asarray(selected['mask'], bool), arm,
                          saved['phase_reference'], np.asarray(selected['means']))
                from evaluate_ds23_phase_refreshed import extend_associations
                from dbg01_unassociated import ownership
                from audit_ds23_algo01_coverage import retained_metrics
                extended = extend_associations(p, np.asarray(saved['endpoint_east_north_km']), retained_metrics(p, np.asarray(saved['endpoint_east_north_km'])))
                lookup = {t['key']: t for t in d['scan'].tracks}
                ids = ownership([dict(r, observation_ids=r.get('observation_ids', lookup[r['component']]['observation_ids']))
                                 for r in extended['tracks']])
                coverage[arm] = dict(associated=len(ids), total_GLRT=len(d['observations']),
                    percent=100*len(ids)/len(d['observations']), accepted_observation_ids=sorted(ids),
                    active_curved_points=int(np.asarray(selected['mask']).sum()),
                    predictive_points=sum(e['points'] for e in d['entries']), associations=extended)
        result = dict(case=case, selected=selected, coverage=coverage, nulls=nulls, checks=checks,
                      all_passed=True, original_control_sha256=sha(OUT/(case+'.json')),
                      selected_without_geographic_evaluation=True, no_ALGO_version_promoted=True)
        write(OUT/(case+'_audited.json'), result)
        all_cases.append(dict(case=case, selected=selected is not None, checks=len(checks)))
    write(OUT/'finalization_audit.json', dict(all_passed=True, rows=all_cases,
          no_geographic_evaluation_yet=True, source_sha256=sha(Path(__file__))))


if __name__ == '__main__':
    main()
