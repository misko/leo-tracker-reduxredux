"""Conditional mechanism diagnostics of two frozen full-data endpoint pairs.

No position fitting, association selection, GPS, receiver tuning, or heldout claim.
Five zero-initialized phase refresh rounds at each of eleven frozen locations.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import time

import numpy as np

from matched_controls import (ARMS, canonical, digest, factor_contract, load_baseline,
                              measurement_binding, read, write)
from probe_ds23_graph_seeded_paths import build as original_build
from ds23_family_cavity import legacy_phase_reference
from ds23_height_problem import geometry_features
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
import adapter

HERE = Path(__file__).resolve().parent
PRIOR = Path('/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025')
CASES = ('DS24-0017', 'DS24-0095')
MODELS = ('baseline', 'rf50')
ROUND_COUNT = 5
PHASE_TOL = .01


def build(d, arm, reference, model):
    if model == 'baseline':
        return original_build(d, 'default', arm, reference)
    if model == 'rf50':
        return adapter.build_method(d, arm, reference, d['case'], 'fast_rx1_rf50')
    raise ValueError(model)


def blocks(p):
    nb, ns, nl = p.hardware.shape[1], p.smooth.shape[1], len(p.labels)
    width = ns // 2
    old_width = width - 31 if width > 11 else width
    smooth_old = np.r_[np.arange(nb, nb + old_width),
                       np.arange(nb + width, nb + width + old_width)]
    extra1 = np.arange(nb + old_width, nb + width)
    extra2 = np.arange(nb + width + old_width, nb + ns)
    n = nb + ns + nl + 3 * len(p.supported) + len(p.members)
    return dict(offset=np.arange(4), drift=np.arange(4, 8), c=np.arange(8, nb),
                receiver_slow=smooth_old, receiver_extra_rx1=extra1,
                receiver_extra_rx2=extra2, phase=np.arange(nb+ns, nb+ns+nl),
                orbit=np.arange(nb+ns+nl, n-len(p.members)),
                fragment=np.arange(n-len(p.members), n))


def terms(p, x):
    c = p.calculate(x)
    curved = p.curved_calculate(x) if hasattr(p, 'curved_calculate') else c
    latent = curved['latent_coefficient']
    priors = {f'prior_{k}': float(np.sum(latent[ix]**2 * curved['coefficient_prior_precision'][ix]))
              for k, ix in blocks(p).items()}
    g = p.noise_groups[p.keep]
    w = np.asarray(p.analysis_powers)[g] * curved['noise_precision'][g] / p.point_noise[p.keep]**2
    data = float(np.sum(w * curved['conditional_residual_hz'][p.keep]**2))
    np.testing.assert_allclose(data + sum(priors.values()), curved['quadratic'], atol=1e-7, rtol=1e-10)
    # c includes predictive normalization; take the curved normalization afresh.
    result = dict(weighted_data=data, **priors, logvolume=float(curved['logvolume']),
                  noise_Gamma=float(curved['noise_gamma_cost']), prior_Gamma=float(curved['prior_gamma_cost']),
                  normalization=float(curved['normalization_constant']),
                  predictive=float(c['negative_twice_elbo'] - curved['negative_twice_elbo']))
    np.testing.assert_allclose(sum(result.values()), c['negative_twice_elbo'], atol=1e-6, rtol=1e-11)
    return result


def point_summary(p, x, phase_changes):
    c = p.calculate(x)
    curved = p.curved_calculate(x) if hasattr(p, 'curved_calculate') else c
    state = p.state(x)
    return dict(position_east_north_km=x, phase_reference=p.reference,
                phase_refresh_changes_s=phase_changes,
                final_phase_change_s=phase_changes[-1], phase_converged=phase_changes[-1] < PHASE_TOL,
                precision_iterations=curved['precision_iterations'],
                final_log_precision_change=curved['final_log_precision_change'],
                Gamma_converged=curved['final_log_precision_change'] < 1e-5,
                negative_twice_elbo=float(c['negative_twice_elbo']),
                curved_negative_twice_elbo=float(curved['negative_twice_elbo']),
                terms=terms(p, x), state=state,
                RMS_hz=float(np.sqrt(np.mean(curved['conditional_residual_hz'][p.keep]**2))),
                phases_s=state['phases'][p.labels], labels=p.labels,
                norads=[int(p.scan.norads[j]) for j in p.labels],
                phase_prior_sigma_s=p.phase_sigma,
                phase_prior_precision=curved['coefficient_prior_precision'][blocks(p)['phase']],
                physical_orbit_coefficients=curved['coefficient'][blocks(p)['orbit']],
                active_points=int(p.keep.sum()), predictive_points=sum(e['points'] for e in getattr(p, 'linear_entries', [])),
                predictive_calibration_max_difference=float(np.max(abs(c['coefficient']-curved['coefficient']))))


def fixed(d, arm, model, x):
    reference = np.zeros(len(d['means']))
    changes = []
    for _ in range(ROUND_COUNT):
        p = build(d, arm, reference, model)
        p.analysis_powers = d['powers']
        phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
        changes.append(float(np.max(abs(phase-reference))))
        reference = phase
    return p, point_summary(p, x, changes)


def saved_replay(d, arm, model, record):
    """Reconstruct final-fit phase reference for legacy posterior-reference saves."""
    recorded = np.asarray(record['phase_reference'])
    if 'curved_negative_twice_elbo' not in record and model == 'baseline':
        def posterior(ref, x):
            previous = build(d, arm, ref, model)
            return previous.state(x)['phases'][previous.labels]
        reference = legacy_phase_reference(record['history'], np.zeros(len(d['means'])),
                                           posterior)
        kind = 'history_reconstructed_final_fit_reference'
    else:
        reference = recorded
        kind = 'explicit_final_fit_reference'
    p = build(d, arm, reference, model)
    p.analysis_powers = d['powers']
    x = np.asarray(record['endpoint_east_north_km'])
    difference = float(p.calculate(x)['negative_twice_elbo']-record['negative_twice_elbo'])
    np.testing.assert_allclose(difference, 0, atol=1e-5)
    return dict(reference_kind=kind, objective_replay_difference=difference,
                recorded_to_used_reference_max_difference_s=float(np.max(abs(recorded-reference))),
                used_phase_reference=reference,
                factor_contract=factor_contract(p, d['entries']))


def data_groups(p, x, group_kind):
    c = p.curved_calculate(x) if hasattr(p, 'curved_calculate') else p.calculate(x)
    weights = np.asarray(p.analysis_powers)[p.noise_groups] * c['noise_precision'][p.noise_groups] / p.point_noise**2
    energy = weights * c['conditional_residual_hz']**2
    result = {}
    for row, i, sl in zip(p.rows, p.members, p.slices, strict=True):
        t = p.scan.tracks[i]
        active = p.keep[sl]
        if not active.any():
            continue
        if group_kind == 'family':
            keys = np.full(len(t['times']), str(row['candidate_norad']), object)
        elif group_kind == 'receiver_band_time':
            band = 'CH1-4' if t['channel'] <= 4 else 'CH5-8'
            keys = np.array([f"RX{t['receiver']}:{band}:{int(tau//30)*30:03d}-{int(tau//30)*30+30:03d}s"
                             for tau in t['times']], object)
        elif group_kind == 'component':
            keys = np.full(len(t['times']), t['key'], object)
        else:
            raise ValueError(group_kind)
        for key in np.unique(keys[active]):
            use = active & (keys == key)
            rowout = result.setdefault(key, dict(weighted_data=0., points=0))
            rowout['weighted_data'] += float(energy[sl][use].sum())
            rowout['points'] += int(use.sum())
    np.testing.assert_allclose(sum(r['weighted_data'] for r in result.values()), terms(p, x)['weighted_data'], atol=1e-7)
    return result


def local_derivatives(p, x, displacement, h=.01):
    """Nuisance/Gamma refit each call; phase linearization fixed at center.

    Data-term derivatives are a decomposition, not independent family evidence.
    Shared covariance/logvolume is retained as a global term.
    """
    direction = displacement / np.linalg.norm(displacement)
    gradient = []
    for k in range(2):
        delta = np.eye(2)[k]*h
        gradient.append(float((p.calculate(x+delta)['negative_twice_elbo']-
                               p.calculate(x-delta)['negative_twice_elbo'])/(2*h)))
    plus, minus = x+h*direction, x-h*direction
    tp, tm = terms(p, plus), terms(p, minus)
    term_derivatives = {key:(tp[key]-tm[key])/(2*h) for key in tp}
    grouped = {}
    for kind in ('family', 'receiver_band_time', 'component'):
        gp, gm = data_groups(p, plus, kind), data_groups(p, minus, kind)
        grouped[kind] = {key:dict(derivative_per_km=(gp[key]['weighted_data']-gm[key]['weighted_data'])/(2*h),
                                 points=gp[key]['points']) for key in gp}
        np.testing.assert_allclose(sum(r['derivative_per_km'] for r in grouped[kind].values()),
                                   term_derivatives['weighted_data'], atol=1e-6)
    return dict(gradient_east_north_per_km=gradient,
                directional_derivative_per_km=float(np.dot(gradient, direction)),
                term_directional_derivatives_per_km=term_derivatives,
                grouped_weighted_data_derivatives=grouped, difference_step_km=h,
                phase_linearization_fixed_nuisance_and_Gamma_refit=True)


def schur_information(jacobian, features, weights, precision):
    gram = np.diag(precision) + features.T @ (features*weights[:, None])
    cross = features.T @ (jacobian*weights[:, None])
    info = jacobian.T @ (jacobian*weights[:, None]) - cross.T @ np.linalg.solve(gram, cross)
    return (info+info.T)/2, gram, cross


def geometry(p, x, displacement):
    """Local mean-only Gaussian information, conditional on Gamma precisions."""
    c = p.curved_calculate(x) if hasattr(p, 'curved_calculate') else p.calculate(x)
    coefficient = c['coefficient']
    columns = []
    for k in range(2):
        delta = np.eye(2)[k]*.01
        means = []
        for pos in (x+delta, x-delta):
            g = geometry_features(p, pos, 0.)
            means.append(p.q*g['intercept']+g['features']@coefficient)
        columns.append((means[0]-means[1])/.02)
    jacobian = np.column_stack(columns)[p.keep]
    features = c['features'][p.keep]
    g = p.noise_groups[p.keep]
    weights = np.asarray(p.analysis_powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
    precision = c['coefficient_prior_precision']
    info, gram, cross = schur_information(jacobian, features, weights, precision)
    val, vec = np.linalg.eigh(info)
    direction = displacement/np.linalg.norm(displacement)
    weak_cosine = float(np.clip(abs(vec[:, 0]@direction), 0, 1))
    out = dict(position_information_per_km2=info, eigenvalues=val,
               weak_direction_east_north=vec[:, 0],
               weak_axis_angle_to_displacement_deg=float(np.degrees(np.arccos(weak_cosine))),
               weak_axis_sigma_km=float(1/np.sqrt(val[0])),
               displacement_direction_information=float(direction@info@direction),
               conditional_on_Gamma_precisions_and_labels=True,
               mean_only_information_excludes_volume_curvature_and_predictive_terms=True)
    block = blocks(p)
    extras = np.r_[block['receiver_extra_rx1'], block['receiver_extra_rx2']]
    baseline = np.setdiff1d(np.arange(features.shape[1]), extras)
    without, _, _ = schur_information(jacobian, features[:, baseline], weights, precision[baseline])
    denominator = float(direction@without@direction)
    fraction = float(np.clip(1-(direction@info@direction)/denominator, 0, 1))
    out.update(information_without_appended_modes_same_J_Gamma_and_other_priors=without,
               appended_modes_displacement_information_fraction_removed=fraction,
               regularized_projected_RX1_angle_proxy_deg=
                   float(np.degrees(np.arccos(np.sqrt(fraction)))) if len(extras) else None)
    invgram = np.linalg.inv(gram)
    covx = np.linalg.inv(info)
    covxn = -covx @ cross.T @ invgram
    covn = invgram + invgram@cross@covx@cross.T@invgram
    var_dir = float(direction@covx@direction)
    phase_corr = direction@covxn[:, block['phase']] / np.sqrt(var_dir*np.diag(covn)[block['phase']])
    out['displacement_coordinate_phase_correlations'] = phase_corr
    out['maximum_absolute_phase_correlation'] = float(np.max(abs(phase_corr)))
    return out


def receiver_curves(p, x):
    state = p.state(x)
    grid = np.linspace(0, 300, 601)
    old = projected_receiver_basis(grid)
    width = p.smooth.shape[1]//2
    if width not in (11, 42):
        raise ValueError('unexpected original receiver width')
    curves = []
    for rx in (1, 2):
        for band in (0, 1):
            tracks = [t for t in p.scan.tracks if t['receiver'] == rx and int(t['channel']>4) == band]
            if not tracks:
                continue
            rf = float(np.median([t['rf_hz'] for t in tracks]))
            t = dict(receiver=rx, channel=1+4*band, rf_hz=rf, times=grid)
            slow = old@state['smooth'][rx-1, :11] * rf/11.5e9
            extra = np.zeros(len(grid))
            if width == 42:
                extra = projected_receiver_basis(grid, spacing_s=10., width_s=5.)@state['smooth'][rx-1, 11:]*.25*rf/11.5e9
                if rx == 2:
                    extra *= 0
            hardware = p.scan.hardware(t, state['beta'])
            curves.append(dict(receiver=rx, band=band, rf_hz=rf, time_s=grid,
                               hardware_hz=hardware, slow_hz=slow, extra_hz=extra,
                               total_hz=hardware+slow+extra))
    # Confirm plotting basis equals actual per-track loading at all native times.
    errors = []
    for t, basis in zip(p.scan.tracks, p.scan.rx_basis, strict=True):
        candidate = projected_receiver_basis(t['times'])
        if width == 42:
            extra = projected_receiver_basis(t['times'], spacing_s=10., width_s=5.)*.25
            if t['receiver'] == 2:
                extra *= 0
            candidate = np.column_stack((candidate, extra))
        errors.append(float(np.max(abs(candidate-basis))))
    np.testing.assert_allclose(max(errors), 0, atol=1e-12)
    return dict(curves=curves, maximum_basis_reconstruction_error=max(errors))


def one(case):
    began = time.monotonic()
    source_hash = digest(Path(__file__))
    source_paths = [Path(__file__), Path(adapter.__file__),
        PRIOR/'evaluation/matched_controls.py',
        Path('tools/probe_ds23_graph_seeded_paths.py'), Path('tools/dsx01_joint_marginal.py'),
        Path('tools/dsx01_hierarchical_bound.py'), Path('tools/probe_ds23_history_calibrated_phase.py'),
        Path('tools/ds23_frequency_events.py'), Path('tools/ds23_height_problem.py'),
        Path('tools/ds23_predictive_linear.py'), Path('tools/ds23_family_cavity.py'),
        Path('src/leo/analysis/research/retained_track_likelihood.py')]
    source_seals = [dict(path=str(p.resolve()), sha256=digest(p)) for p in source_paths]
    d = load_baseline(case)
    binding = measurement_binding(d)
    source = PRIOR/'evaluation/models/receiver_fast_rx1_rf50'/(case+'.json')
    saved = read(source)
    assert saved['adopted'] and saved['input_binding_sha256'] == binding
    result = dict(case=case, GPS_used=False, full_data_conditional_diagnostic=True,
                  baseline_path=d['baseline_path'], baseline_sha256=d['baseline_sha256'],
                  rf50_path=str(source), rf50_sha256=digest(source), measurement_binding=binding,
                  phase_refresh_rounds=ROUND_COUNT, position_fitting=False, arms={},
                  source_seals=source_seals, source_sha256=source_hash,
                  warning='All endpoints and memberships were RF-selected on full data; these diagnostics are conditional, not heldout.',
                  interpolation_alphas=np.linspace(0, 1, 11),
                  maximum_workers=1, BLAS_threads=1)
    for arm in ARMS:
        xa = np.asarray(d['arms'][arm]['endpoint_east_north_km'])
        xb = np.asarray(saved['arms'][arm]['endpoint_east_north_km'])
        displacement = xb-xa
        ar = dict(baseline_endpoint=xa, rf50_endpoint=xb, displacement_east_north_km=displacement,
                  displacement_km=float(np.linalg.norm(displacement)), models={})
        contracts = []
        for model in MODELS:
            record = d['arms'][arm] if model == 'baseline' else saved['arms'][arm]
            replay = saved_replay(d, arm, model, record)
            contracts.append(replay['factor_contract'])
            paths, endpoints = [], {}
            for alpha in np.linspace(0, 1, 11):
                x = xa+alpha*displacement
                p, summary = fixed(d, arm, model, x)
                summary['alpha'] = float(alpha)
                paths.append(summary)
                if alpha in (0., 1.):
                    key = 'baseline_endpoint' if alpha == 0 else 'rf50_endpoint'
                    endpoints[key] = dict(summary=summary,
                        derivatives=local_derivatives(p, x, displacement),
                        geometry=geometry(p, x, displacement),
                        receiver_curves=receiver_curves(p, x),
                        family_data=data_groups(p, x, 'family'),
                        receiver_band_time_data=data_groups(p, x, 'receiver_band_time'),
                        component_data=data_groups(p, x, 'component'))
                print(case, arm, model, f'{alpha:.1f}', round(summary['negative_twice_elbo'], 5),
                      'phase', f"{summary['final_phase_change_s']:.2g}", flush=True)
            ar['models'][model] = dict(saved_endpoint_replay=replay, path=paths, endpoints=endpoints)
        assert contracts[0] == contracts[1]
        result['arms'][arm] = ar
    assert measurement_binding(d) == binding
    result['seconds'] = time.monotonic()-began
    result['inputs_preserved'] = True
    assert source_hash == digest(Path(__file__))
    for item in source_seals:
        assert digest(item['path']) == item['sha256']
    write(HERE/(case+'.json'), result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=CASES, required=True)
    args = parser.parse_args()
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        if os.environ.get(name) != '1':
            raise ValueError('explicit BLAS1 required')
    one(args.case)


if __name__ == '__main__':
    main()
