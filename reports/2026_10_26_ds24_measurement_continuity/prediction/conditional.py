"""One-owner conditional Gaussian/phase mixture; train-only forecasting."""
import numpy as np
from scipy.special import logsumexp


def split_indices(times, native_ids):
    times, native_ids = np.asarray(times), np.asarray(native_ids).astype(str)
    if len(times) != 29 or len(set(native_ids)) != 29:
        raise ValueError('The complete unique29-ID owner is required')
    order = np.lexsort((native_ids, times))
    return [('early_to_late', order[:14], order[14:]),
            ('late_to_early', order[14:], order[:14])]


def log_gaussian(residual, covariance):
    """residual[node,coordinate,alias], covariance[node,coordinate,coordinate]."""
    root = np.linalg.cholesky(covariance)
    whitened = np.linalg.solve(root, residual)
    return -.5 * (np.sum(whitened ** 2, axis=1)
        + 2 * np.log(np.diagonal(root, axis1=1, axis2=2)).sum(axis=1)[:, None]
        + residual.shape[1] * np.log(2 * np.pi))


def node_forecast(raw_train, covariance, frequency, modes, train, held, aliases, period):
    """No held response argument exists at this forecasting port."""
    train, held = np.asarray(train), np.asarray(held)
    full = covariance[None] + np.einsum('nik,njk->nij', modes, modes)
    tt = full[:, train[:, None], train]
    ht = full[:, held[:, None], train]
    hh = full[:, held[:, None], held]
    residual = raw_train[None, :, None] + aliases[None, None, :] * period - frequency[:, train, None]
    train_loglike = log_gaussian(residual, tt)
    solved = np.linalg.solve(tt, residual)
    mean = (frequency[:, held, None] - aliases[None, None, :] * period
            + ht @ solved).transpose(0, 2, 1)
    conditional = hh - ht @ np.linalg.solve(tt, ht.transpose(0, 2, 1))
    conditional = (conditional + conditional.transpose(0, 2, 1)) / 2
    np.linalg.cholesky(conditional)
    shape_mean = np.einsum('nti,nta->nai', modes[:, train], solved)
    constant_mean = 300. ** 2 * np.sum(solved, axis=1)
    return dict(train_loglike=train_loglike, mean=mean, covariance=conditional,
                shape_mean=shape_mean, constant_mean=constant_mean, joint_covariance=full)


def evaluate(raw, covariance, geometry, train, held, physical_modes, period, chunk_size=256):
    """Same discrete rule for train posterior, held density and direct joint check."""
    raw, covariance = np.asarray(raw), np.asarray(covariance)
    train, held = np.asarray(train), np.asarray(held)
    if set(train) & set(held) or set(np.r_[train, held]) != set(range(len(raw))):
        raise ValueError('Train/held must partition the whole owner')
    aliases = np.arange(-4, 5)
    total = -np.inf
    conditional_total = direct_joint = -np.inf
    mean = np.zeros(len(held)); second = np.zeros((len(held), len(held)))
    phase_mean = phase_second = constant_mean = 0.
    shape_mean = np.zeros(3 if physical_modes else 0)
    alias_mass = np.zeros(9)
    node_logs = []
    for start in range(0, len(geometry['nodes']), chunk_size):
        stop = start + chunk_size
        phases = geometry['nodes'][start:stop]
        frequency = geometry['frequency'][start:stop]
        modes = geometry['modes'][start:stop] if physical_modes else np.zeros((len(phases), len(raw), 0))
        forecast = node_forecast(raw[train], covariance, frequency, modes, train, held, aliases, period)
        logs = geometry['log_prior_weights'][start:stop, None] + forecast['train_loglike']
        chunk = float(logsumexp(logs)); combined = float(np.logaddexp(total, chunk))
        old_factor, new_factor = float(np.exp(total-combined)), float(np.exp(chunk-combined))
        weights = np.exp(logs-chunk)
        chunk_mean = np.einsum('na,nai->i', weights, forecast['mean'])
        chunk_second = (np.einsum('n,nij->ij', weights.sum(axis=1), forecast['covariance'])
                        + np.einsum('na,nai,naj->ij', weights, forecast['mean'], forecast['mean']))
        mean = old_factor * mean + new_factor * chunk_mean
        second = old_factor * second + new_factor * chunk_second
        phase_mean = old_factor * phase_mean + new_factor * float(weights.sum(axis=1) @ phases)
        phase_second = old_factor * phase_second + new_factor * float(weights.sum(axis=1) @ phases ** 2)
        shape_mean = old_factor * shape_mean + new_factor * np.einsum('na,nai->i', weights, forecast['shape_mean'])
        constant_mean = old_factor * constant_mean + new_factor * float(np.sum(weights * forecast['constant_mean']))
        alias_mass = old_factor * alias_mass + new_factor * weights.sum(axis=0)
        # Held data enter ONLY these evaluation densities, after forecasting.
        held_residual = (raw[held][None, None, :] - forecast['mean']).transpose(0, 2, 1)
        held_loglike = log_gaussian(held_residual, forecast['covariance'])
        conditional_total = float(np.logaddexp(conditional_total, logsumexp(logs + held_loglike)))
        all_residual = raw[None, :, None] + aliases[None, None, :] * period - frequency[:, :, None]
        joint_loglike = log_gaussian(all_residual, forecast['joint_covariance'])
        direct_joint = float(np.logaddexp(direct_joint,
            logsumexp(geometry['log_prior_weights'][start:stop, None] + joint_loglike)))
        node_logs.append(logs)
        total = combined
    predictive_covariance = second - np.outer(mean, mean)
    predictive_covariance = (predictive_covariance + predictive_covariance.T) / 2
    if np.min(np.linalg.eigvalsh(predictive_covariance)) <= 0:
        raise ValueError('Integrated predictive covariance nonpositive')
    posterior = np.exp(np.concatenate(node_logs) - total)
    conditional_log_density = conditional_total - total
    direct_conditional = direct_joint - total
    return dict(train_log_evidence=total, joint_log_evidence=direct_joint,
        held_negative_twice_log_density=float(-2*conditional_log_density),
        direct_joint_minus_train_negative_twice_log_density=float(-2*direct_conditional),
        joint_conditional_identity_error=float(abs(conditional_log_density-direct_conditional)),
        phase_mean_s=float(phase_mean), phase_SD_s=float(np.sqrt(max(0., phase_second-phase_mean**2))),
        alias_probabilities=alias_mass, alias_edge_mass=float(alias_mass[0]+alias_mass[-1]),
        shape_mean=shape_mean, source_constant_mean_Hz=float(constant_mean),
        prediction_mean=mean, prediction_covariance=predictive_covariance,
        prediction_SD=np.sqrt(np.diag(predictive_covariance)), posterior_node_alias_mass=posterior,
        held_raw_residual=raw[held]-mean,
        raw_RMS_Hz=float(np.sqrt(np.mean((raw[held]-mean)**2))),
        maximum_absolute_predictive_z=float(np.max(abs(raw[held]-mean)/np.sqrt(np.diag(predictive_covariance)))),
        training_only_forecast=True, one_shared_owner_alias_and_constant=True)
