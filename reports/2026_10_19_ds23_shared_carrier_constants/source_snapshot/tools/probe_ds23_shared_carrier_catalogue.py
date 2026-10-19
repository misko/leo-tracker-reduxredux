"""Fresh all-bank family screening after dense receiver/carrier-model changes."""

import argparse
from pathlib import Path
import numpy as np
from ds23_correlated_family_screen import screen
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo01_0217_improvements import changed_node
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_refined_family_catalogue import OUT as CATALOGUE
from probe_ds23_shared_carrier_constants import OUT, context, constant_covariance, refit
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency


def prepare(case):
    scan, node, keep, powers, noise, radio, model, means, old = context(case, 'dense', 'fast_rx1')
    current = read(OUT / 'dense/fast_rx1' / (case + '.json'))
    mode = current['selected']
    incumbent = current['results'][mode]
    state = incumbent['arms']['c0']['state']
    previous = read(CATALOGUE / (case + '_companion.json'))
    source = previous['chosen']['proposal']['index']
    p = problem(scan, node, 'c0', keep)
    members = [k for k, row in enumerate(p.rows) if row['candidate_index'] == source]
    if not members or not all(keep[p.slices[k]].any() for k in members):
        raise ValueError('complete active target family required')
    rf = [scan.tracks[p.members[k]]['rf_hz'] for k in members]
    covariance = constant_covariance(np.zeros(len(members), int), rf, mode)
    endpoint = np.array(incumbent['arms']['c0']['endpoint_east_north_km'])
    anchors = [np.zeros(2), endpoint] + [np.clip(endpoint+d, -12.5, 12.5) for d in ([2, 0], [-2, 0], [0, 2], [0, -2])]
    widths, receipts = phase_widths(scan, list(range(len(scan.norads))))
    phase_means = forecast_phase_mean(receipts, model['shrinkage'])
    widths = np.array(widths)*model['multiplier']
    proposals, screens = {}, []
    occupied = {row['candidate_index'] for row, sl in zip(p.rows, p.slices, strict=True) if keep[sl].any() and row['candidate_index'] != source}
    for ai, anchor in enumerate(anchors):
        frequency, elevation, derivative = phase_linear_frequency(scan.geometry, *latlon(anchor))
        curves = []
        for k in members:
            i, sl = p.members[k], p.slices[k]
            track, active = scan.tracks[i], keep[sl]
            index, q = scan.index[i][active], track['rf_hz']/11.5e9
            y = track['values'] - scan.hardware(track, np.array(state['beta'])) - q*scan.rx_basis[i] @ np.array(state['smooth'])[track['receiver']-1]
            sigma = np.array([noise.get(o, s) for o, s in zip(track['observation_ids'], p.point_noise[sl], strict=True)])[active]
            curves.append(dict(observed=y[active], predicted=q*(frequency[:, index]+derivative[:, index]*phase_means[:, None]),
                derivative=q*derivative[:, index], sigma=sigma, power=powers[k], visible=np.min(elevation[:, index], axis=1) >= 0))
        result = screen(curves, widths, covariance)
        order = [int(j) for j in np.argsort(result['cost']) if np.isfinite(result['cost'][j]) and j not in occupied]
        screens.append(dict(anchor=anchor, eligible_count=len(order), source_rank=order.index(source)+1 if source in order else None,
            top=[dict(index=j, norad=int(scan.norads[j]), cost=float(result['cost'][j])) for j in order[:20]]))
        for j in order[:6] + [source] + [r['proposal']['index'] for r in previous['trials'] if 'arms' in r]:
            if j in occupied:
                continue
            changes = [dict(row_index=k, candidate_index=j, alias=int(node['aliases'][k]) if j == source else int(a[j])) for k, a in zip(members, result['aliases'], strict=True)]
            cost = float(result['cost'][j]) if np.isfinite(result['cost'][j]) else None
            proposal = dict(index=j, norad=int(scan.norads[j]), cost=cost, anchor=ai, changes=changes)
            if j not in proposals or (cost is not None and (proposals[j]['cost'] is None or cost < proposals[j]['cost'])):
                proposals[j] = proposal
    selected = sorted(proposals.values(), key=lambda r:r['cost'] if r['cost'] is not None else np.inf)[:6]
    retained = {source} | {r['proposal']['index'] for r in previous['trials'] if 'arms' in r}
    selected += [r for j, r in proposals.items() if j in retained and not any(s['index'] == j for s in selected)]
    if len(selected) > 12:
        raise ValueError('bounded twelve-finalist budget exceeded')
    destination = OUT / 'catalogue'
    destination.mkdir(parents=True, exist_ok=True)
    write(destination / (case + '_plan.json'), dict(case=case, mode=mode, catalogue_size=len(scan.norads), source_index=int(source),
        source_norad=int(scan.norads[source]), proposals=selected, screens=screens, mask=keep,
        baseline_sha256=sha(OUT / 'dense/fast_rx1' / (case + '.json')), source_sha256=sha(Path(__file__)),
        screen_source_sha256=sha(ROOT / 'tools/ds23_correlated_family_screen.py'),
        no_GPS_used=True, mergers_excluded=True, previous_RF_shortlist_retained=True, source_aliases_preserved_for_reused_baseline=True,
        phase_and_correlated_biases_integrated_but_physical_orbit_modes_not_in_cheap_screen=True))
    print(case, 'fresh correlated all-bank screen', len(scan.norads), 'shortlist', len(selected), flush=True)


def run(case):
    directory = OUT / 'catalogue'
    plan = read(directory / (case + '_plan.json'))
    assert plan['source_sha256'] == sha(Path(__file__))
    scan, node, keep, powers, noise, radio, model, means, old = context(case, 'dense', 'fast_rx1')
    current = read(OUT / 'dense/fast_rx1' / (case + '.json'))
    assert sha(OUT / 'dense/fast_rx1' / (case + '.json')) == plan['baseline_sha256']
    trials = []
    for proposal in plan['proposals']:
        if proposal['index'] == plan['source_index']:
            record = dict(current['results'][plan['mode']], reused_exact_frozen_fit=True)
        else:
            candidate = changed_node(scan, node, proposal['changes'])
            p = problem(scan, candidate, 'c0', keep)
            _, receipts = phase_widths(scan, p.labels)
            candidate_means = forecast_phase_mean(receipts, model['shrinkage'])
            pair = {arm: refit(scan, candidate, keep, powers, noise, model, candidate_means, arm, plan['mode'], 'dense') for arm in ('c0', 'fitted_c')}
            valid = all(t['compatible'] for r in pair.values() for t in r['gates']['tracks'])
            record = dict(arms=pair, paired_valid=valid)
        trials.append(dict(proposal=proposal, **record))
        write(directory / (case + '_partial.json'), dict(case=case, trials=trials))
        print(case, 'new carrier catalogue', proposal['norad'], 'valid', record['paired_valid'], flush=True)
    valid = [t for t in trials if t['paired_valid']]
    selected = min(valid, key=lambda t:t['arms']['c0']['negative_twice_elbo'])
    write(directory / (case + '.json'), dict(case=case, mode=plan['mode'], trials=trials, chosen=selected,
        source_sha256=sha(Path(__file__)), plan_sha256=sha(directory / (case + '_plan.json')),
        no_GPS_used=True, matched_c_pair_five_rounds_48_steps_from_regional_center=True,
        candidate_phase_means_recomputed_in_candidate_label_order=True,
        same_data_masks_powers_noise_and_fixed_carrier_prior_for_all_identities=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True)
    parser.add_argument('--stage', choices=['prepare', 'fit'], required=True)
    args = parser.parse_args()
    prepare(args.case) if args.stage == 'prepare' else run(args.case)
