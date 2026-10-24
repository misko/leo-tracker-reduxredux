"""Frozen-identity DS24 local information diagnostics; never infer from GPS.

Replays persisted all-channel cavity endpoints, then conditions on their Gamma
precisions. Band/RX controls slice the SAME observations and geometry. The
curved-plus-predictive surrogate is a joint Gaussian marginal at fixed priors,
including independent 300 Hz predictive fragment biases. Its mean derivative
holds the curved coefficient fixed before nuisance elimination. It is a local
diagnostic, not a replacement inference algorithm or calibrated confidence.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import os
from pathlib import Path
import time

import numpy as np

import algo02_scan as algo
from ds23_height_problem import geometry_features
from ds23_position_information import marginal_position_information
from ds23_predictive_linear import linear_geometry
from probe_ds23_graph_seeded_paths import build
from run_algo01_ds23_sample import read

HERE = Path(__file__).resolve().parent
ALL = Path('/srv/bulk/leo/research/ds25-20261024')
HALF = Path('/srv/bulk/leo/research/ds24-channel-halves-20261024')


def encode(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def write(path, value):
    path.write_text(json.dumps(value, default=encode, indent=2) + '\n')


def replay(case):
    """Rebuild persisted inference inputs, avoiding context's signed refits."""
    saved = read(ALL/'family_cavity/position'/(case+'.json'))
    assert saved['status'] == 'complete'
    algo.bind_run_directory(ALL)
    selected = saved['selected'] if saved['accepted'] else None
    d = dict(scan=algo.load_scan(ALL, case),
        node=selected['node'] if selected else saved['baseline_node'],
        keep=np.array(saved['original_mask'], bool), powers=np.array(saved['powers']),
        model=saved['model'],
        means=np.array(selected['means'] if selected else saved['baseline_means']),
        entries=selected['entries'] if selected else saved['baseline_entries'],
        arms=saved['policy_arms'])
    return d, saved


def information(j, u, w, precision):
    """Stable ridge projection, including squared prior residuals.

    Avoid subtracting nearly equal raw and eliminated Fisher matrices.
    Equivalent to augmented QR in ds23_position_information.
    """
    a, b = u*np.sqrt(w[:, None]), j*np.sqrt(w[:, None])
    gram = np.diag(precision) + a.T@a
    root = np.linalg.cholesky(gram)
    response = np.linalg.solve(root.T, np.linalg.solve(root, a.T@b))
    residual = b-a@response
    info = residual.T@residual + response.T@(precision[:, None]*response)
    return (info+info.T)/2


def describe(info):
    values, axes = np.linalg.eigh(info)
    assert values[0] > 0, values
    covariance = np.linalg.inv(info)
    return dict(information_hz_weighted_per_km2=info, covariance_km2=covariance,
        principal_sigma_km=1/np.sqrt(values), rms_radius_km=np.sqrt(np.trace(covariance)),
        weak_axis_east_north=axes[:, 0], eigenvalues_per_km2=values,
        anisotropy_sigma=np.sqrt(values[1]/values[0]))


def row_metadata(p):
    rx = np.concatenate([np.full(len(p.scan.tracks[i]['times']), p.scan.tracks[i]['receiver']) for i in p.members])
    ch = np.concatenate([np.full(len(p.scan.tracks[i]['times']), p.scan.tracks[i]['channel']) for i in p.members])
    family = np.asarray(p.labels)[p.flat_labels]
    return rx, ch, family


def column_groups(p, predictive_count):
    nb, ns = p.hardware.shape[1], p.smooth.shape[1]
    phase = nb+ns
    orbit = phase+len(p.labels)
    fragment = orbit+3*len(p.supported)
    end = fragment+len(p.members)
    groups = dict(receiver_offsets=np.arange(4), receiver_drifts=np.arange(4, 8),
        rf_c=np.arange(8, nb), receiver_smooth=np.arange(nb, phase),
        phase=np.arange(phase, orbit), orbit=np.arange(orbit, fragment),
        curved_fragment_bias=np.arange(fragment, end),
        predictive_fragment_bias=np.arange(end, end+predictive_count))
    groups['receiver_all'] = np.r_[groups['receiver_offsets'], groups['receiver_drifts'], groups['rf_c'], groups['receiver_smooth']]
    groups['phase_and_orbit'] = np.r_[groups['phase'], groups['orbit']]
    groups['all_fragment_bias'] = np.r_[groups['curved_fragment_bias'], groups['predictive_fragment_bias']]
    return groups


def column_names(p, entries):
    names = [f'RX{rx}_band{band}_offset' for rx in (1, 2) for band in ('low', 'high')]
    names += [f'RX{rx}_{kind}' for rx in (1, 2) for kind in ('mean_drift', 'band_drift_contrast')]
    if p.fitted_c:
        names += ['RF_c']
    for rx in (1, 2):
        names += [f'RX{rx}_smooth_{i}' for i in range(p.smooth.shape[1]//2)]
    names += [f'phase_NORAD{int(p.scan.norads[j])}' for j in p.labels]
    names += [f'orbit_NORAD{int(p.scan.norads[j])}_{mode}' for j in p.supported for mode in ('mean_motion', 'inclination', 'RAAN')]
    names += [f'curved_bias_{p.scan.tracks[i]["key"]}' for i in p.members]
    names += [f'predictive_bias_{e["component"]}' for e in entries]
    return names


def correlations(j, u, w, prior, groups, names):
    a, b = u*np.sqrt(w[:, None]), j*np.sqrt(w[:, None])
    gram = np.diag(prior) + a.T@a
    root = np.linalg.cholesky(gram)
    inverse = np.linalg.solve(root.T, np.linalg.solve(root, np.eye(len(gram))))
    response = inverse@(a.T@b)
    cx = np.linalg.inv(information(j, u, w, prior))
    cross = -cx@response.T
    cn = inverse+response@cx@response.T
    corr = cross/np.sqrt(np.diag(cx)[:, None]*np.diag(cn)[None, :])
    vals, axes = np.linalg.eigh(cx)
    weak = axes[:, -1]
    weak_corr = (weak@cross)/np.sqrt(vals[-1]*np.diag(cn))
    ranking = np.argsort(abs(weak_corr))[::-1][:12]
    top = [dict(coordinate=names[k], weak_axis_correlation=weak_corr[k], east_north_correlation=corr[:, k],
        coefficient_shift_per_weak_axis_km=-response[k]@weak) for k in ranking]
    result = {}
    for name, idx in groups.items():
        if not len(idx):
            continue
        result[name] = dict(maximum_absolute_weak_axis_correlation=np.max(abs(weak_corr[idx])),
            maximum_absolute_east_north_correlation=np.max(abs(corr[:, idx])),
            maximum_weak_correlate=names[idx[np.argmax(abs(weak_corr[idx]))]],
            coefficient_shift_l2_per_weak_axis_km=np.linalg.norm(response[idx]@weak))
    return dict(groups=result, top_weak_axis_correlates=top,
        weak_axis_east_north=weak, position_covariance_km2=cx)


def subsets(rx, ch):
    return dict(all=np.ones(len(rx), bool), low=ch<=4, high=ch>4,
        rx1=rx==1, rx2=rx==2,
        rx1_low=(rx==1)&(ch<=4), rx1_high=(rx==1)&(ch>4),
        rx2_low=(rx==2)&(ch<=4), rx2_high=(rx==2)&(ch>4))


def summarize_design(j, u, w, prior, rx, ch, family, groups, names, *, audit=False):
    raw = j.T@(w[:, None]*j)
    full = information(j, u, w, prior)
    data = dict(all=describe(full), all_nuisance_known=describe(raw),
        fraction_trace_information_retained=np.trace(full)/np.trace(raw), subsets={}, freeze_controls={})
    data['fixed_nuisance_prior_noise_controls'] = {
        'sigma_half_weights_times4': describe(information(j, u, w*4, prior)),
        'sigma_tenth_weights_times100': describe(information(j, u, w*100, prior))}
    for name, mask in subsets(rx, ch).items():
        if not mask.any():
            continue
        info = information(j[mask], u[mask], w[mask], prior)
        record = describe(info)
        record.update(points=int(mask.sum()), families=len(set(family[mask])),
            fraction_trace_retained=np.trace(info)/np.trace(j[mask].T@(w[mask, None]*j[mask])))
        data['subsets'][name] = record
        assert np.linalg.eigvalsh(full-info)[0] > -1e-6
    for name, columns in groups.items():
        if not len(columns):
            continue
        use = np.ones(len(prior), bool)
        use[columns] = False
        data['freeze_controls'][name] = describe(information(j, u[:, use], w, prior[use]))
    data['correlations'] = correlations(j, u, w, prior, groups, names)
    data['families_low_high_shared'] = len(set(family[ch<=4]) & set(family[ch>4]))
    data['families_rx1_rx2_shared'] = len(set(family[rx==1]) & set(family[rx==2]))
    if audit:
        qr = marginal_position_information(j, u, w, prior)
        data['stable_projection_QR_relative_difference'] = np.linalg.norm(qr-full)/np.linalg.norm(full)
        assert data['stable_projection_QR_relative_difference'] < 1e-8
    return data


def hessian(function, x, step):
    eye = np.eye(2)*step
    center = function(x)
    matrix = np.empty((2, 2))
    for k in range(2):
        matrix[k, k] = (function(x+eye[k])-2*center+function(x-eye[k]))/step**2/2
    matrix[0, 1] = matrix[1, 0] = (function(x+eye[0]+eye[1])-function(x+eye[0]-eye[1])
        -function(x-eye[0]+eye[1])+function(x-eye[0]-eye[1]))/(4*step**2)/2
    return dict(negative_twice_elbo_Hessian_divided_by_two=matrix,
        eigenvalues=np.linalg.eigvalsh(matrix))


def one(case):
    start = time.monotonic()
    d, source = replay(case)
    records = {}
    for arm, saved in d['arms'].items():
        p = build(d, 'default', arm, saved['phase_reference'])
        assert p.events == []
        x = np.asarray(saved['endpoint_east_north_km'])
        c = p.calculate(x)
        delta = float(c['negative_twice_elbo']-saved['negative_twice_elbo'])
        assert abs(delta) < 1e-3 and abs(delta)/max(abs(saved['negative_twice_elbo']), 1) < 1e-8, (case, arm, delta)
        coefficient = c['coefficient'].copy()
        geometry = geometry_features(p, x, 0.)
        assert np.max(abs(geometry['features']-c['features'])) < 1e-9
        prior = c['coefficient_prior_precision']
        g = p.noise_groups[p.keep]
        weight = d['powers'][g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        rx, ch, family = row_metadata(p)
        u = c['features'][p.keep]
        def derivative(view, step):
            def prediction(position):
                h = geometry_features(view, position, 0.)
                return view.q*h['intercept']+h['features']@coefficient
            return np.column_stack([(prediction(x+dv)-prediction(x-dv))/(2*step) for dv in np.eye(2)*step])
        j_full = derivative(p, .02)
        j = j_full[p.keep]
        check = derivative(p, .04)[p.keep]
        relative = np.linalg.norm(check-j)/np.linalg.norm(j)
        assert relative < 1e-5, relative
        groups = column_groups(p, 0)
        names = column_names(p, [])
        curved = summarize_design(j, u, weight, prior, rx[p.keep], ch[p.keep], family[p.keep], groups, names, audit=True)
        combined = None
        if d['entries']:
            view, values, sigma, biasgroups, slices = linear_geometry(p, d['entries'])
            pg = geometry_features(view, x, 0.)
            pred_j = derivative(view, .02)
            n_bias = int(biasgroups.max())+1
            biases = np.eye(n_bias)[biasgroups]*300.
            full_u = np.vstack((np.column_stack((u, np.zeros((len(u), n_bias)))), np.column_stack((pg['features'], biases))))
            full_j = np.vstack((j, pred_j))
            full_w = np.r_[weight, 1/(2*sigma**2)]
            full_prior = np.r_[prior, np.ones(n_bias)]
            pred_rx = np.concatenate([np.full(len(p.scan.tracks[e['track_index']]['times']), p.scan.tracks[e['track_index']]['receiver']) for e in d['entries']])
            pred_ch = np.concatenate([np.full(len(p.scan.tracks[e['track_index']]['times']), p.scan.tracks[e['track_index']]['channel']) for e in d['entries']])
            pred_family = np.asarray(p.labels)[view.flat_labels]
            combined = summarize_design(full_j, full_u, full_w, full_prior,
                np.r_[rx[p.keep], pred_rx], np.r_[ch[p.keep], pred_ch], np.r_[family[p.keep], pred_family],
                column_groups(p, n_bias), column_names(p, d['entries']), audit=True)
        objective = lambda position: float(p.calculate(position)['negative_twice_elbo'])
        h1, h2 = hessian(objective, x, .1), hessian(objective, x, .2)
        mat1 = np.asarray(h1['negative_twice_elbo_Hessian_divided_by_two'])
        mat2 = np.asarray(h2['negative_twice_elbo_Hessian_divided_by_two'])
        records[arm] = dict(endpoint_east_north_km=x, endpoint_latlon=saved['endpoint_latlon'],
            persisted_negative_twice_elbo=saved['negative_twice_elbo'], RMS_hz=saved['RMS_hz'],
            replay_objective_difference=delta, finite_difference_relative_change=relative,
            curved=curved, curved_plus_predictive_fixed_Gamma_surrogate=combined,
            actual_objective_half_Hessian_step_0p1=h1, actual_objective_half_Hessian_step_0p2=h2,
            actual_objective_Hessian_relative_change=np.linalg.norm(mat1-mat2)/np.linalg.norm(mat2),
            physical_orbit_metadata=p.mode_metadata,
            predictive_points=sum(e['points'] for e in d['entries']),
            curved_points=int(p.keep.sum()), active_curved_families=len(set(family[p.keep])),
            fitted_c_beta_hz_per_GHz=float(saved['state']['beta'][-1]) if arm=='fitted_c' else 0.)
    record = dict(case=case, cavity_accepted=source['accepted'], arms=records,
        shared_c_arms_masks_identities_priors_and_predictive_entries=True,
        elapsed_seconds=time.monotonic()-start, GPS_used=False, no_post_scan_TLE=True)
    write(HERE/(case+'.json'), record)
    print(case, 'seconds', round(record['elapsed_seconds'], 2), flush=True)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    assert 1 <= args.workers <= 4
    cases = read(HALF/'summary.json')['baseline']['fitted_c']['common_cases']
    write(HERE/'protocol.json', dict(cases=cases, all_channel_root=str(ALL),
        channel_half_root=str(HALF), primary='same all-channel endpoint, masks, identities, Gamma precisions and nuisance priors',
        arms=['c0', 'fitted_c'], finite_difference_steps_km=[.02, .04],
        actual_objective_Hessian_steps_km=[.1, .2], workers=args.workers,
        no_GPS_in_inference_or_information=True, no_post_scan_TLE=True,
        all_freezing_controls_are_unavailable_information_oracles=True,
        predictive_surrogate='joint Gaussian marginal with fixed curved Gamma/prior precisions, original conditional linear noise sqrt(2), and 300 Hz independent fragment biases',
        no_claim_of_calibrated_uncertainty=True,
        BLAS_threads={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')}))
    if args.case:
        one(args.case)
    else:
        pending = [case for case in cases if args.refresh or not (HERE/(case+'.json')).exists()]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(one, pending))
        rows = [read(HERE/(case+'.json')) for case in cases]
        write(HERE/'all_cases.json', dict(rows=rows, GPS_used=False))


if __name__ == '__main__':
    main()
