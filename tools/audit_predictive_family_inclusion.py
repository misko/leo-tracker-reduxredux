"""Replay a predictive-family addition without refitting or changing acceptance."""
import argparse
import hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read, write, memberships
from diagnose_all_large_tracks import context
from ds23_frequency_events import make_event_problem, attach_event_predictive
from probe_ds23_frequency_events import cached
from predictive_new_family import NewFamily
from audit_explicit_phase_endpoint import exact_gate_replay
from phase_reference_checks import phase_refresh


def owner_changes(before, after):
    return [dict(observation_id=o, before=n, after=after.get(o))
            for o, n in before.items() if after.get(o) != n]


def run(args):
    pr = read(args.trial / 'protocol.json')
    inv = read(args.study / 'all-large-track-recovery' / pr['job']['job_id'] / 'inventory.json')
    d = context(inv)
    for source in pr.get('inactive_fragment_sources',[]):
        from inactive_graph_fragment import validated_inactive_context
        d,_=validated_inactive_context(d,inv,Path(source))
    for source in pr.get('graph_bundle_sources',[]):
        from predictive_graph_bundle import validated_bundle_context
        d,_=validated_bundle_context(d,inv,Path(source))
    family = NewFamily(d['scan'], pr['targets'], d['model'], phase_step=pr['phase_step_s'],
                       allow_uncalibrated_label=pr.get('uncalibrated_label', False),
                       integrate_orbit_uncertainty=pr['family_prior'].get('integrate_orbit_uncertainty', True),
                       integrate_receiver_uncertainty=pr['family_prior'].get('integrate_receiver_uncertainty', True))
    incumbent = {}; controls = {}; rows = []; hashes = {}
    for arm, (p, x) in d['problems'].items():
        _, _, ids, incumbent[arm] = memberships(p, x, d['entries'])
        if ids != set(inv['policy'][arm]['proposed_associated_ids']):
            raise ValueError('incumbent membership replay failed')
    for role in ('control', 'new_family'):
        path = args.trial / (role + '.json'); saved = read(path)
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        for arm, v in saved['arms'].items():
            kw = {'base_problem_factory': d['problem_factory']} if 'problem_factory' in d else {}
            p = make_event_problem(d['scan'], d['node'], d['keep'], arm, np.array(v['phase_reference']),
                                   d['powers'], d['means'], d['model'], [], **kw)
            attach_event_predictive(p, d['entries'], d['powers']); cached(p)
            x = np.array(v['endpoint_east_north_km'])
            objective = p.calculate(x)['negative_twice_elbo']
            from inactive_graph_fragment import original_graph_view
            _, _, ids, owners = memberships(original_graph_view(p,pr.get('original_graph_count',len(p.scan.tracks))), x, d['entries'])
            target = None; refined = None
            if role == 'new_family':
                target = family.evaluate(p, x, d['powers'], d['entries'], details=True)
                refined = family.evaluate(p, x, d['powers'], d['entries'], details=True, refine_phase=True)
                if abs(target['negative_twice_log_density'] - v['family']['negative_twice_log_density']) > 1e-6:
                    raise ValueError('family density failed replay')
                objective += target['negative_twice_log_density']
                for e in pr['targets']:
                    if ids.intersection(e['observation_ids']):
                        raise ValueError('target duplicates incumbent evidence')
                    ids.update(e['observation_ids'])
                    owners.update({o: e['norad'] for o in e['observation_ids']})
            difference = float(objective - v['negative_twice_elbo'])
            if abs(difference) > 1e-5 or ids != set(v['proposed_associated_ids']):
                raise ValueError('objective or membership failed replay')
            if role == 'control': controls[arm] = owners
            labels = {r['candidate_index'] for r, sl in zip(p.rows, p.slices, strict=True) if p.keep[sl].any()}
            labels.update(e['candidate_index'] for e in d['entries'])
            exact = []
            for j in sorted(labels):
                p.explicit_phase_family = j
                exact.append(dict(norad=int(p.scan.norads[j]), **exact_gate_replay(p, x, d['entries'])))
            _, check = phase_refresh(p.state(x)['phases'][p.labels], p.reference)
            row = dict(role=role, arm=arm, objective_difference=difference,
                       incumbent_ownership_changes=owner_changes(incumbent[arm], owners),
                       control_ownership_changes=owner_changes(controls[arm], owners),
                       phase_reference_check=check, exact_incumbent_family_replays=exact,
                       target=target, continuous_target=refined, owners=owners)
            row['verified'] = (check['phase_change_s'] <= .01 and all(r['all_pass'] for r in exact)
                               and not row['incumbent_ownership_changes'] and not row['control_ownership_changes']
                               and (target is None or (all(g['compatible'] for g in target['gates'])
                                    and all(g['compatible'] for g in refined['gates'])
                                    and target['receiver_calibration_change'] == 0)))
            rows.append(row)
            print(role, arm, row['verified'], flush=True)
    write(args.output, dict(rows=rows, all_verified=all(r['verified'] for r in rows), source_hashes=hashes,
                           incumbent_orbits_replaced_one_family_at_a_time=True,
                           no_refit=True, no_acceptance_changes=True))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('study', 'trial', 'output'): p.add_argument('--' + key, type=Path, required=True)
    run(p.parse_args())
