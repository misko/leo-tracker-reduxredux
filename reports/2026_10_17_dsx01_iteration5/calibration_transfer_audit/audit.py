"""TRAIN-only donor transport and changing-q calibration-gradient audit."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ITERATION = HERE.parent


def band_gradient(terms, receiver, channel, offsets, prior_sigma=50000.):
    row = terms.prediction_gradient.sum(axis=1)
    return np.array([row[(receiver==rx) & (channel>=5)].sum() for rx in (0, 1)])+np.asarray(offsets)/prior_sigma**2


def main():
    sys.path.insert(0, str(ITERATION/'blocked_cold'))
    from training_context import load_training_context
    from leo.cli.shared_fast_position import load_input
    from leo.application.shared_fast_position import prepare_views
    from leo.application.channel_group_refinement import objective
    from leo.analysis.shared_scan_model import SharedScanObjective, donor_state
    from leo.analysis.hard60_score import predict_orbits, likelihood
    from leo.analysis.shared_scan_model import density

    attempt = ITERATION/'blocked_cold/S03-block20-parity0'
    ctx = load_training_context(attempt)
    prepared, nodes = prepare_views(load_input(json.loads((attempt/'training-input.json').read_text())))
    joint = objective(prepared['all'], ctx.bank, ctx.prior, nodes)
    selected = json.loads((attempt/'output/stages/source-selection.json').read_text())
    receipt = json.loads((attempt/f"output/stages/B-{selected['B_index']}.json").read_text())['result']
    assert receipt['audit']['accepted']
    fit = receipt['fit']
    v, n = np.asarray(fit['vector']), np.asarray(fit['nuisance'])
    old = joint.evaluate_joint(v, n)
    raw, shift, rebased, clock, error = donor_state(joint, fit)
    donor = SharedScanObjective(raw, shift)
    zero_q = np.r_[clock, np.zeros(donor.observation_parameter_count)]
    result, details = donor.evaluate_details(rebased, zero_q)
    obs = donor.scored_observations
    new_gradient = band_gradient(result[3], obs.receiver, obs.channel, shift.offsets_hz)
    # Old offsets use centered (high-fraction) columns; new offsets are absolute
    # high columns. Rebased intercepts make the corresponding chain rule explicit.
    old_group = old[2][joint.clock_count:]
    chain = old_group + joint.frame.high_fractions*np.array([old[1][2], old[1][4]])
    tau = rebased[7]+donor.basis@rebased[8:]
    prediction, visible, _, _ = predict_orbits(ctx.bank, obs, ctx.prior, rebased[:2], tau)
    prediction += raw.correction(rebased, clock)[:, None]
    hard = likelihood(obs.measured_hz, prediction, visible, donor.score)
    same, _ = density(obs.measured_hz, prediction, visible.astype(float),
        np.full(len(obs.times_s), 125.), np.full(len(ctx.bank.numbers), donor.score.detection_budget/len(ctx.bank.numbers)), donor.score)
    uniform_error = float(np.max(abs(hard.prediction_gradient-same.prediction_gradient)))
    assert uniform_error < 1e-12
    endpoint, endpoint_details = ctx.model.evaluate_details(ctx.vector, ctx.nuisance)
    uniform_n = ctx.nuisance.copy()
    uniform_n[ctx.model.base_nuisance_count:] = 0.
    endpoint_uniform, _ = ctx.model.evaluate_details(ctx.vector, uniform_n)
    offsets = np.array([ctx.model.original.baseline[(ctx.observations.receiver==rx) & (ctx.observations.channel>=5)][0] for rx in (0, 1)])
    actual_gradient = band_gradient(endpoint[3], ctx.observations.receiver, ctx.observations.channel, offsets)
    uniform_gradient = band_gradient(endpoint_uniform[3], ctx.observations.receiver, ctx.observations.channel, offsets)
    value = dict(training_observations=len(obs.times_s), selected_joint_donor=selected['B_index'],
        original_joint_donor_strict_audit=receipt['audit'], donor_transport_max_error_hz=float(error),
        donor_legacy_centered_band_gradient=old_group.tolist(),
        donor_legacy_chain_rule_absolute_band_gradient=chain.tolist(),
        donor_shared_uniform_q_absolute_band_gradient=new_gradient.tolist(),
        donor_soft_vs_hard_visibility_max_error=float(np.max(abs(details['visibility_weight']-visible))),
        legacy_vs_conditional_uniform_q_frequency_gradient_max_error=uniform_error,
        donor_chain_rule_gradient_max_error=float(np.max(abs(chain-new_gradient))),
        final_source_band_offsets_hz=offsets.tolist(),
        final_shared_learned_q_band_gradient=actual_gradient.tolist(),
        final_shared_uniform_q_band_gradient=uniform_gradient.tolist(),
        final_q_range=[float(endpoint_details['detection_probability'].min()),float(endpoint_details['detection_probability'].max())],
        qualification='TRAIN-only fixed-state diagnostics. Frequency likelihood gradients coincide at uniform q and identical visibility; the conditional normalizer alone is not a band-gradient explanation. Exact donor transport does not preserve band stationarity after q, geometry, timing or clock changes. Final selected A source differs from the B donor audited here; this is not a causal isolation of the complete source-selection path. No fitting, held measurements or station coordinates.',
        source_hashes={str(p):'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [attempt/'training-input.json', attempt/'output/terminal.json', attempt/'output/stages/source-selection.json',
             attempt/f"output/stages/B-{selected['B_index']}.json", Path(__file__)]})
    (HERE/'results.json').write_text(json.dumps(value, indent=2)+'\n')
    print(json.dumps(value, indent=2))


if __name__=='__main__':
    main()
