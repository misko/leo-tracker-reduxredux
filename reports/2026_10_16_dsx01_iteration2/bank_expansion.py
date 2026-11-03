"""Declared small expansion of the ORIGINAL causal regional bank, no selection.

The parent profiles all training observations to choose additions. This adapter
never reads challenge membership, candidate hypotheses or measured CFO values.
"""

import hashlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np

MAX_ADDITIONS = 8
ROOT = Path(__file__).resolve().parents[2]


def _same_common(old, full):
    lookup = {int(n): i for i, n in enumerate(full.numbers)}
    if not set(map(int, old.numbers)) <= set(lookup):
        raise ValueError("original candidate missing from regional bank")
    selected = full.select([lookup[int(n)] for n in old.numbers])
    for name in ("numbers", "nodes_s", "position_km", "velocity_km_s"):
        np.testing.assert_array_equal(getattr(selected, name), getattr(old, name))


def regional_bank(context, *, maximum_seconds=90, return_receipt=False):
    """Rebuild exact pinned causal regional eligibility; no latest/provider switch."""
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.contracts.regional_position import PositionOrbitBank
    from leo.storage.shared_fast_scan import SharedFastScanStore

    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets

    source = context.source
    job, _, terminal, _ = SharedFastScanStore('/srv/bulk/leo', 'shared-scan-q-v2').plot_evidence(
        source['job_id'])
    if (job['input_sha256'] != source['tracking_input_sha256']
            or job['terminal']['sha256'] != source['terminal_sha256']):
        raise ValueError("original public source binding changed")
    digest, collection = source['tle_sha256'], source['tle_collected_utc_ns']
    if digest != terminal['provenance']['tle_sha256']:
        raise ValueError("source and original terminal TLE disagree")
    eligible = list(map(int, terminal['provenance']['full_candidate_numbers']))
    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    snapshots = [s for s in archive.list_snapshots()
                 if s.digest == digest and s.collected_utc_ns == collection]
    if len(snapshots) != 1 or collection > source['first_sample_estimate_utc_ns']:
        raise ValueError("unique original causal TLE snapshot required")
    snapshot = snapshots[0]
    catalogue = parse_element_sets(archive.read(snapshot))
    lookup = {int(n): i for i, n in enumerate(catalogue.satellite_numbers)}
    if not set(eligible) <= set(lookup):
        raise ValueError("original regional candidate absent from pinned TLE")
    rebuilt, _ = build_regional_bank(catalogue, [lookup[n] for n in eligible],
        source['first_sample_estimate_utc_ns'], context.observations, context.prior,
        maximum_seconds=maximum_seconds)
    order = {int(n): i for i, n in enumerate(rebuilt.numbers)}
    if set(order) != set(eligible):
        raise ValueError("original causal regional eligibility changed")
    rebuilt = rebuilt.select([order[n] for n in eligible])
    _same_common(context.bank, rebuilt)
    cache = ROOT/source['report_directory']/'orbit-bank.npz'
    cache_receipt = dict(path=str(cache), exists=cache.exists(), verified=False)
    if cache.exists():
        with np.load(cache) as data:
            cached = PositionOrbitBank(data['numbers'], data['nodes'], data['positions'],
                                       data['velocities'])
        _same_common(rebuilt, cached)
        cache_receipt.update(verified=True,
            sha256='sha256:'+hashlib.sha256(cache.read_bytes()).hexdigest())
    receipt = dict(tle_sha256=digest, tle_collected_utc_ns=collection,
        tle_provider=snapshot.provider, original_regional_numbers=eligible,
        original_selected_numbers=list(map(int, context.bank.numbers)),
        cached_bank=cache_receipt, common_orbit_maximum_error=0.,
        qualification="Original causal snapshot; no provider or candidate re-selection")
    return (rebuilt, receipt) if return_receipt else rebuilt


def fixed_shift(model):
    """Recover the existing fixed high-minus-low function, never estimate a new one."""
    from leo.analysis.sequential_group_calibration import SequentialShift

    raw, obs = model.original, model.observations
    receivers = tuple(map(int, np.unique(obs.receiver[obs.channel >= 5])))
    offsets = np.array([raw.baseline[(obs.receiver == r) & (obs.channel >= 5)][0]
                        for r in receivers])
    shift = SequentialShift(receivers, offsets)
    np.testing.assert_allclose(shift.predict(obs.receiver, obs.channel >= 5), raw.baseline,
                               atol=1e-10, rtol=0)
    np.testing.assert_allclose(.5*float(offsets@offsets)/50000.**2,
                               model.fixed_contrast_prior_penalty, atol=1e-12, rtol=0)
    return shift


def project_q(old, new, old_tail, added_count):
    """One bounded logit projection with unchanged total detection budget.

    Positive new q cannot be added while retaining every old q at fixed budget.
    Allocate each addition budget/(K+m), proportionally scale the old q by
    K/(K+m), and disclose the subsequent existing-coordinate bound projection.
    """
    from scipy.optimize import lsq_linear
    from scipy.special import logit

    old_q = old.hyperparameters(old_tail)[2]
    k, total = len(old_q), len(new.bank.numbers)
    if total != k+added_count or new.score.detection_budget != old.score.detection_budget:
        raise ValueError("unchanged q budget and explicit expanded cardinality required")
    target = np.r_[old_q*k/total, np.full(added_count, old.score.detection_budget/total)]
    centered = logit(target)-logit(target).mean()
    basis = new.catalogue_basis
    unconstrained = basis.T@centered
    limits = new.group_limits[new.original.group_count:]
    if np.all(abs(unconstrained) <= limits):
        tail, active, projections = unconstrained, [], 0
    else:
        solved = lsq_linear(basis, centered, bounds=(-limits, limits),
                           tol=1e-12, max_iter=200, lsq_solver='exact')
        if not solved.success:
            raise ValueError("bounded q-logit projection failed")
        tail, active, projections = solved.x, np.flatnonzero(solved.active_mask).tolist(), 1
    projected = new.hyperparameters(tail)[2]
    error = projected-target
    return tail, dict(target_probabilities=target.tolist(), actual_probabilities=projected.tolist(),
        original_probabilities=old_q.tolist(), projection_active_coordinates=active,
        probability_maximum_error=float(abs(error).max(initial=0)),
        probability_rms_error=float(np.sqrt(np.mean(error**2))),
        centered_logit_rms_error=float(np.sqrt(np.mean((basis@tail-centered)**2))),
        old_probability_mass=float(old_q.sum()), expanded_probability_mass=float(projected.sum()),
        numerical_linear_projections=projections,
        target_policy="old q*K/(K+m); each new q=unchanged budget/(K+m)")


def expandable_context(context, numbers, *, regional=None):
    """Return (expanded Context, receipt), without evaluating the likelihood."""
    from leo.analysis.sequential_group_calibration import fixed_shift_objective
    from leo.analysis.shared_scan_model import SharedScanObjective
    from leo.application.channel_group_refinement import objective

    proposed = list(numbers)
    if any(isinstance(n, (bool, np.bool_)) or not isinstance(n, (int, np.integer))
           for n in proposed):
        raise ValueError("integer catalogue numbers required")
    additions = list(map(int, proposed))
    old_numbers = list(map(int, context.bank.numbers))
    if (len(additions) > MAX_ADDITIONS or len(set(additions)) != len(additions)
            or set(additions) & set(old_numbers)):
        raise ValueError("at most eight unique NEW candidates; originals retained automatically")
    if not additions:
        return context, dict(additions=[], original_numbers=old_numbers,
                             expanded_numbers=old_numbers, unchanged=True,
                             numerical_linear_projections=0, objective_calls=0)
    if type(context.model) is not SharedScanObjective:
        raise ValueError("exact original shared objective required")
    if regional is None:
        regional, authority = regional_bank(context, return_receipt=True)
    else:
        authority = dict(qualification="Caller supplied ORIGINAL pinned regional bank")
    _same_common(context.bank, regional)
    lookup = {int(n): i for i, n in enumerate(regional.numbers)}
    if not set(additions) <= set(lookup):
        raise ValueError("addition outside original causal regional eligibility")
    ordered = old_numbers+sorted(additions)
    bank = regional.select([lookup[n] for n in ordered])
    old, v, n = context.model, np.asarray(context.vector), np.asarray(context.nuisance)
    shift = fixed_shift(old)
    joint = objective(SimpleNamespace(observations=context.observations), bank,
                      context.prior, context.nodes)
    raw = fixed_shift_objective(joint.base, shift)
    model = SharedScanObjective(raw, shift, mask=context.train_mask)
    full = SharedScanObjective(raw, shift)
    if model.score != old.score or model.visibility_width != old.visibility_width:
        raise ValueError("physical score or smooth visibility policy changed")
    for name in ('design', 'clock_design', 'baseline'):
        np.testing.assert_array_equal(getattr(raw, name), getattr(old.original, name))
    np.testing.assert_array_equal(model.precision[:model.base_nuisance_count,
        :model.base_nuisance_count], old.precision[:old.base_nuisance_count,
        :old.base_nuisance_count])
    tau = np.r_[v[7]+old.basis@v[8:], np.zeros(len(additions))]
    vector = np.r_[v[:7], tau.mean(), model.basis.T@(tau-tau.mean())]
    tail, q_receipt = project_q(old, model, n[old.base_nuisance_count:], len(additions))
    nuisance = np.r_[n[:old.base_nuisance_count], tail]
    if context.fixed_c and vector[6] != 0:
        raise ValueError("fixed-c context has nonzero original RF coefficient")
    actual_tau = vector[7]+model.basis@vector[8:]
    timing_error = float(np.max(abs(actual_tau-tau)))
    correction_error = float(np.max(abs(raw.correction(vector, nuisance[:model.clock_count])
        -old.original.correction(v, n[:old.clock_count]))))
    if timing_error > 1e-11 or correction_error > 1e-8:
        raise ValueError("complete source timing or calibration transport failed")
    receipt = dict(additions=sorted(additions), original_numbers=old_numbers,
        expanded_numbers=ordered, authority=authority, q_projection=q_receipt,
        original_satellite_timing_maximum_error_s=timing_error,
        added_satellite_timing_seed_s=0., calibration_maximum_error_hz=correction_error,
        fixed_contrast_receivers=list(shift.receivers),
        fixed_contrast_offsets_hz=shift.offsets_hz.tolist(),
        fixed_contrast_prior=model.fixed_contrast_prior_penalty,
        numerical_linear_projections=q_receipt['numerical_linear_projections'], objective_calls=0,
        full_mask=context.train_mask.tolist(), fixed_c=bool(context.fixed_c))
    return replace(context, model=model, full_model=full, vector=vector, nuisance=nuisance,
                   bank=bank), receipt
