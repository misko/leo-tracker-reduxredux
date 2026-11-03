"""TRAIN-only common RF-coefficient tension; no state fitting or held reads."""
import hashlib
from pathlib import Path
import sys
import time
import numpy as np
from contrast import contrast_basis, mixture_score, profile_frequency_score, normalized, SCORE_SOURCE

HERE = Path(__file__).resolve().parent
ITERATION = HERE.parent
REPORTS = HERE.parents[1]


def support(weights):
    weights = np.asarray(weights, float)
    return dict(sum=float(weights.sum()), kish_rows=float(weights.sum()**2/np.sum(weights**2))
        if np.any(weights) else 0.)


def main():
    started = time.monotonic()
    sys.path.insert(0, str(ITERATION/'blocked_cold'))
    sys.path.insert(0, str(REPORTS/'2026_10_16_dsx01_models'))
    import common
    from training_context import load_training_context
    from leo.analysis.hard60_score import predict_orbits
    from leo.analysis.regional_position_score import PositionObjective
    import inspect
    ctx = load_training_context()
    model, v, n = ctx.model, ctx.vector, ctx.nuisance
    ev, details = model.evaluate_details(v, n)
    obs, raw = model.scored_observations, model.original
    rf_column = raw.design[model.mask, 4]
    np.testing.assert_allclose(rf_column, (obs.rf_hz-ctx.observations.rf_center_hz)/1e9, atol=0., rtol=0.)
    basis = contrast_basis(rf_column, obs.receiver)
    local = mixture_score(ev[3].responsibilities, ev[3].residual_hz, details['sigma_hz'], basis)
    tau = v[7]+model.basis@v[8:]
    _, _, spatial, timing = predict_orbits(ctx.bank, obs, ctx.prior, v[:2], tau)
    clock = np.column_stack([raw.clock_design[model.mask], raw.group_design[model.mask]])
    old = np.empty((*timing.shape, len(v)+clock.shape[1]))
    old[:, :, :2] = spatial
    old[:, :, 2:7] = raw.design[model.mask, None, :]
    old[:, :, 7:len(v)] = timing[:, :, None]*np.column_stack([np.ones(len(ctx.bank.numbers)), model.basis])[None, :, :]
    old[:, :, len(v):] = clock[:, None, :]
    frequency_profiled = profile_frequency_score(ev[3].responsibilities, ev[3].residual_hz,
        details['sigma_hz'], basis, old)
    band_constants = np.column_stack([((obs.receiver == rx) & (obs.channel >= 5)).astype(float) for rx in [0, 1]])
    augmented = np.concatenate([old, np.broadcast_to(band_constants[:, None, :], (*timing.shape, 2))], axis=2)
    fully_profiled = profile_frequency_score(ev[3].responsibilities, ev[3].residual_hz,
        details['sigma_hz'], basis, augmented)
    receiver_rows, lane_rows = [], []
    for rx in [0, 1]:
        use = obs.receiver == rx
        common_gradient = float(rf_column[use]@local['row_gradient'][use])
        receiver_rows.append(dict(receiver=rx, rows=int(use.sum()),
            common_c_data_gradient=common_gradient,
            contrast_c_data_gradient=common_gradient*(1 if rx == 0 else -1),
            common_c_observed_curvature=float(np.sum(local['row_curvature'][use]*rf_column[use]**2)),
            common_c_complete_information=float(np.sum(local['gaussian_information_weight'][use]*rf_column[use]**2)),
            signal_support=support(local['signal_mass'][use]),
            rf_information_support=support(local['gaussian_information_weight'][use]*rf_column[use]**2)))
        for high in [False, True]:
            lane = use & ((obs.channel >= 5) == high)
            rf, weight = rf_column[lane], local['signal_mass'][lane]
            mean = np.sum(rf*weight)/weight.sum() if weight.sum() else None
            variance = np.sum(weight*(rf-mean)**2)/weight.sum() if weight.sum() else None
            lane_rows.append(dict(receiver=rx, high=high, rows=int(lane.sum()),
                distinct_rf_count=len(np.unique(obs.rf_hz[lane])),
                distinct_actual_rf_hz=list(map(float, np.unique(obs.rf_hz[lane]))),
                rf_column_range_ghz=[float(rf.min()), float(rf.max())] if len(rf) else [],
                responsibility_weighted_rf_std_ghz=float(np.sqrt(variance)) if variance is not None else None,
                signal_support=support(weight)))
    np.testing.assert_allclose(sum(r['common_c_data_gradient'] for r in receiver_rows), ev[1][6], atol=1e-10, rtol=0.)
    np.testing.assert_allclose(sum(r['contrast_c_data_gradient'] for r in receiver_rows), local['gradient'][0], atol=1e-10, rtol=0.)
    output = dict(source_id=ctx.source_id, train_rows=len(obs.times_s), selected_ids=len(ctx.bank.numbers),
        shared_c_hz_per_ghz=float(v[6]), original_rf_center_hz=float(ctx.observations.rf_center_hz),
        basis_definition='raw.design[:,4] * (+1 for RX0, -1 for RX1)',
        units='Hz/GHz; c_RX0 = existing_common_c + contrast, c_RX1 = existing_common_c - contrast; receiver coefficient difference = 2*contrast.',
        public_definition=inspect.getsource(PositionObjective.__init__),
        direct=normalized({k:value for k, value in local.items() if k in ['gradient', 'observed_hessian', 'complete_gaussian_information']}),
        all_existing_frequency_profiled=normalized(frequency_profiled),
        all_existing_frequency_and_new_band_constants_profiled=normalized(fully_profiled),
        per_receiver=receiver_rows, within_band_rf_support=lane_rows,
        existing_full_physical_gradient=ev[1], existing_full_nuisance_gradient=ev[2],
        observed_negative_row_curvature_count=int(np.sum(local['row_curvature'] < 0)),
        training_objective=float(ev[0]), training_nll=float(ev[3].nll),
        elapsed_seconds=time.monotonic()-started, explicit_mixture_evaluations=1, additional_frequency_jacobian_projections=1,
        code_sha256={str(path):'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [HERE/'run.py', HERE/'contrast.py', SCORE_SOURCE/'score.py',
                ITERATION/'blocked_cold/training_context.py']},
        input_sha256={name:'sha256:'+hashlib.sha256((ITERATION/'blocked_cold'/name).read_bytes()).hexdigest()
            for name in ['S03-block20-parity0/training-input.json', 'S03-block20-parity0/output/terminal.json']},
        qualification='TRAIN-only local direction diagnostic; no fitted state or held/reference read. Exact NLL score/observed curvature use all candidates; positive Gaussian information freezes responsibilities. Tangent projection omits q/visibility/prior effects and has no significance, covariance, hardware-cause, identity or predictive claim. A future c0 arm must zero both common c and this contrast.')
    common.save_json(HERE/'diagnosis.json', output)
    print(common.jsonable(output) if hasattr(common, 'jsonable') else
        {key:output[key] for key in ['shared_c_hz_per_ghz', 'per_receiver', 'within_band_rf_support', 'elapsed_seconds']})
    print('DIRECT',output['direct']['signed_gradient_over_sqrt_complete_information'])
    print('PROFILED',output['all_existing_frequency_and_new_band_constants_profiled']['signed_gradient_over_sqrt_complete_information'])


if __name__ == '__main__':
    main()
