"""Independent original-coordinate ELBO and gate replay; no evaluation GPS."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np

import probe_ds23_soft_predictive_identity as study
import audit_ds23_family_cavity as curved_audit
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from probe_ds23_frequency_events import summary
from probe_ds23_reentry_family_cavity import assert_curved_gate_replay
from run_algo01_ds23_sample import ROOT,read,write,sha


def direct_bound(p,position,entries,powers,c):
    """Dense per-track covariances in original calibration coordinates.

    No whitening/sufficient-statistic/identity-bound implementation is reused.
    The shared posterior covariance is transformed back to physical design
    coordinates, and Gaussian KL is evaluated against curved-data precision.
    """
    curved=p.curved_calculate(position);features=curved['features'][p.keep]
    g=p.noise_groups[p.keep];w=powers[g]*curved['noise_precision'][g]/p.point_noise[p.keep]**2
    precision=np.diag(curved['coefficient_prior_precision'])+features.T@(features*w[:,None])
    root=np.linalg.cholesky(precision);inverse=np.linalg.solve(root,np.eye(len(root)))
    soft=c['soft_identity'];mean=inverse.T@soft['mean'];covariance=inverse.T@soft['covariance']@inverse
    prior_cov=np.linalg.inv(precision)
    gaussian_KL=float(np.trace(precision@covariance)+mean@precision@mean-len(mean)
        +np.linalg.slogdet(prior_cov)[1]-np.linalg.slogdet(covariance)[1])
    offered=[dict(entry,candidate_index=j,norad=int(p.scan.norads[j])) for entry,choices in zip(entries,c['identity_candidates'],strict=True) for j in choices]
    view,values,sigma,_,slices=linear_geometry(p,offered);geometry=geometry_features(view,position,0.)
    raw=values-view.q*geometry['intercept']-geometry['features']@curved['coefficient']
    objective=gaussian_KL;index=0
    for weights,choices in zip(soft['weights'],c['identity_candidates'],strict=True):
        used=np.asarray(weights)>0;objective+=2*float(np.sum(np.asarray(weights)[used]*np.log(np.asarray(weights)[used]*len(choices))))
        for weight in weights:
            sl=slices[index];index+=1
            if not weight:continue
            design=geometry['features'][sl];r=raw[sl]-design@mean
            noise=np.diag(2*sigma[sl]**2)+300.**2
            objective+=weight*float(r@np.linalg.solve(noise,r)
                +np.trace(np.linalg.solve(noise,design@covariance@design.T))
                +np.linalg.slogdet(noise)[1]+len(r)*np.log(2*np.pi))
    return float(objective)


def one(case,stage='positions'):
    source=study.OUT/stage/(case+'.json');saved=read(source);assert saved['status']=='complete'
    if stage=='qualified_positions':assert saved['initial_position_sha256']==sha(study.OUT/'positions'/(case+'.json'))
    d=study.setup(case);rows=[]
    for arm,r in saved['arms'].items():
        x=np.asarray(r['endpoint_east_north_km']);p=study.problem(d,arm,r['phase_reference'],'soft');c=p.calculate(x)
        assert abs(c['negative_twice_elbo']-r['negative_twice_elbo'])<1e-6
        entries=c.get('MAP_linear_entries',d['entries']);replay=summary(p,x,entries)
        assert_curved_gate_replay(r['gates'],replay['gates']);assert replay['linear_gates']==r['linear_gates']
        delta=0.
        if d['entries']:
            delta=abs(direct_bound(p,x,d['entries'],d['powers'],c)-c['soft_identity']['objective']);assert delta<2e-5
            assert np.array_equal(c['coefficient'],p.curved_calculate(x)['coefficient'])
            assert np.array_equal(c['noise_precision'],p.curved_calculate(x)['noise_precision'])
            assert np.array_equal(c['coefficient_prior_precision'],p.curved_calculate(x)['coefficient_prior_precision'])
        original=p.calculate;p.calculate=p.curved_calculate if d['entries'] else original
        try:density=curved_audit.density(d,p,x,d['means'],[])
        finally:p.calculate=original
        rows.append(dict(arm=arm,direct_original_coordinate_predictive_bound_difference=delta,
            curved_calibration_coefficients_and_precisions_identical=True,MAP_gate_IDs_and_decisions_identical=True,**density))
    return dict(case=case,rows=rows,all_passed=True,source_sha256=sha(source),no_GPS_used=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cohort',choices=['engineering','random20'],required=True);parser.add_argument('--workers',type=int,default=20)
    parser.add_argument('--stage',choices=['positions','qualified_positions'],default='positions');args=parser.parse_args()
    protocol=read(study.OUT/'protocol.json')
    for name,digest in protocol['source_sha256'].items():assert sha(ROOT/'tools'/name)==digest
    execution=read(study.OUT/(args.cohort+'_positions_execution.json'));assert execution['all_passed']
    if args.stage=='qualified_positions':assert read(study.OUT/'qualified_execution.json')['all_passed']
    rows=[]
    with ProcessPoolExecutor(max_workers=min(args.workers,len(protocol[args.cohort]))) as pool:
        for f in as_completed([pool.submit(one,case,args.stage) for case in protocol[args.cohort]]):
            rows.append(f.result());print(rows[-1]['case'],'audited',flush=True)
    write(study.OUT/(args.cohort+'_'+args.stage+'_audit.json'),dict(rows=rows,all_passed=True,stage=args.stage,source_execution_sha256=sha(study.OUT/(args.cohort+'_positions_execution.json')),
        auditor_sha256=sha(__import__('pathlib').Path(__file__)),original_inference_source_hashes_unchanged=True,no_GPS_used=True))


if __name__=='__main__':main()
