"""Matched regional position test of a strictly causal neighbor phase prior."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np

from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_neighbor_phase_forecast import attach_orbits, features, orbit_coordinates, KINDS
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import summary, cached
from probe_ds23_neighbor_phase_prior import OUT as PRIORS, CASES, inputs
from probe_ds23_sign_carrier_position import context_signed
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_neighbor_phase_position'


def prepare(case):
    data = context_signed(case); scan, node, mask, powers, means, hyper, entries, *_ = data
    prior = read(PRIORS/(case+'.json'))
    hp, fp, history, forecast, _, full, location = inputs(case)
    if sha(hp) != prior['history_sha256'] or sha(fp) != prior['forecast_sha256']:
        raise ValueError('causal neighbor prior history changed')
    p = make_event_problem(scan, node, mask, 'c0', np.zeros(len(means)), powers, means, hyper, [])
    sigma, receipts = phase_widths(scan, p.labels)
    queries = [dict(norad=int(scan.norads[j]), validation_time_ns=scan.receipt['origin_utc_ns']+150_000_000_000,
                    target_orbit=orbit_coordinates(scan.elements[str(int(scan.norads[j]))]['lines'])) for j in p.labels]
    design, counts = features(attach_orbits(forecast['transitions'], history['past_versions']), full,
                             location if location['qualified'] else {}, queries)
    selection = prior['selection']; correction = np.zeros(len(means))
    if selection['qualified']:
        model = selection['full']
        correction = model['coefficient']*sigma*full['multiplier']*design[:, KINDS.index(model['kind'])]
    modified = np.clip(means+correction, -np.minimum(15., 3*sigma), np.minimum(15., 3*sigma))
    return data, prior, modified, design, counts


def refit(data, means, arm):
    scan, node, mask, powers, _, hyper, entries, *_ = data
    x, reference, history = np.zeros(2), np.zeros(len(means)), []
    for _ in range(5):
        p = make_event_problem(scan, node, mask, arm, reference, powers, means, hyper, [])
        attach_event_predictive(p, entries, powers); cached(p)
        result = fit(p, x, iterations=48); x = np.asarray(result['parameters'])
        phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
        change = float(np.max(abs(phase-reference)))
        history.append(dict(fit=result, phase_change_s=change)); reference = phase
    return dict(summary(p, x, entries), history=history, final_phase_change_s=change)


def run(case):
    path = OUT/(case+'.json')
    if path.exists():
        return read(path)
    data, prior, modified, design, counts = prepare(case); signed = data[-2]
    if prior['selection']['qualified']:
        pair = {a: refit(data, modified, a) for a in ARMS}; accepted = valid(pair)
    else:
        pair, accepted = signed['policy_arms'], False
    result = dict(case=case, prior_qualified=prior['selection']['qualified'], arms=pair, paired_valid=accepted,
        policy_arms=pair if accepted else signed['policy_arms'], incumbent_arms=signed['policy_arms'],
        modified_means_s=modified, original_means_s=data[4], neighbor_features=design, effective_neighbor_counts=counts,
        prior_sha256=sha(PRIORS/(case+'.json')), original_observations_aliases_gates_and_variances_preserved=True,
        regional_start=[0, 0], matched_c0_fitted_c=True, no_GPS_inference=True)
    write(path, result); print(case, 'neighbor position gates', accepted, flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True)
    protocol = dict(cases=CASES, workers=6, phase_rounds=5, position_iterations=48,
        regional_center=[37.906, -122.545], regional_width_km=25, cold_start=[0, 0],
        only_change='add qualified causal neighbor phase forecast to existing phase means; same variances',
        prior_protocol_sha256=sha(PRIORS/'protocol.json'),
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_neighbor_phase_forecast.py',
                                              ROOT/'tools/probe_ds23_neighbor_phase_prior.py']})
    path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('causal neighbor position comparison changed')
    if not path.exists():
        write(path, protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows = [f.result() for f in as_completed([pool.submit(run, c) for c in CASES])]
    write(OUT/'execution.json', dict(rows=rows, all_terminal=True))


if __name__ == '__main__':
    main()
