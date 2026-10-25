"""Independent frozen-parent audit: fixed positions only, never a fit or GPS."""

import hashlib
import inspect
import json
import os
from pathlib import Path
import signal
import sys
import time

import numpy as np

import recovery as old
import repair01 as repair
from matched_controls import measurement_binding

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PREVIOUS = Path('/srv/bulk/leo/research/ds24-movement-policy-r01')
CASES = {'DS24-0095': (65500, 49, 1, 5), 'DS24-0087': (57752, 43, 2, 7)}
ARMS = ('c0', 'fitted_c')
OFFSETS = np.array([[0., 0.], [.05, 0.], [-.05, 0.], [0., .05], [0., -.05],
                    [.5, 0.], [-.5, 0.], [0., .5], [0., -.5]])


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    def encode(v):
        if isinstance(v, np.ndarray):
            return v.tolist()
        if isinstance(v, np.generic):
            return v.item()
        raise TypeError(type(v).__name__)
    return json.dumps(value, default=encode, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def write_new(path, value):
    with Path(path).open('x') as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False)+'\n')


def fail_fit(*args, **kwargs):
    raise AssertionError('No position fits are permitted in this independent audit')


def equation(p, x, powers):
    """Test the actual residual vector and account explicitly for visibility."""
    c = p.calculate(x)
    residual = np.asarray(p.residual(x))
    base = np.asarray(c['residual'])
    visible = np.maximum(0., -np.asarray(c['elevation'])[p.keep])/2
    np.testing.assert_array_equal(residual[:len(base)], base)
    np.testing.assert_array_equal(residual[len(base):], visible)
    volume = float(2*np.sum(np.asarray(powers)[p.noise_groups[p.keep]]*np.log(p.point_noise[p.keep]/40)))
    if not getattr(p, 'linear_entries', []):
        np.testing.assert_allclose(base[-1]**2, volume, atol=1e-9, rtol=0)
    score = float(residual@residual)
    objective = float(c['negative_twice_elbo'])
    visibility = float(visible@visible)
    expected = volume-float(c['normalization_constant'])+visibility
    error = score-objective-expected
    if abs(error) > 2e-8:
        raise AssertionError(f'actual residual / ELBO identity failed: {error}')
    return dict(position_east_north_km=np.asarray(x).tolist(), actual_residual_scalar=score,
        reported_negative_twice_elbo=objective, normalization_constant=float(c['normalization_constant']),
        fixed_noise_volume=volume, visibility_penalty=visibility,
        below_horizon_active_points=int(np.count_nonzero(visible)),
        minimum_active_elevation_deg=float(np.min(c['elevation'][p.keep])),
        adjusted_offset=score-objective-visibility, identity_error=error,
        final_log_precision_change=float(c['final_log_precision_change']))


def main():
    began = time.monotonic()
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        if os.environ.get(name) != '1':
            raise ValueError('one numerical thread required')
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('180s fixed audit cap')))
    signal.alarm(180)
    # Block the position-fit entry point before reconstructing any context.
    import investigate_dsx01_localization_failures as fitter
    fitter.fit = fail_fit
    old.fit = fail_fit
    old.refit = fail_fit
    old.support.refit = fail_fit
    old.single.refit = fail_fit
    rows, ownership, files = [], [], {}
    ledger_path = PREVIOUS/'cohort_ledger.json'
    ledger = read(ledger_path)
    files[str(ledger_path)] = sha(ledger_path)
    frozen_members = read(PREVIOUS/'audit/baseline_membership.json')['cases']
    for case, (norad, count, rx, channel) in CASES.items():
        d = old.context(case)
        binding_before = measurement_binding(d)
        parent_path = old.HERE/case/'parent.json'
        control_path = old.HERE/'eligibility02'/case/'result.json'
        parent, control = read(parent_path), read(control_path)
        assert parent['arms'] == d['arms'] and parent['node'] == d['node']
        assert parent['entries'] == d['entries'] and parent['model'] == d['model']
        for key, field in [('mask', 'keep'), ('powers', 'powers'), ('means', 'means')]:
            np.testing.assert_array_equal(parent[key], d[field])
        assert measurement_binding(d) == frozen_members[case]['measurement_binding_sha256']
        selected = control['selected']
        assert selected is not None and selected['accepted'] and len(selected['additions']) == 1
        addition = selected['additions'][0]
        assert addition['norad'] == norad
        assert int(d['scan'].norads[addition['candidate_index']]) == norad
        track_index = next(i for i, t in enumerate(d['scan'].tracks) if t['key'] == addition['component'])
        track = d['scan'].tracks[track_index]
        ids = list(track['observation_ids'])
        assert len(ids) == len(set(ids)) == count
        assert track['receiver'] == rx and track['channel'] == channel
        observations = {o['observation_id']: o for o in d['observations']}
        assert len(observations) == len(d['observations']) and set(ids) <= observations.keys()
        occupied = set().union(*(set(v['accepted_observation_ids']) for v in parent['coverage'].values()))
        assert not set(ids)&occupied
        curved, predictive = set(), set()
        for family in frozen_members[case]['family_membership']:
            curved.update(family['curved_ids']); predictive.update(family['predictive_ids'])
        assert not curved&predictive and not set(ids)&(curved|predictive)
        assert addition['candidate_index'] not in d['original_protected']
        cutoff = d['scan'].receipt['cutoff_utc_ns']
        epochs, collections = [], []
        for element in d['scan'].elements.values():
            provenance = element['provenance']
            epochs.append(provenance['element_epoch_utc_ns'])
            collections.append(provenance['collected_utc_ns'])
        assert max(epochs) <= cutoff and max(collections) <= cutoff
        frozen_case = next(row for row in ledger['rows'] if row['case'] == case)
        for item in frozen_case['frozen_scan_files']+[frozen_case['baseline']]:
            assert sha(item['path']) == item['sha256']
            files[item['path']] = item['sha256']
        for path in [parent_path, control_path, old.SOURCE/'causal_phase_history'/(case+'.json'),
                     old.SOURCE/'causal_phase_history'/(case+'_forecast.json')]:
            files[str(path)] = sha(path)
        target_data = dict(case=case, component=track['key'], candidate_index=addition['candidate_index'],
            norad=norad, receiver=rx, channel=channel, rf_hz=track['rf_hz'], alias=addition['alias'],
            observation_ids=ids, times_s=np.asarray(track['times']).tolist(),
            graph_values_hz=np.asarray(track['values']).tolist(),
            native_measured_cfo_hz=[observations[oid]['measured_cfo_hz'] for oid in ids])
        write_new(HERE/(case+'_target_binding.json'), target_data)
        files[str(HERE/(case+'_target_binding.json'))] = sha(HERE/(case+'_target_binding.json'))
        ownership.append(dict(case=case, target_component=track['key'], norad=norad,
            candidate_index=addition['candidate_index'], target_points=count,
            target_native_IDs_disjoint_from_parent_accepted=True,
            parent_curved_points=len(curved), parent_predictive_points=len(predictive),
            parent_measurement_binding_sha256=binding_before, causal_cutoff_utc_ns=cutoff,
            causal_candidate_count=len(epochs), maximum_element_epoch_utc_ns=max(epochs),
            maximum_element_collection_utc_ns=max(collections),
            prior_phase_mean_s=float(d['all_means'][addition['candidate_index']]),
            prior_phase_sigma_s=float(d['widths'][addition['candidate_index']]),
            context_prior_reconstruction=d['signed_prior_reconstruction'],
            target_binding_sha256=files[str(HERE/(case+'_target_binding.json'))]))
        for name, context, arms, kind in [
            ('original_parent', d, parent['arms'], 'graph'),
            ('saved_support_control', dict(d, node=selected['node'], keep=np.asarray(selected['mask'], bool),
                means=np.asarray(selected['means']), entries=selected['entries']), selected['arms'], 'support')]:
            for arm in ARMS:
                saved = arms[arm]
                p = repair.corrected_build(context, arm, saved['phase_reference'], kind)
                # Establish fresh fixed state; never refresh phase from new target values.
                anchor = np.asarray(saved['endpoint_east_north_km'])
                values = [equation(p, anchor+offset, context['powers']) for offset in OFFSETS]
                replay = values[0]['reported_negative_twice_elbo']-saved['negative_twice_elbo']
                assert abs(replay) < 1e-3 and abs(replay)/max(1., abs(saved['negative_twice_elbo'])) < 1e-8
                offsets = [v['adjusted_offset'] for v in values]
                spread = float(np.ptp(offsets))
                if spread > 2e-8:
                    raise AssertionError(f'position-dependent residual / ELBO offset: {spread}')
                rows.append(dict(case=case, context=name, arm=arm, fixed_phase_reference_sha256=
                    hashlib.sha256(canonical(saved['phase_reference'])).hexdigest(),
                    saved_objective_replay_difference=replay, adjusted_offset_spread=spread, values=values))
        assert measurement_binding(d) == binding_before, 'audit mutated original context'
        print(case, 'fixed contexts and target ownership passed', flush=True)
    source_files = [Path(__file__), Path(old.__file__), Path(repair.__file__),
        Path(inspect.getsourcefile(fitter)), Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools/dsx01_hierarchical_bound.py'),
        Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools/ds23_predictive_linear.py'),
        Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools/ds23_frozen_precision.py'),
        Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools/ds23_active_mode_support.py')]
    source = {str(path): sha(path) for path in source_files}
    output = dict(all_passed=True, no_position_fits=True, GPS_used=False,
        coordinator_plan_sha256=sha(ROOT/'COORDINATOR_PLAN.md'), rows=rows, ownership=ownership,
        input_sha256=files, source_sha256=source,
        position_evaluations=sum(len(row['values']) for row in rows),
        equation='actual_residual_scalar - reported_ELBO = fixed_noise_volume - normalization_constant + visibility_penalty',
        interpretation='No position-dependent objective inconsistency in audited fixed contexts after explicit visibility correction. This is not a global optimizer audit.',
        maximum_identity_error=max(abs(v['identity_error']) for row in rows for v in row['values']),
        maximum_adjusted_offset_spread=max(row['adjusted_offset_spread'] for row in rows),
        threads=1, audit_seconds=time.monotonic()-began, scientific_launch_approved=False)
    write_new(HERE/'parent_audit.json', output)
    signal.alarm(0)
    print(json.dumps({k: v for k, v in output.items() if k not in ('rows', 'ownership', 'input_sha256', 'source_sha256')}, indent=2))


if __name__ == '__main__':
    main()
