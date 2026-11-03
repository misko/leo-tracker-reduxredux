"""Joint two-emitter RF fitting on two fixed probes per archived scan.

Select the longest qualified native pair per scan, before new joint fits or
position errors are inspected. No orbit, location, or frame phase is an input.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
from collections import defaultdict
from pathlib import Path
import json
import signal
import time
import numpy as np
from ds23_joint_component_refinement import JointComponentWorkspace
from probe_ds23_differential_frame_phase import jobs as archived_jobs
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_joint_component_refinement'
BULK = Path('/srv/bulk/leo/research/ds23-joint-component-refinement-20261021')


def selected_jobs():
    pool = archived_jobs(); counts = {}
    for source in sorted({j['source'] for j in pool}):
        source = Path(source); protocol = read(source/'protocol.json'); evaluation = read(source/'evaluation.json')
        qualified = {(r['case'], r['probe']) for r in evaluation['rows'] if r['status'] == 'complete' and r['two_components_qualified']}
        for j in protocol['jobs']:
            if (j['case'], j['probe']) in qualified: counts[j['group']] = counts.get(j['group'], 0)+1
    by_case = defaultdict(list)
    for item in pool: by_case[item['job']['case']].append(item)
    result = []
    for case, group in sorted(by_case.items()):
        lane = max({j['job']['group'] for j in group}, key=lambda g: (counts[g], g))
        eligible = sorted([j for j in group if j['job']['group'] == lane], key=lambda j: j['job']['time_s'])
        result.extend([eligible[0], eligible[-1]])
    return result


def one(item):
    j, source = item['job'], Path(item['source']); target = BULK/(j['group']+f"_probe{j['probe']:06d}.json")
    if target.exists(): return read(target)
    started = time.monotonic()
    def timeout(*_): raise TimeoutError('90-second two-component refinement cap exhausted')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(90)
    result = dict(case=j['case'], group=j['group'], probe=j['probe'], source=str(source))
    try:
        with np.load(source/'panels'/(j['case']+'.npz'), allow_pickle=False) as z:
            metadata = json.loads(str(z['metadata_json'])); point = next(p for p in metadata['points'] if p['probe'] == j['probe'])
            v = z[point['window_key']][:, point['receiver_offset']]
        y = v[:, 0].astype(float)+1j*v[:, 1].astype(float)
        fits = [item['fit']['first_fit'], item['fit']['second_fit']]
        p = JointComponentWorkspace(y, metadata['sample_rate_hz'], j['edge'], [j['first']['epoch'], j['second']['epoch']], fits)
        baseline = p.statistics(p.start, derivatives=False)
        frequency = p.optimize(active=(0, 3)); full = p.optimize()
        folds = []
        for parity in [0, 1]:
            old = p.statistics(p.start, parity, derivatives=False, prediction=True)
            fitted = p.optimize(parity); prediction = p.statistics(fitted['parameters'], parity, derivatives=False, prediction=True)
            gain = 2*old['heldout_samples']*np.log(old['heldout_squared_error']/prediction['heldout_squared_error'])
            folds.append(dict(parity=parity, fit=fitted, baseline=old, prediction=prediction,
                heldout_profile_gain=float(gain), heldout_SSE_fractional_improvement=1-prediction['heldout_squared_error']/old['heldout_squared_error']))
        last = p.statistics(full['parameters']); n = last['samples']; variance = last['squared_error']/(n-17*len(p.segments)-6)
        covariance = variance/2*np.linalg.inv(last['normal'])*p.scale[:, None]*p.scale[None]
        checks = dict(both_symbol_folds_predict_better=all(f['heldout_profile_gain'] > 10 for f in folds),
            full_and_fold_solutions_interior=not any(f['boundary'] for f in [full]+[v['fit'] for v in folds]),
            both_fold_CFO_changes_consistent=bool(np.max(abs(folds[0]['fit']['parameters'][[0, 3]]-folds[1]['fit']['parameters'][[0, 3]])) <= 10))
        result.update(status='complete', initial_parameters=p.start, baseline=baseline, frequency_only=frequency,
            full=full, folds=folds, local_Gaussian_parameter_covariance=covariance,
            CFO_delta_hz=(full['parameters']-p.start)[[0, 3]], checks=checks, qualified_for_full_curve_test=all(checks.values()),
            no_phase_continuity_or_geographic_information_used=True,
            initial_RF_seed_conditioned_on_whole_probe_but_new_parameter_and_channel_updates_fit_only_on_training_symbols=True,
            local_noise_proxy_not_calibrated_uncertainty=True)
    except Exception as exc: result.update(status='failed', error=repr(exc))
    finally: signal.alarm(0)
    result['seconds'] = time.monotonic()-started; write(target, result)
    return result


def main():
    OUT.mkdir(exist_ok=True); BULK.mkdir(exist_ok=True); jobs = selected_jobs()
    source_protocol = ROOT/'reports/2026_10_21_ds23_differential_frame_phase_v2/protocol.json'
    source = read(source_protocol)
    for name, digest in source['source_bindings'].items():
        if sha(Path(name)) != digest: raise ValueError('native RF source changed')
    for panel in {Path(j['source'])/'panels'/(j['job']['case']+'.npz') for j in jobs}:
        if sha(panel) != source['saved_panel_sha256'][str(panel)]: raise ValueError('saved IQ panel changed')
    protocol = dict(jobs=jobs, workers=8, per_probe_seconds=90, position_fits=False, new_RF_collection=False,
        selection='first/last qualified probe of longest simultaneous pair per archived scan; phase/position results not used',
        fixed_raw_symbol_prediction_folds=[0, 1], all_phases_channels_independent_per_frame_intersection=True,
        fits=['two_CFO_only', 'two_CFO_two_epoch_two_code_rate'], full_optimizer_iterations=12,
        new_parameter_box='each CFO within120Hz of RF seed; epochs within.75sample; rates within40ppm',
        no_RF_evidence_compared_across_different_samples_or_channel_dimensions=True,
        source_panel_and_native_RF_bindings_sha256=sha(source_protocol),
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_joint_component_refinement.py',
            ROOT/'tools/ds23_fractional_differential_phase.py', ROOT/'tools/probe_ds23_differential_frame_phase.py']})
    path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol: raise ValueError('joint component refinement protocol changed')
    if not path.exists(): write(path, protocol)
    results = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        for future in as_completed([pool.submit(one, j) for j in jobs]):
            r = future.result(); results.append(r)
            print(r['group'], r['probe'], r['status'], r.get('CFO_delta_hz'), r.get('checks'), r.get('error'), flush=True)
            write(OUT/'progress.json', dict(total=len(jobs), terminal=len(results), rows=results))
    complete = [r for r in results if r['status'] == 'complete']
    summary = dict(total=len(jobs), complete=len(complete), failed=len(jobs)-len(complete),
        full_curve_test_candidates=sum(r['qualified_for_full_curve_test'] for r in complete),
        both_folds_predict_better=sum(r['checks']['both_symbol_folds_predict_better'] for r in complete),
        median_absolute_CFO_change_hz=float(np.median([abs(v) for r in complete for v in r['CFO_delta_hz']])),
        median_heldout_profile_gain=float(np.median([f['heldout_profile_gain'] for r in complete for f in r['folds']])))
    write(OUT/'evaluation.json', dict(summary=summary, rows=results, all_terminal=True, protocol_sha256=sha(path),
        no_position_accuracy_claim=True, no_GPS_or_satellite_identity_input=True))
    print('SUMMARY', summary, flush=True)


if __name__ == '__main__': main()
