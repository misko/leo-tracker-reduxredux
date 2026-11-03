"""Audit matched inputs/derivatives and attribute the roof-to-best score change.

Partitions use original association owners, not a claim of fixed posterior
membership. Negative data-NLL changes favor the off-roof best-found point.
These are in-sample influence diagnostics, not satellite identity tests.
"""
import csv
import json
from types import SimpleNamespace
import numpy as np
from joint_full_calibration import (OUT,SCANS,ARMS,MODES,prepare,JointReceiverObjective,
                                    spline_prior,serial,digest)
from timing_bound_comparison import feasible_start
from render_leave_one_satellite_out import check_stationarity
from position_direct import coordinate_jacobian


def snapshot(obj,data,record):
    vector=np.asarray(record['vector']);value,g=obj.evaluate(vector)
    like=obj.likelihood.last_result
    order=np.argsort(data.group)
    np.testing.assert_array_equal(like['group_values'],data.group[order])
    loss=np.zeros(len(data.times));loss[order]=-like['log_likelihood']
    timing,_=obj.base.penalty(vector[:obj.size]);spline,_=spline_prior(vector[obj.size+1:])
    assert abs(loss.sum()+timing+spline-value)<1e-7
    _,_,jac=obj.base.predict(vector[:obj.size],with_jacobian=True)
    cj=coordinate_jacobian(record['point_km']);parts={}
    for n in data.numbers:
        mask=data.owners==n
        w=np.zeros_like(like['prediction_gradient']);w[mask]=-like['prediction_gradient'][mask]
        grad=cj.T@jac.transpose_multiply(w.ravel())[:2]
        parts[int(n)]=dict(windows=int(sum(mask)),nll=float(loss[mask].sum()),gradient=grad)
    np.testing.assert_allclose(sum((r['gradient'] for r in parts.values())),cj.T@g[:2],atol=1e-7)
    return parts


def main():
    audits=[];contributions=[];comparisons=[]
    for scan in SCANS:
        data,center,beta,previous,source=prepare(scan)
        with np.load(source) as z:old=SimpleNamespace(**{k:z[k].copy() for k in z.files})
        np.testing.assert_allclose(data.measured+data.fixed_receiver_hz,old.measured+old.fixed_receiver_hz,atol=1e-8,rtol=0)
        for arm in ARMS:
            pair={}
            for mode in MODES:
                path=OUT/f'{scan}-{arm}-{mode}.json';r=json.loads(path.read_text());pair[mode]=r
                assert r['input_sha256']==digest(source)
                assert r['fit_original_rows']==r['evaluation_original_rows']==data.original_rows.tolist()
                assert not r['heldout_original_rows']
                obj=JointReceiverObjective(data,center,beta,arm,mode);obj.base.deadline=float('inf')
                v=np.r_[feasible_start(obj,previous['arms'][arm]['best'],20.,arm),beta.ravel()]
                value,g=obj.evaluate(v);prior,_=spline_prior(beta)
                assert abs(value-prior-previous['arms'][arm]['best']['objective'])<1e-7
                errors=[]
                for j in range(obj.size,len(v)):
                    e=np.zeros(len(v));e[j]=.01
                    fd=(obj.evaluate(v+e)[0]-obj.evaluate(v-e)[0])/.02
                    errors.append(abs(fd-g[j]))
                assert max(errors)<1e-6
                score,kkt=check_stationarity(obj,r['best'],4.)
                assert abs(score-r['objective'])<1e-7 and kkt<=1e-3 and r['converged']
                roof=snapshot(obj,data,r['roof']);best=snapshot(obj,data,r['best'])
                for n in data.numbers:
                    a,b=roof[int(n)],best[int(n)]
                    contributions.append(dict(scan=scan,arm=arm,mode=mode,satellite=int(n),windows=a['windows'],
                        roof_nuisance_converged=r['roof']['success'],roof_nll=a['nll'],best_nll=b['nll'],
                        best_minus_roof_data_nll=b['nll']-a['nll'],
                        roof_east_gradient_per_100m=a['gradient'][0]/10,
                        roof_north_gradient_per_100m=a['gradient'][1]/10))
                audits.append(dict(scan=scan,arm=arm,mode=mode,matched_raw_observations=True,
                    all_input_rows_fitted_and_evaluated=True,score_error=score-r['objective'],kkt=kkt,
                    maximum_calibration_derivative_error=max(errors),receipt_sha256=digest(path)))
            a,b=[pair[m] for m in MODES]
            for key in ('input_sha256','fit_original_rows','numbers','maximum_budgets_s','radius_km','total_timing_bound_s','spline_priors'):
                assert a[key]==b[key]
            comparisons.append(dict(scan=scan,arm=arm,
                delta_position_error_m=b['distance_m']-a['distance_m'],
                delta_total_score=b['objective']-a['objective'],delta_data_nll=b['data_nll']-a['data_nll'],
                delta_timing_prior=b['timing_prior_nll']-a['timing_prior_nll'],
                delta_spline_prior=b['spline_prior_nll']-a['spline_prior_nll']))
    for name,rows in [('satellite-score-contributions.csv',contributions),('score-change-decomposition.csv',comparisons)]:
        with (OUT/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    report=dict(scope=__doc__,status='passed',cases=len(audits),audits=audits,comparisons=comparisons)
    (OUT/'audit.json').write_text(json.dumps(report,default=serial,indent=2,allow_nan=False))
    print(json.dumps(report,default=serial,indent=2))


if __name__=='__main__':main()
