"""Phase-domain sensitivity at immutable soft-fit endpoints; no position refit."""
import argparse,hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from predictive_graph_bundle import bundle_context
from predictive_label_mixture import LabelMixture
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached
from audit_soft_bundle_members import member_checks


def run(args):
    args.output.mkdir(parents=True,exist_ok=False);pr=read(args.trial/'protocol.json');inv=read(args.inventory);d=context(inv)
    d,target=bundle_context(d,inv,Path(pr['target']['bundle_source']),pr['target']['track_id']);saved=read(args.trial/'soft_mixture.json')
    settings=[(15,.025),(20,.025),(30,.025),(30,.0125)];rows=[]
    write(args.output/'protocol.json',dict(job=inv['job'],settings=settings,positions_and_receiver_fits_frozen=True,
        original_phase_prior_parameters_unchanged=True,integration_support_changes=True,existing_orbit_bank_only=True,
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.inventory,args.trial/'protocol.json',args.trial/'soft_mixture.json')},
        no_position_improvement_or_new_association_claim=True))
    for arm,v in saved['arms'].items():
        kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
        p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.array(v['phase_reference']),d['powers'],d['means'],d['model'],[],**kw)
        attach_event_predictive(p,d['entries'],d['powers']);cached(p);x=np.array(v['endpoint_east_north_km'])
        original=LabelMixture(d,target,pr['candidates'],pr['phase_step_s'])
        difference=original.evaluate(p,x,d['powers'],d['entries'])-v['mixture']['negative_twice_log_density']
        if abs(difference)>1e-5:raise ValueError('original mixture did not replay')
        for limit,step in settings:
            mixture=LabelMixture(d,target,pr['candidates'],step,limit);detail=mixture.evaluate(p,x,d['powers'],d['entries'],details=True)
            exact=mixture.evaluate(p,x,d['powers'],d['entries'],details=True,refine_phase=True)
            member_mass=0.;components=[]
            for c in exact['components']:
                checks=member_checks(c,target['member_indices'],target['members']);passed=all(q['passed'] for q in checks) and all(g['compatible'] for g in c['gates']) and c['phase_boundary_mass']<.01
                if passed:member_mass+=c['weight']
                components.append(dict(norad=c['entry']['norad'],weight=c['weight'],phase_mean_s=c.get('phase_mean_s'),phase_sigma_s=c.get('phase_sigma_s'),phase_boundary_mass=c['phase_boundary_mass'],
                    RMS_hz=c['diagnostics'][0]['profile_RMS_hz'],noise=c['diagnostics'][0]['noise'],member_checks=checks,passes=passed))
            row=dict(arm=arm,phase_limit_s=limit,phase_step_s=step,score=detail['negative_twice_log_density'],
                score_change_from_original=detail['negative_twice_log_density']-v['mixture']['negative_twice_log_density'],
                compatible_mass=exact['compatible_mass'],compatible_member_mass=member_mass,components=components)
            rows.append(row);write(args.output/f'{arm}-{limit}-{step}.json',dict(row=row,detail=detail,exact=exact))
            print(inv['job']['label'],arm,limit,step,'mass',member_mass,flush=True)
    write(args.output/'result.json',dict(rows=rows,no_refit=True,no_acceptance_authorized=True,original_prior_parameters_unchanged=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('inventory','trial','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
