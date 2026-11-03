"""Optimistic local EN information from empirical source-pooled curvature.

Use calibration donors only. Hold timing, orbit, identities and empirical clock
law fixed. A Gaussian information calculation with robust measured source
scatter diagnoses sensitivity; it is not a validated uncertainty estimate.
"""
import json
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
sys.path.insert(0,str(PARENT))
from doppler_pilot import fast,read,digest


def coefficients(times,mask):
    times=np.asarray(times);mask=np.asarray(mask,bool)
    center=np.mean(times[mask]);scale=np.ptp(times[mask])
    u=(times[mask]-center)/scale
    return np.linalg.pinv(np.column_stack((np.ones(mask.sum()),u,u*u)))[2]/scale**2


def main():
    summary_path=HERE/'summary.json';summary=read(summary_path)
    geometry_path=PARENT/'causal-calibration-geometry.polished.json';geometry=read(geometry_path)
    plan_path=PARENT.parents[1]/'2026_09_30_ds10_scale_weighting/plan.json';plan=read(plan_path)
    sources={str(p):digest(p) for p in (Path(__file__),summary_path,geometry_path,plan_path)}
    rows=[]
    for family in summary['families']:
        index=family['calibration']
        donor_path=PARENT/f'acquisition_calibration/donor-{index:02d}.json';donor=read(donor_path)
        input_path=HERE/f'input-{index:02d}.json';phase=read(input_path)
        for obj in (donor,phase):
            for p,h in obj['sources'].items():assert digest(p)==h,p
        sources.update({str(p):digest(p) for p in (donor_path,input_path)})
        doc=fast.load_documents(dict(config=geometry['config'],inputs=[plan['inputs'][index]]))[0]
        engine=fast.Stationary(doc,geometry['config']);x=np.array(donor['fixed_geometry_x'])
        by_id={t['track_id']:t for t in doc['tracks']}
        phase_by_id={t['track_id']:t for t in phase['rows']}
        record=next(r for r in summary['recordings'] if r['index']==index)
        eligible=[r for r in record['rows'] if r['qualified']]
        hi=int(np.searchsorted(engine.taus,x[2],side='right'));lo=hi-1
        weight=(x[2]-engine.taus[lo])/(engine.taus[hi]-engine.taus[lo])
        fixed={}
        for row in eligible:
            track=by_id[row['track_id']];p=phase_by_id[row['track_id']]['points']
            predicted,visible=engine.prediction(track,x)
            score,_,audits,_=fast.profile(track['y'][None]-predicted,track['mask'])
            assert all(a['converged'] for a in audits)
            slot=int(np.argmax(np.where(visible,score,-np.inf)))
            times=np.array([v['frame_time_s'] for v in p]);mask=np.asarray(track['mask'],bool)
            pos=track['candidate_position_km'][slot,lo]*(1-weight)+track['candidate_position_km'][slot,hi]*weight
            vel=track['candidate_velocity_km_s'][slot,lo]*(1-weight)+track['candidate_velocity_km_s'][slot,hi]*weight
            pos=pos+vel*(times-track['times_s'])[:,None]
            fixed[row['track_id']]=(pos[mask],coefficients(times,mask))
        def pooled(position):
            receiver,_=fast.baseline.site(*engine.coordinates(position))
            groups={}
            for row in eligible:
                pos,projection=fixed[row['track_id']]
                curvature=float(projection@(np.linalg.norm(pos-receiver,axis=-1)/299792.458*1e6))
                groups.setdefault(row['norad'],[]).append(curvature)
            return np.array([np.median(groups[r['norad']]) for r in record['groups']])
        nominal=pooled(x)
        np.testing.assert_allclose(nominal,[r['orbit'] for r in record['groups']],atol=1e-8,rtol=1e-8)
        derivatives=[]
        for axis in (0,1):
            plus=x.copy();minus=x.copy();plus[axis]+=.1;minus[axis]-=.1
            derivatives.append(family['beta']*(pooled(plus)-pooled(minus))/.2)
        jac=np.array(derivatives).T
        measured=np.array([r['phase'] for r in record['groups']])
        residual=measured-(family['intercept']+family['beta']*nominal)
        sigma=float(1.4826*np.median(abs(residual-np.median(residual))))
        assert sigma>0
        eigen=np.linalg.eigvalsh(jac.T@jac/sigma**2)
        assert np.all(eigen>0)
        rows.append(dict(family=family['family'],index=index,source_groups=len(nominal),source_scatter_us_per_s2=sigma,median_position_sensitivity_us_per_s2_per_km=float(np.median(np.linalg.norm(jac,axis=1))),optimistic_fixed_nuisance_principal_sd_km=(1/np.sqrt(eigen)).tolist(),scope='local Gaussian diagnostic, fixed orbit/time/identity/clock parameters; not validated position uncertainty'))
    result=dict(rows=rows,sources=sources,position_improvement_established=False)
    with (HERE/'sensitivity.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
