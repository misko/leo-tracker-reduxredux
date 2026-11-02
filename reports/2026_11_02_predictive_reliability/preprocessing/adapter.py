"""RF-clean preprocessing conditional on an already discovered graph.

This module does no RF fitting or family selection. It preserves a caller's
problem factory, including a fixed family SD intervention. The frozen numerical
engine learns coefficient and Gamma noise posteriors from ``train_mask`` only.
"""
import copy
import hashlib
import json

import numpy as np

BASE_SIGMA_HZ = 150.0
MODE = 'fixed150_unit'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def native_ids(scan, problem):
    ids = [oid for i in problem.members for oid in scan.tracks[i]['observation_ids']]
    if len(ids) != len(problem.keep) or len(ids) != len(set(ids)):
        raise ValueError('Unique native IDs matching the full curved design required')
    return ids


def context_inventory(d):
    """Audit inherited preprocessing without evaluating any RF objective."""
    p = d['problems']['fitted_c'][0]
    ids = native_ids(d['scan'], p)
    noise = np.asarray(p.point_noise, float)
    powers = np.asarray(d['powers'], float)
    def quantiles(values):
        return np.quantile(values, [0, .25, .5, .75, 1]).tolist()
    return dict(
        full_curved_ids_sha256=digest(ids), original_eligible_points=int(np.sum(d['keep'])),
        curved_design_points=len(ids), native_aliases=list(map(int, p.alias)),
        inherited_noise_sigma_hz_quantiles=quantiles(noise),
        inherited_noise_metadata_sha256=getattr(p, 'noise_sha256', None),
        inherited_powers=powers.tolist(), inherited_power_quantiles=quantiles(powers),
        causal_phase_prior_means_s=np.asarray(d['means'], float).tolist(),
        causal_phase_model={key: d['model'].get(key) for key in ('multiplier', 'nu', 'shrinkage')},
        phase_prior_sigmas_s=np.asarray(p.phase_sigma, float).tolist(),
        supported_norads=[int(d['scan'].norads[j]) for j in p.supported],
        ancillary_entries=len(d.get('entries', [])), ancillary_families=len(d.get('families', [])),
        measured_frequencies_read=False, objective_evaluated=False, GPS_read=False)


def initial_conditions(d):
    """Common regional-center position and declared zero phase reference.

    The caller must establish causal provenance of d['means']; the adapter does
    not infer provenance from a floating-point vector. This is an absolute phase
    reference, not a posterior phase or a centered latent coefficient.
    """
    means = np.asarray(d['means'], float)
    if means.ndim != 1 or not len(means) or not np.isfinite(means).all():
        raise ValueError('Finite causal prior mean vector required')
    return dict(start=np.zeros(2), reference=np.zeros_like(means))


def prepare_context(d, z, train_mask, *, mode=MODE):
    """Return (context, selection_record, receipt) for a fixed training split.

    No inherited empirical scales, family confidence powers or ancillary
    likelihoods enter the returned context. Fixed identities, graph pieces,
    aliases, mask eligibility and orbital support remain conditional inputs.
    Pass **initial_conditions(dd) explicitly to solver.fit: its default starts
    intentionally remain the published full-data endpoint in the frozen solver.
    """
    if mode != MODE:
        raise ValueError('Only the declared fixed150/unit-power preprocessing is supported')
    base = d['problems']['fitted_c'][0]
    ids = native_ids(d['scan'], base)
    train = np.asarray(train_mask)
    original_keep = np.asarray(d['keep'], bool)
    if (train.dtype != np.dtype(bool) or train.shape != original_keep.shape
            or train.shape != (len(ids),) or not train.any()
            or np.any(train & ~original_keep)):
        raise ValueError('Nonempty boolean training subset of fixed eligible native IDs required')
    train = train.copy()
    initial_conditions(d)  # Validate the causal prior independently of starts.
    means = np.asarray(d['means'], float).copy()
    if len(means) != len(base.labels):
        raise ValueError('Causal phase mean order must match the frozen label order')
    scan = copy.copy(d['scan'])
    scan.radio_sigma_hz = BASE_SIGMA_HZ
    # WindowNoise reads this at construction. Replace it before invoking even a
    # custom factory, then override p.point_noise before the first calculation.
    scan.fixed_window_noise = dict(
        constant_radio_sigma_hz=BASE_SIGMA_HZ, extra_parameter_BIC_gain=0.0,
        per_observation_noise_sigma_hz={oid: BASE_SIGMA_HZ for t in scan.tracks
                                       for oid in t['observation_ids']},
        rule='Existing fixed150 engineering scale; no RF-estimated base noise')
    scan.fixed_window_noise_sha256 = digest(scan.fixed_window_noise)
    original_factory = d.get('problem_factory')
    if original_factory is None:
        from probe_ds23_history_calibrated_phase import make_problem
        original_factory = make_problem
    powers = np.ones(len(base.members))
    aliases = list(base.alias)

    def factory(scan_arg, node, keep, arm, reference, weights, prior_means, multiplier, nu):
        if (not np.array_equal(keep, train) or not np.array_equal(weights, powers)
                or not np.array_equal(prior_means, means)):
            raise ValueError('Frozen preprocessing inputs changed before construction')
        p = original_factory(scan_arg, node, keep, arm, reference, weights,
                             prior_means, multiplier, nu)
        if native_ids(scan_arg, p) != ids or list(p.alias) != aliases:
            raise ValueError('Factory changed fixed native identity order or aliases')
        p.point_noise = np.full(len(ids), BASE_SIGMA_HZ)
        p.diagonal_logvolume = float(2 * len(ids) * np.log(BASE_SIGMA_HZ / 40))
        if hasattr(p, 'noise_volume'):
            p.noise_volume = float(2 * train.sum() * np.log(BASE_SIGMA_HZ / 40))
        p.noise_metadata = copy.deepcopy(scan.fixed_window_noise)
        p.noise_sha256 = scan.fixed_window_noise_sha256
        p.preprocessing_mode = MODE
        return p

    dd = dict(d, scan=scan, keep=train, powers=powers, entries=[], families=[],
              problem_factory=factory)
    zz = dict(z)
    for key in ('selected', 'gap_selected'):
        zz.pop(key, None)
    receipt = dict(
        mode=MODE, base_sigma_hz=BASE_SIGMA_HZ, likelihood_powers='all one',
        train_ids_sha256=digest([oid for oid, active in zip(ids, train, strict=True) if active]),
        eligible_ids_sha256=digest([oid for oid, active in zip(ids, original_keep, strict=True) if active]),
        full_curved_ids_sha256=digest(ids), aliases_sha256=digest(aliases),
        phase_prior_means_sha256=digest(means.tolist()),
        labels=list(map(int, base.labels)), training_points=int(train.sum()),
        excluded_ancillary_entries=len(d.get('entries', [])),
        excluded_ancillary_families=len(d.get('families', [])),
        starts='regional center; zero initial absolute phase reference; causal means remain priors',
        noise_prior='Gamma(shape=2, rate=2); training-only posterior per present fragment',
        wholly_absent_noise_groups='prior only; zero engine placeholders are not precisions',
        conditional_inputs=['graph pieces and peak selection', 'native mask eligibility',
                            'satellite identities and family nomination', 'integer aliases',
                            'nominal physical-mode support'],
        blind_cross_validation=False)
    dd['preprocessing_receipt'] = receipt
    return dd, zz, receipt
