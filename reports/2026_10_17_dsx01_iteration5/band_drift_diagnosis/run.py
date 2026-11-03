"""One bounded TRAIN-only affine band-direction diagnostic, no optimization."""
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
from score import NAMES, SCALES, design, mixture_score, profile_frequency_score

HERE = Path(__file__).resolve().parent
ITERATION = HERE.parent
REPORTS = HERE.parents[1]


def scaled_summary(result):
    gradient = np.asarray(result['gradient'])
    info = np.asarray(result['complete_gaussian_information'])
    standardized = np.divide(gradient, np.sqrt(np.maximum(np.diag(info), 0.)),
        out=np.zeros_like(gradient), where=np.diag(info) > 0)
    return dict(result, scaled_gradient=gradient*SCALES,
        scaled_complete_gaussian_information=info*SCALES[:, None]*SCALES[None, :],
        signed_gradient_over_sqrt_complete_information=standardized,
        squared_complete_information_score=float(gradient@np.linalg.pinv(info, rcond=1e-10)@gradient),
        qualification=result.get('qualification', '')+' Score normalization is descriptive, not a p-value or model-selection threshold.')


def drift_after_constants(result):
    """Schur-project the two new constants from the positive local information."""
    gradient = np.asarray(result['gradient'])
    information = np.asarray(result['complete_gaussian_information'])
    constants, drifts = [0, 2], [1, 3]
    cross = information[np.ix_(drifts, constants)]
    inverse = np.linalg.pinv(information[np.ix_(constants, constants)], rcond=1e-10)
    efficient = gradient[drifts]-cross@inverse@gradient[constants]
    remaining = information[np.ix_(drifts, drifts)]-cross@inverse@cross.T
    standardized = np.divide(efficient, np.sqrt(np.maximum(np.diag(remaining), 0.)),
        out=np.zeros(2), where=np.diag(remaining) > 0)
    return dict(gradient=efficient, complete_gaussian_information=remaining,
        signed_gradient_over_sqrt_complete_information=standardized,
        squared_complete_information_score=float(efficient@np.linalg.pinv(remaining, rcond=1e-10)@efficient),
        qualification='Positive Gaussian tangent approximation additionally profiles both new high-band constants; not a fitted drift, p-value or full efficient-score statistic.')


def main():
    started = time.monotonic()
    sys.path.insert(0, str(ITERATION/'blocked_cold'))
    sys.path.insert(0, str(REPORTS/'2026_10_16_dsx01_models'))
    import common
    from training_context import load_training_context
    from leo.analysis.hard60_score import predict_orbits
    ctx = load_training_context()
    v, n, model = ctx.vector, ctx.nuisance, ctx.model
    ev, details = model.evaluate_details(v, n)
    obs = model.scored_observations
    basis, midpoint = design(obs.times_s, obs.receiver, obs.channel)
    local = mixture_score(ev[3].responsibilities, ev[3].residual_hz, details['sigma_hz'], basis)
    tau = v[7]+model.basis@v[8:]
    _, _, spatial, timing = predict_orbits(ctx.bank, obs, ctx.prior, v[:2], tau)
    raw = model.original
    clock = np.column_stack([raw.clock_design[model.mask], raw.group_design[model.mask]])
    old = np.empty((*timing.shape, len(v)+clock.shape[1]))
    old[:, :, :2] = spatial
    old[:, :, 2:7] = raw.design[model.mask, None, :]
    shift_basis = np.column_stack([np.ones(len(ctx.bank.numbers)), model.basis])
    old[:, :, 7:len(v)] = timing[:, :, None]*shift_basis[None, :, :]
    old[:, :, len(v):] = clock[:, None, :]
    profiled = profile_frequency_score(ev[3].responsibilities, ev[3].residual_hz,
        details['sigma_hz'], basis, old)
    # A smaller row-space comparison profiles only existing shared calibration
    # and residual clocks; full candidate projection above also includes orbit
    # timing and physical point directions.
    calibration = np.broadcast_to(np.column_stack([raw.design[model.mask], clock])[:, None, :],
        (*timing.shape, 5+clock.shape[1]))
    calibration_profiled = profile_frequency_score(ev[3].responsibilities, ev[3].residual_hz,
        details['sigma_hz'], basis, calibration)
    rows = []
    for j, name in enumerate(NAMES):
        use = basis[:, j//2*2] != 0
        mass = local['signal_mass'][use]
        rows.append(dict(name=name, scale=float(SCALES[j]), raw_rows=int(use.sum()),
            responsibility_signal_rows=float(mass.sum()),
            kish_signal_rows=float(mass.sum()**2/np.sum(mass**2)) if np.any(mass) else 0.,
            exact_gradient=float(local['gradient'][j]),
            exact_observed_curvature=float(local['observed_hessian'][j, j]),
            positive_complete_gaussian_information=float(local['complete_gaussian_information'][j, j]),
            row_negative_curvature_count=int(np.sum(local['row_curvature'][use] < 0))))
    direct = {key:value for key, value in local.items() if not key.startswith('row_')
        and key not in ['signal_mass', 'gaussian_information_weight']}
    result = dict(source_id='S03', split='block20-parity0', train_rows=len(obs.times_s),
        selected_ids=len(ctx.bank.numbers), training_midpoint_s=midpoint,
        basis_names=NAMES, scales=SCALES, training_objective=float(ev[0]), training_nll=float(ev[3].nll),
        training_full_physical_gradient=ev[1], training_full_nuisance_gradient=ev[2],
        existing_receiver_intercept_and_shared_drift_gradient=ev[1][2:6],
        rows=rows, direct=scaled_summary(direct),
        calibration_profiled=scaled_summary(calibration_profiled),
        all_frequency_profiled=scaled_summary(profiled),
        drift_after_existing_calibration_and_new_constants=drift_after_constants(calibration_profiled),
        drift_after_all_frequency_and_new_constants=drift_after_constants(profiled),
        observed_hessian_eigenvalues=np.linalg.eigvalsh(local['observed_hessian']*SCALES[:, None]*SCALES[None, :]),
        physical_frequency_projection_calls=1, mixture_objective_evaluations=1,
        elapsed_seconds=time.monotonic()-started,
        input_sha256={name:'sha256:'+hashlib.sha256((ITERATION/'blocked_cold'/name).read_bytes()).hexdigest()
            for name in ['training_context.py', 'S03-block20-parity0/training-input.json',
                'S03-block20-parity0/output/terminal.json']},
        code_sha256={name:'sha256:'+hashlib.sha256((HERE/name).read_bytes()).hexdigest()
            for name in ['score.py', 'run.py']},
        qualification='TRAIN rows only; held measurements and saved held evaluations never opened. No state fit or direction selection. Exact zero-direction NLL gradient/observed curvature; positive Gaussian information freezes responsibilities and is not observed Fisher, variance or identity confidence. Four general receiver-band directions only; no target-window/ID/position exceptions.')
    common.save_json(HERE/'diagnosis.json', result)
    print(json.dumps(dict(rows=rows, direct=result['direct']['signed_gradient_over_sqrt_complete_information'].tolist(),
        calibration_profiled=result['calibration_profiled']['signed_gradient_over_sqrt_complete_information'].tolist(),
        all_frequency_profiled=result['all_frequency_profiled']['signed_gradient_over_sqrt_complete_information'].tolist(),
        observed_eigenvalues=result['observed_hessian_eigenvalues'].tolist(), elapsed_seconds=result['elapsed_seconds']), indent=2))


if __name__ == '__main__':
    main()
