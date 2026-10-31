"""Read-only accounting of DS26-0154's extra c0 extension memberships."""
from pathlib import Path
import numpy as np
from run_inclusion import source_receipt,check_domains
from debug_fast_graph_unassociated import read,write,screen
from annotate_predictive_only import context
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached
from evaluate_ds23_phase_refreshed import extend_associations
from audit_ds23_algo01_coverage import retained_metrics
from report_inclusion import verify_seal


ROOT=Path(__file__).resolve().parent
CONT=ROOT/'DS26-0154-numerical-continuation'


def main():
    verify_seal(CONT/'inference_seal.json')
    protocol=read(ROOT/'cases/DS26-0154/protocol.json');inv=read(protocol['inventory']);d=context(inv)
    control=read(CONT/'control.json');addition=read(CONT/'new_family.json');audit=read(CONT/'exact_owner_replay.json')
    target_ids={o for t in read(CONT/'protocol.json')['targets'] for o in t['observation_ids']}
    rows=[]
    newly_added={arm:set(addition['arms'][arm]['proposed_associated_ids'])-set(control['arms'][arm]['proposed_associated_ids']) for arm in ('c0','fitted_c')}
    other=newly_added['c0']-target_ids
    tracks=[t for t in d['scan'].tracks if other&set(t['observation_ids'])]
    for role,saved in (('control',control),('new_family',addition)):
        for arm,v in saved['arms'].items():
            kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
            p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.asarray(v['phase_reference']),d['powers'],d['means'],d['model'],[],**kw)
            attach_event_predictive(p,d['entries'],d['powers']);cached(p);x=np.asarray(v['endpoint_east_north_km'])
            expected=v.get('incumbent_objective',v['negative_twice_elbo']);delta=p.calculate(x)['negative_twice_elbo']-expected
            if abs(delta)>1e-5:raise ValueError('extension audit endpoint objective failed replay')
            domains=check_domains(p,p.state(x)['phases'][p.labels],d['entries'])
            extension=extend_associations(p,x,retained_metrics(p,x))
            for track in tracks:
                diagnostic=screen(p,x,track,np.arange(len(track['times'])),full_catalogue=False)
                witness=next((r for r in extension['tracks'] if r['component']==track['key']),None)
                rows.append(dict(role=role,arm=arm,component=track['key'],objective_replay_difference=delta,
                    extension_membership=witness,diagnostic=diagnostic,domains=domains,
                    all_track_ids=track['observation_ids'],other_new_c0_ids=sorted(other&set(track['observation_ids']))))
    owners={r['arm']:r['owners'] for r in audit['rows'] if r['role']=='new_family'}
    fitted_control=next(r['owners'] for r in audit['rows'] if r['role']=='control' and r['arm']=='fitted_c')
    accounting=dict(target_ids=sorted(target_ids),common_new_target_ids_both_arms=sorted(target_ids&newly_added['c0']&newly_added['fitted_c']),
        target_recovered_points_both_arms=len(target_ids&newly_added['c0']&newly_added['fitted_c']),
        c0_net_new_ids=sorted(newly_added['c0']),fitted_c_net_new_ids=sorted(newly_added['fitted_c']),
        additional_c0_ids=[dict(observation_id=o,owner=owners['c0'][o],already_associated_in_fitted_c_control=o in fitted_control,
            fitted_c_control_owner=fitted_control.get(o)) for o in sorted(other)],
        rows=rows,no_refit=True,no_acceptance_change=True,
        source_sha256=source_receipt([Path(__file__),CONT/'inference_seal.json',CONT/'control.json',CONT/'new_family.json',CONT/'exact_owner_replay.json']))
    write(ROOT/'extension-id-accounting.json',accounting)


if __name__=='__main__':main()
