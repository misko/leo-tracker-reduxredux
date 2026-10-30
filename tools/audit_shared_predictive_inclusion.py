"""Replay default shared-family additions, with owner and exact-orbit checks."""
import argparse
import hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write,memberships
from diagnose_all_large_tracks import context
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached
from audit_explicit_phase_endpoint import exact_gate_replay
from audit_predictive_family_inclusion import owner_changes
from phase_reference_checks import phase_refresh


def run(args):
    pr=read(args.trial/'protocol.json')
    if any(pr.get(k) for k in ('target_orbit_prior','orphan_phase_refresh','orphan_orbit_prior')):
        raise ValueError('this replay covers default, marginal or conditional shared satellite refresh only')
    if pr.get('shared_satellite_refresh') and pr.get('conditional_satellite_refresh'):
        raise ValueError('one shared posterior variant at a time required')
    if pr['noise_policy']!='original':raise ValueError('original noise required')
    inv=read(args.study/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json');d=context(inv)
    for source in pr.get('inactive_fragment_sources',[]):
        from inactive_graph_fragment import validated_inactive_context
        d,_=validated_inactive_context(d,inv,Path(source))
    old={};controls={};rows=[];hashes={}
    for arm,(p,x) in d['problems'].items():
        _,_,ids,old[arm]=memberships(p,x,d['entries'])
        if ids!=set(inv['policy'][arm]['proposed_associated_ids']):raise ValueError('incumbent membership replay failed')
    for role in ('control','target_0'):
        path=args.trial/(role+'.json');r=read(path);hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        entries=d['entries']+r['target_entries']
        for arm,v in r['arms'].items():
            kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
            p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.array(v['phase_reference']),d['powers'],d['means'],d['model'],[],**kw)
            attach_event_predictive(p,entries,d['powers'])
            if pr.get('shared_satellite_refresh'):
                from shared_satellite_refresh import attach_shared_satellite_refresh
                attach_shared_satellite_refresh(p,entries,d['powers'],[t['candidate_index'] for t in pr['targets']])
            if pr.get('conditional_satellite_refresh'):
                from conditional_satellite_refresh import attach_conditional_satellite_refresh
                attach_conditional_satellite_refresh(p,entries,d['powers'],[t['candidate_index'] for t in pr['targets']])
            cached(p);x=np.array(v['endpoint_east_north_km'])
            difference=p.calculate(x)['negative_twice_elbo']-v['negative_twice_elbo']
            from inactive_graph_fragment import original_graph_view
            _,_,ids,owners=memberships(original_graph_view(p,pr.get('original_graph_count',len(p.scan.tracks))),x,entries)
            if abs(difference)>1e-5 or ids!=set(v['proposed_associated_ids']) or owners!=v['proposed_owners']:
                raise ValueError('objective, membership or owners failed replay')
            if role=='control':controls[arm]=owners
            labels={q['candidate_index'] for q,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()}
            labels.update(e['candidate_index'] for e in entries);exact=[]
            for j in sorted(labels):
                p.explicit_phase_family=j
                exact.append(dict(norad=int(p.scan.norads[j]),**exact_gate_replay(p,x,entries)))
            _,check=phase_refresh(p.state(x)['phases'][p.labels],p.reference)
            incumbent_changes=owner_changes(old[arm],owners);control_changes=owner_changes(controls[arm],owners)
            receiver_change=p.calculate(x).get('shared_satellite_receiver_change',v['linear_calibration_max_difference'])
            verified=(not incumbent_changes and not control_changes and all(q['all_pass'] for q in exact)
                      and check['phase_change_s']<=.01 and receiver_change<=1e-10)
            rows.append(dict(role=role,arm=arm,objective_difference=difference,phase_reference_check=check,
                             exact_family_replays=exact,incumbent_ownership_changes=incumbent_changes,
                             control_ownership_changes=control_changes,receiver_coefficient_change=receiver_change,verified=verified))
            print(role,arm,verified,flush=True)
    write(args.output,dict(rows=rows,all_verified=all(r['verified'] for r in rows),source_hashes=hashes,
                          exact_orbits_replaced_one_family_at_a_time=True,no_refit=True,no_acceptance_changes=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('study','trial','output'):p.add_argument('--'+key,type=Path,required=True)
    run(p.parse_args())
