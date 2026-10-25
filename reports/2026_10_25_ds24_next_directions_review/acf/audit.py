"""Archived and current-parent DS24 ACF rejection audit; never fits positions."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import signal
import time
import traceback

import numpy as np

import recovery as r
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile

HERE = Path(__file__).resolve().parent
LEDGER = Path('/srv/bulk/leo/research/ds24-movement-policy-r01/cohort_ledger.json')
ARMS = ('c0', 'fitted_c')


def flags(diagnostics, n, prefix=''):
    limits = dict(mean_z=3., slope_z=3., quadratic_bic_gain=10., maximum_step_z=4., lag1_acf=4 / np.sqrt(n))
    return {prefix + key: bool(abs(diagnostics[key]) <= limit) if key == 'lag1_acf'
            else bool(diagnostics[key] <= limit) for key, limit in limits.items()}


def diagnostics(residual, times):
    value = batch_noise_screen(np.asarray(residual)[None, :], np.asarray(times))
    return {key: float(item[0]) for key, item in value.items() if key != 'noise_screen_pass'}


def category(checks):
    failed = [key for key, value in checks.items() if not value]
    if not failed: return 'all_observed_primitive_checks_pass'
    if all(key.endswith('lag1_acf') for key in failed): return 'ACF_only'
    if any(key.endswith('lag1_acf') for key in failed): return 'ACF_and_other'
    return 'other_only'


def distribution(rows, key):
    values = np.asarray([row[key] for row in rows if row.get(key) is not None], float)
    return None if not len(values) else dict(n=len(values), minimum=float(values.min()),
        q25=float(np.quantile(values, .25)), median=float(np.median(values)),
        q75=float(np.quantile(values, .75)), maximum=float(values.max()))


def summarize(rows):
    return dict(records=len(rows), category_counts=dict(Counter(row['category'] for row in rows)),
        by_category={name:dict(records=sum(row['category'] == name for row in rows),
            residual_RMS_hz=distribution([row for row in rows if row['category'] == name], 'residual_RMS_hz'),
            native_sigma_median_hz=distribution([row for row in rows if row['category'] == name], 'native_sigma_median_hz'),
            residual_RMS_over_native_sigma_median=distribution([row for row in rows if row['category'] == name], 'RMS_over_native_sigma_median'))
            for name in sorted({row['category'] for row in rows})})


def run():
    began = time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('300s total audit compute cap')))
    signal.alarm(300)
    HERE.mkdir(parents=True, exist_ok=True)
    hashes = {str(LEDGER): r.sha(LEDGER), str(Path(__file__)): r.sha(__file__)}
    ledger = r.read(LEDGER)
    cases = [row['case'] for row in sorted(ledger['rows'], key=lambda row:(row['captured_utc_ns'], row['case'])) if row['eligible']]
    historical, replay, case_rows = [], [], []
    errors = []
    for case in cases:
        try:
            original_path = r.SOURCE / case / 'result.json'
            parent_path = r.SOURCE / 'family_cavity/position' / (case + '.json')
            tracks_path = r.SOURCE / case / 'tracks.json'
            for path in (original_path, parent_path, tracks_path): hashes[str(path)] = r.sha(path)
            original = r.read(original_path)
            d = r.context(case)
            coverage = {arm:r.membership(d, arm, d['arms'][arm]) for arm in ARMS}
            accepted = {arm:set(coverage[arm]['accepted_observation_ids']) for arm in ARMS}
            by_key = {track['key']:track for track in d['scan'].tracks}
            sigma_meta = d['scan'].fixed_window_noise
            def noise_reference(track):
                return np.asarray([sigma_meta['per_observation_noise_sigma_hz'][oid]
                    if sigma_meta['extra_parameter_BIC_gain'] > 0 else d['scan'].radio_sigma_hz
                    for oid in track['observation_ids']])
            for row in original['final_node']['seed']['rows']:
                if not row['active_curvature']: continue
                if not all(key in row for key in ('times_s', 'residual_hz', 'innovations_hz')):
                    historical.append(dict(case=case, component=row['component'], missing_vectors=True,
                        archived_compatible=row['compatible'])); continue
                track = by_key[row['component']]; native = noise_reference(track)
                diag = diagnostics(row['innovations_hz'], row['times_s'])
                checks = flags(diag, len(row['times_s']))
                checks.update(RMS=bool(row['rms_hz'] <= 450), bias=bool(abs(row['bias_hz']) <= 3000))
                actual_rms = float(np.sqrt(np.mean(np.asarray(row['residual_hz']) ** 2)))
                rms_match = bool(np.isclose(actual_rms, row['rms_hz'], rtol=1e-8, atol=1e-6))
                historical.append(dict(case=case, component=row['component'], points=row['points'],
                    archived_compatible=bool(row['compatible']), candidate_index=row['candidate_index'],
                    archived_rms_hz=row['rms_hz'], residual_RMS_hz=actual_rms,
                    native_sigma_median_hz=float(np.median(native)),
                    RMS_over_native_sigma_median=float(actual_rms / np.median(native)),
                    feasible_candidates=row['feasible_candidates'], vector_RMS_matches_reported_RMS=rms_match,
                    coherent_zero_feasible_snapshot=bool(row['feasible_candidates'] == 0 and rms_match),
                    diagnostic_vector_binding='nomination_rows may overwrite candidate/scalars without replacing copied residual vectors',
                    category=category(checks), checks=checks, diagnostics=diag,
                    failed_predicates=[key for key, value in checks.items() if not value]))
            whole = []
            for source, i, sl in zip(d['base'].rows, d['base'].members, d['base'].slices, strict=True):
                if d['keep'][sl].any(): continue
                track = d['scan'].tracks[i]; ids = set(track['observation_ids'])
                overlap = {arm:len(ids & accepted[arm]) for arm in ARMS}
                whole.append((source, i, sl, overlap))
            for arm in ARMS:
                saved = d['arms'][arm]; p = r.build(d, arm, saved['phase_reference'])
                x = np.asarray(saved['endpoint_east_north_km'])
                c, state = p.calculate(x), p.state(x)
                frequency, elevation = p.conditional_frequency(x)
                assert abs(c['negative_twice_elbo'] - saved['negative_twice_elbo']) < 1e-3
                for source, i, sl, overlap in whole:
                    track = d['scan'].tracks[i]; n = len(track['times'])
                    q = track['rf_hz'] / 11.5e9
                    corrected = track['values'] - d['scan'].hardware(track, state['beta'])
                    corrected -= q * d['scan'].rx_basis[i] @ state['smooth'][track['receiver'] - 1]
                    terms = profile(corrected, q * frequency[sl], *d['scan'].white[i])
                    profile_diag = diagnostics(terms['innovations'][0], track['times'])
                    conditional_raw = c['conditional_residual_hz'][sl]
                    conditional_diag = diagnostics(conditional_raw, track['times'])
                    checks = flags(profile_diag, n, 'profile_')
                    checks.update(flags(conditional_diag, n, 'conditional_'))
                    known_alias = p.alias[p.members.index(i)]
                    checks.update(profile_RMS=bool(terms['rms'][0] <= 450),
                        conditional_RMS=bool(np.sqrt(np.mean(conditional_raw ** 2)) <= 450),
                        profile_bias=bool(abs(terms['bias'][0]) <= 3000),
                        alias=bool(int(terms['alias'][0]) == known_alias),
                        visibility=bool(elevation[sl].min() >= 0))
                    native = noise_reference(track)
                    rms = float(np.sqrt(np.mean(conditional_raw ** 2)))
                    replay.append(dict(case=case, arm=arm, component=track['key'], points=n,
                        candidate_index=source['candidate_index'], candidate_norad=source['candidate_norad'],
                        receiver=track['receiver'], channel=track['channel'], alias=known_alias,
                        parent_accepted_ID_overlap=overlap, unowned_in_both_parent_arms=not any(overlap.values()),
                        whole_source_excluded_from_curved_calibration=True,
                        residual_RMS_hz=rms, profile_RMS_hz=float(terms['rms'][0]),
                        native_sigma_median_hz=float(np.median(native)),
                        native_sigma_minimum_hz=float(native.min()), native_sigma_maximum_hz=float(native.max()),
                        RMS_over_native_sigma_median=float(rms / np.median(native)),
                        noise_reference='unchanged supplied per-ID sigma; excludes target-fitted Gamma precision',
                        category=category(checks), checks=checks, profile_diagnostics=profile_diag,
                        conditional_diagnostics=conditional_diag,
                        failed_predicates=[key for key, value in checks.items() if not value],
                        not_an_association_qualification=True))
            case_rows.append(dict(case=case, status='complete', historical_curved_nomination_rows=sum(row['active_curvature'] for row in original['final_node']['seed']['rows']),
                whole_calibration_excluded_curves=len(whole),
                whole_calibration_excluded_and_unowned_both_arms=sum(not any(overlap.values()) for _, _, _, overlap in whole),
                accepted_ID_counts={arm:len(accepted[arm]) for arm in ARMS}))
            print(case, 'complete', len(whole), 'whole excluded', round(time.monotonic() - began, 3), flush=True)
        except Exception as exc:
            errors.append(dict(case=case, error=repr(exc), traceback=traceback.format_exc()))
            if isinstance(exc, TimeoutError): break
    signal.alarm(0)
    observed = [row for row in historical if not row.get('missing_vectors')]
    rejected = [row for row in observed if not row['archived_compatible']]
    coherent = [row for row in rejected if row['coherent_zero_feasible_snapshot']]
    primary = [row for row in replay if row['unowned_in_both_parent_arms']]
    summary = dict(all_cases_completed=len(case_rows) == 24 and not errors, completed_cases=len(case_rows), expected_cases=24,
        elapsed_seconds=time.monotonic() - began, position_fits=0, GPS_used=False,
        historical_nomination=dict(all_rows=len(historical), missing_vector_rows=sum(row.get('missing_vectors', False) for row in historical),
            archived_compatible_false=summarize(rejected), coherent_zero_feasible_rejected=summarize(coherent),
            rejected_ambiguous_vector_binding=sum(not row['coherent_zero_feasible_snapshot'] for row in rejected)),
        current_parent=dict(whole_calibration_excluded_curve_count=sum(row['whole_calibration_excluded_curves'] for row in case_rows),
            unowned_in_both_arms_curve_count=sum(row['whole_calibration_excluded_and_unowned_both_arms'] for row in case_rows),
            all_whole_excluded_arm_records=summarize(replay),
            unowned_whole_excluded_arm_records=summarize(primary)),
        historical_and_current_states_are_distinct=True, native_sigma_is_not_independent_calibrated_noise_truth=True,
        no_new_threshold_no_gate_waiver_no_association_adoption=True, input_sha256=hashes, errors=errors)
    for name, data in [('historical.json', historical), ('current_parent.json', replay), ('cases.json', case_rows), ('summary.json', summary)]:
        r.write_new(HERE / name, data)
    source = Path('/home/mouse9911/gits/leo-tracker-reduxredux/src/leo/analysis/research/polynomial_satellite_diagnostics.py')
    r.write_new(HERE / 'seal.json', dict(files={str(HERE / name):r.sha(HERE / name) for name in
        ('audit.py', 'historical.json', 'current_parent.json', 'cases.json', 'summary.json')},
        fixed_gate_source_sha256=r.sha(source), input_sha256=hashes, position_fits=0, GPS_used=False))
    print(json.dumps({key:value for key, value in summary.items() if key not in ('input_sha256',)}, indent=2), flush=True)


if __name__ == '__main__': run()
