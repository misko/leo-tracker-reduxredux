"""No-fit construction ports for original154 control/native selected B7 states."""
import copy
import numpy as np


def selected_projection(operation):
    """Explicit154→137 numerical projection; no reporting/reference fields."""
    fields = ('vector', 'clock_coefficients', 'objective', 'converged', 'joint_state')
    state_fields = ('stage', 'vector', 'clock_coefficients', 'receiver_baseline_hz',
                    'clock_nodes_s', 'satellite_centers_s', 'total_objective')
    fit = {key: copy.deepcopy(operation['fit'][key]) for key in fields}
    fit['joint_state'] = {key: copy.deepcopy(fit['joint_state'][key]) for key in state_fields}
    return dict(selection={key: copy.deepcopy(operation[key])
                           for key in ('accepted_stage', 'satellites')}, fit=fit)


def b7_seed(receipt):
    """Mirror frozen B7 seed choice; inherited regional seed_audit is not it."""
    attempts = receipt['attempts']
    for name in ('B3', 'B4'):
        fit = attempts[name]['fitted-c']
        if fit is None or not fit['converged']:
            raise ValueError('selected B7 lacks qualified fitted stage chain')
    chosen, source = attempts['B4']['fitted-c'], 'B4'
    for name in ('B4W', 'B5'):
        fit = attempts[name]['fitted-c']
        if fit is not None and fit['converged']:
            chosen, source = fit, name
    vector = np.array(chosen['vector'], dtype=float, copy=True)
    if vector.ndim != 1 or not np.isfinite(vector).all():
        raise ValueError('invalid B7 seed authority')
    return vector, source


def reconstruct(case, receipt, arm, *, construct, components, problem_type):
    """No objective calls; recording/source identities must be verified upstream."""
    if arm not in ('fitted-c', 'zero-c'):
        raise ValueError('unknown final c arm')
    if receipt['status'] != 'complete' or receipt['branch'] != 'native':
        raise ValueError('original complete control/native receipt required')
    operation = receipt['operational'][arm]
    if operation['arm'] != arm:
        raise ValueError('selected arm differs')
    projected = selected_projection(operation)
    if projected['selection']['accepted_stage'] != 'B7':
        raise ValueError('unsupported selected stage; do not substitute endpoint')
    attempted = receipt['attempts']['B7'][arm]
    if attempted is None or not attempted['converged']:
        raise ValueError('missing qualified selected B7 attempt')
    for key in ('vector', 'clock_coefficients', 'objective'):
        np.testing.assert_array_equal(projected['fit'][key], attempted[key])
    model, vector, clock = construct(case, projected, components)
    vector, clock = np.array(vector, copy=True), np.array(clock, copy=True)
    seed, source = b7_seed(receipt)
    if seed.shape != vector.shape:
        raise ValueError('B7 seed/endpoint dimensions differ')
    problem = problem_type(model, vector.copy(), rf_arm=arm, fixed_position=False,
                           local_center=seed[:2].copy(), local_radius_km=25,
                           slope_half_width_hz_s=60)
    helper_delta = np.asarray(problem.start) - vector
    if not problem.feasible(vector):
        raise ValueError('original endpoint violates physical constraints')
    anchor_vector, anchor_clock = vector.copy(), clock.copy()
    smooth = model.smooth_clock_count

    def feasible(candidate_vector, candidate_clock):
        v, c = np.asarray(candidate_vector), np.asarray(candidate_clock)
        if (v.shape != anchor_vector.shape or c.shape != anchor_clock.shape
                or not np.isfinite(v).all() or not np.isfinite(c).all()
                or not np.array_equal(v, anchor_vector)
                or not np.array_equal(c[smooth:], anchor_clock[smooth:])):
            return False
        if not problem.feasible(v) or np.any(abs(c) > 2000) or np.any(abs(c[-2:]) > 1000):
            return False
        if arm == 'zero-c' and (v[6] != 0 or np.any(c[-2:] != 0)):
            return False
        if getattr(model, 'fixed_rf_drift', False) and np.any(c[-2:] != 0):
            return False
        return True

    if not feasible(vector, clock):
        raise ValueError('original clock bounds or c locks invalid')

    def anchor_audit(v, c, physical_gradient, clock_gradient, actual_arm):
        if actual_arm != arm or not feasible(v, c) or not np.array_equal(c, anchor_clock):
            raise ValueError('anchor audit state changed')
        pg, cg = np.asarray(physical_gradient), np.asarray(clock_gradient)
        if (pg.shape != vector.shape or cg.shape != clock.shape
                or not np.isfinite(pg).all() or not np.isfinite(cg).all()):
            raise ValueError('invalid anchor gradients')
        lower, upper = np.full(len(clock), -2000.), np.full(len(clock), 2000.)
        locked = arm == 'zero-c' or getattr(model, 'fixed_rf_drift', False)
        lower[-2:], upper[-2:] = (0., 0.) if locked else (-1000., 1000.)
        scaled = 50 * cg.copy()
        scaled[(c <= lower + 1e-7) & (scaled >= 0)] = 0
        scaled[(c >= upper - 1e-7) & (scaled <= 0)] = 0
        physical = float(problem.stationarity(v, pg))
        clock_kkt = float(np.max(abs(scaled), initial=0))
        kkt = max(physical, clock_kkt)
        return dict(feasible=True, qualified=kkt <= .001, stationarity=kkt,
                    physical_stationarity=physical, clock_stationarity=clock_kkt,
                    rf_arm=arm)
    saved = float(projected['fit']['objective'])
    joint_saved = float(projected['fit']['joint_state']['total_objective'])
    if not np.isfinite(saved) or not np.isfinite(joint_saved) or abs(saved-joint_saved) > 1e-6:
        raise ValueError('saved objective authorities disagree')
    return dict(model=model, vector=vector, clock=clock, arm=arm,
                saved_objective=saved, saved_joint_objective=joint_saved,
                feasible=feasible, anchor_audit=anchor_audit, physical_problem=problem,
                local_center=seed[:2].copy(), seed_stage=source,
                helper_projection_delta=helper_delta,
                bank_numbers=np.asarray(model.bank.numbers).copy())
