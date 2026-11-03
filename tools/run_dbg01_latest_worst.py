"""Bounded DBG01 adapter for the current published DS23 research method."""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
import signal
import time

import numpy as np

import debug_algo02_ds23_0268 as engine
import report_dbg01_algo02_ds23_0268 as figures
from algo02_scan import pair_passes
from ds23_family_cavity import unused_student_gap
from ds23_frequency_events import make_event_problem, attach_event_predictive
from dsx01_inference_audit import disk_grid
from investigate_dsx01_localization_failures import fit
from probe_ds23_family_cavity_position import unused_count
from probe_ds23_worst_association_bottleneck import OUT as PARENT, setup
from run_dsx01_joint_descent import descend
from run_algo01_ds23_sample import ROOT, read, sha, write

WORKERS = 24


@lru_cache(maxsize=2)
def data(case):
    return setup(case)


def configure(case):
    d = data(case)
    out = PARENT/case/'DBG01'
    engine.CASE, engine.OUT, engine.WORKERS = case, out, WORKERS
    roots = read(ROOT/'reports/2026_10_20_ds23_combined_recovery_full/protocol.json')['input_roots']
    engine.SOURCE = Path(roots[case])
    old = dict(policy_arms=d['arms'], hyperparameters_from_pre_RF_TLE_only=d['model'], weights=d['powers'],
               linear_entries=d['entries'], linear_paired_valid=True)
    engine.context = lambda: (d['scan'], d['node'], d['keep'], d['base'], old)
    def build(node, keep, arm, reference, entries, control='baseline'):
        model = dict(d['model'])
        labels = sorted({r['candidate_index'] for r in node['seed']['rows']})
        means = d['all_means'][labels].copy()
        if control == 'phase_x2':
            model['multiplier'] *= 2
        elif control == 'phase_zero_mean':
            means *= 0
        elif control != 'baseline':
            raise ValueError('undeclared prior sensitivity')
        p = make_event_problem(d['scan'], node, keep, arm, np.asarray(reference), d['powers'], means, model, [])
        attach_event_predictive(p, entries, d['powers'])
        from probe_ds23_frequency_events import cached
        return cached(p)
    engine.build = build
    return out


def prepare(case):
    out = configure(case)
    out.mkdir(exist_ok=True)
    d = data(case)
    if (out/'protocol.json').exists():
        return
    axis, regional = disk_grid(step_km=1)
    local_axis = np.arange(-2, 2.001, .25)
    local = figures.REFERENCE_XY+np.array([(x, y) for y in local_axis for x in local_axis])
    if np.any(abs(local) > 12.5):
        raise ValueError('local oracle view outside original box')
    write(out/'request.json', dict(case=case, algorithm='published conditional-family DS23 method',
          diagnostic_point=figures.REFERENCE_XY, surface_points=np.vstack([regional, local]),
          regional_count=len(regional), regional_axis=axis, local_axis=local_axis,
          reference_xy=figures.REFERENCE_XY, GPS_is_report_oracle_only=True))
    p = d['base']
    families = sorted({r['candidate_norad'] for r, sl in zip(p.rows, p.slices, strict=True) if d['keep'][sl].any()})
    tracks = [r['component'] for r, sl in zip(p.rows, p.slices, strict=True) if d['keep'][sl].any()]
    write(out/'interventions.json', dict(family=families, track=tracks,
                                        prior=['phase_x2', 'phase_zero_mean']))
    write(out/'protocol.json', dict(case=case, algorithm='current published conditional-family method',
          baseline_inventory_sha256=sha(PARENT/case/'inventory.json'), regional_width_km=25,
          phase_rounds=5, fit_steps=48, grid_step_km=1., local_step_km=.25,
          restart_count=len(engine.STARTS), discovery_count=len(engine.DISCOVERY_STARTS),
          maximum_shared_assignment_branches=4,
          bank_cap='original plus three finite candidates with lowest corrected full c0 RF objective at regional center',
          restart_c0_reselects_assignment_after_each_accepted_step=True,
          fitted_c_follows_c0_phase_round_branch_schedule=True,
          unused_Student_coordinates_corrected_only_for_same_mask_branch_ranking=True,
          both_c_arms_for_all_grids_restarts_and_ablations=True,
          all_active_satellite_families_and_curved_tracks_ablated=True,
          prior_sensitivities=['phase_x2', 'phase_zero_mean'],
          no_default_prior_changed_no_GPS_based_adoption=True,
          following_TLE_diagnostic_not_in_this_causal_iteration=True,
          job_seconds=180, workers=WORKERS,
          source_sha256=sha(Path(__file__))))


def bank():
    engine.bank()
    path = engine.OUT/'hypothesis_bank.json'
    record = read(path)
    if len(record['nodes']) <= 4:
        return dict(stage='bank', candidates=len(record['nodes']))
    d = data(engine.CASE)
    scores = []
    for index, node in enumerate(record['nodes']):
        reference = np.zeros(len({r['candidate_index'] for r in node['seed']['rows']}))
        p = engine.build(node, d['keep'], 'c0', reference, d['entries'])
        value = p.calculate(np.zeros(2))['negative_twice_elbo']
        value -= unused_count(p, d['entries'])*unused_student_gap(d['model']['nu'])
        scores.append(dict(index=index, corrected_RF_cost=value))
    selected = [0]+[r['index'] for r in sorted(scores[1:], key=lambda r:r['corrected_RF_cost'])[:3]]
    record.update(uncapped_nodes=record['nodes'], nodes=[record['nodes'][k] for k in selected],
                  cap_selection_indices=selected, cap_scores=scores,
                  cap_has_no_GPS_input=True)
    write(path, record)
    return dict(stage='bank', candidates=len(record['nodes']))


def restart(index):
    d = data(engine.CASE)
    nodes = read(engine.OUT/'hypothesis_bank.json')['nodes']
    entries = d['entries']
    schedule, arms = [], {}
    for arm in engine.ARMS:
        refs = [np.zeros(len({r['candidate_index'] for r in node['seed']['rows']})) for node in nodes]
        x = np.asarray(engine.STARTS[index], float)
        history = []
        for epoch in range(5):
            problems = [engine.build(n, d['keep'], arm, r, entries) for n, r in zip(nodes, refs, strict=True)]
            if arm == 'c0':
                for p in problems:
                    residual = p.residual
                    gap = unused_count(p, entries)*unused_student_gap(d['model']['nu'])
                    def normalized(z, p=p, residual=residual, gap=gap):
                        r = residual(z)
                        c = p.calculate(z)
                        offset = c['negative_twice_elbo']-float(c['residual']@c['residual'])-gap+1e6
                        if offset < 0:
                            raise ValueError('normalized branch padding too small')
                        return np.r_[r, np.sqrt(offset)]
                    p.residual = normalized
                result = descend(problems, x, max_steps=48)
                chosen = result['final_mode']
                schedule.append(chosen)
            else:
                chosen = schedule[epoch]
                fitted = fit(problems[chosen], x, iterations=48)
                result = dict(parameters=fitted['parameters'], final_mode=chosen,
                              switches=[], stopped=fitted['stopped'],
                              trace=[dict(point=h['parameters'], score=h['score'], mode=chosen) for h in fitted['history']])
            x = np.asarray(result['parameters'])
            changes = []
            for k, p in enumerate(problems):
                phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
                changes.append(float(np.max(abs(phase-refs[k]))))
                refs[k] = phase
            history.append(dict(epoch=epoch, descent=result, selected_mode=chosen, phase_changes_s=changes))
        arms[arm] = dict(engine.summary(problems[chosen], x, entries), history=history,
                         final_mode=chosen, final_phase_change_s=changes[chosen])
    write(engine.OUT/f'restart_{index:02d}.json', dict(start_id=index, start=engine.STARTS[index], arms=arms,
          paired_valid=pair_passes(arms, include_linear=True),
          fitted_c_follows_c0_phase_round_branch_schedule=True,
          curved_labels_and_aliases_can_switch_each_c0_step=True,
          conditional_predictive_labels_fixed=True))
    return dict(stage='restart', index=index)


def execute(job):
    case, kind, index = job
    out = configure(case)
    name = 'audit.json' if kind == 'audit' else f'{kind}_{index:02d}.json'
    path = out/name
    if path.exists():
        return dict(case=case, kind=kind, index=index, status='complete', reused=True)
    start = time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('180 s DBG01 job cap')))
    signal.alarm(180)
    try:
        result = restart(index) if kind == 'restart' else engine.execute((kind, index))
        status = 'complete'
    except Exception as exc:
        import traceback
        result = dict(error=repr(exc), traceback=traceback.format_exc())
        status = 'failed'
        write(out/(name[:-5]+'_failed.json'), result)
    finally:
        signal.alarm(0)
    return dict(case=case, kind=kind, index=index, status=status, seconds=time.monotonic()-start, result=result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['prepare', 'audit_discover', 'bank', 'analysis', 'figures'], required=True)
    args = parser.parse_args()
    cases = read(PARENT/'protocol.json')['cases']
    if args.stage == 'prepare':
        for case in cases:
            prepare(case)
        return
    if args.stage == 'bank':
        for case in cases:
            configure(case)
            print(case, bank(), flush=True)
        return
    if args.stage == 'figures':
        for case in cases:
            configure(case)
            figures.CASE, figures.OUT = case, engine.OUT
            figures.context = engine.context
            audit = read(engine.OUT/'audit.json')
            figures.surfaces(audit)
            figures.restarts(audit)
            figures.influence(audit)
        return
    jobs = []
    for case in cases:
        if args.stage == 'audit_discover':
            jobs += [(case, 'audit', 0)]+[(case, 'discover', k) for k in range(13)]
        else:
            request = read(PARENT/case/'DBG01/interventions.json')
            jobs += [(case, 'grid', k) for k in range(WORKERS)]
            jobs += [(case, 'restart', k) for k in range(len(engine.STARTS))]
            jobs += [(case, kind, k) for kind in ['family', 'track', 'prior'] for k in range(len(request[kind]))]
    rows = []
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        for f in as_completed([pool.submit(execute, j) for j in jobs]):
            result = f.result()
            rows.append(result)
            print(result['case'], result['kind'], result['index'], result['status'], round(result.get('seconds', 0), 2), flush=True)
            write(PARENT/('DBG01_'+args.stage+'_progress.json'), dict(completed=len(rows), requested=len(jobs), rows=rows))
    write(PARENT/('DBG01_'+args.stage+'_execution.json'), dict(all_terminal=True, rows=rows,
          all_passed=all(r['status'] == 'complete' for r in rows)))


if __name__ == '__main__':
    main()
