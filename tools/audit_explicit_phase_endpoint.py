"""Rebuild explicit-phase endpoints and replay gates with exact family orbits."""
import argparse
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write,memberships
from diagnose_all_large_tracks import context
from native_predictive_branch import native_context,validated_native_source
from ds23_frequency_events import make_event_problem,attach_event_predictive
from explicit_shared_phase import attach_explicit_phase,evidence_context
from probe_ds23_frequency_events import cached
from probe_algo03_feasible_recovery import gate_slacks
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from investigate_ds23_0268_remaining_tracks import family_frequency
from leo.analysis.research.retained_track_likelihood import profile


def exact_gate_replay(p,z,entries):
    """Keep every fitted coefficient; replace only the selected family's orbit."""
    c=p.calculate(z);j=p.explicit_phase_family;frequency,elevation=p.conditional_frequency(z)
    frequency=frequency.copy();elevation=elevation.copy();conditional=c['conditional_residual_hz'].copy()
    linear=c['linear_raw_prediction_residual_hz'].copy() if entries else np.empty(0)
    le=c['linear_elevation'].copy() if entries else np.empty(0);maximum=0.
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        if row['candidate_index']!=j:continue
        t=p.scan.tracks[i];f,e=family_frequency(p,z,j,times=t['times']);difference=p.q[sl]*(f-frequency[sl])
        maximum=max(maximum,float(np.max(abs(difference))));conditional[sl]-=difference;frequency[sl]=f;elevation[sl]=e
    for entry,sl in zip(entries,getattr(p,'linear_slices',[]),strict=True):
        if entry['candidate_index']!=j:continue
        view,*_=linear_geometry(p,[entry]);g=geometry_features(view,z,0.);t=p.scan.tracks[entry['track_index']]
        begin=p.hardware.shape[1]+p.smooth.shape[1];stop=begin+len(p.labels)+3*len(p.supported)
        f,e=family_frequency(p,z,j,times=t['times'])
        approximate=view.q*g['intercept']+g['features'][:,begin:stop]@c['coefficient'][begin:stop]
        difference=view.q*f-approximate;maximum=max(maximum,float(np.max(abs(difference))));linear[sl]-=difference;le[sl]=e
    calculate=p.calculate;conditional_frequency=p.conditional_frequency
    p.calculate=lambda _:dict(c,conditional_residual_hz=conditional,linear_raw_prediction_residual_hz=linear,linear_elevation=le)
    p.conditional_frequency=lambda _: (frequency,elevation)
    try:gates=gate_slacks(p,z,entries)
    finally:p.calculate=calculate;p.conditional_frequency=conditional_frequency
    witnesses=[]
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        active=p.keep[sl]
        if row['candidate_index']!=j or not active.any():continue
        t=p.scan.tracks[i];residual=conditional[sl][active]
        witnesses.append(dict(component=t['key'],times_s=t['times'][active],residual_hz=residual,
            RMS_hz=float(np.sqrt(np.mean(residual**2)))))
    return dict(all_gate_slacks=gates,minimum_slack=min(gates.values()),family_witnesses=witnesses,
        maximum_linearization_difference_hz=maximum,all_pass=min(gates.values())>=0)


def run(args):
    rows=[]
    for root in args.runs:
        protocol=read(root/'protocol.json');pr=protocol['source_protocol'];inv=read(Path(pr['inventory']));d=context(inv)
        incumbent_owners={}
        for arm,(base,x) in d['problems'].items():
            _,_,ids,owners=memberships(base,x,d['entries'])
            if ids!=set(inv['policy'][arm]['proposed_associated_ids']):raise ValueError('incumbent membership failed replay')
            incumbent_owners[arm]=owners
        control=read(root/'control.json')
        d=evidence_context(d,protocol.get('noise_policy','original'))
        source=validated_native_source(Path(pr['validation']));target=pr['target']
        d,_=native_context(d,inv,source,target['component'].split('-NATIVE-')[-1])
        for role in ('control','target'):
            saved=read(root/(role+'.json'));entries=d['entries']+saved['target_entries']
            for arm,r in saved['arms'].items():
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.array(r['phase_reference']),d['powers'],d['means'],d['model'],[],**kw)
                attach_event_predictive(p,entries,d['powers']);attach_explicit_phase(p,entries,d['powers'],target['candidate_index']);cached(p)
                z=np.array(r['optimizer_parameters']);difference=p.calculate(z)['negative_twice_elbo']-r['negative_twice_elbo']
                if abs(difference)>1e-5:raise ValueError('explicit endpoint objective failed replay')
                q=exact_gate_replay(p,z,entries)
                # Predict the native curve after fitting the control; these
                # observations never enter that control's objective or gates.
                view,values,*_=linear_geometry(p,[target]);geo=geometry_features(view,z,0.)
                t=p.scan.tracks[target['track_index']];c=p.calculate(z);begin=p.hardware.shape[1]+p.smooth.shape[1]
                f,_=family_frequency(p,z,target['candidate_index'],times=t['times'])
                raw=values-geo['features'][:,:begin]@c['coefficient'][:begin]-view.q*f
                terms=profile(raw,np.zeros(len(raw)),*p.scan.white[target['track_index']],bias_sigma=300.)
                native=dict(component=t['key'],times_s=t['times'],CFO_hz=t['values'],residual_hz=terms['residual'][0],
                    predicted_CFO_hz=t['values']-terms['residual'][0],RMS_hz=float(terms['rms'][0]),
                    prediction_only_after_control_fit=role=='control')
                current=r['proposed_owners'];old=incumbent_owners[arm];control_owners=control['arms'][arm]['proposed_owners']
                changes=lambda before:[dict(observation_id=oid,before=norad,after=current.get(oid))
                    for oid,norad in before.items() if current.get(oid)!=norad]
                rows.append(dict(run=str(root),role=role,arm=arm,objective_replay_difference=difference,native=native,
                    incumbent_ownership_changes=changes(old),control_ownership_changes=changes(control_owners),**q))
                print(root.name,role,arm,q['minimum_slack'],q['maximum_linearization_difference_hz'],flush=True)
    write(args.output,dict(rows=rows,exact_selected_family_orbit=True,coefficients_unchanged=True,no_acceptance_changes=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runs',type=Path,nargs='+',required=True)
    p.add_argument('--output',type=Path,required=True);run(p.parse_args())
