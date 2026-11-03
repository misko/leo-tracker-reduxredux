"""Joint full-data tests of whole-family and receiver-split catalogue nominations."""

import argparse
import copy
import itertools
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time
import numpy as np

from algo02_scan import pair_passes
from build_dsx01_orbit_modes import build_modes
from calibrate_ds23_excluded_catalogue import OUT, ARMS, context
from ds23_excluded_catalogue import apply_changes, orbit_frequency_modes
from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_symmetric_family_code import family_code, observed_labels, symmetric_gain
from probe_ds23_frequency_events import refit
from probe_ds23_symmetric_family_selection import constrain
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write, sha
from run_dsx01_clean_region import zero_state
from screen_ds23_excluded_catalogue import prepare as screen_protocol, subbank
from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry, phase_linear_frequency
from leo.analysis.research.retained_track_likelihood import profile


def prepare():
    base = screen_protocol()
    path = OUT / 'fit_protocol.json'
    hashes = {str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),
        ROOT/'tools/ds23_excluded_catalogue.py', ROOT/'tools/ds23_symmetric_family_code.py',
        ROOT/'tools/probe_ds23_symmetric_family_selection.py')}
    if path.exists():
        p = read(path)
        if p['source_sha256'] != hashes:
            raise ValueError('frozen joint catalogue-association experiment changed')
        return p
    p = dict(development_cases=base['development_cases'], confirmation_cases=base['confirmation_cases'],
        pilot_cases=base['pilot_cases'], workers=24, source_sha256=hashes,
        screen_protocol_sha256=sha(OUT/'screen_protocol.json'),
        maximum_nonnull_hypotheses=6, constrained_finalists=2,
        options='unchanged, best distinct whole-family identity, best distinct RX1 identity, best distinct RX2 identity, both RX identities',
        proposal_rank='sum of conditional proposal log-density gains; at least one simultaneous two-family change when possible',
        final_score='complete original curved and predictive RF bound plus symmetric family-label code',
        selection='original paired gates and both coded gains >2log7; choose smallest c0 coded score',
        every_original_point_restored=True, masks_noise_powers_receiver_covariance_and_other_priors_unchanged=True,
        cold_start_km=[0, 0], box_width_km=25, phase_rounds=5, position_iterations=48,
        constrained_phase_rounds=5, constrained_iterations=40, stricter_gate_margin=.01,
        all_changed_predictive_identities_and_aliases_update_coherently=True,
        same_nominations_aliases_masks_priors_and_budgets_in_c_pair=True,
        no_linear_observation_updates_radio_calibration=True,
        no_GPS_future_TLE_new_RF_or_cross_scan_position_prior=True,
        failed_pair_fallback='exact published signed-prior incumbent',
        primary='fitted-c mean AND median improve in both cohorts, all c0 disclosed; frozen broader evaluation before publication')
    write(path, p)
    return p


def nomination(scan, node, p, position, entries, block, candidate):
    old, j, receiver = block['family'], candidate['candidate_index'], block['receiver']
    sky = subbank(scan.sky, [j])
    modes, _ = build_modes(scan, [j], [j], 'physical')
    phase = np.array([candidate['phase_s']])
    orbit_coefficient = np.asarray(candidate['coefficient'])[1:]
    state = p.state(position)
    changes = []
    owners = [('curve', k, i) for k, (row, i) in enumerate(zip(p.rows, p.members, strict=True))
              if row['candidate_index']==old and (receiver is None or scan.tracks[i]['receiver']==receiver)]
    owners += [('linear', k, e['track_index']) for k, e in enumerate(entries)
               if e['candidate_index']==old and (receiver is None or scan.tracks[e['track_index']]['receiver']==receiver)]
    for kind, k, i in owners:
        track = scan.tracks[i]
        geometry = prepare_phase_geometry(sky, track['times'], phase, derivative_step_s=.01)
        frequency, _, _ = phase_linear_frequency(geometry, *latlon(position))
        physical = orbit_frequency_modes(sky, modes, track['times'], phase, latlon(position))[0]
        expected = track['rf_hz']/11.5e9*(frequency[0]+physical@orbit_coefficient)
        radio = scan.hardware(track, state['beta'])+track['rf_hz']/11.5e9*scan.rx_basis[i]@state['smooth'][track['receiver']-1]
        terms = profile(track['values']-radio, expected, *scan.white[i], bias_sigma=300.)
        changes.append(dict(kind=kind, index=k, original_index=old,
            candidate_index=j, norad=candidate['norad'], alias=int(terms['alias'][0])))
    return dict(family=old, receiver=receiver, norad=candidate['norad'],
        conditional_gain=next(r['score'] for r in block['candidates'] if r['candidate_index']==old)-candidate['score'],
        changes=changes, candidate_phase_s=candidate['phase_s'])


def signature(choices):
    return tuple(sorted((r['kind'], r['index'], r['candidate_index'], r['alias']) for c in choices for r in c['changes']))


def hypotheses(scan, node, p, position, entries, screen):
    pools = []
    for target in screen['excluded_targets']:
        family = target['candidate_index']
        offers = []
        for block in screen['blocks']:
            if block['family'] != family:
                continue
            alternative = next((r for r in block['candidates'] if r['candidate_index']!=family and r['qualified']), None)
            if alternative:
                offers.append(nomination(scan, node, p, position, entries, block, alternative))
        options = [[]]+[[offer] for offer in offers]
        split = [o for o in offers if o['receiver'] is not None]
        if len(split)==2:
            options.append(split)
        unique = {}
        for option in options:
            key = signature(option)
            if key not in unique or sum(o['conditional_gain'] for o in option)>sum(o['conditional_gain'] for o in unique[key]):
                unique[key] = option
        pools.append(list(unique.values()))
    all_choices = []
    for parts in itertools.product(*pools):
        choices = [o for part in parts for o in part]
        if choices:
            all_choices.append(dict(choices=choices, gain=sum(o['conditional_gain'] for o in choices),
                changed_family_count=sum(bool(part) for part in parts)))
    unique = {}
    for item in all_choices:
        key = signature(item['choices'])
        if key not in unique or item['gain']>unique[key]['gain']:
            unique[key] = item
    ordered = sorted(unique.values(), key=lambda r:-r['gain'])
    selected = ordered[:6]
    joint = next((r for r in ordered if r['changed_family_count']==2), None)
    if joint and not any(r['changed_family_count']==2 for r in selected):
        selected = selected[:5]+[joint]
    return selected


def run(case):
    protocol = prepare()
    directory = OUT/case
    directory.mkdir(exist_ok=True)
    path = directory/'result.json'
    if path.exists():
        return dict(case=case, cached=True)
    began = time.monotonic()
    scan, node, keep, base, old, signed, model, powers, means, entries, calibration = context(case)
    screen_path = OUT/(case+'_screen.json')
    screen = read(screen_path)
    incumbent = signed['policy_arms']
    if screen['calibration_sha256']!=sha(OUT/(case+'_calibration.json')):
        raise ValueError('screen calibration binding changed')
    if not screen['qualified']:
        write(path, dict(case=case, accepted=False, trials=[], policy_arms=incumbent,
            incumbent_arms=incumbent, reason='excluded calibration did not qualify', no_GPS_or_future_TLE_used=True))
        return dict(case=case, accepted=False, qualified_context=False)
    full_means = np.asarray(screen['means_s'])
    np.testing.assert_allclose(full_means[base.labels], means, atol=1e-12, rtol=0)
    r = calibration['arms']['c0']
    p = make_event_problem(scan, node, np.asarray(calibration['mask'], bool), 'c0', np.asarray(r['phase_reference']), powers, means, model, [])
    attach_event_predictive(p, calibration['predictive_entries'], powers)
    position = np.asarray(r['endpoint_east_north_km'])
    if abs(p.calculate(position)['negative_twice_elbo']-r['negative_twice_elbo'])>1e-3:
        raise ValueError('calibration changed before alias nomination')
    offers = hypotheses(scan, node, p, position, entries, screen)
    write(directory/'hypotheses.json', dict(offers=offers, screen_sha256=sha(screen_path)))
    incumbent_code = family_code(len(scan.norads), observed_labels(node, entries, keep, base.slices))
    trials = []
    for k, offered in enumerate([dict(choices=[], gain=0., changed_family_count=0)]+offers):
        changed, predictive = apply_changes(node, entries, offered['choices'])
        changed['seed']['state'] = zero_state(scan)
        labels = sorted({r['candidate_index'] for r in changed['seed']['rows']})
        arms = {a:refit(scan, changed, keep, a, powers, full_means[labels], model, [], predictive) for a in ARMS}
        code = family_code(len(scan.norads), observed_labels(changed, predictive, keep, base.slices))
        gains = {a:symmetric_gain(incumbent[a]['negative_twice_elbo'], incumbent_code, arms[a]['negative_twice_elbo'], code) for a in ARMS}
        trial = dict(index=k, choices=offered['choices'], changed_family_count=offered['changed_family_count'],
            node=changed, predictive_entries=predictive, arms=arms, code=code,
            coded_gains=gains, paired_valid=pair_passes(arms, include_linear=True))
        trials.append(trial)
        write(directory/f'trial_{k:02d}.json', trial)
    finalists = sorted([t for t in trials if not t['paired_valid'] and t['coded_gains']['c0']>2*np.log(7)],
        key=lambda t:t['arms']['c0']['negative_twice_elbo']+t['code'])[:2]
    for trial in finalists:
        arms = constrain(scan, trial['node'], keep, powers, full_means, model, trial['predictive_entries'], trial['arms'])
        gains = {a:symmetric_gain(incumbent[a]['negative_twice_elbo'], incumbent_code, arms[a]['negative_twice_elbo'], trial['code']) for a in ARMS}
        refined = dict(trial, stage='constrained', arms=arms, coded_gains=gains,
            paired_valid=pair_passes(arms, include_linear=True))
        trials.append(refined)
        write(directory/f"trial_{trial['index']:02d}_constrained.json", refined)
    valid = [t for t in trials if t['paired_valid'] and all(g>2*np.log(7) for g in t['coded_gains'].values())]
    best = min(valid, key=lambda t:t['arms']['c0']['negative_twice_elbo']+t['code']) if valid else None
    write(path, dict(case=case, accepted=best is not None,
        selected_index=best['index'] if best else None, selected_stage=best.get('stage', 'cold') if best else None,
        selected_node=best['node'] if best else node,
        selected_entries=best['predictive_entries'] if best else entries,
        selected_choices=best['choices'] if best else [],
        policy_arms=best['arms'] if best else incumbent, incumbent_arms=incumbent,
        trial_count=len(trials), code=best['code'] if best else incumbent_code,
        coded_gains=best['coded_gains'] if best else {}, original_mask=keep,
        means_s=full_means, powers=powers, incumbent_code=incumbent_code,
        screen_sha256=sha(screen_path), calibration_sha256=sha(OUT/(case+'_calibration.json')),
        seconds=time.monotonic()-began, no_original_points_removed=True,
        no_GPS_or_future_TLE_used=True, source_sha256=protocol['source_sha256']))
    row = dict(case=case, accepted=best is not None, trial_count=len(trials),
        joint_hypotheses=sum(bool(t['changed_family_count']==2) for t in trials), seconds=time.monotonic()-began)
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
                write(OUT/(args.stage+'_fit_progress.json'), dict(completed=len(receipts), total=len(cases)))
        write(OUT/(args.stage+'_fit_execution.json'), dict(all_terminal=True, receipts=receipts,
            errors=[r for r in receipts if 'error' in r]))
        print('Terminal', len(receipts), 'errors', sum('error' in r for r in receipts), flush=True)
