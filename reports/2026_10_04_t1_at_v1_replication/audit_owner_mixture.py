"""Reconstruct all 64 owner-mixture fits and audit matched full-data inputs."""
import json
from pathlib import Path
import numpy as np
import owner_mixture_localization as experiment
from owner_mixture_localization import OwnerObjective,load,digest,serial,ALIAS
from render_leave_one_satellite_out import check_stationarity

OUT=experiment.OUT/'polished'


def main():
    rows=[];derivatives=[];cohort=[];kinematics=[]
    from joint_inputs import _ecef
    from cohort import ROOF
    for scan in experiment.SCANS:
        data,meta,_=load(scan);receipts={}
        dt=data.nodes[2:]-data.nodes[:-2]
        derivative=(data.position[:,2:]-data.position[:,:-2])/dt[None,:,None]
        line=data.position[:,1:-1]-_ecef(*ROOF);line/=np.linalg.norm(line,axis=-1)[:,:,None]
        difference=np.sum((derivative-data.velocity[:,1:-1])*line,axis=-1)*11.085e9/299792.458
        kinematics.append(dict(scan=scan,doppler_rms_difference_hz=np.sqrt(np.mean(difference**2)),
                               maximum_absolute_difference_hz=np.max(abs(difference))))
        for arm in experiment.ARMS:
            for mode in ('fixed-noise','learned-noise'):
                path=OUT/f'{scan}-{arm}-{mode}.json';r=json.loads(path.read_text());receipts[arm,mode]=r
                assert r['input_sha256']==meta['input_sha256']
                assert r['numbers']==data.numbers.tolist()
                assert r['fit_original_rows']==r['evaluation_original_rows']==data.original_rows.tolist()
                assert not r['heldout_original_rows']
                obj=OwnerObjective(data,meta['rf_center_hz'],arm,mode=='learned-noise');obj.base.deadline=float('inf')
                score,kkt=check_stationarity(obj,r['best'],4.)
                assert abs(score-r['objective'])<1e-7 and abs(kkt-r['kkt'])<1e-7
                assert (kkt<=1e-3 and not r['best']['fixed_location'])==r['converged']
                assert max(abs(np.asarray(r['best']['parameters'])[6:]))<=20.+1e-7
                assert np.linalg.norm(r['best']['point_km'])<=4.+1e-7
                rows.append(dict(scan=scan,arm=arm,mode=mode,score_error=score-r['objective'],kkt=kkt,converged=r['converged'],
                    receipt_sha256=digest(path),all_input_rows_fitted=True))
                # Nonstationary perturbation avoids testing only a zero gradient.
                if scan in ('N01','N05','N12','N15') and mode=='learned-noise':
                    v=np.asarray(r['best']['vector']);v=v.copy();v[2]+=13.;v[4]-=17.
                    v[-2]=np.log(200.);v[-1]=np.log(19.);_,g=obj.evaluate(v);errors=[]
                    for j in (2,3,4,5,6,7,obj.size,len(v)-2,len(v)-1):
                        eps=1e-5 if j in (6,7,len(v)-2,len(v)-1) else .001
                        e=np.zeros(len(v));e[j]=eps
                        fd=(obj.evaluate(v+e)[0]-obj.evaluate(v-e)[0])/(2*eps)
                        errors.append(abs(fd-g[j])/max(1.,abs(g[j])))
                    assert max(errors)<1e-4
                    derivatives.append(dict(scan=scan,arm=arm,maximum_relative_gradient_error=max(errors)))
        for mode in ('fixed-noise','learned-noise'):
            a,b=[receipts[arm,mode] for arm in experiment.ARMS]
            for key in ('input_sha256','numbers','fit_original_rows','maximum_budgets_s','polish_maximum_budgets_s',
                        'total_timing_bound_s','radius_km','prior_note','sigma_bounds_hz','inlier_probability_bounds'):
                assert a[key]==b[key],(scan,mode,key)
    for arm in experiment.ARMS:
        for mode in ('baseline','fixed-noise','learned-noise'):
            rs=[json.loads((OUT/f"{s}-{arm}-{'learned-noise' if mode=='baseline' else mode}.json").read_text()) for s in experiment.SCANS]
            values=np.array([r['baseline_error_m'] if mode=='baseline' else r['distance_m'] for r in rs])
            cohort.append(dict(arm=arm,mode=mode,scans=len(values),below_1km=int(sum(values<1000)),
                median_error_m=float(np.median(values)),mean_error_m=float(np.mean(values)),maximum_error_m=float(max(values)),
                unconverged=sum(not (r['baseline_converged'] if mode=='baseline' else r['converged']) for r in rs)))
    assert len(rows)==64
    ceiling=[]
    for n in (10,20,30,40,50):
        q=(.8/n)/(1-.8/n)/(np.sqrt(2*np.pi)*200.)
        ceiling.append(dict(satellite_count=n,isolated_zero_residual_posterior=q/(q+2/ALIAS)))
    report=dict(status='passed',cases=len(rows),converged=sum(r['converged'] for r in rows),
        caveat='Audit success does not mean every optimization converged or that the localization goal is achieved.',
        rows=rows,derivative_checks=derivatives,cohort=cohort,legacy_confidence_ceiling=ceiling,
        orbit_velocity_consistency=kinematics,
        scientific_scope='No row deletion or identity reselection. In-sample conditional comparison. Do not compare absolute NLL between different likelihoods.')
    (OUT/'audit.json').write_text(json.dumps(report,default=serial,indent=2,allow_nan=False))
    print(json.dumps(dict(cases=len(rows),converged=report['converged'],cohort=cohort,ceilings=ceiling),indent=2))
    experiment.OUT=OUT;experiment.render()


if __name__=='__main__':main()
