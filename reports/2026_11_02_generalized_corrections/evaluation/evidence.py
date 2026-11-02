"""Full likelihood/native-ownership qualification, without geography imports."""
import hashlib
import json
import numpy as np
from algo06_science.position import family_score
from probe_algo03_feasible_recovery import gate_slacks
from audit_explicit_phase_endpoint import exact_gate_replay
from debug_fast_graph_unassociated import memberships
from inactive_graph_fragment import original_graph_view


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def native_inventory(p, context):
    owners = {}
    counts = {}
    def add(kind, ids, norad):
        counts[kind] = counts.get(kind, 0) + len(ids)
        for oid in ids:
            if oid in owners:
                raise ValueError('Native observation duplicated across likelihood pieces')
            owners[oid] = int(norad)
    for row, index, sl in zip(p.rows, p.members, p.slices):
        add('curved', [o for o, use in zip(p.scan.tracks[index]['observation_ids'], p.keep[sl]) if use], row['candidate_norad'])
    for entry in context['entries']:
        add('conditional_entries', entry['observation_ids'], entry['norad'])
    for family in context['families']:
        for entry in family.entries:
            add('phase_mixture_families', entry['observation_ids'], entry['norad'])
    return dict(ids=sorted(owners), owners=owners, counts=counts,
                native_ids_sha256=digest(sorted(owners)), fitted_owners_sha256=digest(owners))


def qualify(p, context, x, z, arm, fitted):
    inventory = native_inventory(p, context)
    old = z['baseline_owners'][arm]
    slacks = gate_slacks(p, x, context['entries'])
    exact = []
    try:
        for j in sorted({r['candidate_index'] for r, sl in zip(p.rows, p.slices) if p.keep[sl].any()}):
            p.explicit_phase_family = j
            row = exact_gate_replay(p, x, context['entries'])
            exact.append(dict(norad=int(p.scan.norads[j]), all_pass=row['all_pass'],
                              minimum_slack=row['minimum_slack'],
                              maximum_linearization_difference_hz=row['maximum_linearization_difference_hz']))
    finally:
        if hasattr(p, 'explicit_phase_family'):
            del p.explicit_phase_family
    _, details = family_score(context['families'], context, p, x, details=True)
    boundary = [f['phase_boundary_mass'] for f in details]
    mixture = all(g['compatible'] for f in details for g in f['gates'])
    _, _, _, proposed = memberships(original_graph_view(p, len(p.scan.index)), x, context['entries'])
    for family in context['families']:
        for entry in family.entries:
            proposed.update({o:entry['norad'] for o in entry['observation_ids']})
    lost = [o for o in old if o not in proposed]
    reassigned = [o for o, n in old.items() if o in proposed and proposed[o] != n]
    flags = dict(optimizer_success=bool(fitted['optimizer_success']), phase_closed=bool(fitted['phase_closed']),
                 central_stationary=bool(fitted['central_stationary']),
                 inner_precision_converged=bool(np.isfinite(fitted['final_inner_precision_change']) and fitted['final_inner_precision_change']<=1e-5),
                 base_gates_pass=bool(min(slacks.values()) >= 0),
                 exact_gates_pass=bool(all(r['all_pass'] for r in exact)), mixture_gates_pass=bool(mixture),
                 mixture_phase_interior=bool(all(m < .01 for m in boundary)),
                 native_union_preserved=inventory['ids'] == sorted(old), fitted_owners_preserved=inventory['owners'] == old,
                 no_lost_owners=not lost, no_reassigned_owners=not reassigned,
                 position_interior=not fitted['boundary'])
    return dict(qualified=bool(all(flags.values())), flags=flags,
                failed_qualification=[key for key, value in flags.items() if not value],
                native_inventory={k:v for k,v in inventory.items() if k not in ('ids','owners')},
                failed_gates={k:v for k,v in slacks.items() if v < 0}, exact_checks=exact,
                mixture_boundary_masses=boundary, lost_owner_count=len(lost),
                reassigned_owner_count=len(reassigned),
                incidental_extension_proposals=len(set(proposed)-set(old)),
                proposal_mapping_sha256=digest(proposed))
