"""Bounded receiver-family catalogue search on a fixed ALGO02 observation set.

No geographic reference is imported. All trials retain every original curved
and predictive observation. Only a reporter may evaluate position accuracy.
"""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time

import numpy as np

from algo02_scan import pair_passes
from ds23_receiver_family_search import (
    apply_proposals, curve_blocks, fine_receiver_basis, replacement_penalty,
)
from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_feasible_position import feasible_fit
from investigate_ds23_adaptive_failures import phase_widths
from learn_ds23_causal_phase_forecast import distribution_cost
from probe_algo03_frame_peak_recovery import context, SOURCE
from probe_algo03_feasible_recovery import gate_slacks
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_frequency_events import cached, refit, summary
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write, sha
from run_dsx01_clean_region import zero_state
from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry, phase_linear_frequency
from leo.analysis.research.retained_track_likelihood import profile, whitening

OUT = ROOT / 'reports/2026_10_20_ds23_receiver_family_search'
ARMS = ('c0', 'fitted_c')


def source_hashes():
    return {str(p.relative_to(ROOT)): sha(p) for p in (
        ROOT/'tools/probe_ds23_receiver_family_search.py',
        ROOT/'tools/ds23_receiver_family_search.py',
        ROOT/'tools/ds23_frequency_events.py', ROOT/'tools/ds23_feasible_position.py')}


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT/'protocol.json'
    if path.exists():
        protocol = read(path)
        if protocol['source_sha256'] != source_hashes():
            raise ValueError('receiver-family experiment source changed')
        return protocol
    cases = read(ROOT/'reports/2026_10_20_ds23_causal_phase_location_validation/protocol.json')['cases']
    protocol = dict(cases=cases, development_case='DS23-0268', workers=20,
        same_site_preselected_random20_not_new_locations=True,
        frozen_before_new_position_error_evaluation=True, minimum_block_points=24,
        minimum_distinct_channels=2, maximum_proposed_blocks=2,
        coarse_phases_s=np.unique(np.r_[np.linspace(-15, 15, 31), np.linspace(-2, 2, 17)]),
        refined_phase_step_s=.05, refined_phase_halfwidth_s=1.,
        candidates_refined_per_block=3, masks_powers_observations_and_other_priors_unchanged=True,
        fine_receiver_basis_spacing_s=10, fine_receiver_basis_width_s=15,
        receiver_basis_variance_normalized_on_fixed_0_300s_grid=True,
        alternatives='fine-basis null, top two receiver-family singles and their simultaneous pair',
        cold_phase_rounds=5, cold_position_iterations_per_round=48,
        constrained_finalists=2, constrained_phase_rounds=5, SLSQP_iterations=40,
        original_gates_unchanged_stricter_normalized_interior=.01,
        discrete_search_cost='2*changed_blocks*log(catalogue_count-1)+2*log(2*max(1,block_count))',
        selection='paired valid; c0 penalized RF gain positive; fitted-c RF gain positive; lowest c0 loss plus penalty',
        incumbent_and_original_covariance_retained_as_fallback=True,
        no_GPS_future_TLE_new_RF_or_point_trimming=True,
        linear_tracks_do_not_update_calibration=True, source_sha256=source_hashes())
    write(path, protocol)
    return protocol


def screen(scan, node, keep, base, old, protocol):
    saved = old['policy_arms']['c0']
    model = old['hyperparameters_from_pre_RF_TLE_only']
    powers = np.asarray(old['weights'])
    labels = sorted({r['candidate_index'] for r in node['seed']['rows']})
    widths, receipts = phase_widths(scan, list(range(len(scan.norads))))
    means = forecast_phase_mean(receipts, model['shrinkage'])
    p = make_event_problem(scan, node, keep, 'c0', np.asarray(saved['phase_reference']),
        powers, means[labels], model, [])
    entries = old['linear_entries'] if old['linear_paired_valid'] else []
    attach_event_predictive(p, entries, powers)
    cached(p)
    x = np.asarray(saved['endpoint_east_north_km'])
    difference = p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo']
    if abs(difference) > 1e-3:
        raise ValueError('original RF likelihood does not replay')
    state = p.state(x)
    blocks = curve_blocks(p.rows, p.members, p.slices, keep, scan.tracks)
    members = sorted({k for b in blocks for k in b['row_indices']})
    data = {}
    for k in members:
        i, sl = p.members[k], p.slices[k]
        t = scan.tracks[i]
        use = keep[sl]
        corrected = t['values']-scan.hardware(t, state['beta'])
        corrected -= t['rf_hz']/11.5e9*scan.rx_basis[i]@state['smooth'][t['receiver']-1]
        data[k] = dict(y=corrected[use], times=t['times'][use], q=t['rf_hz']/11.5e9,
                       white=whitening(t['times'][use]))
    if not blocks:
        return [], dict(blocks=[], null_RF_difference=difference), means, entries
    times = np.unique(np.concatenate([r['times'] for r in data.values()]))
    costs = [np.full(len(scan.norads), np.inf) for _ in blocks]
    phases = [np.zeros(len(scan.norads)) for _ in blocks]
    for phase in protocol['coarse_phases_s']:
        geometry = prepare_phase_geometry(scan.sky, times, np.full(len(scan.norads), phase))
        frequency, elevation, _ = phase_linear_frequency(geometry, *latlon(x))
        terms = {}
        for k, d in data.items():
            ix = np.searchsorted(times, d['times'])
            result = profile(d['y'], d['q']*frequency[:, ix], *d['white'])
            terms[k] = np.where(elevation[:, ix].min(axis=1) >= 0, result['cost'], np.inf)
        prior = distribution_cost(phase-means, widths, model['multiplier'], model['nu'])
        for b, block in enumerate(blocks):
            score = sum(powers[k]*terms[k] for k in block['row_indices'])+prior
            improve = score < costs[b]
            costs[b][improve] = score[improve]
            phases[b][improve] = phase
    records, proposals = [], []
    for b, block in enumerate(blocks):
        ordered = [int(j) for j in np.argsort(costs[b]) if np.isfinite(costs[b][j])]
        alternatives = [j for j in ordered if j != block['original_index']][:protocol['candidates_refined_per_block']]
        nominees = [block['original_index']]+alternatives
        candidates = []
        for j in nominees:
            if not np.isfinite(costs[b][j]):
                continue
            center = phases[b][j]
            local = dict(time_s=scan.sky['time_s'], position_km=scan.sky['position_km'][[j]],
                         velocity_km_s=scan.sky['velocity_km_s'][[j]])
            best = None
            for phase in np.linspace(max(-15, center-1), min(15, center+1), 41):
                geometry = prepare_phase_geometry(local, times, np.array([phase]))
                frequency, elevation, _ = phase_linear_frequency(geometry, *latlon(x))
                score = float(distribution_cost(phase-means[j], widths[j], model['multiplier'], model['nu']))
                aliases = []
                for k in block['row_indices']:
                    d = data[k]
                    ix = np.searchsorted(times, d['times'])
                    r = profile(d['y'], d['q']*frequency[:, ix], *d['white'])
                    score += powers[k]*float(r['cost'][0])
                    aliases.append(int(r['alias'][0]))
                    if elevation[:, ix].min() < 0:
                        score = np.inf
                if np.isfinite(score) and (best is None or score < best['score']):
                    best = dict(candidate_index=j, norad=int(scan.norads[j]), score=score,
                                phase_s=float(phase), aliases=aliases)
            if best is not None:
                candidates.append(best)
        incumbent = next((r for r in candidates if r['candidate_index'] == block['original_index']), None)
        others = [r for r in candidates if r['candidate_index'] != block['original_index']]
        if incumbent is not None and others:
            best = min(others, key=lambda r:r['score'])
            proposals.append(dict(best, block=block, proposal_gain=incumbent['score']-best['score']))
        records.append(dict(block=block, candidates=candidates))
    proposals = sorted(proposals, key=lambda r:r['proposal_gain'], reverse=True)[:protocol['maximum_proposed_blocks']]
    return proposals, dict(blocks=records, null_RF_difference=difference,
        catalogue_candidates=len(scan.norads), proposal_position_RF_only=x,
        shared_phase_per_receiver_block=True, proposal_scores_not_joint_posterior_probabilities=True), means, entries


def make(scan, node, keep, arm, reference, powers, means, model, entries):
    labels = sorted({r['candidate_index'] for r in node['seed']['rows']})
    p = make_event_problem(scan, node, keep, arm, reference, powers, means[labels], model, [])
    attach_event_predictive(p, entries, powers)
    cached(p)
    return p


def constrain(scan, node, keep, powers, means, model, entries, pair):
    result = {}
    for arm in ARMS:
        x = np.asarray(pair[arm]['endpoint_east_north_km'])
        reference = np.asarray(pair[arm]['phase_reference'])
        history = []
        for epoch in range(5):
            p = make(scan, node, keep, arm, reference, powers, means, model, entries)
            fit = feasible_fit(lambda z:p.calculate(z)['negative_twice_elbo'],
                lambda z:np.array(list(gate_slacks(p, z, entries).values()))-.01,
                x, p.lower, p.upper, iterations=40)
            x = np.asarray(fit['parameters'])
            phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
            change = float(np.max(abs(phase-reference)))
            history.append(dict(epoch=epoch, fit=fit, phase_change_s=change))
            reference = phase
        result[arm] = dict(summary(p, x, entries), history=history, final_phase_change_s=change,
                           minimum_gate_slack=min(gate_slacks(p, x, entries).values()))
    return result


def run(case):
    protocol = prepare()
    directory = OUT/case
    directory.mkdir(exist_ok=True)
    if (directory/'result.json').exists():
        return dict(case=case, cached=True)
    scan, node, keep, base, old = context(case)
    original = np.asarray(keep, bool)
    started = time.monotonic()
    proposals, receipt, means, entries = screen(scan, node, original, base, old, protocol)
    write(directory/'screen.json', dict(proposals=proposals, receipt=receipt))
    changed = copy.copy(scan)
    changed.rx_basis = [fine_receiver_basis(t['times']) for t in scan.tracks]
    model, powers = old['hyperparameters_from_pre_RF_TLE_only'], np.asarray(old['weights'])
    combinations = [[]]+[[p] for p in proposals]+([proposals] if len(proposals)>1 else [])
    records = []
    baseline = old['policy_arms']
    for k, offered in enumerate(combinations):
        candidate, predictive = apply_proposals(node, entries, scan.tracks, offered)
        candidate['seed']['state'] = zero_state(changed)
        # Recompute only aliases of changed predictive families against the
        # same original RF calibration used for proposals, never linear fits.
        if offered and predictive:
            source_state = baseline['c0']['state']
            anchor = baseline['c0']['endpoint_east_north_km']
            for original_entry, entry in zip(entries, predictive, strict=True):
                if entry['candidate_index'] == original_entry['candidate_index']:
                    continue
                proposal = next(p for p in offered if p['block']['original_index']==original_entry['candidate_index']
                    and p['block']['receiver']==scan.tracks[entry['track_index']]['receiver'])
                t = scan.tracks[entry['track_index']]
                j = entry['candidate_index']
                local = dict(time_s=scan.sky['time_s'], position_km=scan.sky['position_km'][[j]],
                             velocity_km_s=scan.sky['velocity_km_s'][[j]])
                geometry = prepare_phase_geometry(local, t['times'], np.array([proposal['phase_s']]))
                f, _, _ = phase_linear_frequency(geometry, *latlon(anchor))
                y = t['values']-scan.hardware(t, np.asarray(source_state['beta']))
                y -= t['rf_hz']/11.5e9*scan.rx_basis[entry['track_index']]@np.asarray(source_state['smooth'])[t['receiver']-1]
                terms = profile(y, t['rf_hz']/11.5e9*f, *scan.white[entry['track_index']], bias_sigma=300.)
                entry['alias'] = int(terms['alias'][0])
        labels = sorted({r['candidate_index'] for r in candidate['seed']['rows']})
        arms = {arm:refit(changed, candidate, original, arm, powers, means[labels], model, [], predictive) for arm in ARMS}
        penalty = replacement_penalty(len(scan.norads), len(offered), len(receipt['blocks']))
        record = dict(index=k, node=candidate, entries=predictive, arms=arms, offered=offered,
                      penalty=penalty, paired_valid=pair_passes(arms, include_linear=True))
        records.append(record)
        write(directory/f'trial_{k:02d}.json', record)
        print(case, 'trial', k, 'valid', record['paired_valid'], flush=True)
    # Only RF-preferred failed hypotheses receive the bounded constrained stage.
    failed = [r for r in records if not r['paired_valid'] and
        baseline['c0']['negative_twice_elbo']-r['arms']['c0']['negative_twice_elbo'] > r['penalty']]
    for r in sorted(failed, key=lambda r:r['arms']['c0']['negative_twice_elbo']+r['penalty'])[:2]:
        arms = constrain(changed, r['node'], original, powers, means, model, r['entries'], r['arms'])
        repaired = dict(r, arms=arms, constrained=True, paired_valid=pair_passes(arms, include_linear=True))
        write(directory/f"constrained_{r['index']:02d}.json", repaired)
        records.append(repaired)
    eligible = [r for r in records if r['paired_valid'] and
        baseline['c0']['negative_twice_elbo']-r['arms']['c0']['negative_twice_elbo'] > r['penalty'] and
        baseline['fitted_c']['negative_twice_elbo'] > r['arms']['fitted_c']['negative_twice_elbo']]
    best = min(eligible, key=lambda r:r['arms']['c0']['negative_twice_elbo']+r['penalty']) if eligible else None
    result = dict(case=case, accepted=best is not None, selected=best,
        policy_arms=best['arms'] if best else baseline, baseline_arms=baseline,
        original_mask=original, original_entries=entries, proposals=proposals,
        trial_summaries=[dict(index=r['index'], constrained=r.get('constrained', False),
            valid=r['paired_valid'], penalty=r['penalty'], c0_loss=r['arms']['c0']['negative_twice_elbo']) for r in records],
        seconds=time.monotonic()-started, GPS_used=False, future_TLE_used=False,
        baseline_sha256=sha(SOURCE/case/'algo02_result.json'), source_sha256=source_hashes(),
        every_original_curved_and_predictive_observation_retained=True)
    write(directory/'result.json', result)
    print(case, 'accepted', best is not None, 'seconds', result['seconds'], flush=True)
    return dict(case=case, accepted=best is not None, seconds=result['seconds'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case')
    parser.add_argument('--cohort', action='store_true')
    args = parser.parse_args()
    protocol = prepare()
    if args.case:
        run(args.case)
    elif args.cohort:
        receipts = []
        with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
            futures = {pool.submit(run, case):case for case in protocol['cases']}
            for future in as_completed(futures):
                try:
                    receipts.append(future.result())
                except Exception as exc:
                    receipts.append(dict(case=futures[future], error=repr(exc)))
                write(OUT/'progress.json', dict(completed=len(receipts), total=len(futures), receipts=receipts))
        write(OUT/'execution.json', dict(all_terminal=True, receipts=receipts))
    else:
        print(protocol['cases'])


if __name__ == '__main__':
    main()
