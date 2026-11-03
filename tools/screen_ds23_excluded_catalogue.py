"""Whole-catalogue uncertainty-aware nominations from two-family-excluded fits."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time
import numpy as np

from build_dsx01_orbit_modes import build_modes
from calibrate_ds23_excluded_catalogue import OUT, ARMS, context, prepare as calibration_protocol
from ds23_excluded_catalogue import gaussian_candidates, propose_aliases, orbit_frequency_modes
from ds23_causal_phase_location import adjust_means
from ds23_frequency_events import make_event_problem, attach_event_predictive
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry, phase_linear_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD


def prepare():
    base = calibration_protocol()
    path = OUT / 'screen_protocol.json'
    hashes = {str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),
        ROOT / 'tools/ds23_excluded_catalogue.py', ROOT / 'tools/build_dsx01_orbit_modes.py')}
    if path.exists():
        p = read(path)
        if p['source_sha256'] != hashes:
            raise ValueError('frozen excluded-family catalogue screen changed')
        return p
    p = dict(development_cases=base['development_cases'], confirmation_cases=base['confirmation_cases'],
        pilot_cases=base['pilot_cases'], workers=24, source_sha256=hashes,
        calibration_protocol_sha256=sha(OUT / 'calibration_protocol.json'),
        catalogue='every nominal causal satellite; no earlier shortlist reused',
        proposal_position='cold two-family-excluded c0 RF fit, never evaluation coordinate',
        covariance='full shared radio posterior covariance plus unseen Gamma noise and 300Hz independent fragment constants',
        candidate_prior='same causal phase mean/variance and same three physical orbit modes as final model; moment-matched Gaussian proposal only',
        anchors_in_phase_sigma=[-1., 0., 1.], maximum_anchor_offset_s=10.,
        shortlist_alternatives=6, refined_phase_rounds=6,
        blocks='whole held family and each receiver block with >=24 active curved points and >=2 channels',
        alias_proposals='one integer 1/4.4us pilot period per fragment; common c0 nominations in both final c arms',
        proposal_scores_not_final_joint_evidence_or_identity_probabilities=True,
        no_held_family_calibrates_radio_or_position=True,
        no_GPS_future_TLE_new_RF_or_cross_scan_position_prior=True)
    write(path, p)
    return p


def block_data(p, x, original, family, receiver=None):
    c = p.calculate(x)
    rows, indices, groups, offset = [], [], [], 0
    for k, (row, i, sl) in enumerate(zip(p.rows, p.members, p.slices, strict=True)):
        t = p.scan.tracks[i]
        if row['candidate_index'] != family or (receiver is not None and t['receiver'] != receiver):
            continue
        use = original[sl]
        if not use.any():
            continue
        rows.append(k)
        indices.extend(np.arange(sl.start, sl.stop)[use].tolist())
        groups.extend([offset]*int(use.sum()))
        offset += 1
    if not indices:
        return None
    index, groups = np.asarray(indices, int), np.asarray(groups, int)
    radio_width = p.hardware.shape[1]+p.smooth.shape[1]
    design = c['features']
    w = p.powers[p.noise_groups[p.keep]]*c['noise_precision'][p.noise_groups[p.keep]]/p.point_noise[p.keep]**2
    gram = np.diag(c['coefficient_prior_precision'])+design[p.keep].T@(design[p.keep]*w[:, None])
    root = np.linalg.cholesky((gram+gram.T)/2)
    radio = np.zeros((len(index), design.shape[1]))
    radio[:, :radio_width] = design[index, :radio_width]
    transform = np.linalg.solve(root, radio.T)
    covariance = transform.T@transform
    sigma2 = 2*p.point_noise[index]**2/p.powers[p.noise_groups[index]]
    covariance += np.diag(sigma2)
    constants = np.eye(offset)[groups]*300.
    covariance += constants@constants.T
    native = np.concatenate([p.scan.tracks[p.members[k]]['values'][original[p.slices[k]]] for k in rows])
    radio_mean = radio@c['coefficient']
    channels = sorted({p.scan.tracks[p.members[k]]['channel'] for k in rows})
    return dict(family=family, receiver=receiver, rows=rows, index=index, groups=groups,
        observed=native-radio_mean, times=p.flat_times[index], q=p.q[index], covariance=covariance,
        points=len(index), channels=channels, radio_covariance_trace=float(np.sum(transform**2)))


def subbank(bank, labels, modes=False):
    labels = np.asarray(labels, int)
    selected = (3*labels[:, None]+np.arange(3)).ravel() if modes else labels
    return dict(time_s=bank['time_s'], position_km=bank['position_km'][selected], velocity_km_s=bank['velocity_km_s'][selected])


def evaluate_candidates(data, sky, modes, reference, means, sigma, location):
    geometry = prepare_phase_geometry(sky, data['times'], reference, derivative_step_s=.01)
    f, elevation, derivative = phase_linear_frequency(geometry, *location)
    expected = data['q'][None]*(f+derivative*(means-reference)[:, None])
    phase = data['q'][None]*derivative*sigma[:, None]
    orbital = orbit_frequency_modes(sky, modes, data['times'], reference, location)*data['q'][None, :, None]
    features = np.concatenate((phase[..., None], orbital), axis=2)
    aliases, raw = propose_aliases(data['observed'], expected, data['groups'], data['covariance'])
    result = gaussian_candidates(raw, features, data['covariance'])
    result.update(phase_s=means+sigma*result['coefficient'][:, 0], aliases=aliases,
        visible=elevation.min(axis=1)>=0, minimum_elevation_deg=elevation.min(axis=1))
    return result


def screen_block(scan, mode_bank, data, means, sigma, position, protocol):
    count = len(scan.norads)
    costs, phases = np.full(count, np.inf), np.zeros(count)
    for anchor in protocol['anchors_in_phase_sigma']:
        reference = np.clip(means+anchor*np.minimum(sigma, 10.), -15, 15)
        result = evaluate_candidates(data, scan.sky, mode_bank, reference, means, sigma, latlon(position))
        valid = result['visible'] & (abs(result['phase_s'])<=15)
        improved = valid & (result['cost']<costs)
        costs[improved] = result['cost'][improved]
        phases[improved] = result['phase_s'][improved]
    family = data['family']
    order = [int(j) for j in np.argsort(costs) if np.isfinite(costs[j])]
    shortlist = [family]+[j for j in order if j != family][:protocol['shortlist_alternatives']]
    sky, modes = subbank(scan.sky, shortlist), subbank(mode_bank, shortlist, True)
    reference = phases[shortlist]
    reference[~np.isfinite(costs[shortlist])] = means[shortlist][~np.isfinite(costs[shortlist])]
    for _ in range(protocol['refined_phase_rounds']):
        result = evaluate_candidates(data, sky, modes, reference, means[shortlist], sigma[shortlist], latlon(position))
        next_reference = np.clip(result['phase_s'], -15, 15)
        changes = abs(next_reference-reference)
        reference = next_reference
    candidates = []
    for k, j in enumerate(shortlist):
        candidates.append(dict(candidate_index=int(j), norad=int(scan.norads[j]), score=float(result['cost'][k]),
            phase_s=float(result['phase_s'][k]), coefficient=result['coefficient'][k],
            phase_change_s=float(changes[k]), aliases=result['aliases'][k],
            qualified=bool(result['visible'][k] and abs(result['phase_s'][k])<=15 and changes[k]<=.01),
            minimum_elevation_deg=float(result['minimum_elevation_deg'][k])))
    return dict(family=family, original_norad=int(scan.norads[family]), receiver=data['receiver'],
        points=data['points'], channels=data['channels'], rows=data['rows'],
        radio_covariance_trace=data['radio_covariance_trace'], candidates=sorted(candidates, key=lambda r:r['score']),
        catalogue_candidates=count, original_family_absent_from_calibration=True)


def run(case):
    protocol = prepare()
    path = OUT / (case+'_screen.json')
    if path.exists():
        return dict(case=case, cached=True)
    began = time.monotonic()
    scan, node, original, base, old, signed, model, powers, means, entries, calibration = context(case)
    if not calibration['qualified']:
        write(path, dict(case=case, qualified=False, blocks=[], calibration_sha256=sha(OUT/(case+'_calibration.json'))))
        return dict(case=case, qualified=False)
    r = calibration['arms']['c0']
    p = make_event_problem(scan, node, np.asarray(calibration['mask'], bool), 'c0', np.asarray(r['phase_reference']), powers, means, model, [])
    attach_event_predictive(p, calibration['predictive_entries'], powers)
    p.powers = powers
    x = np.asarray(r['endpoint_east_north_km'])
    difference = p.calculate(x)['negative_twice_elbo']-r['negative_twice_elbo']
    if abs(difference)>1e-3:
        raise ValueError('excluded-family calibration does not replay')
    labels = list(range(len(scan.norads)))
    widths, receipts = phase_widths(scan, labels)
    full_means = forecast_phase_mean(receipts, model['shrinkage'])
    if signed['accepted']:
        full_means = adjust_means(full_means, receipts, model, signed['selection'])
    np.testing.assert_allclose(full_means[base.labels], means, atol=1e-12, rtol=0)
    mode_started = time.monotonic()
    modes, metadata = build_modes(scan, labels, labels, 'physical')
    mode_seconds = time.monotonic()-mode_started
    blocks = []
    for target in calibration['targets']:
        family = target['candidate_index']
        for receiver in (None, 1, 2):
            data = block_data(p, x, original, family, receiver)
            if data is None or (receiver is not None and (data['points']<24 or len(data['channels'])<2)):
                continue
            blocks.append(screen_block(scan, modes, data, full_means, widths*model['multiplier'], x, protocol))
    write(path, dict(case=case, qualified=True, blocks=blocks, means_s=full_means,
        physical_mode_metadata=metadata, mode_build_seconds=mode_seconds,
        calibration_position_km=x, excluded_targets=calibration['targets'],
        calibration_sha256=sha(OUT/(case+'_calibration.json')),
        seconds=time.monotonic()-began, no_GPS_or_future_TLE_used=True,
        no_held_observation_updates_calibration=True, proposal_Gaussian_approximation=True,
        source_sha256=protocol['source_sha256']))
    row = dict(case=case, blocks=len(blocks), catalogue_count=len(scan.norads), mode_build_seconds=mode_seconds,
        seconds=time.monotonic()-began)
    print(row, flush=True)
    return row


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('prepare', 'pilot', 'cohort'), required=True)
    args = parser.parse_args()
    protocol = prepare()
    if args.stage != 'prepare':
        cases = protocol['pilot_cases'] if args.stage=='pilot' else protocol['development_cases']+protocol['confirmation_cases']
        receipts = []
        with ProcessPoolExecutor(max_workers=min(24, len(cases))) as pool:
            futures = {pool.submit(run, c):c for c in cases}
            for f in as_completed(futures):
                try:
                    receipts.append(f.result())
                except Exception as exc:
                    receipts.append(dict(case=futures[f], error=repr(exc)))
                write(OUT / (args.stage+'_screen_progress.json'), dict(completed=len(receipts), total=len(cases)))
        write(OUT / (args.stage+'_screen_execution.json'), dict(all_terminal=True, receipts=receipts,
            errors=[r for r in receipts if 'error' in r]))
        print('Terminal', len(receipts), 'errors', sum('error' in r for r in receipts), flush=True)
