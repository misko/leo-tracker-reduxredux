"""Diagnostic causal/following orbit profiles; never feeds position inference."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from sgp4.api import Satrec

from analyze_dsx01_fixed_site import ecef_states
from dbg01_unassociated import validate_post_version
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.sky.propagation import ElementSetCatalogue
from probe_ds23_single_curved_reentry import predictive_track_data
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import read, sha, write
import run_ds23_dbg01_iteration_002 as iteration

OUT = iteration.RAW/'curve_diagnostics'


def conditional_noise(raw, covariance, noise):
    r, c, s = np.asarray(raw), np.asarray(covariance), np.asarray(noise)
    precision_residual = np.linalg.solve(c, r)
    return s*s*precision_residual, float(r@precision_residual)


def phase_profile(data, bank, x, aliases):
    covariance = data['base_covariance']
    inverse = np.linalg.inv(covariance)
    raw = data['values']+aliases[0]/4.4e-6-data['radio']@data['coefficient'][:data['radio_width']]
    def evaluate(phase):
        f, e = phase_frequency_grid(bank, data['times'], *latlon(x), phase_seconds=phase)
        residual = raw-data['q']*f[0]
        cost = float(residual@inverse@residual)
        return cost if e[0].min() >= 0 else np.inf, residual, float(e[0].min())
    phases = np.arange(-15., 15.001, .25)
    coarse = [evaluate(t)[0] for t in phases]
    choices = [(cost, phase) for cost, phase in zip(coarse, phases, strict=True) if np.isfinite(cost)]
    for k in range(1, len(phases)-1):
        if np.isfinite(coarse[k]) and coarse[k] <= min(coarse[k-1], coarse[k+1]):
            fit = minimize_scalar(lambda t:evaluate(t)[0], bounds=(phases[k-1], phases[k+1]),
                                  method='bounded', options=dict(xatol=1e-8))
            choices.append((float(fit.fun), float(fit.x)))
    if not choices:
        return dict(visible=False)
    cost, phase = min(choices)
    _, raw_residual, elevation = evaluate(phase)
    residual, direct = conditional_noise(raw_residual, covariance, data['noise'])
    if abs(direct-cost) > 1e-5:
        raise ValueError('independent dense phase-profile cost does not replay')
    return dict(visible=True, phase_s=phase, quadratic=cost,
        minimum_elevation_deg=elevation, residual_hz=residual,
        conditional_RMS_hz=float(np.sqrt(np.mean(residual**2))),
        noise={k:v[0] for k,v in batch_noise_screen(residual[None,:], data['times']).items()},
        independent_cost_difference=abs(direct-cost))


def one(case):
    d = iteration.current_setup(case)
    old = read(iteration.RAW/'single_curve_reentry'/(case+'_nominations.json'))
    future_path = iteration.RAW/(case+'_following_elements.json')
    future = read(future_path)
    end = future['end_utc_ns']
    if any(not validate_post_version(v, end) for v in future['versions'].values()):
        raise ValueError('following element outside fixed postscan window')
    x = np.asarray(d['arms']['c0']['endpoint_east_north_km'])
    p = iteration.baseline.build(d, 'c0', d['arms']['c0']['phase_reference'])
    rows = []
    for target in old['targets']:
        data = predictive_track_data(d, p, x, target['row_index'])
        track = d['scan'].tracks[target['target']['track_index']]
        graph_residual = np.asarray(track['values']).copy()
        for piece in track['pieces']:
            use = (track['times'] >= piece['start_s']-1e-8)&(track['times'] <= piece['end_s']+1e-8)
            graph_residual[use] -= np.polynomial.legendre.legval(
                (track['times'][use]-piece['reference_time_s'])/piece['time_scale_s'], piece['coefficients_hz'])
        candidates = target['candidates'][:3]
        original = target['original']
        if original['norad'] not in {r['norad'] for r in candidates}:
            candidates = candidates+[original]
        results = []
        for candidate in candidates:
            j, n = candidate['candidate_index'], candidate['norad']
            bank = dict(time_s=d['scan'].sky['time_s'], position_km=d['scan'].sky['position_km'][[j]],
                        velocity_km_s=d['scan'].sky['velocity_km_s'][[j]])
            pair = dict(causal=phase_profile(data, bank, x, candidate['aliases']))
            version = future['versions'].get(str(n))
            if version is not None:
                catalogue = ElementSetCatalogue((str(n),), (n,), (Satrec.twoline2rv(*version['lines']),))
                position, velocity, usable = ecef_states(catalogue, d['scan'].receipt['origin_utc_ns'], bank['time_s'])
                if not usable.all():
                    raise ValueError('following propagation failed')
                pair['following'] = phase_profile(data, dict(bank, position_km=position, velocity_km_s=velocity), x, candidate['aliases'])
            results.append(dict(norad=n, aliases=candidate['aliases'], arms=pair,
                real_following_version=version is not None, following_provenance=version))
        rows.append(dict(component=track['key'], receiver=track['receiver'], channel=track['channel'],
            times=track['times'], points=len(track['times']), graph_residual_hz=graph_residual,
            graph_RMS_hz=float(np.sqrt(np.mean(graph_residual**2))), pieces=len(track['pieces']), candidates=results))
    result = dict(case=case, targets=rows, future_TLE_diagnostic_only_not_a_position_result=True,
        frozen_RF_endpoint_and_causal_receiver_calibration=True, full_correlated_radio_and_fragment_uncertainty=True,
        same_original_observations_and_fixed_aliases_in_both_versions=True,
        phase_profile='all local minima on -15..15 seconds, quarter-second seed grid; no phase prior in either diagnostic',
        physical_orbit_shape_modes_in_neither_diagnostic=True,
        no_inference_or_identity_adoption_from_following_comparison=True,
        future_elements_sha256=sha(future_path), source_sha256=sha(Path(__file__)),
        all_costs_independently_dense_replayed=True)
    write(OUT/(case+'.json'), result)
    for row in rows:
        best = row['candidates'][0]
        print(case, row['component'], row['graph_RMS_hz'], best['norad'],
              {a:r.get('conditional_RMS_hz') for a,r in best['arms'].items()}, flush=True)
    return dict(case=case, all_passed=True)


def main():
    iteration.configure()
    OUT.mkdir(exist_ok=True)
    if (OUT/'execution.json').exists():
        raise FileExistsError('preserve diagnostic evidence')
    with ProcessPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(one, read(iteration.RAW/'protocol.json')['cases']))
    write(OUT/'execution.json', dict(rows=rows, all_passed=True, following_TLEs_are_diagnostics_only=True))


if __name__ == '__main__':
    main()
