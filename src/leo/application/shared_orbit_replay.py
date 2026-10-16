"""Replay an accepted shared fit into renderer lanes; never refit or acquire RF."""

import numpy as np

from leo.analysis.hard60_score import predict_orbits
from leo.analysis.sequential_group_calibration import SequentialShift, fixed_shift_objective
from leo.analysis.shared_scan_model import SharedScanObjective, audit_endpoint, donor_state
from leo.application.channel_group_refinement import objective
from leo.contracts.regional_position import PositionObservations
from leo.presentation.orbit_plot import OrbitCurve, OrbitLane, OrbitPeak


def selected_model(prepared, bank, prior, nodes, terminal, stages):
    joint = objective(prepared['all'], bank, prior, nodes)
    selected = terminal['selection']
    source = selected['source']
    selection = stages['source-selection']
    if source == 'B-all':
        donor = stages[f"B-{selection['B_index']}"]['result']
        if not donor['audit']['accepted']:
            raise ValueError('Rejected B donor')
        raw, shift, _, _, _ = donor_state(joint, donor['fit'])
    elif source == selection['A']:
        high = stages[f'{source}-high']['result']
        if not high['audit']['accepted']:
            raise ValueError('Rejected A high stage')
        shift = SequentialShift(tuple(high['fit']['group_receivers']),
                                high['fit']['group_offsets_hz'])
        raw = fixed_shift_objective(joint.base, shift)
    else:
        raise ValueError('Unknown selected shared source')
    model = SharedScanObjective(raw, shift)
    endpoint = stages[selected['call']]['result']
    fit = terminal['selected_fit']
    if endpoint['fit'] != fit or not endpoint['audit']['accepted']:
        raise ValueError('Selected endpoint differs from immutable stage')
    audit = audit_endpoint(model, fit, endpoint['options'])
    if (not audit['accepted'] or abs(audit['objective'] - selected['objective']) > 1e-7
            or abs(audit['likelihood_nll'] - selected['NLL']) > 1e-7):
        raise ValueError('Shared selected likelihood/strict audit replay differs')
    return model, fit, audit


def orbit_lanes(model, fit, curve_bank):
    """Display classification uses maximum satellite posterior > clutter posterior."""
    obs = model.observations
    vector, nuisance = (np.asarray(fit[k], float) for k in ('vector', 'nuisance'))
    evaluation, details = model.evaluate_details(vector, nuisance)
    terms = evaluation[3]
    clock = nuisance[:model.clock_count]
    correction = model.original.correction(vector, clock)
    best = terms.responsibilities.argmax(axis=1)
    associated = terms.responsibilities[np.arange(len(best)), best] > terms.clutter_probability
    shifts = vector[7] + model.basis @ vector[8:]
    if not np.array_equal(model.bank.numbers, curve_bank.numbers):
        raise ValueError('Plot curve bank ordering differs')
    times = np.linspace(0, 300, 1201)
    lanes = []
    for channel in range(1, 9):
        rf = np.unique(obs.rf_hz[obs.channel == channel])
        if len(rf) != 1:
            raise ValueError(f'CH{channel} requires exactly one recorded RF')
        for receiver in (0, 1):
            mask = (obs.channel == channel) & (obs.receiver == receiver)
            dense = PositionObservations(
                tuple(f'dense-{i}' for i in range(len(times))), times, np.zeros(len(times)),
                np.full(len(times), rf[0]), np.full(len(times), receiver),
                np.full(len(times), channel), np.ones(len(times)))
            curves, visible, _, _ = predict_orbits(
                curve_bank, dense, model.prior, vector[:2], shifts, derivatives=False)
            lanes.append(OrbitLane(
                f'RX{receiver + 1}', f'CH{channel}',
                tuple(OrbitPeak(obs.window_ids[i], float(obs.times_s[i]),
                                float(obs.measured_hz[i] - correction[i]),
                                str(model.bank.numbers[best[i]]) if associated[i] else None)
                      for i in np.flatnonzero(mask)),
                tuple(OrbitCurve(str(number), tuple(times),
                                 tuple(np.where(visible[:, j], curves[:, j], np.nan)))
                      for j, number in enumerate(curve_bank.numbers))))
    return tuple(lanes), dict(
        observations=len(best), associated=int(associated.sum()),
        unassociated=int((~associated).sum()), replayed_likelihood_nll=terms.nll,
        detection_probabilities=details['detection_probability'].tolist(),
        association='shared-model maximum satellite posterior exceeds clutter posterior',
        frequency_frame='receiver calibration and frozen band offsets removed; alias wrapped',
        curve_visibility='hard horizon for display; association uses fitted smooth visibility')
