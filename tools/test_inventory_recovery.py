"""Bounded whole-curve joint fits for nominated inventory targets.

Research only: retains all original points and verifies all old memberships.
No new receiver freedom, gate relaxation or evaluation-based selection.
"""
import argparse
import copy
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write,memberships
from diagnose_all_large_tracks import context


def run(args):
    args.output.mkdir(parents=True,exist_ok=False)
    inv=read(args.inventory);d=context(inv);p0,x0=d['problems']['c0'];scan=d['scan']
    from ds23_frequency_events import make_event_problem,attach_event_predictive
    from probe_ds23_frequency_events import cached,summary
    from investigate_dsx01_localization_failures import fit
    from algo02_scan import pair_passes
    from leo.analysis.research.retained_track_likelihood import profile
    from investigate_ds23_0268_remaining_tracks import family_frequency,corrected_observation
    proposals=read(args.proposals)
    for proposal in proposals:
        node=copy.deepcopy(d['node']);keep=d['keep'].copy();ks=[]
        for component,norad in proposal['targets']:
            k=next(k for k,r in enumerate(p0.rows) if r['component']==component)
            j=int(np.flatnonzero(scan.norads==norad)[0]);i=p0.members[k];t=scan.tracks[i]
            f,_=family_frequency(p0,x0,j,times=t['times'])
            term=profile(corrected_observation(p0,x0,i),t['rf_hz']/11.5e9*f,*scan.white[i])
            node['seed']['rows'][k].update(candidate_index=j,candidate_norad=norad)
            node['aliases'][k]=int(term['alias'][0]);keep[p0.slices[k]]=True;ks.append(k)
        labels=sorted({r['candidate_index'] for r in node['seed']['rows']})
        prior_means=dict(zip(p0.labels,d['means'],strict=True));new_labels=[j for j in labels if j not in prior_means]
        new_receipts=[]
        if new_labels:
            # Instantiate the same causal prior for a newly discovered identity;
            # absent from the incumbent model is not evidence against a satellite.
            from investigate_ds23_adaptive_failures import phase_widths
            from probe_ds23_causal_phase_mean import forecast_phase_mean
            _,new_receipts=phase_widths(scan,new_labels)
            prior_means.update(zip(new_labels,forecast_phase_mean(new_receipts,d['model']['shrinkage']),strict=True))
        means=np.array([prior_means[j] for j in labels])
        from probe_graph_shared_high_channels import receiver_basis
        fit_scan,node=receiver_basis(scan,node,proposal.get('receiver_basis','original'))
        pair={}
        for arm in ('c0','fitted_c'):
            reference=np.zeros(len(means));x=np.asarray(proposal.get('start_east_north_km',[0.,0.]));history=[]
            for epoch in range(5):
                kwargs={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(fit_scan,node,keep,arm,reference,d['powers'],means,d['model'],[],**kwargs)
                attach_event_predictive(p,d['entries'],d['powers']);cached(p)
                fitted=fit(p,x,iterations=48);x=np.asarray(fitted['parameters'])
                phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
                history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference)))))
                reference=phase
            r=summary(p,x,d['entries']);curved,pred,ids,_=memberships(p,x,d['entries'])
            old=set(inv['policy'][arm]['proposed_associated_ids'])
            r.update(final_phase_change_s=history[-1]['phase_change_s'],history=history,
                     associated_points=len(ids),added_points=len(ids-old),lost_points=len(old-ids),
                     proposed_associated_ids=sorted(ids),
                     target_gates=[g for g in r['gates']['tracks'] if g['component'] in {p.rows[k]['component'] for k in ks}],
                     failed_existing=[g['component'] for g in r['gates']['tracks'] if not g['compatible'] and g['component'] not in {p.rows[k]['component'] for k in ks}])
            pair[arm]=r
        valid=pair_passes(pair,include_linear=True) and all(r['lost_points']==0 for r in pair.values())
        result=dict(proposal=proposal,arms=pair,baseline=inv['policy'],paired_valid=valid,new_causal_prior_receipts=new_receipts,
                    provisional_only=True,no_production_change=True,no_GPS_used=True,
                    phase_rounds=5,steps_per_round=48,start=proposal.get('start_east_north_km',[0,0]),box_width_km=25)
        write(args.output/(proposal['name']+'.json'),result)
        print(proposal['name'],valid,[(a,r['added_points'],r['lost_points'],r['RMS_hz']) for a,r in pair.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('inventory','proposals','output'):p.add_argument('--'+key,type=Path,required=True)
    run(p.parse_args())
