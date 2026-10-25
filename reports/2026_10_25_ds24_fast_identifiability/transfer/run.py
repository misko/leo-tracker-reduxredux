"""Bounded predictive-prior transfer using the unchanged R2 numerical model."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import argparse
import multiprocessing
from pathlib import Path
import signal
import time
import traceback

import numpy as np

import transfer as t

HERE, r, q = t.HERE, t.r, t.q


def freeze():
    panel_path = HERE/'panel.json'; panel = r.read(panel_path)
    inputs = {str(panel_path):r.sha(panel_path),
        str(t.R2/'next_inventory/inventory.json'):panel['original_inventory_sha256']}
    for row in panel['panel']:
        path = Path(row['parent_ledger_path']); parent = r.read(path)
        inputs[str(path)] = row['parent_ledger_sha256']
        case = row['case']
        for suffix in ('tracks.json', 'observations.json', 'receipt.json', 'radio_noise.json'):
            path = r.SOURCE/case/suffix; inputs[str(path)] = r.sha(path)
        for path in (r.SOURCE/'family_cavity/position'/(case+'.json'),
                     r.SOURCE/'causal_phase_history'/(case+'.json'),
                     r.SOURCE/'causal_phase_history'/(case+'_forecast.json')):
            inputs[str(path)] = r.sha(path)
    sources = [Path(__file__), HERE/'transfer.py', HERE/'test_transfer.py',
        t.R2/'scientific/adapter.py', t.R2/'scientific/quadrature02.py',
        t.R2/'scientific/execution03.py', t.RECOVERY/'recovery.py']
    sources += [r.REPO/'tools'/name for name in ('ds23_height_problem.py',
        'ds23_predictive_linear.py', 'ds23_frequency_events.py', 'build_dsx01_orbit_modes.py',
        'dsx01_hierarchical_bound.py', 'dsx01_joint_marginal.py',
        'run_ds23_combined_recovery_full.py', 'algo02_scan.py')]
    protocol = dict(version='chronological raw-graph predictive-prior transfer r01',
        panel=[{key:row[key] for key in ('case', 'component', 'candidate_norad', 'candidate_index',
                                       'alias', 'points', 'recording_utc')} for row in panel['panel']],
        input_sha256=inputs, source_sha256={str(path):r.sha(path) for path in sources},
        ownership='complete original parent accepted-ID ledger at unchanged saved positions/references, including postfit-only extensions; exact both-arm target nonoverlap',
        order=panel['ordering'], panel_frozen_before_RF_or_geographic_selection=True,
        no_backfill_after_panel_freeze=True,
        target_status='archived rejected nominee; unqualified experimental predictive factor',
        implementation='unchanged R2 adapter/quadrature02 conditional p(T|E,C,phi), full physical covariance and exact shared E/T uncertainty',
        target_phase_prior='original causal Student nu3 parameters conditioned[-15,+15]s; no shrink/recenter/tuning',
        fixed_phase_nodes=1281, denser_reference_nodes=2561,
        score_tolerance=1e-3, gradient_tolerance_per_km=1e-3, gradient_step_km=.01,
        prior_mass_tolerance=1e-8,
        preflight='2c arms x5baseline/axis positions x2covariance branches per case; denser and independent adaptive references; no new nomination/gates',
        maximum_fixed_branch_checks=20*len(panel['panel']),
        preflight_failure='retain selected failure, no rule change/backfill, no fits for that matched case',
        target_leakage='redact target CFO at fixed baseline; parent coefficients/noise/phase references and covariance must remain unchanged',
        fit_branch='physical prior only', maximum_position_fits=2*len(panel['panel']),
        cold_start_km=[0., 0.], regional_width_km=25., parent_phase_rounds=5,
        iterations_per_round=48, workers=2, BLAS_threads=1,
        seconds_per_arm=180., global_science_seconds=1200.,
        global_start='before first transfer numerical preflight; ownership reconstruction and test time separately recorded',
        preflight_case_seconds_cap=180.,
        endpoint_qualification='unchanged R2 final-reference endpoint +axis NLL/gradient comparisons at1281 vs2561+adaptive, same tolerances and arm budget; no retry/refine',
        gates='exact original r.valid, Gamma convergence, all original accepted and likelihood IDs preserved; no target admission by renaming',
        visibility='all phase nodes and domain endpoints must propagate and be visible; no clipping/dropping/visibility truncation',
        retries=0, rescue=False, variance_tuning=False, new_candidates=False,
        target_accepted_points=0, operational_policy='saved_baseline',
        RF_seal_before_geography=True,
        saved_R2_RF_seal_sha256=r.sha(t.R2/'scientific/RF_seal03.json'))
    t.write(HERE/'protocol.json', protocol)
    t.write(HERE/'protocol_seal.json', dict(protocol_sha256=r.sha(HERE/'protocol.json')))
    print(r.sha(HERE/'protocol.json'), flush=True)


def verify():
    p = r.read(HERE/'protocol.json')
    if r.sha(HERE/'protocol.json') != r.read(HERE/'protocol_seal.json')['protocol_sha256']:
        raise ValueError('protocol seal changed')
    for field in ('source_sha256', 'input_sha256'):
        for path, digest in p[field].items():
            if r.sha(path) != digest:
                raise ValueError('frozen source/input changed: '+path)
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        if r.os.environ.get(name) != '1':
            raise ValueError('one numerical thread required')
    return p


def leakage(d, arm, p, x):
    before = q.conditional_components(d, p, x)
    changed = dict(d, scan=t.copy.copy(d['scan']))
    changed['scan'].tracks = list(d['scan'].tracks)
    i = d['target']['track_index']
    changed['scan'].tracks[i] = dict(d['target_track'], values=np.asarray(d['target_track']['values'])+999.)
    changed['target_track'] = changed['scan'].tracks[i]
    pp = q.build(changed, arm, p.reference, t.BRANCHES[0], t.NODES)
    after = q.conditional_components(changed, pp, x)
    checks = {key:bool(np.array_equal(before['parent'][key], after['parent'][key]))
              for key in ('coefficient', 'noise_precision', 'coefficient_prior_precision')}
    checks['references'] = bool(np.array_equal(p.reference, pp.reference))
    checks['target_base_covariance'] = bool(np.array_equal(before['base_covariance_hz2'], after['base_covariance_hz2']))
    checks['target_redaction_applied'] = bool(np.allclose(after['base_raw_hz']-before['base_raw_hz'], 999., atol=1e-8, rtol=0))
    return dict(checks=checks, passed=all(checks.values()))


def preflight(row, deadline):
    began = time.monotonic(); case = row['case']; out = HERE/'preflight'/case
    records, contexts = [], []
    try:
        t.timeout(min(180., (deadline-time.time_ns())/1e9), 'preflight/global cap')
        d = t.load_target(row)
        law = {key:value for key,value in q.prior(d).items() if key != 'distribution'}
        leak = {}
        for arm in t.ARMS:
            saved = d['arms'][arm]; x = np.asarray(saved['endpoint_east_north_km'])
            p = q.build(d, arm, saved['phase_reference'], t.BRANCHES[0], t.NODES)
            leak[arm] = leakage(d, arm, p, x)
            points = [x]
            for axis in range(2):
                step = np.zeros(2); step[axis] = .01
                points += [x+step, x-step]
            arm_records = []
            for index, at in enumerate(points):
                components = q.conditional_components(d, p, at)
                for branch in t.BRANCHES:
                    shape = branch == t.BRANCHES[1]
                    fixed = q.integrate(d, components, 1281, shape)
                    dense = q.integrate(d, components, 2561, shape)
                    adaptive = q.adaptive_reference(d, components, shape)
                    record = dict(case=case, arm=arm, branch=branch, point_index=index,
                        position_east_north_km=at, frozen=fixed if index==0 else {k:fixed[k] for k in
                            ('objective', 'quadrature_prior_mass', 'minimum_node_elevation_deg', 'minimum_domain_endpoint_elevation_deg')},
                        denser={k:dense[k] for k in ('objective', 'minimum_node_elevation_deg', 'minimum_domain_endpoint_elevation_deg')},
                        adaptive=adaptive, parent_negative_twice_elbo=components['parent']['negative_twice_elbo'])
                    t.write(out/f'{arm}_{branch}_{index}.json', record)
                    arm_records.append(record); records.append(record)
            for branch in t.BRANCHES:
                selected = [v for v in arm_records if v['branch']==branch]
                gradient = lambda key: np.array([(selected[1][key]['objective']-selected[2][key]['objective'])/.02,
                                                 (selected[3][key]['objective']-selected[4][key]['objective'])/.02])
                score_error = max(abs(v['frozen']['objective']-v['adaptive']['objective']) for v in selected)
                dense_error = max(abs(v['frozen']['objective']-v['denser']['objective']) for v in selected)
                gradient_error = float(max(abs(gradient('frozen')-gradient('adaptive'))))
                dense_gradient_error = float(max(abs(gradient('frozen')-gradient('denser'))))
                mass_error = max(abs(v['frozen']['quadrature_prior_mass']-1) for v in selected)
                visible = all(min(v[key]['minimum_node_elevation_deg'], v[key]['minimum_domain_endpoint_elevation_deg']) >=0
                              for v in selected for key in ('frozen', 'denser'))
                contexts.append(dict(arm=arm, branch=branch,
                    score_error_vs_adaptive=score_error, score_error_vs_denser=dense_error,
                    gradient_error_vs_adaptive_per_km=gradient_error,
                    gradient_error_vs_denser_per_km=dense_gradient_error,
                    prior_mass_error=mass_error, visible=visible,
                    frozen_gradient=gradient('frozen'),
                    passed=bool(score_error<=1e-3 and dense_error<=1e-3 and gradient_error<=1e-3
                        and dense_gradient_error<=1e-3 and mass_error<=1e-8 and visible)))
        passed = all(v['passed'] for v in contexts) and all(v['passed'] for v in leak.values())
        result = dict(case=case, status='complete', passed=passed,
            fixed_branch_checks=len(records), contexts=contexts, leakage=leak, causal_conditioned_phase=law,
            seconds=time.monotonic()-began, no_backfill=True, position_fits=0)
    except Exception as exc:
        result = dict(case=case, status='failed', passed=False, error=repr(exc), traceback=traceback.format_exc(),
            fixed_branch_checks=len(records), contexts=contexts, seconds=time.monotonic()-began,
            no_backfill=True, position_fits=0)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    t.write(out/'result.json', result)
    print(case, 'preflight', result['status'], result['passed'], round(result['seconds'], 3), result.get('error', ''), flush=True)
    return result


def one_fit(row, arm, deadline):
    began = time.monotonic(); case=row['case']; out=HERE/'fits'/case/arm
    history=[]
    try:
        t.timeout(min(180., (deadline-time.time_ns())/1e9), 'arm/global cap')
        d=t.load_target(row); x=np.zeros(2); reference=np.zeros(len(d['means']))
        for epoch in range(5):
            p=q.build(d, arm, reference, t.BRANCHES[1], 1281)
            fitted=t.controls.fit(p, x, iterations=48); x=np.asarray(fitted['parameters'])
            phase=np.clip(p.state(x)['phases'][p.labels], -15, 15)
            history.append(dict(epoch=epoch, fit=fitted, parent_phase_reference=reference,
                parent_posterior_phase_s=phase, phase_change_s=float(max(abs(phase-reference)))))
            t.write(out/f'round_{epoch}.json', history[-1]); reference=phase
        c=p.calculate(x)
        raw=dict(case=case, arm=arm, endpoint_east_north_km=x, parent_phase_reference=p.reference,
            final_parent_phase_change_s=history[-1]['phase_change_s'],
            total_negative_twice_elbo=c['negative_twice_elbo'],
            seconds_to_raw_endpoint=time.monotonic()-began, history=history)
        t.write(out/'raw_endpoint.json', raw)
        numeric=t.controls.endpoint_qualification(d, p, x)
        t.write(out/'endpoint_numerical_qualification.json', numeric)
        gates=t.controls.parent_gates(d, arm, p, x, c, history[-1]['phase_change_s'])
        t.write(out/'parent_gates.json', gates)
        diagnostics=t.controls.predictive_record(d, p, x)
        t.write(out/'rf_diagnostics.json', diagnostics)
        result=dict(raw, status='complete', numerical_qualified=numeric['passed'],
            parent_qualified=bool(gates['passed'] and c['final_log_precision_change']<=1e-5),
            seconds=time.monotonic()-began, target_association_qualified=False,
            target_accepted_points=0, operational_policy='saved_baseline')
    except Exception as exc:
        result=dict(case=case, arm=arm, status='failed', error=repr(exc), traceback=traceback.format_exc(),
            completed_rounds=len(history), raw_endpoint_checkpoint_exists=(out/'raw_endpoint.json').exists(),
            seconds=time.monotonic()-began, target_association_qualified=False,
            target_accepted_points=0, operational_policy='saved_baseline')
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    t.write(out/'result.json', result)
    print(case, arm, 'fit', result['status'], round(result['seconds'], 3), result.get('error', ''), flush=True)
    return result


def run():
    protocol=verify(); panel=r.read(HERE/'panel.json')['panel']
    start=time.time_ns(); deadline=start+int(1200e9)
    t.write(HERE/'execution_start.json', dict(started_utc_ns=start, deadline_utc_ns=deadline,
        protocol_sha256=r.sha(HERE/'protocol.json')))
    context=multiprocessing.get_context('spawn')
    with ProcessPoolExecutor(max_workers=2, mp_context=context) as pool:
        preflights=[future.result() for future in as_completed([pool.submit(preflight, row, deadline) for row in panel])]
    t.write(HERE/'preflight_results.json', dict(rows=preflights,
        fixed_branch_checks=sum(v['fixed_branch_checks'] for v in preflights)))
    passing={v['case'] for v in preflights if v['passed']}
    tasks=[(row, arm) for row in panel if row['case'] in passing for arm in t.ARMS]
    with ProcessPoolExecutor(max_workers=2, mp_context=context) as pool:
        fits=[future.result() for future in as_completed([pool.submit(one_fit, row, arm, deadline) for row,arm in tasks])]
    skipped=[dict(case=row['case'], arm=arm, status='skipped_preflight',
        reason='frozen numerical/implementation preflight failed; no retuning/backfill',
        target_association_qualified=False, target_accepted_points=0, operational_policy='saved_baseline')
        for row in panel if row['case'] not in passing for arm in t.ARMS]
    result=dict(status='terminal', preflights=preflights, fits=fits, skipped=skipped,
        attempted_fits=len(fits), maximum_fits=8,
        elapsed_wall_seconds=(time.time_ns()-start)/1e9,
        target_association_qualified=False, target_accepted_points=0,
        operational_policy='saved_baseline', GPS_used=False)
    t.write(HERE/'execution_result.json', result)
    files=[path for folder in ('ownership', 'preflight', 'fits') for path in (HERE/folder).rglob('*.json')]
    files += [HERE/name for name in ('panel.json','protocol.json','protocol_seal.json',
                                    'execution_start.json','preflight_results.json','execution_result.json')]
    t.write(HERE/'RF_seal.json', dict(files={str(path):r.sha(path) for path in sorted(files)},
        protocol_sha256=r.sha(HERE/'protocol.json'), all_attempts_terminal=True,
        GPS_used=False, operational_policy='saved_baseline', target_association_qualified=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('freeze','run'), required=True)
    args=parser.parse_args(); {'freeze':freeze,'run':run}[args.stage]()
