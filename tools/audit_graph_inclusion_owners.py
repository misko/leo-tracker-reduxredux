"""Replay RF-qualified graph additions, checking exact orbit and old owners."""
import argparse
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write,memberships
from diagnose_all_large_tracks import context
from include_curved_family_annotations import configuration
from annotate_track_predictively import prior_means
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached
from audit_explicit_phase_endpoint import exact_gate_replay
from phase_reference_checks import phase_refresh


def run(args):
    rows=[]
    for job in read(args.batch/'protocol.json')['jobs']:
        root=args.batch/job['track_id'];target=read(root/'target_0.json')
        if not target['paired_valid'] and not getattr(args,'include_unqualified',False):continue
        inv=read(Path(job['inventory']));d=context(inv);base,_=d['problems']['c0']
        family=target['target_entries'][0]['candidate_index'];owners={}
        for arm,(p,x) in d['problems'].items():
            _,_,ids,owners[arm]=memberships(p,x,d['entries'])
            if ids!=set(inv['policy'][arm]['proposed_associated_ids']):raise ValueError('incumbent membership replay failed')
        control_owners={}
        for role in ('control','target_0'):
            saved=read(root/(role+'.json'));node,keep=configuration(d['node'],d['keep'],base.slices,saved['target_entries'])
            means,_=prior_means(d,node)
            for arm,v in saved['arms'].items():
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(d['scan'],node,keep,arm,np.array(v['phase_reference']),d['powers'],means,d['model'],[],**kw)
                attach_event_predictive(p,d['entries'],d['powers']);cached(p);x=np.array(v['endpoint_east_north_km'])
                delta=p.calculate(x)['negative_twice_elbo']-v['negative_twice_elbo']
                if abs(delta)>1e-5:raise ValueError('graph objective replay failed')
                _,_,ids,current=memberships(p,x,d['entries'])
                if ids!=set(v['proposed_associated_ids']):raise ValueError('graph membership replay failed')
                if role=='control':control_owners[arm]=current
                changes=lambda before:[dict(observation_id=oid,before=norad,after=current.get(oid))
                    for oid,norad in before.items() if current.get(oid)!=norad]
                # The replay routine only uses this attribute to select which
                # orbit to replace; it does not alter the fitted graph model.
                p.explicit_phase_family=family
                exact=exact_gate_replay(p,x,d['entries'])
                limit=read(root/'protocol.json').get('reference_limit_s',15.)
                _,phase_check=phase_refresh(p.state(x)['phases'][p.labels],p.reference,limit_s=limit)
                rows.append(dict(scan=job['label'],track_id=job['track_id'],role=role,arm=arm,
                    objective_difference=delta,incumbent_ownership_changes=changes(owners[arm]),
                    control_ownership_changes=changes(control_owners[arm]),owners=current,
                    final_phase_change_s=v['final_phase_change_s'],phase_reference_check=phase_check,
                    phase_converged=phase_check['phase_change_s']<=.01,**exact))
    write(args.output,dict(rows=rows,qualified_trials_only=not getattr(args,'include_unqualified',False),no_acceptance_changes=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--include-unqualified',action='store_true');run(p.parse_args())
