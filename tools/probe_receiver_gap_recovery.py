"""Paired-c common receiver-step tests and withheld-family witness predictions.

The short manually discovered witnesses are provisional. They never calibrate
receiver or orbit parameters and are not promoted to accepted associations.
"""
import argparse
import copy
import hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write,memberships
from diagnose_all_large_tracks import context
from include_curved_family_annotations import configuration
from annotate_track_predictively import prior_means
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached,summary
from investigate_dsx01_localization_failures import fit
from algo02_scan import pair_passes
from leo.analysis.research.retained_track_likelihood import whitening,projected_receiver_basis,profile


def witness_entries(scan,rows,occupied):
    changed=copy.copy(scan);changed.tracks=list(scan.tracks);changed.white=list(scan.white);changed.rx_basis=list(scan.rx_basis)
    used=set(occupied);entries=[]
    for row in rows:
        t=copy.deepcopy(row['track']);ids=t['observation_ids']
        if used.intersection(ids) or len(set(ids))!=len(ids):raise ValueError('witness observations overlap existing evidence')
        used.update(ids);best=row['fixed_family_top'][0]
        if best['norad']!=row['free_phase_top'][0]['norad']:raise ValueError('fixed and free catalogue nominations disagree')
        t.update(times=np.asarray(t['times']),values=np.asarray(t['values']),bank='CH1-4')
        i=len(changed.tracks);changed.tracks.append(t);changed.white.append(whitening(t['times']));changed.rx_basis.append(projected_receiver_basis(t['times']))
        meta=scan.fixed_window_noise
        if meta['extra_parameter_BIC_gain']>0 and any(o not in meta['per_observation_noise_sigma_hz'] for o in ids):raise ValueError('missing frozen per-observation noise')
        entries.append(dict(track_index=i,component=t['key'],candidate_index=best['candidate_index'],norad=best['norad'],alias=best['alias'],
            observation_ids=ids,points=len(ids),discovery_only=True))
    return changed,entries


def run(args):
    out=args.output;out.mkdir(exist_ok=False);inv=read(args.inventory);d=context(inv);base,_=d['problems']['c0']
    targets=read(args.family/'inclusion/protocol.json')['targets'];rows=read(args.witnesses/'result.json')['rows']
    names=['CH3_gap_untracked','CH4_low_branch','CH4_high_branch'];wr=[next(r for r in rows if r['arm']=='c0' and r['track']['key']==name) for name in names]
    # Match IDs and aliases across c arms before freezing the common proposal.
    for row in wr:
        other=next(r for r in rows if r['arm']=='fitted_c' and r['track']['key']==row['track']['key'])
        for key in ['norad','alias']:
            if row['fixed_family_top'][0][key]!=other['fixed_family_top'][0][key]:raise ValueError('c-arm witness nomination disagreement')
    occupied={o for e in d['entries'] for o in e['observation_ids']}
    occupied.update(o for i,sl in zip(base.members,base.slices,strict=True) for o,k in zip(d['scan'].tracks[i]['observation_ids'],d['keep'][sl],strict=True) if k)
    occupied.update(o for t in targets for o in d['scan'].tracks[t['track_index']]['observation_ids'])
    scan,witness=witness_entries(d['scan'],wr,occupied)
    methods=[('matched_control',False,[],False),('targets_no_event',True,[],False),
        ('targets_step65',True,[65.],False),('targets_steps65_95',True,[65.,95.],False),
        ('targets_step65_predictive_witnesses',True,[65.],True),('targets_steps65_95_predictive_witnesses',True,[65.,95.],True)]
    automatic=None
    if args.automatic_events:
        source=read(args.automatic_events);peaks=[]
        for proposal in source['rows']['c0']['with_provisional_witnesses']:
            if proposal['receiver']==1 and proposal['candidate'] and all(abs(proposal['time_s']-r['time_s'])>=10 for r in peaks):peaks.append(proposal)
            if len(peaks)==3:break
        if len(peaks)<2:raise ValueError('automatic experiment requires at least two corroborated peaks')
        automatic=dict(source=str(args.automatic_events),sha256=hashlib.sha256(args.automatic_events.read_bytes()).hexdigest(),
            selection='descending c0 proposal gain; two-family support; 10 s separation; at most three events; shared across c arms',peaks=peaks)
        selected=[r['time_s'] for r in peaks]
        methods=[('matched_control',False,[],False),('targets_no_event',True,[],False),('automatic_top2',True,selected[:2],False),
            ('automatic_all',True,selected,False),('automatic_all_predictive_witnesses',True,selected,True)]
    write(out/'protocol.json',dict(job=inv['job'],targets=targets,witnesses=witness,methods=methods,
        event_kind='receiver_RF',receiver=1,event_prior_sigma_hz=200.,events_selected_from_residual_plot=automatic is None,automatic_selection=automatic,
        short_witnesses_are_provisional=True,witnesses_never_calibrate=True,identities_frozen=True,GPS_used=False,future_TLE=False,
        phase_rounds=5,iterations=48,start=[0,0],box_width_km=25,old_noise_and_priors_unchanged=True))
    for name,add,times,use_witness in methods:
        node,keep=configuration(d['node'],d['keep'],base.slices,targets if add else []);means,_=prior_means(d,node)
        events=[dict(kind='receiver_RF',receiver=1,time_s=t,sigma_hz=200.) for t in times];entries=d['entries']+witness if use_witness else d['entries'];pair={}
        for arm in ['c0','fitted_c']:
            reference=np.zeros(len(means));x=np.zeros(2);history=[]
            def build(ref,ee):
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(scan,node,keep,arm,ref,d['powers'],means,d['model'],events,**kw);attach_event_predictive(p,ee,d['powers']);return cached(p)
            for _ in range(5):
                p=build(reference,entries);result=fit(p,x,iterations=48);x=np.asarray(result['parameters'])
                phase=np.clip(p.state(x)['phases'][p.labels],-15,15);delta=float(np.max(abs(phase-reference)));reference=phase
                history.append(dict(fit=result,phase_change_s=delta))
            row=summary(p,x,entries)
            # New witnesses have no original graph/time-grid index. Keep the
            # legacy postfit search on the unchanged original graph; witnesses
            # count only when explicitly included as predictive entries.
            membership_view=copy.copy(p);membership_view.scan=copy.copy(p.scan)
            membership_view.scan.tracks=p.scan.tracks[:len(d['scan'].tracks)]
            _,_,ids,_=memberships(membership_view,x,entries);old=set(inv['policy'][arm]['proposed_associated_ids'])
            # Score every witness jointly with shared calibration covariance at
            # this endpoint. Held witnesses do not participate in the fit above.
            w=build(p.reference,d['entries']+witness);calc=w.calculate(x);without=build(p.reference,d['entries']).calculate(x)
            predictions=[]
            for entry,sl in zip(w.linear_entries,w.linear_slices,strict=True):
                if entry not in witness:continue
                track=scan.tracks[entry['track_index']];raw=calc['linear_raw_prediction_residual_hz'][sl]
                terms=profile(raw,np.zeros(len(raw)),*scan.white[entry['track_index']],bias_sigma=300.)
                predictions.append(dict(component=entry['component'],norad=entry['norad'],times_s=track['times'],residual_hz=terms['residual'][0],
                    RMS_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0])))
            cr=p.calculate(x);diag=[]
            for target in targets:
                k=target['row'];sl=p.slices[k];track=scan.tracks[target['track_index']]
                diag.append(dict(component=target['component'],times_s=track['times'],CFO_hz=track['values'],residual_hz=cr['conditional_residual_hz'][sl],
                    gate=next((g for g in row['gates']['tracks'] if g['component']==target['component']),None)))
            row.update(history=history,final_phase_change_s=delta,proposed_associated_ids=sorted(ids),added_points=len(ids-old),lost_points=len(old-ids),targets=diag,
                witnesses=predictions,witness_conditional_objective=calc['negative_twice_elbo']-without['negative_twice_elbo'],
                witness_coefficients_max_difference=float(np.max(abs(calc['coefficient']-without['coefficient']))),witnesses_used_for_position=use_witness)
            pair[arm]=row
        valid=pair_passes(pair,include_linear=True) and all(r['lost_points']==0 for r in pair.values())
        write(out/(name+'.json'),dict(job=inv['job'],arms=pair,paired_valid=valid,accepted_recovery=False,discovery_only=True,
            target_entries=targets if add else [],events=events,witnesses_used_for_position=use_witness))
        print(name,'paired checks',valid,[(a,r['added_points'],r['lost_points'],round(r['witness_conditional_objective'],2)) for a,r in pair.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ['inventory','family','witnesses','output']:p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--automatic-events',type=Path)
    run(p.parse_args())
