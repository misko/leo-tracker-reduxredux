"""Reconstruct prior ablations and separate data fit, regularization, and accuracy."""
import argparse
import json
import numpy as np
import timing_prior_ablation as experiment
from timing_prior_ablation import PriorObjective,PRECISIONS,load,diagnostics,serial,digest
from position_direct import coordinate_jacobian


def profile_information(h, nuisance):
    nuisance=np.asarray(nuisance,int)
    cross=h[np.ix_(np.arange(2),nuisance)]
    block=h[np.ix_(nuisance,nuisance)]
    reduced=h[:2,:2]-cross@np.linalg.pinv(block,rcond=1e-12)@cross.T
    reduced=(reduced+reduced.T)/2
    values=np.linalg.eigvalsh(reduced)
    return reduced,values


def geometry(obj,record):
    v=np.asarray(record['vector']);obj.evaluate(v)
    h=obj.curvature(v)
    scale=obj.scale.copy();scale[:2]=1.
    transform=np.diag(scale);transform[:2,:2]=coordinate_jacobian(record['point_km'])
    h=transform.T@h@transform
    # Only c=0 is a fixed coefficient. Do not treat active inequalities as
    # known calibration: this is an unconstrained local information diagnostic.
    nuisance=[i for i in range(2,len(v)) if obj.bounds[i][0]!=obj.bounds[i][1] or obj.bounds[i][0] is None]
    reduced,eig=profile_information(h,nuisance)
    return dict(profile_information_per_km2=reduced.tolist(),eigenvalues_per_km2=eig.tolist(),
        weakest_local_sigma_m=float(1000/np.sqrt(eig[0])) if eig[0]>1e-10 else None,
        strongest_local_sigma_m=float(1000/np.sqrt(eig[1])) if eig[1]>1e-10 else None)


def main(root):
    rows=[];cohort=[];cross_checks=[]
    for scan in experiment.SCANS:
        d,meta,_=load(scan);cases={}
        for arm in experiment.ARMS:
            for mode,precision in PRECISIONS.items():
                path=root/f'{scan}-{arm}-{mode}.json';r=json.loads(path.read_text());cases[arm,mode]=r
                assert r['input_sha256']==meta['input_sha256']
                assert r['numbers']==d.numbers.tolist()
                assert r['fit_original_rows']==r['evaluation_original_rows']==d.original_rows.tolist()
                assert not r['heldout_original_rows']
                obj=PriorObjective(d,meta['rf_center_hz'],arm,precision);obj.base.deadline=float('inf')
                metrics=diagnostics(obj,d,r['best'])
                for key in ('objective','kkt','data_nll','timing_prior_nll'):
                    assert abs(metrics[key]-r[key])<1e-7,(scan,arm,mode,key)
                assert metrics['converged']==r['converged']
                if mode=='data-only':assert metrics['timing_prior_nll']==0.
                assert np.max(abs(np.asarray(r['best']['parameters'])[6:]))<=20.+1e-7
                assert abs(r['best']['vector'][6])<=10.+1e-7
                assert np.linalg.norm(r['best']['point_km'])<=4.+1e-7
                if arm=='zero-c':assert r['best']['vector'][-1]==0.
                information=geometry(obj,r['best'])
                rows.append(dict(scan=scan,arm=arm,mode=mode,**metrics,**information,receipt_sha256=digest(path)))
            # Score each converged solution under the other priors. Any better
            # feasible point is a search deficiency, not evidence for a prior.
            for mode,precision in PRECISIONS.items():
                obj=PriorObjective(d,meta['rf_center_hz'],arm,precision);obj.base.deadline=float('inf')
                current=cases[arm,mode]
                for other in PRECISIONS:
                    if other==mode:continue
                    score=obj.evaluate(np.asarray(cases[arm,other]['best']['vector']))[0]
                    cross_checks.append(dict(scan=scan,arm=arm,mode=mode,other=other,
                        available_score_improvement=current['objective']-score,
                        another_saved_point_is_better=score<current['objective']-1e-5))
        reference=cases['fitted-c','original']
        for r in cases.values():
            for key in ('input_sha256','numbers','fit_original_rows','maximum_budgets_s','radius_km',
                        'total_timing_bound_s','common_timing_bound_s'):
                assert reference[key]==r[key],(scan,key)
            assert reference.get('polish_maximum_budgets_s')==r.get('polish_maximum_budgets_s')
            assert reference.get('continuation_maximum_budget_s')==r.get('continuation_maximum_budget_s')
            assert reference.get('final_candidate_evaluations')==r.get('final_candidate_evaluations')
    for arm in experiment.ARMS:
        for mode in PRECISIONS:
            sub=[r for r in rows if r['arm']==arm and r['mode']==mode];errors=np.array([r['distance_m'] for r in sub])
            cohort.append(dict(arm=arm,mode=mode,scans=len(sub),median_error_m=float(np.median(errors)),
                mean_error_m=float(np.mean(errors)),below_1km=int(sum(errors<1000)),
                unconverged=sum(not r['converged'] for r in sub),boundary=sum(r['boundary'] for r in sub)))
    assert len(rows)==96
    report=dict(status='passed',cases=len(rows),converged=sum(r['converged'] for r in rows),cohort=cohort,
        rows=rows,cross_checks=cross_checks,
        caveats=['No absolute objective comparison across priors; data NLL uses identical observations/likelihood.',
                 'No per-scan truth-selected prior. All input windows fitted and evaluated; no held-out evidence.',
                 'Local Fisher scale ignores upstream calibration uncertainty, temporal correlations and multimodality; not calibrated confidence.',
                 'A passed audit does not mean every fit converged or that every local mode was searched.'])
    (root/'audit.json').write_text(json.dumps(report,default=serial,indent=2,allow_nan=False))
    print(json.dumps(dict(converged=report['converged'],cohort=cohort,
        better_cross_points=sum(r['another_saved_point_is_better'] for r in cross_checks)),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--polished',action='store_true');parser.add_argument('--final',action='store_true');parser.add_argument('--closed',action='store_true');args=parser.parse_args()
    main(experiment.OUT/'closed' if args.closed else (experiment.OUT/'final' if args.final else (experiment.OUT/'polished' if args.polished else experiment.OUT)))
