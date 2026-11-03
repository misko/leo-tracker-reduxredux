"""RF-only test: predictive linear gates, with no gate-driven position refit."""

import copy
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time
import numpy as np

from algo02_scan import pair_passes
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from probe_algo03_frame_peak_recovery import context
from probe_ds23_frequency_events import parameters, refit
from probe_ds23_gate_retention_cohort import OUT as PREVIOUS, ARMS, make
from investigate_ds23_0268_remaining_tracks import fine_receiver_basis
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.predictive_track_gate import predictive_track_gate
from leo.analysis.research.retained_track_likelihood import profile

OUT = ROOT / 'reports/2026_10_20_ds23_predictive_gate_cohort'


def linear_metrics(p, x, entries, powers):
    if not entries:
        return []
    c = p.calculate(x)
    view, values, sigma, groups, slices = linear_geometry(p, entries)
    geometry = geometry_features(view, x, 0.)
    design = geometry['features']
    raw = values-view.q*geometry['intercept']-design@c['coefficient']
    g = p.noise_groups[p.keep]
    weight = powers[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
    u = c['features'][p.keep]
    gram = np.diag(c['coefficient_prior_precision'])+u.T@(u*weight[:, None])
    result = []
    for entry, sl in zip(entries, slices, strict=True):
        t = p.scan.tracks[entry['track_index']]
        terms = profile(raw[sl], np.zeros(sl.stop-sl.start), *p.scan.white[entry['track_index']], bias_sigma=300.)
        gate = predictive_track_gate(raw[sl], design[sl], gram, sigma[sl]*np.sqrt(2), t['times'])
        physical = bool(terms['rms'][0] <= 450 and abs(terms['bias'][0]) <= 3000
                        and int(terms['alias'][0]) == 0 and geometry['elevation'][sl].min() >= 0)
        result.append(dict(component=entry['component'], norad=entry['norad'], candidate_index=entry['candidate_index'],
            observation_ids=entry['observation_ids'], points=len(raw[sl]), compatible=bool(physical and gate['compatible']),
            physical_bounds_pass=physical, predictive_gate=gate, profile_rms_hz=float(terms['rms'][0]),
            profile_bias_hz=float(terms['bias'][0])))
    return result


def run_case(case):
    path = OUT / (case+'.json')
    if path.exists():
        return dict(case=case, cached=True)
    start = time.monotonic()
    scan, node, keep, base, old = context(case)
    powers, means, hyper = parameters(scan, base, old)
    entries = old['linear_entries'] if old['linear_paired_valid'] else []
    fine = copy.copy(scan)
    fine.rx_basis = [fine_receiver_basis(t['times']) for t in scan.tracks]
    node = copy.deepcopy(node)
    node['seed']['state']['smooth'] = np.zeros((2, fine.rx_basis[0].shape[1]))
    arms, legacy = {}, {}
    for arm in ARMS:
        r = refit(fine, node, keep, arm, powers, means, hyper, [], entries)
        legacy[arm] = copy.deepcopy(r)
        p = make(fine, node, keep, arm, np.asarray(r['phase_reference']), powers, means, hyper, entries)
        r['linear_gates'] = linear_metrics(p, np.asarray(r['endpoint_east_north_km']), entries, powers)
        assert r['linear_calibration_max_difference'] == 0
        arms[arm] = r
    gain = old['policy_arms']['c0']['negative_twice_elbo']-arms['c0']['negative_twice_elbo']
    accept = bool(pair_passes(arms, include_linear=True) and gain > 2*np.log(2))
    legacy_accept = bool(pair_passes(legacy, include_linear=True) and gain > 2*np.log(2))
    write(path, dict(case=case, arms=arms, baseline_arms=old['policy_arms'],
        legacy_unconstrained_arms=legacy, accepted=accept, legacy_unconstrained_accepted=legacy_accept,
        policy_arms=arms if accept else old['policy_arms'],
        legacy_policy_arms=legacy if legacy_accept else old['policy_arms'],
        same_mask_c0_RF_gain=gain, original_mask=keep, GPS_used=False, future_TLE_used=False,
        no_linear_calibration_or_gate_driven_position_update=True, seconds=time.monotonic()-start))
    result = dict(case=case, accepted=accept, legacy_unconstrained_accepted=legacy_accept,
                  points=int(keep.sum()), seconds=time.monotonic()-start)
    print(result, flush=True)
    return result


def initialize():
    OUT.mkdir(parents=True, exist_ok=True)
    destination = OUT/'protocol.json'
    if destination.exists():
        return read(destination)
    previous = read(PREVIOUS/'protocol.json')
    result = dict(cases=previous['cases'], development=previous['development'], additional=previous['additional'],
        post_hoc_development_cohort_not_untouched_validation=True, masks_aliases_labels_weights_and_physical_priors_fixed=True,
        cold_start_km=[0, 0], regional_box_width_km=25, phase_rounds=5, position_iterations=48,
        no_gate_constrained_position_update=True,
        linear_gate='existing noise screen on chronological predictive innovations; Gaussian calibration covariance and bias sigma300 Hz',
        curved_gates_and_physical_linear_bounds_unchanged=True,
        new_observations_never_update_calibration=True, RF_choice='paired gates; c0 same-mask gain > 2 log(2)',
        same_Gamma2_predictive_measurement_noise_as_original_objective=True,
        comparison=['original ALGO02','fine basis without rescue, legacy gates','fine basis without rescue, predictive linear gates'],
        GPS_used=False, source_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'src/leo/analysis/research/predictive_track_gate.py'))
    write(destination, result)
    return result


def main():
    protocol = initialize()
    results = []
    with ProcessPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(run_case, case):case for case in protocol['cases']}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(dict(case=futures[future], error=repr(exc)))
            write(OUT/'progress.json', dict(completed=len(results), total=len(futures), results=results))
    write(OUT/'execution.json', dict(results=results, all_terminal=True))


if __name__ == '__main__':
    main()
