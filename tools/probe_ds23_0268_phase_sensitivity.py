"""RF-only family exclusion motivated by the largest fitted sky displacement.

Diagnostic only: a large phase is not proof of a wrong emitter identity.
"""

import copy
import argparse
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from ablate_ds23_frequency_event_satellites import removal_mask
from algo02_scan import pair_passes
from audit_ds23_algo01_coverage import coverage
from debug_ds23_0268_visibility_reentry import OUT as SOURCE_OUT
from ds23_feasible_position import feasible_fit
from ds23_frequency_events import make_event_problem, attach_event_predictive, extend_event_associations
from investigate_ds23_0268_remaining_tracks import load, fine_receiver_basis
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo03_feasible_recovery import gate_slacks
from probe_algo03_frame_peak_recovery import context, SOURCE
from probe_ds23_0268_selected_identity_split import replay_proposal
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_frequency_events import refit, summary, cached
from review_ds23_0268_geometry import OUT, PROPOSAL
from run_algo01_ds23_sample import ROOT, read, write, sha


def job(arm):
    destination = OUT / ('phase_exclusion_' + arm + '.json')
    if destination.exists():
        raise FileExistsError('preserve completed family-exclusion trial')
    source = SOURCE_OUT / (PROPOSAL + '.json')
    record = read(source)
    with (OUT / 'per_satellite_receiver.csv').open() as handle:
        import csv
        rows = list(csv.DictReader(handle))
    # Pick the same family for both arms, without position-error diagnostics.
    target = int(max(rows, key=lambda r: float(r['maximum_direction_correction_deg']))['norad'])
    replay, _ = replay_proposal(record, arm)
    entries = record['predictive_entries']
    keep, entries = removal_mask(replay.rows, replay.slices, record['mask'], entries, norads=(target,))
    scan, _, saved, _, _ = load()
    scan = copy.copy(scan)
    scan.rx_basis = [fine_receiver_basis(t['times']) for t in scan.tracks]
    old = context('DS23-0268')[4]
    hyper = old['hyperparameters_from_pre_RF_TLE_only']
    labels = sorted({r['candidate_index'] for r in record['node']['seed']['rows']})
    _, receipts = phase_widths(scan, labels)
    means = forecast_phase_mean(receipts, hyper['shrinkage'])
    powers = np.asarray(record['powers'])
    cold = refit(scan, record['node'], keep, arm, powers, means, hyper, saved['events'], entries)
    x = np.asarray(cold['endpoint_east_north_km'])
    reference = np.asarray(cold['phase_reference'])
    history = []
    for epoch in range(5):
        p = make_event_problem(scan, record['node'], keep, arm, reference,
            powers, means, hyper, saved['events'])
        attach_event_predictive(p, entries, powers)
        cached(p)
        result = feasible_fit(lambda z: p.calculate(z)['negative_twice_elbo'],
            lambda z: np.array(list(gate_slacks(p, z, entries).values())) - .01,
            x, p.lower, p.upper, iterations=40)
        x = np.asarray(result['parameters'])
        phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
        change = float(np.max(abs(phase - p.reference)))
        history.append(dict(epoch=epoch, fit=result, phase_change_s=change))
        reference = phase
    endpoint = dict(summary(p, x, entries), history=history, final_phase_change_s=change,
        minimum_gate_slack=min(gate_slacks(p, x, entries).values()))
    before = read(SOURCE_OUT / 'accepted_identity_split_coverage.json')[PROPOSAL][arm]
    forbidden = {oid for r in before['accepted_rows'] if r['norad'] == target
                 for oid in r.get('observation_ids', next(t for t in scan.tracks if t['key'] == r['component'])['observation_ids'])}
    allowed = set(before['associated_observation_ids']) - forbidden
    candidates = extend_event_associations(p, x, endpoint['gates'])['tracks']
    accepted = {}
    by_key = {t['key']: t for t in scan.tracks}
    for r in candidates + endpoint['linear_gates'] + endpoint['gates']['tracks']:
        if not r['compatible'] or r['norad'] == target:
            continue
        owned = set(r.get('observation_ids', by_key[r['component']]['observation_ids'])) & allowed
        if owned:
            accepted[r['component']] = dict(r, observation_ids=sorted(owned))
    original = {o['observation_id'] for o in read(SOURCE / 'DS23-0268/observations.json')}
    cov = coverage(list(accepted.values()), scan.tracks, original)
    write(destination, dict(arm=arm, excluded_norad=target, arms={arm: endpoint},
        cold= cold, coverage=cov, accepted_rows=list(accepted.values()),
        expected_remaining_original_associations=len(allowed),
        lost_other_original_associations=len(allowed - set(cov['associated_observation_ids'])),
        mask=keep, predictive_entries=entries, node=record['node'], powers=powers,
        selected_source_sha256=sha(source), geometry_audit_sha256=sha(OUT / 'audit.json'),
        source_sha256=sha(ROOT / 'tools/probe_ds23_0268_phase_sensitivity.py'),
        exclusion_selected_without_GPS=True, no_future_TLE_used=True,
        diagnostic_not_a_general_family_deletion_rule=True, cold_start_km=[0, 0],
        phase_rounds=5, position_steps_per_round=48, constrained_rounds=5, constrained_steps=40))
    print(arm, target, cov['associated_original_percent'], flush=True)


def verify():
    """Fresh original-gate, ownership and nominal-SGP4 replay, with no refit."""
    from analyze_dsx01_fixed_site import ecef_states
    from audit_ds23_0268_sky_visibility import angular_separation
    from leo.sky.propagation import parse_element_sets
    from leo.sky.frames import look_angles, geodetic_to_ecef_km, ecef_to_enu_matrix
    from prototype_dsx01_continuous_position import latlon
    from review_ds23_0268_geometry import csv_write

    records = {a: read(OUT / ('phase_exclusion_' + a + '.json')) for a in ('c0', 'fitted_c')}
    elements = read(SOURCE / 'DS23-0268/nominal_elements.json')
    station_path = ROOT / 'deploy/station/gauss-r20-lt3d-004b-20261001-v1.json'
    station = read(station_path)
    axes = {r['receiver_id'] + 1: (r['azimuth_deg'], r['elevation_deg']
            if r['elevation_deg'] is not None else 90 - station['nominal_outward_tilt_deg'])
            for r in station['receivers']}
    sky, checks = [], {}
    for arm, record in records.items():
        if record['selected_source_sha256'] != sha(SOURCE_OUT / (PROPOSAL + '.json')):
            raise ValueError('family exclusion starting model changed')
        p, x = replay_proposal(record, arm)
        fresh = summary(p, x, record['predictive_entries'])
        if not all(r['compatible'] for r in fresh['gates']['tracks'] + fresh['linear_gates']):
            raise ValueError('original retained gates no longer pass')
        if record['arms'][arm]['final_phase_change_s'] > .01:
            raise ValueError('phase did not converge')
        candidates = extend_event_associations(p, x, fresh['gates'])['tracks']
        accepted = {r['component']: r for r in candidates + fresh['linear_gates'] + fresh['gates']['tracks']
                    if r['compatible'] and r['norad'] != record['excluded_norad']}
        seen = set()
        for row in record['accepted_rows']:
            retained = accepted[row['component']]
            track = next(t for t in p.scan.tracks if t['key'] == row['component'])
            owned = set(row['observation_ids'])
            if retained['norad'] != row['norad'] or not owned <= set(retained.get('observation_ids', track['observation_ids'])):
                raise ValueError('fresh association identity or membership changed')
            if seen & owned:
                raise ValueError('duplicate associated observation')
            seen.update(owned)
            use = np.array([oid in owned for oid in track['observation_ids']])
            times = track['times'][use]
            item = elements[str(row['norad'])]
            provenance = item['provenance']
            if max(provenance['element_epoch_utc_ns'], provenance['collected_utc_ns']) > p.scan.receipt['cutoff_utc_ns']:
                raise ValueError('noncausal nominal element')
            pos, vel, usable = ecef_states(parse_element_sets('\n'.join(item['lines'])),
                p.scan.receipt['origin_utc_ns'], times)
            if not usable.all():
                raise ValueError('nominal SGP4 propagation failed')
            az, el, _, _ = look_angles(pos[0], vel[0], geodetic_to_ecef_km(*latlon(x), 0.),
                ecef_to_enu_matrix(*latlon(x)))
            off = angular_separation(az, el, *axes[track['receiver']])
            for oid, a, e, o in zip(np.array(track['observation_ids'])[use], az, el, off, strict=True):
                sky.append(dict(arm=arm, observation_id=oid, norad=row['norad'], receiver=track['receiver'],
                    azimuth_deg=float(a), elevation_deg=float(e), nominal_off_axis_deg=float(o)))
        if seen != set(record['coverage']['associated_observation_ids']):
            raise ValueError('independent membership does not reproduce')
        selected = [r for r in sky if r['arm'] == arm]
        checks[arm] = dict(points=len(seen), satellites=len({r['norad'] for r in selected}),
            minimum_nominal_elevation_deg=min(r['elevation_deg'] for r in selected),
            maximum_nominal_off_axis_deg=max(r['nominal_off_axis_deg'] for r in selected),
            below_horizon=sum(r['elevation_deg'] < 0 for r in selected),
            behind_nominal_feed=sum(r['nominal_off_axis_deg'] > 90 for r in selected),
            original_residual_gates_and_membership_replayed=True,
            fit_sha256=sha(OUT / ('phase_exclusion_' + arm + '.json')))
    csv_write(OUT / 'phase_exclusion_nominal_sky.csv', sky)
    write(OUT / 'phase_exclusion_independent_audit.json', dict(checks=checks,
        all_terminal=True, station_sha256=sha(station_path), no_GPS_or_future_TLE_used=True))
    print(checks, flush=True)


def run():
    with ProcessPoolExecutor(max_workers=2) as pool:
        list(pool.map(job, ('c0', 'fitted_c')))
    records = {a: read(OUT / ('phase_exclusion_' + a + '.json')) for a in ('c0', 'fitted_c')}
    pair = {a: r['arms'][a] for a, r in records.items()}
    write(OUT / 'phase_exclusion_execution.json', dict(all_terminal=True,
        paired_valid=pair_passes(pair, include_linear=True),
        excluded_norad={a: r['excluded_norad'] for a, r in records.items()}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('run', 'verify'), default='run')
    verify() if parser.parse_args().stage == 'verify' else run()
