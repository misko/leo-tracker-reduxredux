"""Decompose a new family's position pull, without fitting to evaluation GPS."""
import argparse,hashlib
from functools import lru_cache
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached
from predictive_new_family import NewFamily
from phase_reference_checks import phase_refresh


def family_options(protocol):
    prior=protocol.get('family_prior',{})
    return dict(phase_step=protocol['phase_step_s'],allow_uncalibrated_label=protocol.get('uncalibrated_label',False),
        phase_limit_s=prior.get('phase_limit_s',15.),integrate_orbit_uncertainty=prior.get('integrate_orbit_uncertainty',True),
        integrate_receiver_uncertainty=prior.get('integrate_receiver_uncertainty',True))


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);pr=read(args.trial/'protocol.json');trial=read(args.trial/'new_family.json');control=read(args.trial/'control.json')
    invpath=args.study/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json';inv=read(invpath);d=context(inv)
    for source in pr.get('graph_bundle_sources',[]):
        from predictive_graph_bundle import validated_bundle_context
        d,_=validated_bundle_context(d,inv,Path(source))
    for source in pr.get('inactive_fragment_sources',[]):
        from inactive_graph_fragment import validated_inactive_context
        d,_=validated_inactive_context(d,inv,Path(source))
    family=NewFamily(d['scan'],pr['targets'],d['model'],**family_options(pr))
    result={}
    for arm in ('c0','fitted_c'):
        @lru_cache(maxsize=128)
        def evaluate(point):
            x=np.array(point);reference=np.zeros(len(d['means']))
            for _ in range(5):
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(d['scan'],d['node'],d['keep'],arm,reference,d['powers'],d['means'],d['model'],[],**kw)
                attach_event_predictive(p,d['entries'],d['powers']);cached(p)
                reference,check=phase_refresh(p.state(x)['phases'][p.labels],reference);delta=check['phase_change_s']
            if check['phase_outside_reference_window'] or delta>.01:raise ValueError('fixed-position phase refresh did not close')
            c=p.calculate(x);detail=family.evaluate(p,x,d['powers'],d['entries'],details=True,refine_phase=True)
            old=float(c['negative_twice_elbo']);new=detail['negative_twice_log_density']
            saved=family.logprior.copy()
            try:
                family.logprior=np.zeros_like(saved)
                family.logprior[[0,-1]]-=np.log(2)
                flat=family.evaluate(p,x,d['powers'],d['entries'])
            finally:family.logprior=saved
            return dict(x=x,incumbent_objective=old,target_objective=new,joint_objective=old+new,
                uniform_phase_target_objective=flat,phase_prior_penalty=-2*float(family.distribution.logpdf(detail['phase_map_s'])),
                phase_change_s=delta,phase_s=detail['phase_map_s'],phase_sigma_s=detail['phase_sigma_s'],
                orbital_posterior_mean=detail['orbital_posterior_mean'],diagnostics=detail['diagnostics'])
        x0=np.array(control['arms'][arm]['endpoint_east_north_km']);x1=np.array(trial['arms'][arm]['endpoint_east_north_km']);direction=x1-x0
        line=[dict(fraction=float(t),**evaluate(tuple(x0+t*direction))) for t in np.linspace(-.5,1.5,17)]
        step=.025;eye=np.eye(2)*step;center=evaluate(tuple(x0));hessian=np.zeros((2,2));gradient=np.zeros(2);flat_gradient=np.zeros(2)
        for i in range(2):
            plus=evaluate(tuple(x0+eye[i]));minus=evaluate(tuple(x0-eye[i]))
            hessian[i,i]=(plus['incumbent_objective']-2*center['incumbent_objective']+minus['incumbent_objective'])/step**2
            gradient[i]=(plus['target_objective']-minus['target_objective'])/(2*step)
            flat_gradient[i]=(plus['uniform_phase_target_objective']-minus['uniform_phase_target_objective'])/(2*step)
        hessian[0,1]=hessian[1,0]=(evaluate(tuple(x0+eye[0]+eye[1]))['incumbent_objective']-evaluate(tuple(x0+eye[0]-eye[1]))['incumbent_objective']-
            evaluate(tuple(x0-eye[0]+eye[1]))['incumbent_objective']+evaluate(tuple(x0-eye[0]-eye[1]))['incumbent_objective'])/(4*step**2)
        eigenvalues,eigenvectors=np.linalg.eigh(hessian)
        result[arm]=dict(line=line,control=evaluate(tuple(x0)),with_target=evaluate(tuple(x1)),
            position_shift_km=float(np.linalg.norm(direction)),incumbent_hessian_per_km2=hessian,
            incumbent_hessian_eigenvalues=eigenvalues,incumbent_hessian_eigenvectors=eigenvectors,target_gradient_per_km=gradient,
            uniform_phase_target_gradient_per_km=flat_gradient,
            endpoint_joint_difference_from_saved=evaluate(tuple(x1))['joint_objective']-trial['arms'][arm]['negative_twice_elbo'],
            direction_overlap_with_weak_axis=float(abs(eigenvectors[:,0]@direction)/np.linalg.norm(direction)),
            local_Gaussian_sigma_axes_km=np.sqrt(2/eigenvalues) if np.all(eigenvalues>0) else None)
        print(arm,'shift',result[arm]['position_shift_km'],'H eigenvalues',eigenvalues,'weak alignment',result[arm]['direction_overlap_with_weak_axis'],flush=True)
    write(out/'result.json',dict(job=pr['job'],norad=pr['targets'][0]['norad'],arms=result,position_search=False,GPS_used=False,
        family_options=family_options(pr),source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [invpath,args.trial/'protocol.json',args.trial/'control.json',args.trial/'new_family.json']},
        uniform_phase_prior_is_diagnostic_only=True,
        caveat='local objective curvature is conditional on fixed associations and empirical nuisance model; not calibrated position confidence'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ['study','trial','output']:p.add_argument('--'+k,type=Path,required=True)
    run(p.parse_args())
