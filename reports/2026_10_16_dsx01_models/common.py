"""Pinned replay, bounded shared fitting, and common DSX01 measurements.

Research orchestration only. No production writes and no RF acquisition.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
DATASET = HERE.parent / '2026_10_16_dsx01_fast_association_losses'


@dataclass
class Context:
    source_id: str
    model: object
    full_model: object
    vector: np.ndarray
    nuisance: np.ndarray
    observations: object
    bank: object
    prior: object
    train_mask: np.ndarray
    nodes: np.ndarray
    source: dict
    fixed_c: bool = False
    deadline: float = float('inf')


def with_state(context, vector, nuisance):
    return replace(context, vector=np.asarray(vector).copy(), nuisance=np.asarray(nuisance).copy())


def load_context(source_id):
    """Replay original receipts through public adapters, preserving bank order."""
    from leo.storage.shared_fast_scan import SharedFastScanStore
    from leo.cli.shared_fast_position import load_input
    from leo.application.shared_fast_position import prepare_views
    from leo.application.shared_orbit_replay import selected_model
    from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets

    source = next(s for s in json.loads((DATASET / 'sources.json').read_text()) if s['source_id'] == source_id)
    store = SharedFastScanStore('/srv/bulk/leo', 'shared-scan-q-v2')
    job, document, terminal, stages = store.plot_evidence(source['job_id'])
    if job['input_sha256'] != source['tracking_input_sha256'] or job['terminal']['sha256'] != source['terminal_sha256']:
        raise ValueError('Frozen source receipt differs')
    source = dict(source)
    station_path = HERE.parents[1] / 'deploy/station/gauss-r20-lt3d-004b-20261001-v1.json'
    station = json.loads(station_path.read_text())
    origin = source['first_sample_estimate_utc_ns']
    if (document['source']['radio_id'] == station['radio_serial']
            and station['valid_from_utc_ns'] <= origin < station['valid_until_utc_ns']):
        source['configured_station_reference'] = dict(
            latitude_deg=station['latitude_deg'], longitude_deg=station['longitude_deg'],
            revision=station['revision'], sha256='sha256:'+hashlib.sha256(station_path.read_bytes()).hexdigest(),
            binding='matching recording radio serial and configured validity interval',
            qualification=station['position_evidence'])
    inputs = load_input(document)
    prepared, nodes = prepare_views(inputs)
    obs = prepared['all'].observations
    prior = RegionalPrior(**terminal['provenance']['prior'])
    numbers = terminal['candidate_numbers']
    cached = HERE.parents[1] / source['report_directory'] / 'orbit-bank.npz'
    if cached.exists():
        b = np.load(cached)
        bank = PositionOrbitBank(b['numbers'], b['nodes'], b['positions'], b['velocities'])
    else:
        archive = TleArchiveReader(Path('/var/lib/leo/tle'))
        snapshot = next(s for s in archive.list_snapshots() if s.digest == source['tle_sha256']
                        and s.collected_utc_ns == source['tle_collected_utc_ns'])
        catalogue = parse_element_sets(archive.read(snapshot))
        lookup = {int(n): i for i, n in enumerate(catalogue.satellite_numbers)}
        bank, _ = build_regional_bank(catalogue, [lookup[n] for n in numbers],
                                     prepared['all'].start_utc_ns, obs, prior)
    order = {int(n): i for i, n in enumerate(bank.numbers)}
    bank = bank.select([order[n] for n in numbers])
    model, fit, audit = selected_model(prepared, bank, prior, nodes, terminal, stages)
    if not audit['accepted']:
        raise ValueError('Original strict endpoint audit failed')
    context = Context(source_id, model, model, np.array(fit['vector']), np.array(fit['nuisance']),
                      obs, bank, prior, np.ones(len(obs.times_s), bool), np.asarray(nodes), source)
    original = measure(context, context.vector, context.nuisance)
    if original['associated'] != source['original_associated_count']:
        raise ValueError('Original association replay differs')
    np.testing.assert_allclose(original['objective'], source['baseline_audit']['objective'], atol=1e-7, rtol=0)
    return context


def temporal_context(context, direction, *, fixed_c=False):
    """No held CFO is read for seeds, contrasts or track proposals.

    Eligibility is conditioned on the frozen full-recording bank; this is not
    claimed to redo candidate discovery without held observations.
    """
    from leo.application.channel_group_refinement import objective
    from leo.analysis.sequential_group_calibration import SequentialShift, fixed_shift_objective
    from leo.analysis.shared_scan_model import SharedScanObjective

    obs = context.observations
    cut = np.median(obs.times_s)
    if direction == 'early_to_late':
        mask = obs.times_s <= cut
    elif direction == 'late_to_early':
        mask = obs.times_s > cut
    else:
        raise ValueError('Unknown temporal direction')
    joint = objective(SimpleNamespace(observations=obs), context.bank, context.prior, context.nodes)
    shift = SequentialShift(joint.frame.receivers, np.zeros(len(joint.frame.receivers)))
    raw = fixed_shift_objective(joint.base, shift)
    model = SharedScanObjective(raw, shift, mask=mask)
    full_model = SharedScanObjective(raw, shift)
    v = np.zeros(model.size)
    # A neutral, deliberately difficult start. No full-data location/calibration.
    n = np.asarray(model.initial_nuisance).copy()
    return replace(context, model=model, full_model=full_model, vector=v, nuisance=n,
                   train_mask=mask, fixed_c=fixed_c)


def refit(context, vector, nuisance, *, max_evaluations=180, max_seconds=120, fixed_c=False):
    """Scaled constrained fit, exact call cap, retain best feasible research state."""
    from scipy.optimize import minimize
    from leo.analysis.hard60_bounded_fit import _Problem, _parameterization

    if max_evaluations < 1 or max_seconds <= 0:
        raise ValueError('Positive fitting allowance required')
    begun = time.monotonic()
    deadline = min(begun + max_seconds, context.deadline)
    model = context.model
    zero_c = bool(fixed_c or context.fixed_c)
    p = _Problem(model, vector, rf_arm='zero-c' if zero_c else 'fitted-c')
    initial, lower, upper, matrix, constant = _parameterization(p)
    dim = len(initial)
    scales = np.r_[np.full(model.clock_count, 50.), model.group_scales]
    limits = np.r_[np.full(model.clock_count, 2000.), model.group_limits]
    nn = np.asarray(nuisance, float).copy()
    if not np.isfinite(nn).all() or np.any(abs(nn) > limits + 1e-7):
        raise ValueError('Infeasible nuisance seed')
    nn = np.clip(nn, -limits, limits)
    initial = np.r_[initial, nn / scales]
    lower, upper = np.r_[lower, -limits / scales], np.r_[upper, limits / scales]
    count = 0
    best = None

    class BudgetExpired(Exception):
        pass

    def evaluate(z):
        nonlocal count, best
        if count >= max_evaluations or (count and time.monotonic() >= deadline):
            raise BudgetExpired()
        v, n = constant + matrix @ z[:dim], z[dim:] * scales
        count += 1
        ev = model.evaluate_joint(v, n)
        value, grad, extra, terms = ev
        if p.feasible(v) and np.isfinite(value) and (best is None or value < best[0]):
            best = (float(value), v.copy(), n.copy(), np.array(grad), np.array(extra), float(terms.nll))
        return value, np.r_[matrix.T @ grad, scales * extra]

    def constraints(z):
        v = constant + matrix @ z[:dim]
        return np.r_[v[7] + 10, 10 - v[7], p.constraints(v)]

    def jacobian(z):
        v = constant + matrix @ z[:dim]
        core = np.vstack([matrix[7], -matrix[7], p.jacobian(v) @ matrix])
        return np.column_stack([core, np.zeros((len(core), len(scales)))])

    reason = 'not-started'
    try:
        evaluate(initial)  # Retain a feasible fallback within the same allowance.
        solved = minimize(evaluate, initial, jac=True, method='SLSQP', bounds=list(zip(lower, upper)),
                          constraints={'type': 'ineq', 'fun': constraints, 'jac': jacobian},
                          options={'maxiter': max_evaluations, 'ftol': 1e-11})
        reason = str(solved.message)
    except BudgetExpired:
        reason = 'evaluation-or-wall-budget'
    if best is None:
        raise RuntimeError('No feasible objective evaluation')
    value, v, n, gradient, extra, nll = best
    projected = scales * extra
    projected[(n <= -limits + 1e-7) & (projected >= 0)] = 0
    projected[(n >= limits - 1e-7) & (projected <= 0)] = 0
    stationarity = max(p.stationarity(v, gradient), float(np.max(abs(projected), initial=0)))
    return dict(vector=v, nuisance=n, diagnostics=dict(evaluations=count, objective=value,
                likelihood_nll=nll, stationarity=stationarity, accepted=bool(stationarity <= .001),
                elapsed_seconds=time.monotonic()-begun, reason=reason, fixed_c=zero_c))


def point_state(model, vector, nuisance):
    ev, details = model.evaluate_details(np.asarray(vector), np.asarray(nuisance))
    terms = ev[3]
    best = np.argmax(terms.responsibilities, axis=1)
    rows = np.arange(len(best))
    associated = terms.responsibilities[rows, best] > terms.clutter_probability
    residual = terms.residual_hz[rows, best]
    return ev, details, best, associated, residual


def distance_km(a, b):
    """Spherical surface distance; reference uncertainty exceeds this approximation."""
    a, b = np.radians(a), np.radians(b)
    d = b-a
    h = np.sin(d[0]/2)**2 + np.cos(a[0])*np.cos(b[0])*np.sin(d[1]/2)**2
    return float(2*6371.0088*np.arcsin(np.sqrt(np.clip(h, 0, 1))))


def measure(context, vector, nuisance, *, original=None, mask=None):
    from leo.analysis.regional_position_score import coordinates

    model = context.full_model
    ev, _, best, assigned, residual = point_state(model, vector, nuisance)
    use = np.ones(len(assigned), bool) if mask is None else np.asarray(mask, bool)
    selected = assigned & use
    rms = lambda values: float(np.sqrt(np.mean(np.square(values)))) if len(values) else None
    tau = vector[7] + model.basis @ vector[8:]
    relative = tau-vector[7]
    lat, lon = coordinates(context.prior, np.asarray(vector)[:2])
    out = dict(observations=int(use.sum()), associated=int(selected.sum()),
               association_pct=100*int(selected.sum())/max(1,int(use.sum())),
               associated_rms_hz=rms(residual[selected]), objective=float(ev[0]),
               likelihood_nll=float(ev[3].nll), common_timing_s=float(vector[7]),
               relative_timing_rms_s=rms(relative), relative_timing_max_s=float(np.max(abs(relative))),
               total_timing_s={str(int(k)):float(t) for k,t in zip(model.bank.numbers,tau)},
               latitude_deg=float(lat), longitude_deg=float(lon), c=float(vector[6]),
               position_movement_km=distance_km([lat,lon],
                   [context.source['original_position']['latitude_deg'], context.source['original_position']['longitude_deg']]))
    reference = context.source.get('configured_station_reference')
    if reference:
        out['configured_reference_distance_km'] = distance_km([lat,lon],
            [reference['latitude_deg'],reference['longitude_deg']])
    if original is not None:
        _, _, obest, oassigned, oresidual = point_state(model, *original)
        intersection = use & assigned & oassigned
        out.update(new_associations=int(np.sum(use & assigned & ~oassigned)),
                   lost_associations=int(np.sum(use & ~assigned & oassigned)),
                   retained_associations=int(intersection.sum()),
                   retained_identity_changes=int(np.sum(intersection & (best != obest))),
                   intersection_original_rms_hz=rms(oresidual[intersection]),
                   intersection_variant_rms_hz=rms(residual[intersection]))
    return out


def endpoint_status(context, vector, nuisance):
    """Independent research audit, outside the optimization-call allowance."""
    from leo.analysis.hard60_bounded_fit import _Problem
    model = context.model
    v, n = np.asarray(vector), np.asarray(nuisance)
    p = _Problem(model,v,rf_arm='zero-c' if context.fixed_c else 'fitted-c')
    limits = np.r_[np.full(model.clock_count,2000.),model.group_limits]
    scales = np.r_[np.full(model.clock_count,50.),model.group_scales]
    if not p.feasible(v) or np.any(abs(n)>limits+1e-7) or (context.fixed_c and v[6] != 0):
        return dict(feasible=False,accepted=False,reason='physical/nuisance bounds')
    ev = model.evaluate_joint(v,n)
    projected = scales*np.asarray(ev[2])
    projected[(n <= -limits+1e-7)&(projected>=0)] = 0
    projected[(n >= limits-1e-7)&(projected<=0)] = 0
    kkt = max(p.stationarity(v,ev[1]),float(np.max(abs(projected),initial=0)))
    return dict(feasible=True,accepted=bool(kkt<=.001),stationarity=kkt,
                training_objective=float(ev[0]),training_nll=float(ev[3].nll))


def challenge_mask(context):
    import csv
    with (DATASET / 'membership.csv').open() as stream:
        ids = {r['observation_id'] for r in csv.DictReader(stream) if r['source_id'] == context.source_id}
    return np.array([key in ids for key in context.observations.window_ids])


def jsonable(value):
    if isinstance(value, dict):
        return {str(k):jsonable(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(value), indent=2, allow_nan=False)+'\n')
