"""Replay joint-family diagnostic endpoints with unchanged physical gates."""
import argparse
import copy
import hashlib
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from debug_fast_graph_unassociated import read, write, memberships
from diagnose_all_large_tracks import context
from ds23_frequency_events import make_event_problem, attach_event_predictive
from probe_ds23_frequency_events import cached
from predictive_new_family import NewFamily
from probe_joint_predictive_families import joint_inputs
from fit_two_predictive_families import evidence
from audit_explicit_phase_endpoint import exact_gate_replay
from audit_predictive_family_inclusion import owner_changes
from audit_target_membership_scope import scoped_membership
from phase_reference_checks import phase_refresh
from leo.analysis.research.joint_predictive_families import two_family_phase_evidence
from leo.analysis.research.predictive_track import receiver_design, phase_resolution_agreement
from leo.analysis.research.retained_track_likelihood import PERIOD, profile
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from prototype_dsx01_continuous_position import latlon


def at_phases(families, phases):
    result = []
    for family, phase in zip(families, phases, strict=True):
        f = copy.copy(family)
        f.phases = np.array([phase])
        f.grid_times = f.times
        f.grid_labels = np.zeros(len(f.times), int)
        f.logprior = np.zeros(1)
        # One phase is one geometry label; the physical mode bank must likewise
        # contain only that label's three modes, not every integration copy.
        f.bank = {k: v if k == 'time_s' else v[:1] for k, v in family.bank.items()}
        f.modes = {k: v if k == 'time_s' else v[:3] for k, v in family.modes.items()}
        result.append(f)
    return result


def joint_diagnostics(families, p, x, d, refine=False):
    full = two_family_phase_evidence(*joint_inputs(families, p, x, d['powers'], d['entries']))
    phases = np.array([f.phases[k] for f, k in zip(families, full['joint_map_indices'], strict=True)])
    refine_success = None
    if refine:
        def score(z):
            fs = at_phases(families, z)
            r = two_family_phase_evidence(*joint_inputs(fs, p, x, d['powers'], d['entries']))
            return r['negative_twice_log_density'] - 2*sum(f.distribution.logpdf(v) for f, v in zip(families, z, strict=True))
        widths = [f.phases[1]-f.phases[0] for f in families]
        opt = minimize(score, phases, method='Powell',
                       bounds=[(max(-15., v-w), min(15., v+w)) for v, w in zip(phases, widths, strict=True)],
                       options=dict(maxiter=40, maxfev=240, xtol=1e-7, ftol=1e-10))
        phases = opt.x
        refine_success = bool(opt.success)
    fs = at_phases(families, phases)
    point = two_family_phase_evidence(*joint_inputs(fs, p, x, d['powers'], d['entries']))
    c = p.curved_calculate(x) if d['entries'] else p.calculate(x)
    coefficient = c['coefficient'].copy()
    gates, diagnostics = [], []
    for f, orbit in zip(fs, point['orbital_map_mean'], strict=True):
        freq, elevation = paired_phase_frequency(f.bank, f.grid_times, f.grid_labels, f.phases, *latlon(x))
        modes = paired_frequency_modes(f.bank, f.modes, f.grid_times, f.grid_labels, f.phases, *latlon(x))
        receiver = np.concatenate([receiver_design(t['times'], t['rf_hz'], t['receiver'], t['channel'],
                         f.scan.rx_basis[e['track_index']], fitted_c=p.fitted_c)
                         for t, e in zip(f.tracks, f.entries, strict=True)])
        prediction = receiver @ coefficient[:receiver.shape[1]] + f.q*(freq + modes @ orbit)
        raw = f.values-prediction
        for entry, track, sl in zip(f.entries, f.tracks, f.slices, strict=True):
            terms = profile(raw[sl], np.zeros(sl.stop-sl.start), *f.scan.white[entry['track_index']], bias_sigma=300.)
            screen = batch_noise_screen(terms['innovations'], track['times'])
            valid = bool(terms['rms'][0] <= 450 and abs(terms['bias'][0]) <= 3000 and
                         int(terms['alias'][0]) == 0 and screen['noise_screen_pass'][0] and elevation[sl].min() >= 0)
            gates.append(dict(component=entry['component'], norad=entry['norad'], compatible=valid))
            diagnostics.append(dict(component=entry['component'], norad=entry['norad'], times_s=track['times'],
                 CFO_hz=track['values'], prediction_CFO_hz=prediction[sl]-entry['alias']*PERIOD,
                 raw_residual_hz=raw[sl], profile_bias_hz=float(terms['bias'][0]),
                 profile_RMS_hz=float(terms['rms'][0]), minimum_elevation_deg=float(elevation[sl].min()),
                 noise={k: bool(v[0]) if v.dtype == bool else float(v[0]) for k, v in screen.items()}))
    after = p.curved_calculate(x) if d['entries'] else p.calculate(x)
    return dict(gates=gates, diagnostics=diagnostics, phases_s=phases, refined=refine,
                refinement_success=refine_success, receiver_calibration_change=float(np.max(abs(coefficient-after['coefficient']))),
                phase_boundary_mass=[float(w[abs(f.phases) >= 14.9].sum())
                  for f, w in zip(families, full['phase_marginals'], strict=True)])


def run(args):
    args.output.parent.mkdir(parents=True, exist_ok=True)
    hashes = {}
    def load(p):
        hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
        return read(p)
    pr = load(args.trial/'protocol.json')
    for path, digest in pr['source_hashes'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('changed fit source: '+path)
    saved = load(args.trial/'result.json')
    inv = load(args.study/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json')
    d = context(inv)
    arm = pr['arm']
    p0, x0 = d['problems'][arm]
    _, _, old_ids, old_owners = memberships(p0, x0, d['entries'])
    if old_ids != set(inv['policy'][arm]['proposed_associated_ids']):
        raise ValueError('incumbent membership replay failed')
    kw = {'base_problem_factory': d['problem_factory']} if 'problem_factory' in d else {}
    p = make_event_problem(d['scan'], d['node'], d['keep'], arm, np.array(saved['phase_reference']),
                           d['powers'], d['means'], d['model'], [], **kw)
    attach_event_predictive(p, d['entries'], d['powers'])
    cached(p)
    x = np.array(saved['endpoint_east_north_km'])
    families = [NewFamily(d['scan'], group, d['model'], phase_step=pr['phase_step_s'],
                          allow_uncalibrated_label=True) for group in pr['targets']]
    _, _, ids, owners = memberships(p, x, d['entries'])
    objective = p.calculate(x)['negative_twice_elbo']
    target_ids = {o for group in pr['targets'] for e in group for o in e['observation_ids']}
    fitted = {o for i, sl in zip(p.members, p.slices, strict=True)
              for o, k in zip(d['scan'].tracks[i]['observation_ids'], d['keep'][sl], strict=True) if k}
    fitted.update(o for e in d['entries'] for o in e['observation_ids'])
    target = refined = quadrature = scope = None
    if pr['method'] != 'control':
        objective += evidence(families, p, x, d, pr['method'])
        if target_ids & ids:
            raise ValueError('target duplicates retained evidence')
        ids.update(target_ids)
        for group in pr['targets']:
            for e in group:
                owners.update({o: e['norad'] for o in e['observation_ids']})
        fitted.update(target_ids)
        control = load(args.trial.parent/('control-'+arm)/'audit.json')
        scope = scoped_membership(control['reviewed_ids'], ids, target_ids, fitted, control['owners'], owners)
        if pr['method'] == 'joint':
            target = joint_diagnostics(families, p, x, d)
            refined = joint_diagnostics(families, p, x, d, refine=True)
        else:
            target = [f.evaluate(p, x, d['powers'], d['entries'], details=True) for f in families]
            refined = [f.evaluate(p, x, d['powers'], d['entries'], details=True, refine_phase=True) for f in families]
        offsets = np.array([[0, 0], [.025, 0], [-.025, 0], [0, .025], [0, -.025]])
        if np.max(abs(x))+.025 > 12.5:
            quadrature = dict(local_agreement=False, reason='boundary')
        else:
            steps = [pr['phase_step_s']/k for k in (1, 2, 4)]
            fs = [[NewFamily(d['scan'], group, d['model'], phase_step=step, allow_uncalibrated_label=True)
                   for group in pr['targets']] for step in steps]
            scores = np.array([[evidence(f, p, x+offset, d, pr['method']) for f in fs] for offset in offsets])
            quadrature = dict(steps_s=steps, offsets_km=offsets, scores=scores, **phase_resolution_agreement(scores))
    difference = float(objective-saved['negative_twice_elbo'])
    if abs(difference) > 1e-5:
        raise ValueError('objective replay failed')
    labels = {r['candidate_index'] for r, sl in zip(p.rows, p.slices, strict=True) if p.keep[sl].any()}
    labels.update(e['candidate_index'] for e in d['entries'])
    exact = []
    for j in sorted(labels):
        p.explicit_phase_family = j
        exact.append(dict(norad=int(p.scan.norads[j]), **exact_gate_replay(p, x, d['entries'])))
    _, phase = phase_refresh(p.state(x)['phases'][p.labels], p.reference)
    changed = owner_changes(old_owners, owners)
    base_pass = bool(not changed and old_ids <= ids and all(r['all_pass'] for r in exact)
                     and phase['phase_change_s'] <= .01 and saved['history'][-1]['success'])
    checks = dict(incumbent_and_numerical=base_pass)
    if target is not None:
        details = [target, refined] if pr['method'] == 'joint' else target+refined
        checks.update(target_gates=all(g['compatible'] for z in details for g in z['gates']),
                      receiver_unchanged=all(z['receiver_calibration_change'] == 0 for z in details),
                      phase_resolution=quadrature['local_agreement'],
                      phase_interior=all(np.max(z['phase_boundary_mass']) < .01 for z in details),
                      continuous_phase_completed=refined['refinement_success'] if pr['method'] == 'joint' else True)
    reviewed = scope['reviewed_associated_ids'] if scope else sorted(old_ids)
    # Exclude all unscored post-fit extensions, including those in control.
    reviewed_owners = {o: owners[o] for o in reviewed}
    write(args.output, dict(method=pr['method'], arm=arm, source_hashes=hashes, checks=checks,
          RF_qualified_arm=all(checks.values()), joint_pair_requires_both_arms=True,
          objective_difference=difference, target=target, continuous_target=refined,
          quadrature=quadrature, scope=scope, exact_incumbent_orbits=exact,
          incumbent_owner_changes=changed, phase_check=phase, reviewed_ids=reviewed,
          owners=reviewed_owners, production_changed=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('study', 'trial', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    run(parser.parse_args())
