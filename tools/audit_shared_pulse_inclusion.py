"""Reconstruct pulse trials and audit event scope, new curves and ownership."""
import argparse,hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from ds23_frequency_events import make_event_problem,attach_event_predictive,event_design,track_events
from probe_ds23_frequency_events import cached
from test_shared_pulse_inclusion import event_memberships,target_prediction
from ds23_predictive_linear import linear_geometry
from phase_reference_checks import reference_domain


def run(args):
    inv=read(args.inventory);d=context(inv);rows=[];sources={str(args.inventory):hashlib.sha256(args.inventory.read_bytes()).hexdigest()}
    for batch in args.batches:
        for path in sorted(batch.glob('*/result.json')):
            pr=read(path.parent/'protocol.json');record=read(path);sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
            sources[str(path.parent/'protocol.json')]=hashlib.sha256((path.parent/'protocol.json').read_bytes()).hexdigest()
            targets=pr.get('targets',[pr['target']]);event=pr['events']
            for saved in record['rows']:
                arm=saved['arm'];role=saved['role'];entries=d['entries']+(targets if role=='addition' else [])
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.array(saved['phase_reference']),d['powers'],d['means'],d['model'],event,**kw)
                attach_event_predictive(p,entries,d['powers']);cached(p);x=np.array(saved['endpoint_east_north_km']);c=p.calculate(x)
                difference=float(c['negative_twice_elbo']-saved['negative_twice_elbo']);ids,owners=event_memberships(p,x,entries)
                if abs(difference)>1e-5 or ids!=set(saved['proposed_associated_ids']) or owners!=saved['proposed_owners']:
                    raise ValueError('objective or ownership replay mismatch')
                old=set(inv['policy'][arm]['proposed_associated_ids']);added=ids-old;curves=[];seen=set()
                phase=p.state(x)['phases']
                for track in inv['tracks']:
                    if track['track_id'] in seen:continue
                    seen.add(track['track_id']);new=set(track['observation_ids'])&added
                    if not new:continue
                    norads={owners[oid] for oid in new}
                    if len(norads)!=1:raise ValueError('new track has mixed owners')
                    n=next(iter(norads));j=int(np.flatnonzero(p.scan.norads==n)[0]);t=p.scan.tracks[track['track_index']]
                    domain=reference_domain(p.sky['time_s'],t['times'],np.zeros(len(t['times']),int),[phase[j]],padding_s=0)
                    if not domain['in_domain']:raise ValueError('new track leaves exact orbit bank')
                    entry=dict(track_index=track['track_index'],candidate_index=j,norad=n,alias=0)
                    diagnostic=target_prediction(p,x,entry)
                    curves.append(dict(track_id=track['track_id'],norad=n,new_points=len(new),**diagnostic))
                amplitude_sd=None;scope=None
                if event:
                    u=c['features'][p.keep];g=p.noise_groups[p.keep]
                    weights=d['powers'][g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
                    gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*weights[:,None])
                    cov=np.linalg.solve(gram,np.eye(len(gram)))
                    amplitude_sd=float(event[0]['sigma_hz']*np.sqrt(cov[p.event_start,p.event_start]))
                    # Same pulse and scaling, only family versus receiver scope.
                    common=dict(event[0]);rx=p.scan.tracks[targets[0]['track_index']]['receiver'];j=targets[0]['candidate_index']
                    alternatives=[dict(common,kind='receiver',receiver=rx),dict(common,kind='family',candidate_index=j)]
                    design=[];active_points=[]
                    for r,i,sl in zip(p.rows,p.members,p.slices,strict=True):
                        selected=track_events(p.scan.tracks[i],r['candidate_index'],alternatives)[p.keep[sl]]
                        design.extend(selected.tolist());active_points.extend([('curved',r['candidate_index'])]*len(selected))
                    for entry in entries:
                        selected=track_events(p.scan.tracks[entry['track_index']],entry['candidate_index'],alternatives)
                        design.extend(selected.tolist());active_points.extend([('predictive',entry['candidate_index'])]*len(selected))
                    design=np.array(design);active=np.any(design!=0,axis=1)
                    scope=dict(maximum_design_difference_hz=float(np.max(abs(design[:,0]-design[:,1]))),
                        active_event_observations=int(active.sum()),joint_design_rank=int(np.linalg.matrix_rank(design)),
                        indistinguishable_on_all_likelihood_observations=bool(np.array_equal(design[:,0],design[:,1])))
                rows.append(dict(batch=str(batch),method=pr['method'],role=role,arm=arm,
                    objective_difference=difference,owners_replay_identically=True,new_curves=curves,
                    event_amplitude_sigma_hz=amplitude_sd,amplitude_sigma_conditions_on_position_and_Gamma=True,
                    scope=scope,evidence_qualified=saved['evidence_qualified']))
            print(batch.name,path.parent.name,'replayed',flush=True)
    write(args.output,dict(rows=rows,source_hashes=sources,no_refit=True,no_policy_change=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inventory',type=Path,required=True)
    p.add_argument('--batches',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args())
