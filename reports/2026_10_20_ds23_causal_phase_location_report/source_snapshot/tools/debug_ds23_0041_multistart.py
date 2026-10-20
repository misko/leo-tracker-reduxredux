"""Independent regional starts at fixed identities, with causal RF-only choice."""

import copy
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np

from algo02_scan import pair_passes
from debug_ds23_0041_influence import OUT, CASE, ARMS
from ds23_frequency_events import make_event_problem, attach_event_predictive
from investigate_dsx01_localization_failures import fit
from investigate_ds23_0268_remaining_tracks import fine_receiver_basis
from probe_algo03_frame_peak_recovery import context
from probe_ds23_frequency_events import parameters, cached, summary
from run_algo01_ds23_sample import read, write, sha


def fit_from(scan, node, keep, arm, powers, means, hyper, entries, start):
    x = np.asarray(start, float)
    reference = np.zeros(len(means))
    history = []
    for _ in range(5):
        p = make_event_problem(scan, node, keep, arm, reference, powers, means, hyper, [])
        attach_event_predictive(p, entries, powers)
        cached(p)
        r = fit(p, x, iterations=48)
        x = np.asarray(r['parameters'])
        phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
        history.append(dict(fit=r, phase_change_s=float(np.max(abs(phase-reference)))))
        reference = phase
    result = summary(p, x, entries)
    result.update(history=history, final_phase_change_s=history[-1]['phase_change_s'])
    return result


def initialize():
    destination = OUT/'multistart_protocol.json'
    if destination.exists():
        return read(destination)
    starts = [[0., 0.]] + [[float(10*np.cos(a)), float(10*np.sin(a))] for a in np.arange(8)*np.pi/4]
    reentry = read(OUT/'reentry_protocol.json')
    family = reentry['jobs'][0]['norads']
    jobs = [dict(mode=mode, start=start, index=i) for mode in ('original', 'fine_reentry') for i,start in enumerate(starts)]
    jobs.append(dict(mode='no_predictive', start=[0.,0.], index=0))
    document = dict(case=CASE, jobs=jobs, reentry_families=family,
        starts_are_regional_center_and_10km_circle=True,
        no_reference_location_or_satellite_whitelist_used=True, phase_initialization='zero independently for each run',
        matched_c_searches=True, original_25km_box=True, original_noise_physical_priors_and_aliases_unchanged=True,
        selection='minimum c0 RF objective among paired gate-valid fits, separately within each fixed observation mask',
        no_raw_objective_ranking_across_modes=True, no_predictive_control_is_diagnostic_only=True,
        source_sha256=sha(Path(__file__)))
    write(destination, document)
    return document


def job(request, families):
    destination = OUT/f"multistart_{request['mode']}_{request['index']:02d}.json"
    if destination.exists():
        return dict(request=request, cached=True)
    scan, node, keep, base, old = context(CASE)
    powers, means, hyper = parameters(scan, base, old)
    entries = old['linear_entries'] if old['linear_paired_valid'] else []
    if request['mode'] == 'fine_reentry':
        for row,sl in zip(base.rows, base.slices, strict=True):
            if row['candidate_norad'] in families:
                keep[sl] = True
        scan = copy.copy(scan)
        scan.rx_basis = [fine_receiver_basis(t['times']) for t in scan.tracks]
        node = copy.deepcopy(node)
        node['seed']['state']['smooth'] = np.zeros((2, scan.rx_basis[0].shape[1]))
    if request['mode'] == 'no_predictive':
        entries = []
    arms = {arm:fit_from(scan, node, keep, arm, powers, means, hyper, entries, request['start']) for arm in ARMS}
    result = dict(case=CASE, request=request, arms=arms, mask=keep, paired_valid=pair_passes(arms, include_linear=True),
                  GPS_used=False, future_TLE_used=False)
    write(destination, result)
    receipt = dict(request=request, paired_valid=result['paired_valid'],
                   objective=arms['c0']['negative_twice_elbo'])
    print(receipt, flush=True)
    return receipt


def main():
    protocol = initialize()
    results = []
    with ProcessPoolExecutor(max_workers=19) as executor:
        futures = {executor.submit(job, r, protocol['reentry_families']):r for r in protocol['jobs']}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(dict(request=futures[future], error=repr(exc)))
            write(OUT/'multistart_progress.json', dict(completed=len(results), total=len(futures), results=results))
    write(OUT/'multistart_execution.json', dict(results=results, all_terminal=True))


if __name__ == '__main__':
    main()
