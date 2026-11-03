"""Test long single-curve reentry with uncertain receiver calibration.

The old growth rule required two new RX/channel owners. This diagnostic admits
an independently curved whole track to nomination, retaining the original final
physical modes and all residual gates. Full versus fixed calibration covariance
is an explicit candidate-screen ablation. No linear track calibrates anything.
"""

import argparse
import copy
import itertools
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import time

import numpy as np

from ds23_family_cavity import coarse_phase_scores, predictive_density_reference
from ds23_frequency_events import make_event_problem
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from probe_ds23_family_cavity_nominations import candidate_prediction
from probe_ds23_family_cavity_position import fit_configuration
from probe_ds23_reentry_family_cavity import audit_baseline
from probe_ds23_worst_association_bottleneck import OUT as DEBUG, setup, build, inventory
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, sha, write

OUT = DEBUG/'single_curve_reentry'


def predictive_track_data(d, p, x, row_index):
    c = p.curved_calculate(x) if d['entries'] else p.calculate(x)
    group = p.noise_groups[p.keep]
    weight = d['powers'][group]*c['noise_precision'][group]/p.point_noise[p.keep]**2
    features = c['features'][p.keep]
    precision = np.diag(c['coefficient_prior_precision'])+features.T@(features*weight[:, None])
    covariance = np.linalg.inv(precision)
    i, sl = p.members[row_index], p.slices[row_index]
    track = p.scan.tracks[i]
    if p.keep[sl].any() or i not in p.scan.curved:
        raise ValueError('new whole actively curved graph track required')
    radio_width = p.hardware.shape[1]+p.smooth.shape[1]
    radio = c['features'][sl, :radio_width]
    noise = p.point_noise[sl]*np.sqrt(2/d['powers'][row_index])
    independent = np.diag(noise**2)+300.**2*np.ones((len(noise), len(noise)))
    radio_covariance = radio@covariance[:radio_width, :radio_width]@radio.T
    return dict(p=p, coefficient=c['coefficient'], covariance=covariance, radio_width=radio_width,
                times=track['times'], values=track['values'], q=p.q[sl], radio=radio, noise=noise,
                groups=np.zeros(len(noise), int), base_covariance=independent+radio_covariance,
                fixed_calibration_covariance=independent, radio_covariance=radio_covariance,
                members=[dict(component=track['key'], kind='curved', row_index=row_index,
                              observation_ids=track['observation_ids'], points=len(noise),
                              receiver=track['receiver'], channel=track['channel'])],
                held_owners=1, target=p.rows[row_index]['candidate_index'])


def nominate(d, inv):
    saved = d['arms']['c0']
    x = np.asarray(saved['endpoint_east_north_km'])
    d = dict(d, x=x)
    p = build(d, 'c0', saved['phase_reference'])
    targets = [r for r in inv['ranking'] if r['curved'] and r['points'] >= 12][:3]
    rows = []
    for target in targets:
        k = next(k for k, row in enumerate(p.rows) if row['component'] == target['component'])
        data = predictive_track_data(d, p, x, k)
        f, elevation = phase_frequency_grid(d['scan'].sky, data['times'], *latlon(x), phase_seconds=d['all_means'])
        plus, _ = phase_frequency_grid(d['scan'].sky, data['times'], *latlon(x), phase_seconds=d['all_means']+.01)
        minus, _ = phase_frequency_grid(d['scan'].sky, data['times'], *latlon(x), phase_seconds=d['all_means']-.01)
        scores = {}
        for kind, covariance in [('fixed', data['fixed_calibration_covariance']), ('full', data['base_covariance'])]:
            coarse = coarse_phase_scores(data['values'], data['radio']@data['coefficient'][:data['radio_width']],
                                         f*data['q'], (plus-minus)/.02*data['q'], d['widths'], covariance, data['groups'])
            coarse['score'] = np.where(elevation.min(axis=1) >= 0, coarse['score'], np.inf)
            scores[kind] = coarse
        top = [int(j) for j in np.argsort(scores['full']['score']) if np.isfinite(scores['full']['score'][j])][:7]
        original = p.rows[k]['candidate_index']
        candidates = [original]+[j for j in top if j != original]
        refined = [candidate_prediction(d, data, j, scores['full']['aliases'][j]) for j in candidates]
        refined.sort(key=lambda r: r['score'])
        eligible = [r for r in refined if r['qualified']]
        nominal = next(r for r in refined if r['candidate_index'] == original)
        rows.append(dict(target=target, row_index=k, original_norad=int(d['scan'].norads[original]),
                         all_candidates=len(d['scan'].norads), candidates=refined, best=eligible[0] if eligible else None,
                         original=nominal,
                         radio_prediction_SD_hz_quantiles=np.quantile(np.sqrt(np.diag(data['radio_covariance'])), [.1, .5, .9]),
                         receiver_curved_points={str(rx):sum(int(p.keep[sl].sum()) for i, sl in zip(p.members, p.slices, strict=True)
                                                           if p.scan.tracks[i]['receiver'] == rx) for rx in [1, 2]},
                         coarse_rankings={kind:[dict(norad=int(d['scan'].norads[j]), candidate_index=int(j),
                                                      score=float(result['score'][j]))
                                                 for j in np.argsort(result['score'])[:8] if np.isfinite(result['score'][j])]
                                          for kind, result in scores.items()},
                         proposed_whole_track_never_used_to_learn_calibration=True))
    return dict(targets=rows, full_catalogue_causal=True,
                full_covariance_vs_fixed_mean_changes_only_predictive_receiver_uncertainty=True,
                independent_Student_phase_moment_Gaussian_for_nomination_only=True,
                original_final_Student_and_Gamma_priors_restored=True)


def configurations(nominations):
    targets = nominations['targets']
    offers = [(r, r['best']) for r in targets if r['best'] is not None]
    options = [list(c) for count in range(1, len(offers)+1) for c in itertools.combinations(offers, count)]
    # Always test the original nomination separately if the covariance-aware
    # full-catalogue search favors a different identity. No manual satellite list.
    options += [[(r, r['original'])] for r in targets if r['best'] is None or
                r['original']['candidate_index'] != r['best']['candidate_index']]
    return options


def positions(d, nominations, path):
    trials = []
    for offers in configurations(nominations):
        node = copy.deepcopy(d['node'])
        keep = d['keep'].copy()
        added = 0
        for row, offer in offers:
            k = row['row_index']
            old = d['base']
            sl = old.slices[k]
            added += int((~keep[sl]).sum())
            keep[sl] = True
            node['seed']['rows'][k].update(candidate_index=offer['candidate_index'], candidate_norad=offer['norad'])
            node['aliases'][k] = int(offer['aliases'][0])
        labels = sorted({r['candidate_index'] for r in node['seed']['rows']})
        dd = dict(d, keep=keep)
        result = fit_configuration(dd, node, d['entries'], d['all_means'][labels])
        result.update(added_curved_points=added, mask=keep,
                      additions=[dict(component=r['target']['component'], candidate_index=o['candidate_index'],
                                      norad=o['norad'], alias=int(o['aliases'][0])) for r, o in offers])
        trials.append(result)
        write(path.with_name(path.stem+'_checkpoint.json'), dict(case=d['scan'].case, trials=trials))
        print(d['scan'].case, 'reentry', added, 'points', result['paired_valid'],
              [r['norad'] for r in result['additions']], flush=True)
    passing = [r for r in trials if r['paired_valid']]
    # Counts select masks; normalized RF loss may rank only identical masks.
    passing.sort(key=lambda r: (-r['added_curved_points'], tuple(a['component'] for a in r['additions']),
                                r['arms']['c0']['corrected_selection_loss']))
    selected = passing[0] if passing else None
    return dict(trials=trials, selected=selected, policy_arms=selected['arms'] if selected else d['arms'],
                baseline_arms=d['arms'], unchanged_original_points_entries_noise_powers_and_priors=True)


def one(case, stage):
    target = OUT/(case+'_'+stage+'.json')
    if target.exists():
        raise FileExistsError('preserve original research evidence')
    start = time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('600 s single-curve stage cap')))
    signal.alarm(600)
    try:
        d = setup(case)
        if stage == 'nominations':
            record = nominate(d, read(DEBUG/case/'inventory.json')['arms']['c0'])
        elif stage == 'positions':
            record = positions(d, read(OUT/(case+'_nominations.json')), target)
        else:
            source = OUT/(case+'_positions.json')
            original = read(source)
            checks = []
            for trial in original['trials']:
                dd = dict(d, node=trial['node'], keep=np.asarray(trial['mask'], bool),
                          entries=trial['entries'], means=np.asarray(trial['means']))
                for arm, saved in trial['arms'].items():
                    checks.append(audit_baseline(dd, arm, saved))
            selected = original['selected']
            if selected:
                dd = dict(d, node=selected['node'], keep=np.asarray(selected['mask'], bool),
                          entries=selected['entries'], means=np.asarray(selected['means']), arms=selected['arms'])
                coverage = {arm: inventory(dd, arm) for arm in ['c0', 'fitted_c']}
            else:
                coverage = read(DEBUG/case/'inventory.json')['arms']
            record = dict(checks=checks, all_passed=True, coverage=coverage, source_position_sha256=sha(source),
                          no_geographic_evaluation_yet=True)
        record.update(case=case, status='complete', seconds=time.monotonic()-start,
                      source_sha256=sha(Path(__file__)), protocol_sha256=sha(OUT/'protocol.json'))
    except Exception as exc:
        import traceback
        record = dict(case=case, status='failed', error=repr(exc), traceback=traceback.format_exc(), seconds=time.monotonic()-start)
    finally:
        signal.alarm(0)
    write(target, record)
    print(case, stage, record['status'], round(record['seconds'], 2), record.get('error', ''), flush=True)
    return dict(case=case, status=record['status'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['nominations', 'positions', 'audit'], required=True)
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    protocol = dict(cases=read(DEBUG/'protocol.json')['cases'],
                    targets='three longest wholly unassociated actively curved graph tracks per case',
                    full_causal_catalogue=True, proposed_curve_never_calibrates_nomination=True,
                    covariance='full curved Gaussian calibration covariance, including unsupported receiver offsets/drifts',
                    controls='same candidate screen with radio calibration covariance fixed to zero',
                    at_most_eight_refined_candidates_including_original=True,
                    final_fits='all nonempty combinations of best RF prediction per target; original nomination single controls',
                    acceptance='original both-arm curved/predictive gates and phase convergence; maximum retained points',
                    tie_break='component tuple, then corrected normalized c0 loss only among identical masks',
                    original_final_physical_modes_priors_noise_and_gates=True,
                    no_new_minimum_RX_channel_owner_requirement_for_active_curvature=True,
                    no_linear_track_used_for_calibration=True, no_GPS_future_TLE_new_RF_or_original_point_deletion=True,
                    cold_start=[0, 0], regional_width_km=25, phase_rounds=5, position_iterations=48,
                    same_incumbent_constrained_rescue=True, stage_seconds=600, workers=2,
                    source_sha256=sha(Path(__file__)),
                    original_debug_protocol_sha256=sha(DEBUG/'protocol.json'))
    path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('frozen single-curve protocol changed')
    if not path.exists():
        write(path, protocol)
    if args.stage == 'audit' and not read(OUT/'positions_execution.json')['all_passed']:
        raise ValueError('finish all inference before audit')
    with ProcessPoolExecutor(max_workers=2) as pool:
        results = [f.result() for f in as_completed([pool.submit(one, case, args.stage) for case in protocol['cases']])]
    write(OUT/(args.stage+'_execution.json'), dict(rows=results, all_terminal=True,
                                                all_passed=all(r['status'] == 'complete' for r in results)))


if __name__ == '__main__':
    main()
