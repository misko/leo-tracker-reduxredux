"""Frozen DS24 baseline-only whole-curve recovery; geography is external."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time
import traceback

import numpy as np

import algo02_scan as algo
import probe_ds23_single_curved_reentry as single
import probe_ds23_support_aware_reentry as support
from ds23_causal_phase_location import adjust_means, qualify
from ds23_family_cavity import unused_student_gap
from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_active_mode_support import disabled_families
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_frequency_events import cached, refit, summary
from probe_ds23_family_cavity_position import unused_count
from probe_ds23_gate_retention_cohort import constrained
from probe_algo03_feasible_recovery import gate_slacks
from audit_ds23_algo01_coverage import retained_metrics
from evaluate_ds23_phase_refreshed import extend_associations
from run_ds23_combined_recovery_full import valid

REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
HERE = Path(__file__).resolve().parent
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024')
RANKING = Path('/srv/bulk/leo/research/ds24-bottlenecks-20261024/information/all_cases.json')
ARMS = ('c0', 'fitted_c')
CASES = ('DS24-0095', 'DS24-0087')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def encode(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def write_new(path, value):
    """Refuse to overwrite any scientific input, checkpoint or result."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, default=encode, allow_nan=False, indent=2)
        stream.write('\n')


def ranked_cases(document):
    return sorted(document['rows'], key=lambda r: (
        -r['arms']['c0']['curved']['all']['principal_sigma_km'][0], r['case']))


def build(d, arm, reference, kind='graph'):
    if kind == 'support':
        p = support.build(d, d['node'], d['keep'], arm, reference, d['means'])
    else:
        p = make_event_problem(d['scan'], d['node'], d['keep'], arm,
            np.asarray(reference), d['powers'], d['means'], d['model'], [])
        attach_event_predictive(p, d['entries'], d['powers'])
        p = cached(p)
    return p


def context(case):
    """Reconstruct saved inputs without ds24_engine or any position refit."""
    saved = read(SOURCE/'family_cavity/position'/(case+'.json'))
    if saved['status'] != 'complete':
        raise ValueError('saved baseline incomplete')
    selected = saved['selected'] if saved['accepted'] else None
    algo.bind_run_directory(SOURCE)
    scan = algo.load_scan(SOURCE, case)
    d = dict(case=case, scan=scan,
        node=selected['node'] if selected else saved['baseline_node'],
        keep=np.asarray(saved['original_mask'], bool),
        powers=np.asarray(saved['powers']), model=saved['model'],
        means=np.asarray(selected['means'] if selected else saved['baseline_means']),
        entries=selected['entries'] if selected else saved['baseline_entries'],
        arms=saved['policy_arms'], observations=read(SOURCE/case/'observations.json'))
    for element in scan.elements.values():
        provenance = element['provenance']
        if max(provenance['element_epoch_utc_ns'], provenance['collected_utc_ns']) > scan.receipt['cutoff_utc_ns']:
            raise ValueError('noncausal catalogue')
    history = SOURCE/'causal_phase_history'/(case+'.json')
    forecast = read(history.with_name(case+'_forecast.json'))
    algo.validate_history(read(history), forecast, scan, sha(history))
    if any(r['validation_time_ns'] > scan.receipt['cutoff_utc_ns'] for r in forecast['transitions']):
        raise ValueError('noncausal phase forecast transition')
    base = build(d, 'c0', d['arms']['c0']['phase_reference'])
    widths, receipts = phase_widths(scan, list(range(len(scan.norads))))
    ordinary = forecast_phase_mean(receipts, d['model']['shrinkage'])
    signed = qualify(forecast['transitions'], forecast['temporal_split_boundary_ns'],
        forecast['prefix_distribution'], d['model'])
    adjusted = adjust_means(ordinary, receipts, d['model'], signed)
    ordinary_match = np.allclose(ordinary[base.labels], d['means'], rtol=0, atol=1e-9)
    signed_match = np.allclose(adjusted[base.labels], d['means'], rtol=0, atol=1e-9)
    if not (ordinary_match or signed_match):
        raise ValueError('all-catalogue prior does not reproduce saved means')
    d.update(base=base, all_means=adjusted if signed_match else ordinary,
        widths=widths*d['model']['multiplier'],
        signed_prior_reconstruction=dict(ordinary_matches=ordinary_match,
            signed_matches=signed_match, selection=signed),
        reference=np.asarray(d['arms']['c0']['phase_reference']),
        x=np.asarray(d['arms']['c0']['endpoint_east_north_km']))
    d['original_protected'] = support.protected(d)
    return d


def membership(d, arm, saved, kind='graph'):
    """Exact curved/predictive/extension roles; explicit predictive IDs win."""
    p = build(d, arm, saved['phase_reference'], kind)
    x = np.asarray(saved['endpoint_east_north_km'])
    c = p.calculate(x)
    delta = float(c['negative_twice_elbo']-saved['negative_twice_elbo'])
    if abs(delta) >= 1e-3 or abs(delta)/max(1., abs(saved['negative_twice_elbo'])) >= 1e-8:
        raise ValueError(f'endpoint does not replay: {delta}')
    metrics = retained_metrics(p, x)
    curved = [oid for i, sl in zip(p.members, p.slices, strict=True)
        for oid, active in zip(p.scan.tracks[i]['observation_ids'], p.keep[sl], strict=True) if active]
    predictive = [oid for entry in d['entries'] for oid in entry['observation_ids']]
    allids = {o['observation_id'] for o in d['observations']}
    if len(curved) != len(set(curved)) or len(predictive) != len(set(predictive)) or set(curved)&set(predictive):
        raise ValueError('duplicate or overlapping likelihood IDs')
    if not set(curved+predictive) <= allids or len(allids) != len(d['observations']):
        raise ValueError('nonphysical likelihood IDs')
    extension = extend_associations(p, x, metrics)
    lookup = {t['key']: t for t in d['scan'].tracks}
    rows = []
    explicit_ids = set(predictive)
    for row in extension['tracks']:
        if not row['compatible']:
            continue
        ids = row.get('observation_ids', lookup[row['component']]['observation_ids'])
        if set(ids)&explicit_ids:
            continue
        rows.append(dict(row, observation_ids=ids))
    rows += [dict(e, compatible=g['compatible'], association_source='explicit_predictive')
        for e, g in zip(d['entries'], summary(p, x, d['entries'])['linear_gates'], strict=True)]
    accepted = {oid for row in rows if row['compatible'] for oid in row['observation_ids']}
    # likelihood union is retained even when a whole-curve extension conflicts.
    accepted |= set(curved+predictive)
    if not accepted <= allids:
        raise ValueError('nonphysical association IDs')
    active = sorted({row['candidate_index'] for row, sl in zip(p.rows, p.slices, strict=True) if p.keep[sl].any()})
    return dict(accepted_observation_ids=sorted(accepted), curved_observation_ids=sorted(curved),
        predictive_observation_ids=sorted(predictive),
        postfit_only_observation_ids=sorted(accepted-set(curved+predictive)),
        total_GLRT=len(allids), associated=len(accepted), percent=100*len(accepted)/len(allids),
        curved_points=len(curved), predictive_points=len(predictive), likelihood_points=len(curved)+len(predictive),
        likelihood_percent=100*(len(curved)+len(predictive))/len(allids),
        active_curved_families=active, active_curved_norads=[int(d['scan'].norads[j]) for j in active],
        supported_families=list(p.supported), associations=rows,
        objective_replay_difference=delta, gates=metrics)


def target_inventory(d, memberships):
    """Same duration/point/component ordering, requiring whole unowned sources."""
    occupied = set().union(*(set(m['accepted_observation_ids']) for m in memberships.values()))
    ranking, excluded = [], []
    for k, (row, i, sl) in enumerate(zip(d['base'].rows, d['base'].members, d['base'].slices, strict=True)):
        track = d['scan'].tracks[i]
        ids = set(track['observation_ids'])
        if d['keep'][sl].any() or ids&occupied:
            excluded.append(dict(component=track['key'], reason='contains_parent_accepted_ID',
                parent_ID_intersection=sorted(ids&occupied)))
            continue
        ranking.append(dict(track_index=i, component=track['key'], row_index=k,
            receiver=track['receiver'], channel=track['channel'], points=len(ids),
            original_points=len(track['times']), span_s=float(np.ptp(track['times'])),
            start_s=float(min(track['times'])), end_s=float(max(track['times'])),
            curved=i in d['scan'].curved, observation_ids=track['observation_ids']))
    ranking.sort(key=lambda r: (-r['span_s'], -r['points'], r['component']))
    return dict(ranking=ranking, excluded=excluded,
        candidate_targets=[r for r in ranking if r['curved'] and r['points'] >= 12][:3])


def preserve_parent(parent, child, parent_modes):
    return dict(parent_IDs_preserved={a:set(parent[a]['accepted_observation_ids']) <= set(child[a]['accepted_observation_ids']) for a in ARMS},
        parent_likelihood_IDs_preserved={a:set(parent[a]['curved_observation_ids']+parent[a]['predictive_observation_ids']) <= set(child[a]['curved_observation_ids']+child[a]['predictive_observation_ids']) for a in ARMS},
        incumbent_orbit_modes_preserved={a:set(parent_modes[a]) <= set(child[a]['supported_families']) for a in ARMS})


def preserved(checks):
    return all(v for values in checks.values() for v in values.values())


def rescue_eligible(pair_valid, minima):
    return not pair_valid and bool(minima) and min(minima) >= -.25


def fit_record(d, node, entries, means, checkpoint):
    """Instrument unchanged fit_configuration semantics before/after rescue."""
    pair = {arm:refit(d['scan'], node, d['keep'], arm, d['powers'], means,
        d['model'], [], entries) for arm in ARMS}
    ordinary = copy.deepcopy(pair)
    before_valid = valid(pair)
    minima = {}
    if not before_valid:
        for arm in ARMS:
            dd = dict(d, node=node, means=means, entries=entries)
            p = build(dd, arm, pair[arm]['phase_reference'])
            minima[arm] = min(gate_slacks(p, np.asarray(pair[arm]['endpoint_east_north_km']), entries).values())
    attempted = rescue_eligible(before_valid, list(minima.values()))
    # Checkpoint precedes constrained work, including interruption or timeout.
    write_new(checkpoint, dict(ordinary_arms=ordinary, ordinary_paired_valid=before_valid,
        minimum_slacks_before_rescue=minima, rescue_eligible=attempted))
    if attempted:
        pair = constrained(d['scan'], node, d['keep'], d['powers'], means,
            d['model'], entries, pair)
    for arm, r in pair.items():
        p = build(dict(d, node=node, means=means, entries=entries), arm, r['phase_reference'])
        c = p.calculate(np.asarray(r['endpoint_east_north_km']))
        r.update(coefficient=c['coefficient'], unused_phase_coordinates=unused_count(p, entries),
            corrected_selection_loss=r['negative_twice_elbo']-unused_count(p, entries)*unused_student_gap(d['model']['nu']))
    return dict(arms=pair, ordinary_arms=ordinary, rescued_arms=pair if attempted else None,
        ordinary_paired_valid=before_valid, minimum_slacks_before_rescue=minima,
        constrained_refinement_attempted=attempted,
        paired_valid=bool(valid(pair) and all(r['final_phase_change_s'] <= .01 for r in pair.values())),
        node=node, entries=entries, means=means)


def choose_graph(trials):
    passing = [r for r in trials if r['accepted']]
    return min(passing, key=lambda r:(-r['added_curved_points'],
        tuple(a['component'] for a in r['additions']), r['arms']['c0']['corrected_selection_loss'])) if passing else None


def eligible_support(d, trials):
    candidates = []
    for trial in trials:
        if trial['paired_valid'] or len(trial['additions']) > 2:
            continue
        p = support.build(d, trial['node'], np.asarray(trial['mask'], bool), 'c0',
            trial['arms']['c0']['phase_reference'], np.asarray(trial['means']))
        if p.disabled_new_one_owner_orbit_families:
            candidates.append((trial, p.disabled_new_one_owner_orbit_families))
    candidates.sort(key=lambda item:(len(item[0]['additions']), tuple(a['component'] for a in item[0]['additions'])))
    return candidates[:2]


def additions_metadata(d, additions, parent):
    active = set(parent['c0']['active_curved_families'])
    return [dict(row, role='curved_calibration', new_active_curved_family=row['candidate_index'] not in active,
        classification='new_active_curved_family' if row['candidate_index'] not in active else 'additional_owner_or_points_existing_family') for row in additions]


def check_trial(d, trial, parent, kind):
    dd = dict(d, node=trial['node'], keep=np.asarray(trial['mask'], bool),
        means=np.asarray(trial['means']), entries=trial['entries'])
    coverage = {a:membership(dd, a, trial['arms'][a], kind) for a in ARMS}
    checks = preserve_parent(parent, coverage, {a:parent[a]['supported_families'] for a in ARMS})
    trial.update(coverage=coverage, preservation=checks,
        accepted=bool(trial['paired_valid'] and preserved(checks)),
        addition_roles=additions_metadata(d, trial['additions'], parent))
    return trial


def alarm_until(deadline, message):
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        raise TimeoutError(message)
    signal.signal(signal.SIGALRM, lambda *_:(_ for _ in ()).throw(TimeoutError(message)))
    signal.setitimer(signal.ITIMER_REAL, remaining)


def graph_stage(d, parent, inventory, out):
    # Reuse source nomination and configuration ordering without its global run.
    single.build = lambda dd, arm, ref:build(dd, arm, ref)
    nominations = single.nominate(d, inventory)
    write_new(out/'nominations.json', nominations)
    offers = single.configurations(nominations)
    write_new(out/'hypothesis_order.json', dict(hypotheses=[[
        dict(component=r['target']['component'], candidate_index=o['candidate_index'], norad=o['norad'], aliases=o['aliases'])
        for r, o in hypothesis] for hypothesis in offers], sealed_before_position_fits=True))
    trials = []
    for number, hypothesis in enumerate(offers):
        node, keep = copy.deepcopy(d['node']), d['keep'].copy()
        additions = []
        for row, offer in hypothesis:
            k = row['row_index']
            if keep[d['base'].slices[k]].any():
                raise ValueError('whole target overlaps original active data')
            keep[d['base'].slices[k]] = True
            node['seed']['rows'][k].update(candidate_index=offer['candidate_index'], candidate_norad=offer['norad'])
            node['aliases'][k] = int(offer['aliases'][0])
            additions.append(dict(component=row['target']['component'], candidate_index=offer['candidate_index'],
                norad=offer['norad'], alias=int(offer['aliases'][0])))
        labels = sorted({r['candidate_index'] for r in node['seed']['rows']})
        trial = fit_record(dict(d, keep=keep), node, d['entries'], d['all_means'][labels], out/f'trial_{number:02d}_ordinary.json')
        trial.update(additions=additions, mask=keep, added_curved_points=int(keep.sum()-d['keep'].sum()), trial_index=number)
        check_trial(d, trial, parent, 'graph')
        write_new(out/f'trial_{number:02d}.json', trial)
        trials.append(trial)
        print(d['case'], 'graph', number, trial['added_curved_points'], trial['paired_valid'], trial['accepted'], flush=True)
    selected = choose_graph(trials)
    return dict(status='complete', selected=selected, trials=trials,
        policy_arms=selected['arms'] if selected else d['arms'], baseline_fallback=selected is None)


def support_stage(d, parent, graph, out):
    trials = []
    candidates = eligible_support(d, graph['trials'])
    write_new(out/'candidate_order.json', dict(candidates=[dict(trial_index=t['trial_index'],
        additions=t['additions'], disabled_new_one_owner_orbit_families=disabled) for t, disabled in candidates],
        no_merging_or_new_proposals=True))
    for number, (proposal, _) in enumerate(candidates):
        trial = {key:copy.deepcopy(proposal[key]) for key in ('node','mask','entries','means','additions','added_curved_points','trial_index')}
        pair = {a:support.refit(d, trial['node'], np.asarray(trial['mask'], bool), a, np.asarray(trial['means'])) for a in ARMS}
        trial.update(arms=pair, paired_valid=bool(valid(pair) and all(r['final_phase_change_s'] <= .01 for r in pair.values())),
            source_graph_trial=proposal['trial_index'], no_constrained_rescue=True)
        check_trial(d, trial, parent, 'support')
        write_new(out/f'trial_{number:02d}.json', trial)
        trials.append(trial)
        print(d['case'], 'support', number, trial['paired_valid'], trial['accepted'], flush=True)
    good = [r for r in trials if r['accepted']]
    selected = min(good, key=lambda t:(-t['added_curved_points'], tuple(a['component'] for a in t['additions']))) if good else None
    return dict(status='complete', selected=selected, trials=trials,
        policy_arms=selected['arms'] if selected else d['arms'], baseline_fallback=selected is None,
        separately_named_control_not_merged_with_graph=True)


def input_files():
    files = [RANKING, SOURCE/'sample.json', SOURCE/'protocol.json', REPO/'plans/ds24-movement-execution-plan.md']
    files += [HERE.parent/name for name in ('protocol.json','cohort_ledger.json','preflight.json')]
    for case in CASES:
        files += sorted(p for p in (SOURCE/case).iterdir() if p.is_file() and p.suffix in ('.json','.npz','.tle'))
        files += sorted(p for p in (SOURCE/'causal_prior'/case).iterdir() if p.is_file())
        files += [SOURCE/'family_cavity/position'/(case+'.json'),
            SOURCE/'causal_phase_history'/(case+'.json'), SOURCE/'causal_phase_history'/(case+'_forecast.json')]
    return files


def freeze():
    if (HERE/'protocol.json').exists():
        raise FileExistsError('preserve frozen recovery protocol')
    ranking = ranked_cases(read(RANKING))
    if tuple(r['case'] for r in ranking[:2]) != CASES:
        raise ValueError('RF case ranking changed')
    sources = [Path(__file__), HERE/'diagnostics.py', HERE/'test_recovery.py']
    sources += sorted((REPO/'tools').glob('*.py'))
    sources += sorted((REPO/'src/leo').rglob('*.py'))
    protocol = dict(experiment='DS24 movement r01 Wave1B independent recovery',
        cases=list(CASES), receiver_model='exact_saved_baseline', arms=list(ARMS),
        ranking=[dict(case=r['case'], c0_weak_axis_scale_km=r['arms']['c0']['curved']['all']['principal_sigma_km'][0]) for r in ranking],
        ranking_is_RF_model_conditional_not_calibrated_uncertainty=True,
        source_root=str(SOURCE), numpy_version=np.__version__,
        target_rule='three longest wholly unassociated active-curvature graph tracks; >=12 points; rank span descending, points descending, component ascending',
        nominee_rule='full causal catalogue; original then top7 excluding duplicate original; qualified minimum full-covariance score',
        configuration_rule='all nonempty best-nominee combinations in target order, then original-label singleton controls in target order',
        selection_rule='original paired gates/convergence AND parent IDs/modes; most added points, component tuple, c0 corrected loss only among identical masks',
        graph_seconds_per_case=600, support_seconds_per_case=240, global_pilot_seconds=1800,
        ordinary_phase_rounds=5, ordinary_position_steps=48,
        constrained_phase_rounds=5, constrained_position_steps=40, constrained_minimum_slack=-.25, constrained_interior=.01,
        support_max_failed_proposals=2, support_rule='only newly active one-owner shape modes disabled; incumbents protected; no union/merge/new nominees',
        phase_convergence_s=.01, cold_start=[0,0], region_center=[37.906,-122.545], box_width_km=25,
        numerical_workers=1, threads=1, dispatch_order=list(CASES),
        no_native_paths=True, no_raw_IQ=True, no_receiver_candidate=True, no_GPS=True,
        no_parent_ID_loss=True, no_incumbent_mode_loss=True, no_original_data_trim=True,
        original_label_controls_retained=True, ordinary_and_rescued_endpoints_checkpointed=True,
        input_sha256={str(p):sha(p) for p in input_files()}, source_sha256={str(p):sha(p) for p in sources})
    write_new(HERE/'protocol.json', protocol)
    write_new(HERE/'protocol_seal.json', dict(protocol_sha256=sha(HERE/'protocol.json')))
    print('frozen', HERE/'protocol.json', flush=True)


def verify():
    p = read(HERE/'protocol.json')
    if read(HERE/'protocol_seal.json')['protocol_sha256'] != sha(HERE/'protocol.json'):
        raise ValueError('protocol seal changed')
    for group in ('input_sha256', 'source_sha256'):
        for name, digest in p[group].items():
            if sha(name) != digest:
                raise ValueError('frozen '+group+' changed: '+name)
    return p


def prepare():
    verify()
    for case in CASES:
        d = context(case)
        parent = {a:membership(d, a, d['arms'][a]) for a in ARMS}
        inv = target_inventory(d, parent)
        write_new(HERE/case/'parent.json', dict(case=case, arms=d['arms'], coverage=parent,
            node=d['node'], mask=d['keep'], powers=d['powers'], means=d['means'], entries=d['entries'], model=d['model'],
            all_means=d['all_means'], widths=d['widths'], original_protected=sorted(d['original_protected']),
            signed_prior_reconstruction=d['signed_prior_reconstruction'], no_position_refitting=True))
        write_new(HERE/case/'inventory.json', inv)
    write_new(HERE/'prepared_seal.json', dict(protocol_sha256=sha(HERE/'protocol.json'),
        files={str(p.relative_to(HERE)):sha(p) for c in CASES for p in (HERE/c/'parent.json', HERE/c/'inventory.json')}))


def run():
    protocol = verify()
    prepared = read(HERE/'prepared_seal.json')
    for name, digest in prepared['files'].items():
        if sha(HERE/name) != digest:
            raise ValueError('prepared input changed')
    approval = read(HERE.parent/'audit/recovery_preflight.json')
    if approval.get('all_passed') is not True or approval['protocol_sha256'] != sha(HERE/'protocol.json'):
        raise ValueError('independent recovery preflight absent or mismatched')
    if (HERE/'execution_start.json').exists():
        raise FileExistsError('pilot execution cannot restart')
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        if os.environ.get(name) != '1':
            raise ValueError('single-thread environment required: '+name)
    contexts = {case:context(case) for case in CASES}
    began = time.monotonic()
    deadline = began+protocol['global_pilot_seconds']
    write_new(HERE/'execution_start.json', dict(started_utc_ns=time.time_ns(),
        protocol_sha256=sha(HERE/'protocol.json'), pid=os.getpid(), single_numerical_worker=True))
    rows = []
    for case in CASES:
        case_start = time.monotonic()
        d = contexts[case]
        parent = read(HERE/case/'parent.json')['coverage']
        stages = {}
        for stage, seconds in [('graph',600), ('support',240)]:
            start = time.monotonic()
            out = HERE/case/stage
            out.mkdir(exist_ok=False)
            try:
                alarm_until(min(deadline, start+seconds), stage+' stage or global pilot timeout')
                if stage == 'graph':
                    result = graph_stage(d, parent, read(HERE/case/'inventory.json'), out)
                elif stages['graph']['status'] == 'complete':
                    result = support_stage(d, parent, stages['graph'], out)
                else:
                    result = dict(status='abstained', reason='graph_stage_incomplete', selected=None,
                        trials=[], policy_arms=d['arms'], baseline_fallback=True)
            except Exception as exc:
                traceback.print_exc()
                result = dict(status='timeout' if isinstance(exc,TimeoutError) else 'failed',
                    error=repr(exc), traceback=traceback.format_exc(), selected=None, trials=[],
                    policy_arms=d['arms'], baseline_fallback=True,
                    partial_trials_preserved_separately=True)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
            result.update(case=case, stage=stage, seconds=time.monotonic()-start,
                no_GPS=True, protocol_sha256=sha(HERE/'protocol.json'))
            write_new(out/'result.json', result)
            stages[stage] = result
        rows.append(dict(case=case, graph_status=stages['graph']['status'], support_status=stages['support']['status'],
            graph_selected=stages['graph']['selected'] is not None, support_selected=stages['support']['selected'] is not None,
            seconds=time.monotonic()-case_start))
    write_new(HERE/'execution.json', dict(rows=rows, seconds=time.monotonic()-began,
        all_terminal=True, no_GPS=True, global_cap_seconds=1800))
    files = sorted(p for p in HERE.rglob('*.json') if p.name != 'scientific_seal.json')
    write_new(HERE/'scientific_seal.json', dict(sealed_utc_ns=time.time_ns(), no_GPS_before_seal=True,
        protocol_sha256=sha(HERE/'protocol.json'), files={str(p.relative_to(HERE)):sha(p) for p in files}))
    print('RF results sealed', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['freeze','prepare','run','verify'])
    args = parser.parse_args()
    globals()[args.stage]()


if __name__ == '__main__':
    main()
