"""Matched causal deletion diagnostics for a previously unexamined large error."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time
import numpy as np

from algo02_scan import pair_passes
from ablate_ds23_frequency_event_satellites import removal_mask
from diagnose_ds23_position_information import derivative_at, marginal_information
from probe_algo03_frame_peak_recovery import context, SOURCE
from probe_ds23_frequency_events import parameters, refit
from probe_ds23_gate_retention_cohort import make
from run_algo01_ds23_sample import ROOT, read, write, sha

CASE = 'DS23-0041'
OUT = ROOT/'reports/2026_10_20_ds23_0041_influence'
ARMS = ('c0', 'fitted_c')


def initialize():
    OUT.mkdir(parents=True, exist_ok=True)
    destination = OUT/'protocol.json'
    if destination.exists():
        return read(destination)
    scan, node, mask, base, old = context(CASE)
    active = [scan.tracks[i] for i,sl in zip(base.members, base.slices, strict=True) if mask[sl].any()]
    entries = old['linear_entries'] if old['linear_paired_valid'] else []
    jobs = [dict(label='baseline', norads=[], components=[])]
    families = sorted({r['candidate_norad'] for r,sl in zip(base.rows, base.slices, strict=True) if mask[sl].any()}
                      | {e['norad'] for e in entries})
    jobs.extend(dict(label='drop_family_'+str(n), norads=[n], components=[]) for n in families)
    all_tracks = active + [scan.tracks[e['track_index']] for e in entries]
    for rx in (1, 2):
        jobs.append(dict(label='drop_RX'+str(rx), norads=[],
                         components=sorted({t['key'] for t in all_tracks if t['receiver'] == rx})))
    for channel in sorted({t['channel'] for t in all_tracks}):
        jobs.append(dict(label='drop_CH'+str(channel), norads=[],
                         components=sorted({t['key'] for t in all_tracks if t['channel'] == channel})))
    for start in (0, 100, 200):
        jobs.append(dict(label=f'drop_curve_centers_{start}_{start+100}', norads=[],
            components=sorted({t['key'] for t in all_tracks if start <= np.mean(t['times']) < start+100})))
    document = dict(case=CASE, jobs=jobs, cold_start_km=[0, 0], box_width_km=25,
        phase_rounds=5, position_steps=48, workers=20, GPS_used=False, future_TLE_used=False,
        all_original_nuisance_coordinates_support_priors_and_weights_retained=True,
        whole_curves_removed_from_both_calibration_and_prediction=True,
        deletion_is_influence_diagnostic_not_operational_rejection_or_identity_proof=True,
        do_not_rank_raw_objectives_across_different_masks=True,
        baseline_sha256=sha(SOURCE/CASE/'algo02_result.json'), source_sha256=sha(Path(__file__)))
    write(destination, document)
    return document


def information(p, x, powers):
    c = p.calculate(x)
    d = derivative_at(p, np.asarray(x), c['coefficient'], .01)[p.keep]
    g = p.noise_groups[p.keep]
    weights = powers[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
    u, precision = c['features'][p.keep], c['coefficient_prior_precision']
    index = np.arange(u.shape[1])
    phase = p.hardware.shape[1]+p.smooth.shape[1]
    orbit = phase+len(p.labels)
    constant = len(index)-len(p.members)
    groups = dict(all_uncertain=index, phase_known=index[(index < phase)|(index >= orbit)],
        orbits_known=index[(index < phase)|(index >= constant)], receiver_known=index[phase:])
    return {name:marginal_information(d, u[:,use], weights, precision[use]) for name,use in groups.items()}


def job(request):
    destination = OUT/(request['label']+'.json')
    if destination.exists():
        return dict(label=request['label'], cached=True)
    start = time.monotonic()
    scan, node, mask, base, old = context(CASE)
    entries = old['linear_entries'] if old['linear_paired_valid'] else []
    keep, predictive = removal_mask(base.rows, base.slices, mask, entries,
                                    request['norads'], request['components'])
    powers, means, hyper = parameters(scan, base, old)
    arms = {arm:refit(scan, node, keep, arm, powers, means, hyper, [], predictive) for arm in ARMS}
    details = {}
    if request['label'] == 'baseline':
        for arm in ARMS:
            r = arms[arm]
            p = make(scan, node, keep, arm, np.asarray(r['phase_reference']), powers, means, hyper, predictive)
            details[arm] = information(p, r['endpoint_east_north_km'], powers)
    document = dict(case=CASE, request=request, arms=arms, original_mask=mask, mask=keep,
        removed_curved_points=int(mask.sum()-keep.sum()),
        removed_predictive_points=sum(e['points'] for e in entries)-sum(e['points'] for e in predictive),
        paired_valid=pair_passes(arms, include_linear=True), conditional_curved_information=details,
        information_excludes_predictive_points_Gamma_uncertainty_and_identity_uncertainty=True,
        GPS_used=False, future_TLE_used=False, seconds=time.monotonic()-start)
    write(destination, document)
    result = dict(label=request['label'], paired_valid=document['paired_valid'], seconds=document['seconds'])
    print(result, flush=True)
    return result


def main():
    protocol = initialize()
    results = []
    with ProcessPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(job, request):request['label'] for request in protocol['jobs']}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(dict(label=futures[future], error=repr(exc)))
            write(OUT/'progress.json', dict(completed=len(results), total=len(futures), results=results))
    write(OUT/'execution.json', dict(results=results, all_terminal=True))


if __name__ == '__main__':
    main()
